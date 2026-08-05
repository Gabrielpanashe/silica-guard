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


def test_screen_response_carries_advice_line_and_deterioration(client):
    miner_id = _register_miner(client, phone="+263700000011")

    with patch("routers.screening.assess_risk", return_value=FAKE_RESULT):
        resp = client.post(
            "/api/screen",
            json={"miner_id": miner_id, "answers": _ten_answers(), "channel": "APP"},
        )

    body = resp.json()
    assert body["advice_line"]  # non-negotiable rule: never absent
    assert body["deterioration"]["compared_to_screening_id"] is None
    assert body["deterioration"]["changed"] is False


def test_screen_hard_red_flag_overrides_ai_tier_even_when_ai_says_green(client):
    """The model can never downgrade a RED — a red-flag answer forces RED
    even when the (mocked) AI result says GREEN."""
    miner_id = _register_miner(client, phone="+263700000012")

    green_from_model = {
        "tier": "GREEN",
        "confidence": 0.9,
        "contributing_factors": ["looked fine"],
        "explanation_english": "Low risk overall",
    }
    answers = _ten_answers()
    answers[0] = {"question_code": "BREATHLESSNESS", "answer_value": "severe", "answer_score": 5}

    with patch("routers.screening.assess_risk", return_value=green_from_model):
        resp = client.post(
            "/api/screen",
            json={"miner_id": miner_id, "answers": answers, "channel": "APP"},
        )

    body = resp.json()
    assert body["tier"] == "RED"


def test_second_screening_with_worsened_symptom_escalates_tier(client):
    miner_id = _register_miner(client, phone="+263700000013")

    with patch("routers.screening.assess_risk", return_value=FAKE_RESULT):
        first_answers = _ten_answers()
        first_answers[0] = {"question_code": "COUGH_DURATION", "answer_value": "no", "answer_score": 0}
        client.post(
            "/api/screen",
            json={"miner_id": miner_id, "answers": first_answers, "channel": "APP"},
        )

        second_answers = _ten_answers()
        second_answers[0] = {"question_code": "COUGH_DURATION", "answer_value": "severe", "answer_score": 5}
        second = client.post(
            "/api/screen",
            json={"miner_id": miner_id, "answers": second_answers, "channel": "APP"},
        ).json()

    # FAKE_RESULT's tier is YELLOW; worsened cough should escalate it to ORANGE.
    assert second["tier"] == "ORANGE"
    assert second["deterioration"]["changed"] is True
    assert second["deterioration"]["compared_to_screening_id"] is not None


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
