# ============================================================
# ChemStructure Tool — 图像识别模块 (OCSR)
# 化学结构图像 → SMILES
# 识别引擎：DECIMER
# ============================================================

import os
import uuid
import logging
import warnings
from typing import Optional, Dict
from PIL import Image, UnidentifiedImageError
import numpy as np

from config import UPLOAD_FOLDER, ALLOWED_IMAGE_EXTENSIONS, MAX_IMAGE_PIXELS

logger = logging.getLogger(__name__)


class ImageValidationError(ValueError):
    """Raised when an uploaded file is not a safe, supported image."""

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
    try:
        img.save(out_path, "PNG")
    except Exception:
        try:
            os.remove(out_path)
        except FileNotFoundError:
            pass
        except OSError as error:
            logger.warning("Failed to remove partial preprocessed image %s: %s", out_path, error)
        raise
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
    processed_path = None
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
        logger.warning("DECIMER import failed: %s", e)
        return {"smiles": None, "source": "DECIMER", "error": "DECIMER 未安装或不可用"}
    except FileNotFoundError as e:
        logger.warning("DECIMER input file missing: %s", e)
        return {"smiles": None, "source": "DECIMER", "error": "图片文件不可用"}
    except Exception as e:
        logger.warning("DECIMER inference failed: %s", e)
        return {"smiles": None, "source": "DECIMER", "error": "DECIMER 推理失败"}
    finally:
        if processed_path and processed_path != image_path:
            try:
                os.remove(processed_path)
            except FileNotFoundError:
                pass
            except OSError as error:
                logger.warning("Failed to remove DECIMER intermediate %s: %s", processed_path, error)


# ── 统一图像识别入口 ─────────────────────────────────────────

def smart_parse_image(image_path: str) -> Dict:
    """
    使用 DECIMER 解析化学结构图片。
    
    Returns:
        {
            "success": bool,
            "smiles": str or None,
            "source": str,       # "DECIMER"
            "error": str or None,
        }
    """
    if not os.path.exists(image_path):
        return {"success": False, "smiles": None, "source": None,
                "error": "图片文件不可用"}

    result = parse_image_decimer(image_path)
    if result and result.get("smiles"):
        return {"success": True, "error": None, **result}
    decimer_error = result.get("error", "") if result else ""

    error_parts = ["图像识别失败。"]
    if decimer_error:
        error_parts.append(f"\n[DECIMER] {decimer_error}")
    else:
        error_parts.append("\n[DECIMER] 未安装（pip install decimer）。")
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

def save_verified_image(
    file_data,
    filename: str,
    upload_folder: Optional[str] = None,
) -> str:
    """验证、去除元数据并将上传图片重新编码为临时 PNG。"""
    if not _allowed_image(filename):
        raise ImageValidationError("不支持的图片扩展名")

    target_folder = upload_folder or UPLOAD_FOLDER
    os.makedirs(target_folder, exist_ok=True)
    save_path = os.path.join(target_folder, f"{uuid.uuid4().hex}.png")
    stream = file_data.stream
    completed = False

    try:
        stream.seek(0)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(stream) as image:
                image_format = (image.format or "").upper()
                if image_format not in {"PNG", "JPEG", "GIF", "BMP", "TIFF", "WEBP"}:
                    raise ImageValidationError("不支持的图片格式")
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise ImageValidationError(
                        f"图片像素尺寸过大（最多 {MAX_IMAGE_PIXELS} 像素）"
                    )
                image.verify()

            stream.seek(0)
            with Image.open(stream) as image:
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise ImageValidationError(
                        f"图片像素尺寸过大（最多 {MAX_IMAGE_PIXELS} 像素）"
                    )
                image.seek(0)
                normalized = image.convert("RGB")
                normalized.save(save_path, "PNG")
        completed = True
        return save_path
    except ImageValidationError:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as error:
        logger.warning("Rejected uploaded image %s: %s", filename, error)
        raise ImageValidationError("文件不是有效的图片") from error
    finally:
        try:
            stream.seek(0)
        except Exception:
            pass
        if not completed and os.path.exists(save_path):
            try:
                os.remove(save_path)
            except OSError:
                pass
