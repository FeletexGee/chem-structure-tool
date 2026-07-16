import pytest

from app import app


@pytest.mark.parametrize("value", [None, 12, True, [], {}])
def test_process_rejects_non_string_input(value):
    response = app.test_client().post("/api/process", json={"input": value})

    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_request"


def test_process_rejects_unknown_input_type():
    response = app.test_client().post(
        "/api/process",
        json={"input": "CCO", "input_type": "guess"},
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_request"


def test_process_rejects_excessively_long_input():
    response = app.test_client().post(
        "/api/process",
        json={"input": "C" * 5001},
    )

    assert response.status_code == 400


def test_render_2d_rejects_non_boolean_show_indices():
    response = app.test_client().post(
        "/api/render-2d",
        json={"smiles": "CCO", "show_indices": "yes"},
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_request"


def test_render_3d_rejects_non_boolean_optimize():
    response = app.test_client().post(
        "/api/render-3d",
        json={"smiles": "CCO", "optimize": 1},
    )

    assert response.status_code == 400


def test_export_rejects_unknown_format():
    response = app.test_client().post(
        "/api/export",
        json={"smiles": "CCO", "format": "PDF"},
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_request"


def test_json_endpoint_rejects_non_object_body():
    response = app.test_client().post("/api/process", json=["CCO"])

    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_request"
