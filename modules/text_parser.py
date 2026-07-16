# ============================================================
# ChemStructure Tool — 文本解析模块
# 支持：IUPAC命名 / 通用名称 / 分子式 / SMILES → 统一输出 SMILES
# ============================================================

import os
import re
import requests
from typing import Optional, Dict, Tuple

from config import OPSIN_API_URL, PUBCHEM_API_URL, DEEPSEEK_API_KEY

INPUT_TYPES = {"auto", "smiles", "formula", "name"}

# LLM 名称解析（可选，需要 DeepSeek API Key）
try:
    from modules.llm_name_resolver import resolve_name_to_iupac
except ImportError:
    resolve_name_to_iupac = None

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
        status = data.get("status", "")
        smiles = data.get("smiles")
        # 接受 SUCCESS 和 WARNING（如 "hexene" 未指定双键位置时
        # OPSIN 默认解析为 hex-1-ene 并返回 WARNING + SMILES）
        if status in ("SUCCESS", "WARNING") and smiles:
            result = {
                "smiles": smiles,
                "inchi": data.get("inchi"),
                "stdinchi": data.get("stdinchi"),
                "stdinchikey": data.get("stdinchikey"),
                "source": "OPSIN",
                "input_type": "iupac_name",
                "opsin_status": status,
            }
            # 附带 OPSIN 原始消息用于调试/提示
            if status == "WARNING":
                result["opsin_warning"] = data.get("message", "")
            return result
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


def _pubchem_formula_candidates(formula: str, max_results: int = 5) -> list[Dict]:
    """分子式 → PubChem 候选结构列表。"""
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
            return []

        selected_cids = cids[:max_results]
        cid_text = ",".join(str(cid) for cid in selected_cids)
        properties_url = (
            f"{PUBCHEM_API_URL}/compound/cid/{cid_text}/property/"
            "Title,CanonicalSMILES,MolecularFormula/JSON"
        )
        properties_resp = requests.get(properties_url, timeout=8)
        if properties_resp.status_code != 200:
            return []

        properties = properties_resp.json().get("PropertyTable", {}).get("Properties", [])
        candidates = []
        for item in properties:
            smiles = None
            for key in ("CanonicalSMILES", "ConnectivitySMILES", "SMILES", "IsomericSMILES"):
                if item.get(key):
                    smiles = item[key]
                    break
            if not smiles:
                continue
            candidates.append({
                "cid": item.get("CID"),
                "title": item.get("Title") or f"PubChem CID {item.get('CID')}",
                "smiles": smiles,
                "formula": item.get("MolecularFormula") or formula,
            })
        return candidates
    except Exception:
        return []


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
    candidates = _pubchem_formula_candidates(formula_clean)
    if not candidates:
        return None

    normalized_candidates = []
    for candidate in candidates:
        canonical = validate_smiles(candidate["smiles"])
        if not canonical:
            continue
        normalized_candidates.append({
            "id": f"pubchem:{candidate.get('cid')}",
            "label": candidate.get("title") or f"PubChem CID {candidate.get('cid')}",
            "title": candidate.get("title"),
            "input": canonical,
            "input_type": "smiles",
            "smiles": canonical,
            "formula": candidate.get("formula") or formula_clean,
            "cid": candidate.get("cid"),
            "source": "PubChem",
            "note": f"分子式 {formula_clean} 的 PubChem 候选结构",
        })

    if not normalized_candidates:
        return None
    if len(normalized_candidates) == 1:
        candidate = normalized_candidates[0]
        return {
            "smiles": candidate["smiles"],
            "cid": candidate.get("cid"),
            "title": candidate.get("title"),
            "source": "PubChem",
            "input_type": "formula",
        }
    return _ambiguous(
        f"分子式 {formula_clean} 对应多个候选结构，请选择具体化合物",
        normalized_candidates,
    )


# ── SMILES 验证 ─────────────────────────────────────────────

def validate_smiles(smiles: str) -> Optional[str]:
    """
    使用 RDKit 验证并规范化 SMILES。
    返回 canonical SMILES，无效则返回 None。
    """
    try:
        from rdkit import Chem
        from rdkit import RDLogger

        # 静默 RDKit 的 SMILES 解析警告（这些不是真正的错误，
        # 只是 smart_parse 会故意用非 SMILES 输入来试探）
        RDLogger.logger().setLevel(RDLogger.ERROR)

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        return Chem.MolToSmiles(mol, canonical=True)
    except Exception:
        return None


# ── 统一入口：智能识别输入类型并解析 ─────────────────────────

def _resolved(result: Dict) -> Dict:
    return {"success": True, "status": "resolved", "error": None, **result}


def _ambiguous(reason: str, candidates: list[Dict]) -> Dict:
    return {
        "success": False,
        "status": "ambiguous",
        "requires_selection": True,
        "reason": reason,
        "candidates": candidates,
        "smiles": None,
        "error": None,
    }


def _is_formula_like(value: str) -> bool:
    return bool(re.fullmatch(r"(?:[A-Z][a-z]?\d*)+", re.sub(r"\s+", "", value)))


def _smiles_formula(smiles: str) -> Optional[str]:
    try:
        from rdkit import Chem
        from rdkit.Chem import rdMolDescriptors

        mol = Chem.MolFromSmiles(smiles)
        return rdMolDescriptors.CalcMolFormula(mol) if mol is not None else None
    except Exception:
        return None


def _opsin_confirmation(result: Dict, *, label: str, note: str) -> Optional[Dict]:
    canonical = validate_smiles(result.get("smiles", ""))
    if not canonical:
        return None
    return _ambiguous(
        note,
        [{
            "id": f"opsin:{canonical}",
            "label": label,
            "input": canonical,
            "input_type": "smiles",
            "smiles": canonical,
            "formula": _smiles_formula(canonical),
            "source": "OPSIN",
            "note": result.get("opsin_warning") or note,
            "requires_confirmation": True,
        }],
    )


def smart_parse(user_input: str, input_type: str = "auto") -> Dict:
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
        return {"success": False, "status": "error", "smiles": None,
                "error": "输入为空", "extra": {}}

    if input_type not in INPUT_TYPES:
        return {"success": False, "status": "error", "smiles": None,
                "error": f"不支持的输入类型: {input_type}", "extra": {}}

    # 1. 识别 SMILES / 分子式。歧义时不自动选择。
    canonical = validate_smiles(user_input)
    is_formula = _is_formula_like(user_input)

    if input_type == "smiles":
        if canonical:
            return _resolved({
                "smiles": canonical,
                "source": "SMILES",
                "input_type": "smiles",
                "extra": {},
            })
        return {"success": False, "status": "error", "smiles": None,
                "error": "无效的 SMILES 字符串", "extra": {}}

    if input_type == "formula":
        result = parse_formula(user_input)
        if result:
            if result.get("status") == "ambiguous":
                return result
            canonical = validate_smiles(result["smiles"])
            if canonical:
                result["smiles"] = canonical
                return _resolved(result)
        return {"success": False, "status": "error", "smiles": None,
                "error": f"无法查询分子式 '{user_input}' 的候选结构", "extra": {}}

    if input_type == "auto":
        if canonical and is_formula:
            return _ambiguous(
                "输入既可以解释为 SMILES，也可以解释为分子式",
                [
                    {
                        "id": f"smiles:{canonical}",
                        "label": "按 SMILES 解释",
                        "input": canonical,
                        "input_type": "smiles",
                        "smiles": canonical,
                        "formula": _smiles_formula(canonical),
                        "source": "SMILES",
                        "note": "RDKit 可将该文本直接解释为 SMILES",
                    },
                    {
                        "id": f"formula:{user_input}",
                        "label": "按分子式解释",
                        "input": user_input,
                        "input_type": "formula",
                        "formula": re.sub(r"\s+", "", user_input),
                        "source": "PubChem",
                        "note": "该分子式可能对应多个结构，选择后查询候选",
                    },
                ],
            )
        if canonical:
            return _resolved({
                "smiles": canonical,
                "source": "SMILES",
                "input_type": "smiles",
                "extra": {},
            })
        if is_formula:
            result = parse_formula(user_input)
            if result:
                if result.get("status") == "ambiguous":
                    return result
                canonical = validate_smiles(result["smiles"])
                if canonical:
                    result["smiles"] = canonical
                    return _resolved(result)

    # 显式 name 或 auto 未匹配 SMILES/分子式时，进入名称解析链路。

    # 3. 尝试 OPSIN（IUPAC 命名）
    result = parse_iupac_name(user_input)
    if result:
        if result.get("opsin_status") == "WARNING":
            confirmation = _opsin_confirmation(
                result,
                label="确认 OPSIN 的解释",
                note="OPSIN 对该名称给出了警告，请确认其建议结构",
            )
            if confirmation:
                return confirmation
        canonical = validate_smiles(result["smiles"])
        if canonical:
            result["smiles"] = canonical
            return _resolved(result)

    # 4. 尝试 PubChem（通用名称）
    result = parse_common_name(user_input)
    if result:
        canonical = validate_smiles(result["smiles"])
        if canonical:
            result["smiles"] = canonical
            return _resolved(result)

    # 5. 尝试 LLM → IUPAC 名称 → OPSIN（最终兜底）
    #    LLM 只做名称翻译，结构仍由 OPSIN 确定性解析，避免幻觉
    if resolve_name_to_iupac:
        llm_raw = resolve_name_to_iupac(user_input)
        if llm_raw and llm_raw != user_input:
            # 5a. 尝试 OPSIN 解析 LLM 翻译后的名称
            result = parse_iupac_name(llm_raw)

            if result and result.get("opsin_status") == "WARNING":
                confirmation = _opsin_confirmation(
                    result,
                    label="确认 LLM 与 OPSIN 的解释",
                    note="LLM 翻译后的名称被 OPSIN 警告，请确认建议结构",
                )
                if confirmation:
                    return confirmation

            if not result:
                stripped = re.sub(
                    r'^(?:\((?:E|Z|R|S|cis|trans|syn|anti)\)-|'
                    r'(?:E|Z|R|S|cis|trans|syn|anti)-)',
                    '', llm_raw
                )
                if stripped != llm_raw:
                    stripped_result = parse_iupac_name(stripped)
                    if stripped_result:
                        canonical = validate_smiles(stripped_result["smiles"])
                        if canonical:
                            return _ambiguous(
                                "原始立体化学名称无法解析；如需忽略立体化学信息，请明确确认",
                                [{
                                    "id": f"stereo-stripped:{canonical}",
                                    "label": "忽略立体化学信息",
                                    "input": canonical,
                                    "input_type": "smiles",
                                    "smiles": canonical,
                                    "formula": _smiles_formula(canonical),
                                    "source": "LLM(DeepSeek) → OPSIN",
                                    "note": f'候选名称：{stripped}',
                                    "requires_confirmation": True,
                                }],
                            )

            if result:
                canonical = validate_smiles(result["smiles"])
                if canonical:
                    result["smiles"] = canonical
                    result["source"] = f"LLM(DeepSeek) → OPSIN"
                    result["input_type"] = "llm_iupac"
                    result["llm_raw_iupac_name"] = llm_raw
                    result["llm_iupac_name"] = llm_raw
                    result["auto_corrected"] = False
                    return _resolved(result)

            # 5c. OPSIN 仍失败 → 尝试 PubChem 用 LLM 翻译后的名称
            result = parse_common_name(llm_raw)
            if result:
                canonical = validate_smiles(result["smiles"])
                if canonical:
                    result["smiles"] = canonical
                    result["source"] = f"LLM(DeepSeek) → PubChem"
                    result["input_type"] = "llm_common"
                    result["llm_raw_iupac_name"] = llm_raw
                    result["llm_iupac_name"] = llm_raw
                    result["auto_corrected"] = False
                    return _resolved(result)

    # 6. 全部失败
    hint = ""
    # 动态检查 API Key 是否已设置（含 Windows 注册表回退）
    api_key_available = bool(
        os.environ.get("DEEPSEEK_API_KEY", "").strip() or DEEPSEEK_API_KEY.strip()
    )
    if not api_key_available:
        hint = "\n💡 提示：设置环境变量 DEEPSEEK_API_KEY 可启用 LLM 辅助解析俗名和分子式。"
    return {
        "success": False,
        "status": "error",
        "smiles": None,
        "error": f"无法识别输入 '{user_input}'。请尝试输入 IUPAC 命名、通用名称、分子式或 SMILES。{hint}",
        "extra": {},
    }
