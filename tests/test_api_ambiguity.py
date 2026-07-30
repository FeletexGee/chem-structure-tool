from app import app


def test_process_returns_409_with_candidate_payload_for_co():
    client = app.test_client()

    response = client.post(
        "/api/process",
        json={"input": "CO", "input_type": "auto"},
    )

    assert response.status_code == 409
    payload = response.get_json()
    assert payload["requires_selection"] is True
    assert len(payload["candidates"]) == 2
