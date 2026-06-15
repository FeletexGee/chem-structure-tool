# ============================================================
# ChemStructure Tool — 图像识别模块 (OCSR)
# 化学结构图像 → SMILES
# 主要工具：DECIMER（首选） / Img2Mol（备选）
# ============================================================

import os
import uuid
from typing import Optional, Dict
from PIL import Image

from config import UPLOAD_FOLDER, ALLOWED_IMAGE_EXTENSIONS


# ── 图像预处理 ──────────────────────────────────────────────

def _allowed_image(filename: str) -> bool:
    """检查是否为允许的图片格式"""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in ALLOWED_IMAGE_EXTENSIONS


def _preprocess_image(image_path: str, max_size: int = 1024) -> str:
    """
    预处理上传的图片：缩放、转PNG。
    返回处理后的图片路径。
    """
    img = Image.open(image_path).convert("RGB")
    # 缩放大图
    w, h = img.size
    if max(w, h) > max_size:
        ratio = max_size / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    # 保存为 PNG
    out_path = image_path.rsplit(".", 1)[0] + "_processed.png"
    img.save(out_path, "PNG")
    return out_path


# ── DECIMER: EfficientNet-V2 + Transformer (首选) ────────────

def parse_image_decimer(image_path: str) -> Optional[Dict]:
    """
    使用 DECIMER 将化学结构图像转换为 SMILES。
    
    DECIMER 使用 EfficientNet-V2 提取图像特征，
    Transformer 解码器生成 SMILES 序列。
    论文：Nature Communications (2023), DOI: 10.1038/s41467-023-40782-0
    
    Args:
        image_path: 图片文件路径
    
    Returns:
        dict with smiles, 失败返回 None
    """
    try:
        from decimer import Decimer

        # 预处理图片
        processed_path = _preprocess_image(image_path)

        # 初始化 DECIMER（首次会加载模型，约需几秒）
        decimer = Decimer()

        # 预测 SMILES
        smiles = decimer.predict_smiles(processed_path)

        if smiles and smiles.strip():
            return {
                "smiles": smiles.strip(),
                "source": "DECIMER",
                "method": "EfficientNet-V2 + Transformer",
            }
        return None
    except ImportError:
        return None  # DECIMER 未安装
    except Exception as e:
        return None


# ── Img2Mol: CNN + CDDD Decoder (备选) ──────────────────────

def parse_image_img2mol(image_path: str) -> Optional[Dict]:
    """
    使用 Img2Mol 将化学结构图像转换为 SMILES。
    
    Img2Mol 使用 CNN 编码器提取分子图像特征，
    再通过预训练的 CDDD Decoder 解码为 SMILES。
    论文：Chemical Science (2021), DOI: 10.1039/D1SC01839F
    
    注意：Img2Mol 需要 clone 仓库并下载预训练模型。
          详见 https://github.com/bayer-science-for-a-better-life/Img2Mol
    
    Args:
        image_path: 图片文件路径
    
    Returns:
        dict with smiles, 失败返回 None
    """
    try:
        # Img2Mol 导入路径取决于安装方式
        # 标准方式：clone 仓库后在 img2mol/ 目录下运行
        import sys
        import os as _os

        # 尝试查找 Img2Mol 路径（可通过环境变量配置）
        img2mol_path = _os.environ.get("IMG2MOL_PATH", "")
        if img2mol_path and img2mol_path not in sys.path:
            sys.path.insert(0, img2mol_path)

        from img2mol.inference import Img2MolInference

        processed_path = _preprocess_image(image_path)

        # 初始化（需指定模型权重路径）
        model_path = _os.environ.get("IMG2MOL_MODEL_PATH", "")
        if not model_path:
            return {
                "smiles": None,
                "source": "Img2Mol",
                "error": "Img2Mol 模型路径未配置，请设置 IMG2MOL_MODEL_PATH 环境变量",
            }

        infer = Img2MolInference(model_path)
        smiles = infer.predict(processed_path)

        if smiles and smiles.strip():
            return {
                "smiles": smiles.strip(),
                "source": "Img2Mol",
                "method": "CNN + CDDD Decoder",
            }
        return None
    except ImportError:
        return None
    except Exception as e:
        return None


# ── 统一入口：自动选择最佳可用工具 ────────────────────────────

def smart_parse_image(image_path: str) -> Dict:
    """
    智能选择可用的图像识别工具进行解析。
    优先级：DECIMER > Img2Mol
    
    Returns:
        {
            "success": bool,
            "smiles": str or None,
            "source": str,       # "DECIMER" | "Img2Mol"
            "error": str or None,
        }
    """
    if not os.path.exists(image_path):
        return {"success": False, "smiles": None, "source": None,
                "error": f"图片文件不存在: {image_path}"}

    # 1. 尝试 DECIMER（首选）
    result = parse_image_decimer(image_path)
    if result and result.get("smiles"):
        return {"success": True, "error": None, **result}

    # 2. 尝试 Img2Mol（备选）
    result = parse_image_img2mol(image_path)
    if result and result.get("smiles"):
        return {"success": True, "error": None, **result}

    # 3. 全部失败
    return {
        "success": False,
        "smiles": None,
        "source": None,
        "error": (
            "图像识别失败。请确保：\n"
            "1. DECIMER 已安装（pip install decimer）\n"
            "2. 或 Img2Mol 已配置（IMG2MOL_PATH + IMG2MOL_MODEL_PATH）\n"
            "3. 图片清晰、包含完整的化学结构式"
        ),
    }


# ── 文件保存 ─────────────────────────────────────────────────

def save_uploaded_image(file_data, filename: str) -> Optional[str]:
    """
    保存上传的图片文件。
    
    Returns:
        保存后的文件路径，失败返回 None
    """
    if not _allowed_image(filename):
        return None
    
    # 生成唯一文件名防止冲突
    ext = filename.rsplit(".", 1)[-1].lower()
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    save_path = os.path.join(UPLOAD_FOLDER, unique_name)
    
    try:
        file_data.save(save_path)
        return save_path
    except Exception:
        return None
