# ============================================================
# ChemStructure Tool — LLM 名称解析模块
# 使用 DeepSeek 将俗名/通用名/中文名 翻译为 IUPAC 系统命名
# 
# 设计原则：LLM 只做"名称翻译"，不做结构生成。
# 翻译后的 IUPAC 名交给 OPSIN 进行确定性解析，
# 从根源上避免 LLM 幻觉导致的结构错误。
# ============================================================

import json
import logging
import requests
from typing import Optional

from config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_API_URL,
    DEEPSEEK_MODEL,
    DEEPSEEK_MAX_TOKENS,
    DEEPSEEK_TEMPERATURE,
)

logger = logging.getLogger(__name__)

# 公开标志：LLM 是否可用
LLM_AVAILABLE = bool(DEEPSEEK_API_KEY and DEEPSEEK_API_KEY.strip())

# ── Prompt 模板 ─────────────────────────────────────────────

SYSTEM_PROMPT = """You are a chemistry nomenclature expert. Your ONLY job is to translate chemical names into standard IUPAC systematic names.

Rules:
1. If the input is a common/trivial name (e.g., "aspirin", "caffeine", "vitamin C"), output the IUPAC systematic name.
2. If the input is a molecular formula (e.g., "C6H12O6"), output the IUPAC name of the most common compound with that formula.
3. If the input is in Chinese (e.g., "咖啡因", "阿司匹林"), translate to the English IUPAC name.
4. If the input is ALREADY an IUPAC name, output it unchanged.
5. Output ONLY the IUPAC name on a single line. No explanations, no prefixes, no suffixes.
6. If you cannot determine the IUPAC name, output "UNKNOWN".

Examples:
- aspirin → 2-acetoxybenzoic acid
- caffeine → 1,3,7-trimethylpurine-2,6-dione
- vitamin C → (5R)-5-[(1S)-1,2-dihydroxyethyl]-3,4-dihydroxyfuran-2(5H)-one
- C6H12O6 → (2R,3S,4R,5R)-2,3,4,5,6-pentahydroxyhexanal
- 咖啡因 → 1,3,7-trimethylpurine-2,6-dione
- benzene → benzene
- ethanol → ethanol"""


# ── 核心函数 ────────────────────────────────────────────────

def resolve_name_to_iupac(user_input: str) -> Optional[str]:
    """
    使用 DeepSeek LLM 将任意化学名称翻译为 IUPAC 系统命名。
    
    Args:
        user_input: 用户输入的化学名称（俗名/通用名/分子式/中文名）
    
    Returns:
        IUPAC 系统命名，失败返回 None
    """
    if not DEEPSEEK_API_KEY:
        return None

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_input.strip()},
    ]

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "max_tokens": DEEPSEEK_MAX_TOKENS,
        "temperature": DEEPSEEK_TEMPERATURE,
        # DeepSeek V4 默认启用思考模式（thinking），会消耗 tokens 用于推理。
        # 名称翻译是确定性任务，无需思考，显式关闭以节省 tokens。
        "thinking": {"type": "disabled"},
    }

    try:
        resp = requests.post(
            DEEPSEEK_API_URL,
            headers=headers,
            json=payload,
            timeout=30,
        )

        if resp.status_code != 200:
            logger.warning(
                "DeepSeek API returned %d: %s",
                resp.status_code,
                resp.text[:300],
            )
            return None

        data = resp.json()

        # 检查 API 层面的错误
        if "error" in data:
            logger.warning("DeepSeek API error: %s", data["error"])
            return None

        # DeepSeek V4 响应可能有 thinking/reasoning_content 字段
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})

        # 优先取 content，如果为空可能是因为 thinking 消耗了所有 tokens
        content = message.get("content", "")
        if not content:
            logger.warning(
                "DeepSeek response has no content. "
                "May be caused by thinking consuming all tokens. "
                "Raw: %s",
                json.dumps(message, ensure_ascii=False)[:300],
            )
            return None

        # 清理输出：只取第一行，去除空白
        iupac_name = content.strip().split("\n")[0].strip()

        # 检查是否为有效的 IUPAC 名
        if not iupac_name or iupac_name.upper() == "UNKNOWN" or len(iupac_name) < 2:
            return None

        # 去掉可能的引号包裹
        iupac_name = iupac_name.strip('"').strip("'")

        return iupac_name

    except requests.exceptions.Timeout:
        logger.warning("DeepSeek API request timed out")
        return None
    except requests.exceptions.ConnectionError:
        logger.warning("DeepSeek API connection failed")
        return None
    except Exception as e:
        logger.warning("DeepSeek API unexpected error: %s", e)
        return None


# ── 批量解析（预留） ─────────────────────────────────────────

def resolve_batch(names: list[str]) -> dict[str, Optional[str]]:
    """
    批量解析多个名称（为后续批量处理功能预留）。
    """
    results = {}
    for name in names:
        results[name] = resolve_name_to_iupac(name)
    return results
