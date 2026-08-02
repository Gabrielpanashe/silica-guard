from unittest.mock import patch

FAKE_RESULT = {
    "tier": "YELLOW",
    "confidence": 0.82,
    "contributing_factors": ["test factor one", "test factor two"],
    "explanation_english": "test explanation in english",
}


def _register_miner(client, phone="+263700000001"):
    resp = client.post(
        "/api/miners",
        json={"name": "Test Miner", "phone": phone, "mine_site": "Test Site"},
    )
    assert resp.status_code == 200
    return resp.json()["id"]


def _ten_answers():
    return [
        {"question_code": f"Q{i}", "answer_value": "x", "answer_score": 1}
        for i in range(10)
    ]


def test_create_miner(client):
    miner_id = _register_miner(client)
    assert miner_id > 0


def test_duplicate_phone_returns_409(client):
    _register_miner(client, phone="+263700000002")
    resp = client.post(
        "/api/miners", json={"name": "Duplicate", "phone": "+263700000002"}
    )
    assert resp.status_code == 409


def test_screen_miner_persists_and_returns_result(client):
    miner_id = _register_miner(client, phone="+263700000003")

    with patch("routers.screening.assess_risk", return_value=FAKE_RESULT):
        resp = client.post(
            "/api/screen",
            json={"miner_id": miner_id, "answers": _ten_answers(), "channel": "APP"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["tier"] == "YELLOW"
    assert body["confidence"] == 0.82
    assert body["contributing_factors"] == FAKE_RESULT["contributing_factors"]
    assert body["previous_screening_id"] is None
    assert body["provisional"] is False


def test_second_screening_links_previous_screening_id(client):
    miner_id = _register_miner(client, phone="+263700000009")

    with patch("routers.screening.assess_risk", return_value=FAKE_RESULT):
        first = client.post(
            "/api/screen", json={"miner_id": miner_id, "answers": _ten_answers()}
        ).json()
        second = client.post(
            "/api/screen", json={"miner_id": miner_id, "answers": _ten_answers()}
        ).json()

    assert first["previous_screening_id"] is None
    assert second["previous_screening_id"] is not None


def test_offline_fallback_used_marks_screening_provisional(client):
    miner_id = _register_miner(client, phone="+263700000010")

    with patch("routers.screening.assess_risk", return_value=FAKE_RESULT):
        resp = client.post(
            "/api/screen",
            json={
                "miner_id": miner_id,
                "answers": _ten_answers(),
                "offline_fallback_used": True,
            },
        )

    assert resp.json()["provisional"] is True


def test_screen_unknown_miner_returns_404(client):
    with patch("routers.screening.assess_risk", return_value=FAKE_RESULT):
        resp = client.post(
            "/api/screen", json={"miner_id": 999999, "answers": _ten_answers()}
        )
    assert resp.status_code == 404


def test_screen_empty_answers_rejected(client):
    miner_id = _register_miner(client, phone="+263700000004")
    resp = client.post("/api/screen", json={"miner_id": miner_id, "answers": []})
    assert resp.status_code == 422  # Pydantic min_length=1 rejects before our code runs


def test_screen_ai_failure_returns_502(client):
    miner_id = _register_miner(client, phone="+263700000005")

    with patch(
        "routers.screening.assess_risk", side_effect=RuntimeError("Gemini is down")
    ):
        resp = client.post(
            "/api/screen", json={"miner_id": miner_id, "answers": _ten_answers()}
        )

    assert resp.status_code == 502
    assert resp.json()["detail"] == "AI risk engine unavailable, please retry"
