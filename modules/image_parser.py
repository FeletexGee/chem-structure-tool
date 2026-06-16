# ============================================================
# ChemStructure Tool — 图像识别模块 (OCSR)
# 化学结构图像 → SMILES
# 主要工具：DECIMER（首选） / Img2Mol（备选）
# ============================================================

import os
import sys
import uuid
from typing import Optional, Dict
from PIL import Image
import numpy as np

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


def _clean_image_with_cv2(
    img: Image.Image,
    remove_lines: bool = True,
) -> Image.Image:
    """
    使用 OpenCV 对化学结构图像进行智能清洗：
    1. 灰度化 + Otsu 二值化（比自适应更干净，不会放大纸张纹理）
    2. Hough 直线检测 → 仅移除贯穿全图的长直线（如笔记本横线）
    3. 轻度中值滤波去噪

    Args:
        img: PIL Image 对象
        remove_lines: 是否尝试检测并移除长直线

    Returns:
        清洗后的 PIL Image (RGB)
    """
    try:
        import cv2
    except ImportError:
        return img

    # 1. 灰度化
    img_np = np.array(img.convert("RGB"))
    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

    # 2. Otsu 二值化 — 自动找最佳阈值，对浅色笔记本线天然不敏感
    _, binary = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    # ── 3. Hough 直线检测：仅移除贯穿型长直线 ────────────
    if remove_lines:
        h, w = binary.shape
        min_line_len = min(w, h) // 2  # 直线至少占图片一半长度

        # 检测边缘
        edges = cv2.Canny(binary, 50, 150, apertureSize=3)

        # Hough 概率直线检测
        lines = cv2.HoughLinesP(
            edges,
            rho=1,
            theta=np.pi / 180,
            threshold=80,
            minLineLength=min_line_len,
            maxLineGap=10,
        )

        if lines is not None:
            # 创建空白掩膜用于标记要移除的直线
            line_mask = np.zeros_like(binary)

            for line in lines:
                x1, y1, x2, y2 = line[0]
                dx = abs(x2 - x1)
                dy = abs(y2 - y1)

                # 只移除接近水平或接近垂直的长直线
                angle = np.arctan2(dy, dx) * 180 / np.pi if dx > 0 else 90
                is_horizontal = angle < 5 or angle > 175   # 水平（±5°）
                is_vertical = 85 < angle < 95               # 垂直（±5°）

                if is_horizontal or is_vertical:
                    # 将线画到掩膜上（稍加粗以防线宽不一致）
                    thickness = 5
                    cv2.line(line_mask, (x1, y1), (x2, y2), 255, thickness)

            if np.any(line_mask):
                # 从二值图中移除检测到的直线（填白）
                binary[line_mask > 0] = 255

    # ── 4. 轻度去噪 ────────────────────────────────────
    binary = cv2.medianBlur(binary, 3)

    # ── 5. 确保白底黑字 ────────────────────────────────
    black_ratio = np.sum(binary < 128) / binary.size
    if black_ratio > 0.5:
        binary = cv2.bitwise_not(binary)

    return Image.fromarray(cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB))


def _preprocess_image(
    image_path: str,
    max_size: int = 1024,
    clean_lines: bool = True,
) -> str:
    """
    预处理上传的图片：缩放、清洗（去线/去噪）、转PNG。
    返回处理后的图片路径。
    """
    img = Image.open(image_path).convert("RGB")

    # 缩放大图
    w, h = img.size
    if max(w, h) > max_size:
        ratio = max_size / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

    # 高级清洗（去横线、去噪）
    if clean_lines:
        img = _clean_image_with_cv2(img, remove_lines=True)

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
        from DECIMER import predict_SMILES

        # 预处理图片
        processed_path = _preprocess_image(image_path)

        # 调用 DECIMER 预测 SMILES（使用标准模型，非手绘模型）
        smiles = predict_SMILES(processed_path, hand_drawn=False)

        if smiles and smiles.strip():
            return {
                "smiles": smiles.strip(),
                "source": "DECIMER",
                "method": "EfficientNet-V2 + Transformer",
            }
        return None
    except ImportError as e:
        return {"smiles": None, "source": "DECIMER", "error": f"DECIMER 未安装或导入失败: {e}"}
    except FileNotFoundError as e:
        return {"smiles": None, "source": "DECIMER", "error": f"图片文件不存在: {e}"}
    except Exception as e:
        return {"smiles": None, "source": "DECIMER", "error": f"DECIMER 推理异常: {str(e)}"}


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
