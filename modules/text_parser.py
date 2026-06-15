# ============================================================
# ChemStructure Tool — 文本解析模块
# 支持：IUPAC命名 / 通用名称 / 分子式 / SMILES → 统一输出 SMILES
# ============================================================

import re
import requests
from typing import Optional, Dict, Tuple

from config import OPSIN_API_URL, PUBCHEM_API_URL

# LLM 名称解析（可选，需要 DeepSeek API Key）
try:
    from modules.llm_name_resolver import resolve_name_to_iupac, LLM_AVAILABLE
except ImportError:
    resolve_name_to_iupac = None
    LLM_AVAILABLE = False

# ── OPSIN: IUPAC 系统命名 → SMILES ──────────────────────────

def parse_iupac_name(name: str) -> Optional[Dict]:
    """
    通过 OPSIN API 将 IUPAC 系统命名转换为化学结构信息。
    
    Args:
        name: IUPAC 命名，如 "propan-2-one", "1,3,7-trimethylpurine-2,6-dione"
    
    Returns:
        dict with keys: smiles, inchi, stdinchi, stdinchikey, status, message
        失败返回 None
    """
    url = OPSIN_API_URL.format(name=requests.utils.quote(name))
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get("status") == "SUCCESS":
            return {
                "smiles": data.get("smiles"),
                "inchi": data.get("inchi"),
                "stdinchi": data.get("stdinchi"),
                "stdinchikey": data.get("stdinchikey"),
                "source": "OPSIN",
                "input_type": "iupac_name",
            }
        return None
    except Exception:
        return None


# ── PubChem: 通用名称 / 分子式 → SMILES ─────────────────────

def _pubchem_name_to_cid(name: str) -> Optional[int]:
    """通用名称 → PubChem CID"""
    url = f"{PUBCHEM_API_URL}/compound/name/{requests.utils.quote(name)}/cids/JSON"
    try:
        resp = requests.get(url, timeout=8)
        if resp.status_code != 200:
            return None
        data = resp.json()
        cids = data.get("IdentifierList", {}).get("CID", [])
        return cids[0] if cids else None
    except Exception:
        return None


def _pubchem_cid_to_smiles(cid: int) -> Optional[str]:
    """PubChem CID → Canonical SMILES"""
    url = f"{PUBCHEM_API_URL}/compound/cid/{cid}/property/CanonicalSMILES/JSON"
    try:
        resp = requests.get(url, timeout=8)
        if resp.status_code != 200:
            return None
        data = resp.json()
        props = data.get("PropertyTable", {}).get("Properties", [])
        if not props:
            return None
        # PubChem API 有时返回不同命名的 SMILES 字段
        for key in ("CanonicalSMILES", "ConnectivitySMILES", "SMILES", "IsomericSMILES"):
            if props[0].get(key):
                return props[0][key]
        return None
    except Exception:
        return None


def _pubchem_formula_to_smiles(formula: str, max_results: int = 1) -> Optional[Dict]:
    """分子式 → SMILES（返回最常见的一个化合物）"""
    url = (
        f"{PUBCHEM_API_URL}/compound/fastformula/"
        f"{requests.utils.quote(formula)}/cids/JSON?MaxRecords={max_results}"
    )
    try:
        resp = requests.get(url, timeout=8)
        if resp.status_code != 200:
            return None
        data = resp.json()
        cids = data.get("IdentifierList", {}).get("CID", [])
        if not cids:
            return None

        # 只取第一个（最常见）化合物
        cid = cids[0]
        smiles = _pubchem_cid_to_smiles(cid)
        if smiles:
            return {
                "smiles": smiles,
                "cid": cid,
                "source": "PubChem",
                "input_type": "formula",
            }
        return None
    except Exception:
        return None


def parse_common_name(name: str) -> Optional[Dict]:
    """
    通过 PubChem 将通用名称（如 "caffeine", "aspirin"）转换为 SMILES。
    """
    cid = _pubchem_name_to_cid(name)
    if not cid:
        return None
    smiles = _pubchem_cid_to_smiles(cid)
    if not smiles:
        return None
    return {
        "smiles": smiles,
        "cid": cid,
        "source": "PubChem",
        "input_type": "common_name",
    }


# ── 分子式 → SMILES ─────────────────────────────────────────

def parse_formula(formula: str) -> Optional[Dict]:
    """
    通过 PubChem 将分子式转换为 SMILES。
    如 "C6H12O6" → 葡萄糖的 SMILES
    """
    # 简单校验：分子式格式
    formula_clean = re.sub(r"\s+", "", formula)
    if not re.match(r"^([A-Z][a-z]?\d*)+$", formula_clean):
        return None
    return _pubchem_formula_to_smiles(formula_clean)


# ── SMILES 验证 ─────────────────────────────────────────────

def validate_smiles(smiles: str) -> Optional[str]:
    """
    使用 RDKit 验证并规范化 SMILES。
    返回 canonical SMILES，无效则返回 None。
    """
    try:
        from rdkit import Chem
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        return Chem.MolToSmiles(mol, canonical=True)
    except Exception:
        return None


# ── 统一入口：智能识别输入类型并解析 ─────────────────────────

def smart_parse(user_input: str) -> Dict:
    """
    智能解析：自动判断输入类型（IUPAC名/通用名/分子式/SMILES），
    返回统一的结构信息。
    
    Returns:
        {
            "success": bool,
            "smiles": str or None,
            "source": str,       # "OPSIN" | "PubChem" | "SMILES"
            "input_type": str,   # "iupac_name" | "common_name" | "formula" | "smiles"
            "error": str or None,
            "extra": dict,       # 附加信息（InChI, CID, alternatives 等）
        }
    """
    user_input = user_input.strip()
    if not user_input:
        return {"success": False, "smiles": None, "error": "输入为空", "extra": {}}

    # 1. 先尝试作为 SMILES 直接解析
    canonical = validate_smiles(user_input)
    if canonical:
        return {
            "success": True,
            "smiles": canonical,
            "source": "SMILES",
            "input_type": "smiles",
            "error": None,
            "extra": {},
        }

    # 2. 判断是否为分子式（仅含元素符号+数字，无特殊字符）
    is_formula = re.match(r"^([A-Z][a-z]?\d*)+$", re.sub(r"\s+", "", user_input))
    if is_formula:
        result = parse_formula(user_input)
        if result:
            canonical = validate_smiles(result["smiles"])
            if canonical:
                result["smiles"] = canonical
                return {"success": True, "error": None, **result}
        # PubChem 失败不直接返回错误，继续尝试 LLM → OPSIN

    # 3. 尝试 OPSIN（IUPAC 命名）
    result = parse_iupac_name(user_input)
    if result:
        canonical = validate_smiles(result["smiles"])
        if canonical:
            result["smiles"] = canonical
            return {"success": True, "error": None, **result}

    # 4. 尝试 PubChem（通用名称）
    result = parse_common_name(user_input)
    if result:
        canonical = validate_smiles(result["smiles"])
        if canonical:
            result["smiles"] = canonical
            return {"success": True, "error": None, **result}

    # 5. 尝试 LLM → IUPAC 名称 → OPSIN（最终兜底）
    #    LLM 只做名称翻译，结构仍由 OPSIN 确定性解析，避免幻觉
    if resolve_name_to_iupac and LLM_AVAILABLE:
        iupac_name = resolve_name_to_iupac(user_input)
        if iupac_name and iupac_name != user_input:
            result = parse_iupac_name(iupac_name)
            if result:
                canonical = validate_smiles(result["smiles"])
                if canonical:
                    result["smiles"] = canonical
                    result["source"] = f"LLM(DeepSeek) → OPSIN"
                    result["input_type"] = "llm_iupac"
                    result["llm_iupac_name"] = iupac_name
                    return {"success": True, "error": None, **result}
            # LLM 翻译后 OPSIN 仍失败 → 尝试 PubChem 用 LLM 翻译后的名称
            result = parse_common_name(iupac_name)
            if result:
                canonical = validate_smiles(result["smiles"])
                if canonical:
                    result["smiles"] = canonical
                    result["source"] = f"LLM(DeepSeek) → PubChem"
                    result["input_type"] = "llm_common"
                    result["llm_iupac_name"] = iupac_name
                    return {"success": True, "error": None, **result}

    # 6. 全部失败
    hint = ""
    if not LLM_AVAILABLE:
        hint = "\n💡 提示：设置环境变量 DEEPSEEK_API_KEY 可启用 LLM 辅助解析俗名和分子式。"
    return {
        "success": False,
        "smiles": None,
        "error": f"无法识别输入 '{user_input}'。请尝试输入 IUPAC 命名、通用名称、分子式或 SMILES。{hint}",
        "extra": {},
    }
