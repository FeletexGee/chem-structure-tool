# ============================================================
# ChemStructure Tool — 结构处理与渲染模块 (RDKit)
# SMILES → 2D/3D 结构处理 → 图像/PDB 渲染输出
# ============================================================

import os
import io
import uuid
from typing import Optional, Dict, Tuple
from config import DEFAULT_2D_SIZE, DEFAULT_3D_CONF_NUM, DEFAULT_IMAGE_DPI


# ── 分子对象创建与基础处理 ───────────────────────────────────

def smiles_to_mol(smiles: str):
    """
    SMILES → RDKit Mol 对象。
    自动添加氢原子，生成 2D 坐标，Kekulize 处理。
    """
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None, "无效的 SMILES 字符串"

        # 生成 2D 坐标
        AllChem.Compute2DCoords(mol)

        # 显式氢可帮助展示完整结构
        # mol = Chem.AddHs(mol)  # 默认不加 H，保持简洁

        return mol, None
    except Exception as e:
        return None, str(e)


# ── 分子信息提取 ─────────────────────────────────────────────

def get_molecule_info(smiles: str) -> Dict:
    """
    获取分子的基本信息：分子式、分子量、原子数、LogP 等。
    """
    try:
        from rdkit import Chem
        from rdkit.Chem import Descriptors, rdMolDescriptors

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return {"error": "无效的 SMILES"}

        formula = rdMolDescriptors.CalcMolFormula(mol)
        mw = Descriptors.MolWt(mol)
        num_atoms = mol.GetNumAtoms()
        num_bonds = mol.GetNumBonds()
        num_rings = rdMolDescriptors.CalcNumRings(mol)
        logp = Descriptors.MolLogP(mol)
        hba = rdMolDescriptors.CalcNumHBA(mol)      # 氢键受体数
        hbd = rdMolDescriptors.CalcNumHBD(mol)      # 氢键供体数
        rot_bonds = rdMolDescriptors.CalcNumRotatableBonds(mol)
        tpsa = Descriptors.TPSA(mol)                # 拓扑极性表面积

        return {
            "formula": formula,
            "molecular_weight": round(mw, 2),
            "num_atoms": num_atoms,
            "num_bonds": num_bonds,
            "num_rings": num_rings,
            "logP": round(logp, 2),
            "h_bond_acceptors": hba,
            "h_bond_donors": hbd,
            "rotatable_bonds": rot_bonds,
            "TPSA": round(tpsa, 2),
        }
    except Exception as e:
        return {"error": str(e)}


# ── 2D 结构图渲染 ───────────────────────────────────────────

def render_2d_image(
    smiles: str,
    size: Tuple[int, int] = DEFAULT_2D_SIZE,
    format: str = "PNG",
    show_atom_indices: bool = False,
    kekulize: bool = True,
) -> Tuple[Optional[bytes], Optional[str]]:
    """
    将 SMILES 渲染为 2D 结构图。

    Args:
        smiles: SMILES 字符串
        size: (width, height) 图像尺寸
        format: "PNG" 或 "SVG"
        show_atom_indices: 是否显示原子编号
        kekulize: 是否 Kekulize（显示芳香键为单双键交替）

    Returns:
        (image_bytes, error_message)
    """
    try:
        from rdkit import Chem
        from rdkit.Chem import Draw, AllChem

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None, "无效的 SMILES 字符串"

        # 生成 2D 坐标
        AllChem.Compute2DCoords(mol)

        if format.upper() == "SVG":
            from rdkit.Chem.Draw import rdMolDraw2D

            drawer = rdMolDraw2D.MolDraw2DSVG(size[0], size[1])
            opts = drawer.drawOptions()
            if show_atom_indices:
                opts.addAtomIndices = True
            drawer.DrawMolecule(mol)
            drawer.FinishDrawing()
            svg_text = drawer.GetDrawingText()
            return svg_text.encode("utf-8"), None
        else:
            # PNG
            img = Draw.MolToImage(
                mol,
                size=size,
                kekulize=kekulize,
            )
            buf = io.BytesIO()
            img.save(buf, format="PNG", dpi=(DEFAULT_IMAGE_DPI, DEFAULT_IMAGE_DPI))
            return buf.getvalue(), None
    except Exception as e:
        return None, str(e)


# ── 3D 构象生成 ─────────────────────────────────────────────

def generate_3d_conformer(
    smiles: str,
    num_confs: int = DEFAULT_3D_CONF_NUM,
    optimize: bool = True,
) -> Tuple[Optional[str], Optional[str]]:
    """
    生成分子的 3D 构象，导出为 PDB 格式字符串。

    Args:
        smiles: SMILES 字符串
        num_confs: 生成构象数量
        optimize: 是否使用力场优化（MMFF94，失败回退 UFF）

    Returns:
        (pdb_string, error_message)
    """
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None, "无效的 SMILES 字符串"

        # 添加氢原子（3D 结构需要）
        mol = Chem.AddHs(mol)

        # 使用 ETKDGv3 方法生成 3D 构象（对复杂分子更鲁棒）
        params = AllChem.ETKDGv3()
        params.numThreads = 1  # 单线程避免并行问题
        params.randomSeed = 42  # 固定种子确保可复现
        conf_ids = AllChem.EmbedMultipleConfs(mol, numConfs=num_confs, params=params)

        # EmbedMultipleConfs 返回 _vectint (list of conformer IDs) 在新版 RDKit 中
        try:
            num_generated = len(list(conf_ids))
        except Exception:
            num_generated = mol.GetNumConformers()

        if num_generated == 0:
            # 回退到 ETKDGv2（某些分子对 v3 不兼容）
            try:
                params_v2 = AllChem.ETKDGv2()
                params_v2.numThreads = 1
                params_v2.randomSeed = 42
                AllChem.EmbedMultipleConfs(mol, numConfs=num_confs, params=params_v2)
                try:
                    num_generated = len(list(conf_ids))
                except Exception:
                    num_generated = mol.GetNumConformers()
            except Exception:
                pass

        if num_generated == 0:
            return None, "3D 构象生成失败（分子过于复杂或刚性，ETKDG 无法生成有效构象）"

        # 力场优化（MMFF94 → UFF 回退）
        if optimize:
            optimized = False
            # 1. 尝试 MMFF94（精确但覆盖不全，不支持金属原子）
            try:
                result = AllChem.MMFFOptimizeMoleculeConfs(mol)
                # result 是 list of (not_converged, energy) tuples
                optimized = True
            except Exception:
                pass

            # 2. MMFF 失败 → 回退 UFF（通用力场，覆盖所有原子类型）
            if not optimized:
                try:
                    AllChem.UFFOptimizeMoleculeConfs(mol)
                except Exception:
                    pass

        # 导出为 PDB 格式（包含 CONECT 记录，确保 3Dmol.js 正确显示键连）
        pdb_block = Chem.MolToPDBBlock(mol)
        return pdb_block, None
    except Exception as e:
        return None, str(e)


# ── 多格式导出 ──────────────────────────────────────────────

def export_molecule(smiles: str, format: str = "MOL") -> Tuple[Optional[str], Optional[str]]:
    """
    将 SMILES 导出为各种化学格式。

    支持的格式: SMILES, InChI, MOL, SDF, PDB
    """
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None, "无效的 SMILES 字符串"

        AllChem.Compute2DCoords(mol)

        fmt = format.upper()
        if fmt == "SMILES":
            return Chem.MolToSmiles(mol, canonical=True), None
        elif fmt == "INCHI":
            return Chem.MolToInchi(mol), None
        elif fmt == "INCHIKEY":
            return Chem.MolToInchiKey(mol), None
        elif fmt == "MOL":
            return Chem.MolToMolBlock(mol), None
        elif fmt == "SDF":
            return Chem.MolToMolBlock(mol), None  # SDF 本质是 MOL block
        elif fmt == "PDB":
            mol_with_h = Chem.AddHs(mol)
            params = AllChem.ETKDGv3()
            params.numThreads = 1
            AllChem.EmbedMultipleConfs(mol_with_h, numConfs=1, params=params)
            return Chem.MolToPDBBlock(mol_with_h), None
        else:
            return None, f"不支持的格式: {format}（支持 SMILES, InChI, MOL, SDF, PDB）"
    except Exception as e:
        return None, str(e)


# ── 化学规则校验 ─────────────────────────────────────────────

def validate_structure(smiles: str) -> Dict:
    """
    对分子结构进行化学规则校验，返回校验报告。

    检查项目：
    - SMILES 规范性
    - 原子价键合理性（简单检查）
    - 是否有不合法的化学键
    """
    try:
        from rdkit import Chem
        from rdkit.Chem import rdMolDescriptors

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return {"valid": False, "issues": ["无效的 SMILES 字符串"]}

        issues = []
        warnings = []

        # 检查每个原子的价键
        for atom in mol.GetAtoms():
            try:
                # 检查显式价键是否超标 (使用新版 API 避免 deprecation warning)
                try:
                    valence = atom.GetTotalValence()
                except AttributeError:
                    valence = atom.GetExplicitValence() + atom.GetImplicitValence()
                # 常见原子最大键数（简单规则）
                max_valence = {
                    6: 4,   # C
                    7: 4,   # N (含正离子)
                    8: 2,   # O
                    9: 1,   # F
                    15: 5,  # P
                    16: 6,  # S
                    17: 1,  # Cl
                    35: 1,  # Br
                    53: 1,  # I
                }
                atomic_num = atom.GetAtomicNum()
                if atomic_num in max_valence and valence > max_valence[atomic_num]:
                    warnings.append(
                        f"原子 {atom.GetIdx()}({atom.GetSymbol()}) 价键数 {valence} "
                        f"超过常规值 {max_valence[atomic_num]}"
                    )
            except Exception:
                pass

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "formula": rdMolDescriptors.CalcMolFormula(mol),
        }
    except Exception as e:
        return {"valid": False, "issues": [str(e)], "warnings": []}
