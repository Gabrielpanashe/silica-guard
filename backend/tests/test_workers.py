from unittest.mock import patch

FAKE_RESULT = {
    "tier": "YELLOW",
    "confidence": 0.82,
    "contributing_factors": ["test factor one"],
    "explanation_english": "test explanation",
}


def _ten_answers():
    return [
        {"question_code": f"Q{i}", "answer_value": "x", "answer_score": 1}
        for i in range(10)
    ]


def test_create_worker_success(client):
    resp = client.post(
        "/api/workers",
        json={"name": "Tendai Moyo", "phone": "+263780000001", "site": "Sherwood Mine"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Tendai Moyo"
    assert body["phone"] == "+263780000001"
    assert body["site"] == "Sherwood Mine"
    assert body["id"] > 0


def test_create_worker_duplicate_phone_409(client):
    client.post(
        "/api/workers", json={"name": "A", "phone": "+263780000002", "site": "X"}
    )
    resp = client.post(
        "/api/workers", json={"name": "B", "phone": "+263780000002", "site": "Y"}
    )
    assert resp.status_code == 409


def test_lookup_unknown_phone_returns_404(client):
    resp = client.get("/api/workers/+263780000099")
    assert resp.status_code == 404


def test_lookup_worker_with_no_screenings_returns_empty_history(client):
    client.post(
        "/api/workers", json={"name": "Fresh Worker", "phone": "+263780000003", "site": "Test Site"}
    )
    resp = client.get("/api/workers/+263780000003")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Fresh Worker"
    assert body["site"] == "Test Site"
    assert body["screenings"] == []


def test_lookup_worker_returns_screenings_most_recent_first(client):
    reg = client.post(
        "/api/workers", json={"name": "Repeat Worker", "phone": "+263780000004", "site": "Test Site"}
    )
    worker_id = reg.json()["id"]

    with patch("routers.screening.assess_risk", return_value=FAKE_RESULT):
        first = client.post(
            "/api/screen", json={"miner_id": worker_id, "answers": _ten_answers()}
        ).json()
        second = client.post(
            "/api/screen", json={"miner_id": worker_id, "answers": _ten_answers()}
        ).json()

    resp = client.get("/api/workers/+263780000004")
    assert resp.status_code == 200
    screenings = resp.json()["screenings"]
    assert len(screenings) == 2
    # Most recent first.
    assert screenings[0]["id"] > screenings[1]["id"]
    assert screenings[0]["tier"] == "YELLOW"
    assert screenings[0]["advice_line"]  # non-negotiable rule: never absent
    assert first["previous_screening_id"] is None
    assert second["previous_screening_id"] == screenings[1]["id"]
