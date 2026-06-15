# ============================================================
# ChemStructure Tool — 图像识别模块 (OCSR)
# 化学结构图像 → SMILES
# 主要工具：Img2Mol（首选） / DECIMER（备选）
# ============================================================

import os
import sys
import uuid
from typing import Optional, Dict
from PIL import Image

from config import UPLOAD_FOLDER, ALLOWED_IMAGE_EXTENSIONS

# ── Img2Mol 模型路径 ────────────────────────────────────────
_IMG2MOL_REPO = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "img2mol_repo"
)
_IMG2MOL_MODEL = os.path.join(_IMG2MOL_REPO, "model", "model.ckpt")


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
        # DECIMER 的 PyPI 包名是 "decimer" 但 Python 模块名是 "DECIMER"（大写）
        import DECIMER
        from DECIMER import Decimer

        # 预处理图片
        processed_path = _preprocess_image(image_path)

        # 初始化 DECIMER（首次会下载 285MB 模型，约需 1-3 分钟）
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


# ── Img2Mol: CNN + CDDD Decoder (首选) ──────────────────────

def parse_image_img2mol(image_path: str) -> Optional[Dict]:
    """
    使用 Img2Mol 将化学结构图像转换为 SMILES。
    
    Img2Mol 架构：CNN 编码器（提取分子图像特征）→ CDDD Decoder（解码为 SMILES）。
    论文：Chemical Science (2021), DOI: 10.1039/D1SC01839F
    
    前置条件：
    1. Img2Mol 模型权重已下载至 img2mol_repo/model/model.ckpt
    2. CDDD 解码器服务可用（本地或远程）
    
    Args:
        image_path: 图片文件路径
    
    Returns:
        dict with smiles, 失败返回 None
    """
    try:
        # 检查模型权重是否存在
        if not os.path.exists(_IMG2MOL_MODEL):
            return {
                "smiles": None,
                "source": "Img2Mol",
                "error": (
                    "Img2Mol 模型权重未下载。请手动下载：\n"
                    "https://drive.google.com/file/d/1pk21r4Zzb9ZJkszJwP9SObTlfTaRMMtF\n"
                    f"并将 model.ckpt 放置到：{os.path.dirname(_IMG2MOL_MODEL)}"
                ),
            }

        from img2mol.inference import Img2MolInference, CDDDRequest

        # 预处理图片
        processed_path = _preprocess_image(image_path)

        # 初始化 Img2Mol CNN 编码器
        img2mol = Img2MolInference(
            model_ckpt=_IMG2MOL_MODEL,
            device="cpu",  # 无 GPU 环境使用 CPU
            local_cddd=True,  # 优先使用本地 CDDD
        )

        # 尝试本地 CDDD 模式
        if img2mol.cddd_inference_model is not None:
            # 本地 CDDD 已安装 → 端到端推理
            res = img2mol(filepath=processed_path)
            smiles = res.get("smiles", "")
            if smiles and smiles.strip():
                return {
                    "smiles": smiles.strip(),
                    "source": "Img2Mol",
                    "method": "CNN + CDDD Decoder (local)",
                }
        
        # 回退到远程 CDDD 服务器
        cddd_server = CDDDRequest()
        res = img2mol(filepath=processed_path, cddd_server=cddd_server)
        smiles = res.get("smiles", "")
        if smiles and smiles.strip():
            return {
                "smiles": smiles.strip(),
                "source": "Img2Mol",
                "method": "CNN + CDDD Decoder (remote)",
            }

        return None

    except ImportError as e:
        return {
            "smiles": None,
            "source": "Img2Mol",
            "error": f"Img2Mol 依赖缺失: {e}",
        }
    except ConnectionError:
        return {
            "smiles": None,
            "source": "Img2Mol",
            "error": (
                "CDDD 解码服务不可用。Img2Mol 的 CNN 编码器需要 CDDD Decoder 才能输出 SMILES。\n"
                "CDDD 远程服务器已停止服务。如需使用 Img2Mol，请：\n"
                "1. 创建 Python 3.7 conda 环境\n"
                "2. 安装 CDDD: pip install cddd (需 TensorFlow 1.x)\n"
                "3. 下载 CDDD 模型并配置本地解码"
            ),
        }
    except Exception as e:
        return {
            "smiles": None,
            "source": "Img2Mol",
            "error": f"Img2Mol 推理异常: {str(e)}",
        }


# ── 统一入口：自动选择最佳可用工具 ────────────────────────────

def smart_parse_image(image_path: str) -> Dict:
    """
    智能选择可用的图像识别工具进行解析。
    优先级：Img2Mol > DECIMER
    
    Returns:
        {
            "success": bool,
            "smiles": str or None,
            "source": str,       # "Img2Mol" | "DECIMER"
            "error": str or None,
        }
    """
    if not os.path.exists(image_path):
        return {"success": False, "smiles": None, "source": None,
                "error": f"图片文件不存在: {image_path}"}

    # 1. 尝试 DECIMER（首选：EfficientNet-V2 + Transformer，pip install decimer）
    result = parse_image_decimer(image_path)
    if result and result.get("smiles"):
        return {"success": True, "error": None, **result}
    decimer_error = result.get("error", "") if result else ""

    # 2. 尝试 Img2Mol（备选：CNN + CDDD Decoder，需额外配置）
    result = parse_image_img2mol(image_path)
    if result:
        if result.get("smiles"):
            return {"success": True, "error": None, **result}
        img2mol_error = result.get("error", "")
    else:
        img2mol_error = ""

    # 3. 全部失败，提供详细错误信息
    error_parts = ["图像识别失败。"]
    if decimer_error:
        error_parts.append(f"\n[DECIMER] {decimer_error}")
    else:
        error_parts.append("\n[DECIMER] 未安装（pip install decimer）。")
    if img2mol_error:
        error_parts.append(f"\n[Img2Mol] {img2mol_error}")
    error_parts.append(
        "\n\n请确保图片清晰、包含完整的化学结构式。"
    )
    return {
        "success": False,
        "smiles": None,
        "source": None,
        "error": "".join(error_parts),
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
