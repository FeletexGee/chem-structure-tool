# ============================================================
# ChemStructure Tool — 配置文件
# ============================================================

import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Flask
SECRET_KEY = os.environ.get("SECRET_KEY", "chem-structure-dev-key-2026")
DEBUG = os.environ.get("FLASK_DEBUG", "true").lower() == "true"

# 上传配置
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "bmp", "tiff", "webp"}

# API 端点
OPSIN_API_URL = "https://opsin.ch.cam.ac.uk/opsin/{name}.json"
OPSIN_IMAGE_URL = "https://opsin.ch.cam.ac.uk/opsin/{name}.png"
PUBCHEM_API_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

# ── DeepSeek LLM 配置（用于俗名→IUPAC名称转换）─────────────
# 模型只负责名称翻译，不生成结构，从源头避免幻觉
# API 文档: https://api-docs.deepseek.com/zh-cn/
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")  # 用户自行填写
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-v4-flash"  # DeepSeek V4 Flash
DEEPSEEK_MAX_TOKENS = 200
DEEPSEEK_TEMPERATURE = 0.0  # 名称翻译任务需要确定性输出

# 输出配置
DEFAULT_2D_SIZE = (800, 600)      # 2D 结构图默认尺寸
DEFAULT_3D_CONF_NUM = 1           # 生成 3D 构象数量
DEFAULT_IMAGE_DPI = 150           # 导出图片 DPI
