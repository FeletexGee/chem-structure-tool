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
from modules.text_parser import smart_parse
from modules.image_parser import smart_parse_image, save_uploaded_image
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
    data = request.get_json(silent=True)
    if not data or "input" not in data:
        return jsonify({"success": False, "error": "请提供 'input' 参数"}), 400

    user_input = data["input"].strip()
    if not user_input:
        return jsonify({"success": False, "error": "输入不能为空"}), 400

    # 智能解析
    result = smart_parse(user_input)

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

    # 保存图片
    filename = secure_filename(file.filename or "upload.png")
    save_path = save_uploaded_image(file, filename)
    if not save_path:
        return jsonify({"success": False, "error": "不支持的图片格式（支持 PNG/JPG/GIF/BMP/TIFF/WebP）"}), 400

    # 图像识别
    result = smart_parse_image(save_path)

    # 如果识别成功，附加分子信息
    if result["success"] and result["smiles"]:
        mol_info = get_molecule_info(result["smiles"])
        result["molecule_info"] = mol_info
        validation = validate_structure(result["smiles"])
        result["validation"] = validation

    return jsonify(result)


# ── API: 2D 结构图渲染 ──────────────────────────────────────

@app.route("/api/render-2d", methods=["POST"])
def api_render_2d():
    """
    生成 2D 结构图
    
    Request JSON:
        {"smiles": "...", "format": "PNG"|"SVG", "show_indices": false}
    
    Response: 图片数据（base64 编码在 JSON 中，或直接返回图片）
    """
    data = request.get_json(silent=True)
    if not data or "smiles" not in data:
        return jsonify({"success": False, "error": "请提供 'smiles' 参数"}), 400

    smiles = data["smiles"].strip()
    fmt = data.get("format", "PNG").upper()
    show_indices = data.get("show_indices", False)

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
    data = request.get_json(silent=True)
    if not data or "smiles" not in data:
        return jsonify({"success": False, "error": "请提供 'smiles' 参数"}), 400

    smiles = data["smiles"].strip()
    optimize = data.get("optimize", True)

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
    data = request.get_json(silent=True)
    if not data or "smiles" not in data:
        return jsonify({"success": False, "error": "请提供 'smiles' 参数"}), 400

    smiles = data["smiles"].strip()
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
    data = request.get_json(silent=True)
    if not data or "smiles" not in data:
        return jsonify({"success": False, "error": "请提供 'smiles' 参数"}), 400

    smiles = data["smiles"].strip()
    fmt = data.get("format", "MOL").upper()

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
    data = request.get_json(silent=True)
    if not data or "input" not in data:
        return jsonify({"success": False, "error": "请提供 'input' 参数"}), 400

    user_input = data["input"].strip()

    # 1. 文本解析
    parse_result = smart_parse(user_input)
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

    return jsonify({
        "success": True,
        "smiles": smiles,
        "source": parse_result.get("source"),
        "input_type": parse_result.get("input_type"),
        "image_2d_base64": img_b64,
        "pdb_data": pdb_block,
        "molecule_info": mol_info,
        "validation": validation,
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
    app.run(host="0.0.0.0", port=5000, debug=True)
