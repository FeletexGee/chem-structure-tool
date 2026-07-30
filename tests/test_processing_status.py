import app as app_module


def test_process_reports_3d_failure_as_partial(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "smart_parse",
        lambda value, input_type="auto": {
            "success": True,
            "status": "resolved",
            "smiles": "CCO",
            "source": "SMILES",
            "input_type": "smiles",
        },
    )
    monkeypatch.setattr(app_module, "render_2d_image", lambda value: (b"png", None))
    monkeypatch.setattr(
        app_module,
        "generate_3d_conformer",
        lambda value: (None, "3D 构象生成失败"),
    )

    response = app_module.app.test_client().post(
        "/api/process",
        json={"input": "CCO", "input_type": "smiles"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["status"] == "partial"
    assert payload["stages"]["render_3d"] == {
        "success": False,
        "error": "3D 构象生成失败",
    }
    assert payload["pdb_data"] is None


def test_process_reports_2d_failure_without_hiding_other_results(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "smart_parse",
        lambda value, input_type="auto": {
            "success": True,
            "status": "resolved",
            "smiles": "CCO",
            "source": "SMILES",
            "input_type": "smiles",
        },
    )
    monkeypatch.setattr(
        app_module,
        "render_2d_image",
        lambda value: (None, "2D 渲染失败"),
    )
    monkeypatch.setattr(app_module, "generate_3d_conformer", lambda value: ("PDB", None))

    response = app_module.app.test_client().post(
        "/api/process",
        json={"input": "CCO", "input_type": "smiles"},
    )
    payload = response.get_json()

    assert payload["status"] == "partial"
    assert payload["stages"]["render_2d"]["success"] is False
    assert payload["pdb_data"] == "PDB"
