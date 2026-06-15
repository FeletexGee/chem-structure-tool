# ============================================================
# ChemStructure Tool — 配置文件
# ============================================================

import os
import sys

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _get_env_robust(name: str, default: str = "") -> str:
    """
    获取环境变量，带 Windows 注册表回退。
    
    Windows 上通过"系统属性 → 环境变量"设置的系统级变量，
    在设置前启动的终端中不会出现在 os.environ 里。
    此函数会额外查询 Windows 注册表作为回退。
    """
    # 1. 优先从当前进程环境变量读取
    value = os.environ.get(name, "")
    if value:
        return value

    # 2. Windows 注册表回退（Machine + User）
    if sys.platform == "win32":
        try:
            import winreg

            # 2a. 系统级（HKEY_LOCAL_MACHINE）
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
                )
                reg_value, _ = winreg.QueryValueEx(key, name)
                winreg.CloseKey(key)
                if reg_value:
                    return reg_value
            except OSError:
                pass

            # 2b. 用户级（HKEY_CURRENT_USER）
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    "Environment",
                )
                reg_value, _ = winreg.QueryValueEx(key, name)
                winreg.CloseKey(key)
                if reg_value:
                    return reg_value
            except OSError:
                pass

        except Exception:
            pass

    return default


# Flask
SECRET_KEY = _get_env_robust("SECRET_KEY", "chem-structure-dev-key-2026")
DEBUG = _get_env_robust("FLASK_DEBUG", "false").lower() == "true"

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
DEEPSEEK_API_KEY = _get_env_robust("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-v4-flash"  # DeepSeek V4 Flash
DEEPSEEK_MAX_TOKENS = 200
DEEPSEEK_TEMPERATURE = 0.0  # 名称翻译任务需要确定性输出

# 输出配置
DEFAULT_2D_SIZE = (800, 600)      # 2D 结构图默认尺寸
DEFAULT_3D_CONF_NUM = 1           # 生成 3D 构象数量
DEFAULT_IMAGE_DPI = 150           # 导出图片 DPI
