# ============================================================
# ChemStructure Tool — Flask 主应用
# 化学结构智能生成工具 Web 服务
# ============================================================

import os
import base64
import logging
from flask import (
    Flask, render_template, request, jsonify, send_file, url_for
)
from werkzeug.utils import secure_filename
import io

# 配置日志（生产模式仅显示警告，调试模式显示详细信息）
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# ── 静默 RDKit 噪音（必须在导入其他模块之前）───────────────
# smart_parse 会故意用非 SMILES 输入试探类型，RDKit 的 SMILES
# Parse Error 是预期行为而非错误，提前静默避免污染终端输出
os.environ.setdefault("RDKIT_SMILESPARSE_ERRORS", "0")  # 抑制 C++ 层 stderr
try:
    from rdkit import RDLogger
    RDLogger.logger().setLevel(RDLogger.CRITICAL)  # 抑制 Python 层日志
except ImportError:
    pass

from config import SECRET_KEY, DEBUG, UPLOAD_FOLDER, MAX_CONTENT_LENGTH
from modules.text_parser import smart_parse, INPUT_TYPES
from modules.image_parser import (
    ImageValidationError,
    save_verified_image,
    smart_parse_image,
)
from modules.request_validation import (
    RequestValidationError,
    optional_bool,
    optional_choice,
    require_json_object,
    require_string,
)
from modules.structure_processor import (
    smiles_to_mol,
    get_molecule_info,
    render_2d_image,
    generate_3d_conformer,
    export_molecule,
    validate_structure,
)

# ── Flask 应用初始化 ─────────────────────────────────────────

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# 确保上传目录存在
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

MAX_TEXT_INPUT_LENGTH = 5000
MAX_SMILES_LENGTH = 10000


def _invalid_request(error: RequestValidationError):
    return jsonify({
        "success": False,
        "code": "invalid_request",
        "error": str(error),
    }), 400


def _stage(success: bool, error: str | None = None) -> dict:
    return {"success": success, "error": error}


# ── 页面路由 ───────────────────────────────────────────────

@app.route("/")
def index():
    """主页面"""
    return render_template("index.html")


# ── API: 文本解析 ───────────────────────────────────────────

@app.route("/api/parse-text", methods=["POST"])
def api_parse_text():
    """
    文本输入 → SMILES
    
    Request JSON:
        {"input": "caffeine" | "C8H10N4O2" | "CC(=O)O" | ...}
    
    Response JSON:
        {
            "success": true/false,
            "smiles": "...",
            "source": "OPSIN"|"PubChem"|"SMILES",
            "input_type": "...",
            "error": "...",
            "molecule_info": {...}
        }
    """
    try:
        data = require_json_object(request)
        user_input = require_string(data, "input", max_length=MAX_TEXT_INPUT_LENGTH)
        input_type = optional_choice(
            data,
            "input_type",
            allowed=INPUT_TYPES,
            default="auto",
            transform=str.lower,
        )
    except RequestValidationError as error:
        return _invalid_request(error)

    # 智能解析
    result = smart_parse(user_input, input_type=input_type)

    if result.get("status") == "ambiguous":
        return jsonify(result), 409

    # 如果解析成功，附加分子信息
    if result["success"] and result["smiles"]:
        mol_info = get_molecule_info(result["smiles"])
        result["molecule_info"] = mol_info
        # 附加结构校验
        validation = validate_structure(result["smiles"])
        result["validation"] = validation

    return jsonify(result)


# ── API: 图像识别 ───────────────────────────────────────────

@app.route("/api/parse-image", methods=["POST"])
def api_parse_image():
    """
    化学结构图像 → SMILES
    
    Request: multipart/form-data, field name: "image"
    
    Response JSON:
        {
            "success": true/false,
            "smiles": "...",
            "source": "DECIMER"|"Img2Mol",
            "error": "...",
            "molecule_info": {...}
        }
    """
    if "image" not in request.files:
        return jsonify({"success": False, "error": "请上传图片文件（字段名: image）"}), 400

    file = request.files["image"]
    if file.filename == "":
        return jsonify({"success": False, "error": "未选择文件"}), 400

    # 验证并安全地重新编码图片
    filename = secure_filename(file.filename or "upload.png")
    try:
        save_path = save_verified_image(
            file,
            filename,
            upload_folder=app.config["UPLOAD_FOLDER"],
        )
    except ImageValidationError as error:
        return jsonify({
            "success": False,
            "code": "invalid_image",
            "error": str(error),
        }), 400

    try:
        result = smart_parse_image(save_path)

        # 如果识别成功，附加分子信息
        if result["success"] and result["smiles"]:
            mol_info = get_molecule_info(result["smiles"])
            result["molecule_info"] = mol_info
            validation = validate_structure(result["smiles"])
            result["validation"] = validation

        return jsonify(result)
    finally:
        try:
            os.remove(save_path)
        except FileNotFoundError:
            pass
        except OSError as error:
            app.logger.warning("Failed to remove uploaded image %s: %s", save_path, error)


# ── API: 2D 结构图渲染 ──────────────────────────────────────

@app.route("/api/render-2d", methods=["POST"])
def api_render_2d():
    """
    生成 2D 结构图
    
    Request JSON:
        {"smiles": "...", "format": "PNG"|"SVG", "show_indices": false}
    
    Response: 图片数据（base64 编码在 JSON 中，或直接返回图片）
    """
    try:
        data = require_json_object(request)
        smiles = require_string(data, "smiles", max_length=MAX_SMILES_LENGTH)
        fmt = optional_choice(
            data,
            "format",
            allowed={"PNG", "SVG"},
            default="PNG",
            transform=str.upper,
        )
        show_indices = optional_bool(data, "show_indices", default=False)
    except RequestValidationError as error:
        return _invalid_request(error)

    img_bytes, error = render_2d_image(smiles, format=fmt, show_atom_indices=show_indices)
    if error:
        return jsonify({"success": False, "error": error}), 400

    # 返回 base64 编码的图片数据
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    mime = "image/svg+xml" if fmt == "SVG" else "image/png"
    return jsonify({
        "success": True,
        "image_base64": b64,
        "mime_type": mime,
        "format": fmt,
    })


# ── API: 3D 构象生成 ────────────────────────────────────────

@app.route("/api/render-3d", methods=["POST"])
def api_render_3d():
    """
    生成 3D 构象（PDB 格式）
    
    Request JSON:
        {"smiles": "...", "optimize": true}
    
    Response JSON:
        {"success": true, "pdb_data": "...", "smiles": "..."}
    """
    try:
        data = require_json_object(request)
        smiles = require_string(data, "smiles", max_length=MAX_SMILES_LENGTH)
        optimize = optional_bool(data, "optimize", default=True)
    except RequestValidationError as error:
        return _invalid_request(error)

    pdb_block, error = generate_3d_conformer(smiles, optimize=optimize)
    if error:
        return jsonify({"success": False, "error": error}), 400

    return jsonify({
        "success": True,
        "pdb_data": pdb_block,
        "smiles": smiles,
    })


# ── API: 分子信息 ───────────────────────────────────────────

@app.route("/api/molecule-info", methods=["POST"])
def api_molecule_info():
    """
    获取分子详细信息
    
    Request JSON:
        {"smiles": "..."}
    """
    try:
        data = require_json_object(request)
        smiles = require_string(data, "smiles", max_length=MAX_SMILES_LENGTH)
    except RequestValidationError as error:
        return _invalid_request(error)
    info = get_molecule_info(smiles)
    validation = validate_structure(smiles)

    if "error" in info:
        return jsonify({"success": False, "error": info["error"]}), 400

    return jsonify({
        "success": True,
        "molecule_info": info,
        "validation": validation,
    })


# ── API: 多格式导出 ─────────────────────────────────────────

@app.route("/api/export", methods=["POST"])
def api_export():
    """
    导出分子为不同格式
    
    Request JSON:
        {"smiles": "...", "format": "MOL"|"SDF"|"PDB"|"InChI"|"SMILES"}
    
    Response JSON:
        {"success": true, "data": "...", "format": "..."}
    """
    try:
        data = require_json_object(request)
        smiles = require_string(data, "smiles", max_length=MAX_SMILES_LENGTH)
        fmt = optional_choice(
            data,
            "format",
            allowed={"MOL", "SDF", "PDB", "INCHI", "INCHIKEY", "SMILES"},
            default="MOL",
            transform=str.upper,
        )
    except RequestValidationError as error:
        return _invalid_request(error)

    result, error = export_molecule(smiles, format=fmt)
    if error:
        return jsonify({"success": False, "error": error}), 400

    return jsonify({
        "success": True,
        "data": result,
        "format": fmt,
    })


# ── API: 一键处理（文本输入 → 全部结果）──────────────────────

@app.route("/api/process", methods=["POST"])
def api_process():
    """
    一键处理：输入文本 → 返回 2D 图 + 3D PDB + 分子信息 + 校验
    
    Request JSON:
        {"input": "caffeine"}
    
    Response JSON:
        {
            "success": true,
            "smiles": "...",
            "source": "...",
            "image_2d_base64": "...",
            "pdb_data": "...",
            "molecule_info": {...},
            "validation": {...}
        }
    """
    try:
        data = require_json_object(request)
        user_input = require_string(data, "input", max_length=MAX_TEXT_INPUT_LENGTH)
        input_type = optional_choice(
            data,
            "input_type",
            allowed=INPUT_TYPES,
            default="auto",
            transform=str.lower,
        )
    except RequestValidationError as error:
        return _invalid_request(error)

    # 1. 文本解析
    parse_result = smart_parse(user_input, input_type=input_type)
    if parse_result.get("status") == "ambiguous":
        return jsonify(parse_result), 409
    if not parse_result["success"] or not parse_result.get("smiles"):
        return jsonify(parse_result), 400

    smiles = parse_result["smiles"]

    # 2. 2D 渲染
    img_bytes, img_error = render_2d_image(smiles)
    img_b64 = base64.b64encode(img_bytes).decode("utf-8") if img_bytes else None

    # 3. 3D 构象
    pdb_block, pdb_error = generate_3d_conformer(smiles)

    # 4. 分子信息
    mol_info = get_molecule_info(smiles)

    # 5. 校验
    validation = validate_structure(smiles)

    stages = {
        "parse": _stage(True),
        "render_2d": _stage(bool(img_bytes) and not img_error, img_error),
        "render_3d": _stage(bool(pdb_block) and not pdb_error, pdb_error),
        "molecule_info": _stage("error" not in mol_info, mol_info.get("error")),
        "validation": _stage(bool(validation), None if validation else "结构校验失败"),
    }
    overall_status = (
        "resolved"
        if all(stage["success"] for stage in stages.values())
        else "partial"
    )

    return jsonify({
        "success": True,
        "status": overall_status,
        "smiles": smiles,
        "source": parse_result.get("source"),
        "input_type": parse_result.get("input_type"),
        "image_2d_base64": img_b64,
        "pdb_data": pdb_block,
        "molecule_info": mol_info,
        "validation": validation,
        "stages": stages,
        # 自动修正提示（如立体化学剥离）
        "auto_corrected": parse_result.get("auto_corrected", False),
        "correction_detail": parse_result.get("correction_detail"),
        "llm_raw_iupac_name": parse_result.get("llm_raw_iupac_name"),
        "llm_iupac_name": parse_result.get("llm_iupac_name"),
    })


# ── 启动 ────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  ChemStructure Tool — 化学结构智能生成工具")
    print("  访问地址: http://127.0.0.1:5000")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=False)
