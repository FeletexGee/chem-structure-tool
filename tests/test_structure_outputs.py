from rdkit import Chem
from rdkit.Chem import AllChem

from modules.structure_processor import (
    export_molecule,
    generate_3d_conformer,
    render_2d_image,
)


def test_png_atom_indices_change_output():
    plain, plain_error = render_2d_image("CCO", format="PNG", show_atom_indices=False)
    indexed, indexed_error = render_2d_image("CCO", format="PNG", show_atom_indices=True)

    assert plain_error is None
    assert indexed_error is None
    assert plain != indexed


def test_sdf_has_record_separator():
    data, error = export_molecule("CCO", format="SDF")

    assert error is None
    assert data.rstrip().endswith("$$$$")


def test_unknown_2d_format_is_rejected():
    data, error = render_2d_image("CCO", format="WEBP")

    assert data is None
    assert "不支持" in error


def test_etkdgv2_fallback_uses_its_returned_conformer_ids(monkeypatch):
    returned_ids = [[], [7]]

    def fake_embed(*args, **kwargs):
        return returned_ids.pop(0)

    monkeypatch.setattr(AllChem, "EmbedMultipleConfs", fake_embed)
    monkeypatch.setattr(Chem, "MolToPDBBlock", lambda mol: "PDB")

    pdb, error = generate_3d_conformer("CCO", optimize=False)

    assert error is None
    assert pdb == "PDB"
    assert returned_ids == []


def test_pdb_export_rejects_failed_embedding(monkeypatch):
    monkeypatch.setattr(AllChem, "EmbedMultipleConfs", lambda *args, **kwargs: [])

    data, error = export_molecule("CCO", format="PDB")

    assert data is None
    assert "3D 构象生成失败" in error
