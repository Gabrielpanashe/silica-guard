from datetime import datetime, timezone
from unittest.mock import patch

import database

FAKE_RESULT = {
    "tier": "YELLOW",
    "confidence": 0.82,
    "contributing_factors": ["test factor one", "test factor two"],
    "explanation_english": "test explanation in english",
}


def _register_miner(client, phone="+263700000001"):
    resp = client.post(
        "/api/workers",
        json={"name": "Test Miner", "phone": phone, "site": "Test Site"},
    )
    assert resp.status_code == 200
    return resp.json()["id"]


def _ten_answers():
    return [
        {"question_code": f"Q{i}", "answer_value": "x", "answer_score": 1}
        for i in range(10)
    ]


def test_create_worker(client):
    miner_id = _register_miner(client)
    assert miner_id > 0


def test_duplicate_phone_returns_409(client):
    _register_miner(client, phone="+263700000002")
    resp = client.post(
        "/api/workers", json={"name": "Duplicate", "phone": "+263700000002"}
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


def _seed_outreach_visit(site: str, scheduled_date: str) -> int:
    conn = database.get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO outreach_visits
               (site, scheduled_date, expected_headcount, screened_count, health_workers, report_generated)
               VALUES (?, ?, 10, 0, '[]', 0)""",
            (site, scheduled_date),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def test_screen_explicit_outreach_visit_id_links_and_increments_count(client):
    miner_id = _register_miner(client, phone="+263700000014")
    visit_id = _seed_outreach_visit("Test Site", "2026-01-01")  # not date-matched — explicit wins anyway

    with patch("routers.screening.assess_risk", return_value=FAKE_RESULT):
        client.post(
            "/api/screen",
            json={
                "miner_id": miner_id,
                "outreach_visit_id": visit_id,
                "answers": _ten_answers(),
                "channel": "APP",
            },
        )

    conn = database.get_connection()
    try:
        visit = conn.execute(
            "SELECT screened_count FROM outreach_visits WHERE id = ?", (visit_id,)
        ).fetchone()
        screening = conn.execute(
            "SELECT outreach_visit_id FROM screenings WHERE miner_id = ?", (miner_id,)
        ).fetchone()
    finally:
        conn.close()

    assert visit["screened_count"] == 1
    assert screening["outreach_visit_id"] == visit_id


def test_screen_implicit_app_channel_matches_active_visit_by_site(client):
    miner_id = _register_miner(client, phone="+263700000015")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    visit_id = _seed_outreach_visit("Test Site", today)  # same site as _register_miner's default

    with patch("routers.screening.assess_risk", return_value=FAKE_RESULT):
        client.post(
            "/api/screen",
            json={"miner_id": miner_id, "answers": _ten_answers(), "channel": "APP"},
        )

    conn = database.get_connection()
    try:
        screening = conn.execute(
            "SELECT outreach_visit_id FROM screenings WHERE miner_id = ?", (miner_id,)
        ).fetchone()
    finally:
        conn.close()

    assert screening["outreach_visit_id"] == visit_id


def test_screen_ussd_channel_never_auto_links_even_with_matching_visit(client):
    miner_id = _register_miner(client, phone="+263700000016")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    _seed_outreach_visit("Test Site", today)

    with patch("routers.screening.assess_risk", return_value=FAKE_RESULT):
        client.post(
            "/api/screen",
            json={"miner_id": miner_id, "answers": _ten_answers(), "channel": "USSD"},
        )

    conn = database.get_connection()
    try:
        screening = conn.execute(
            "SELECT outreach_visit_id FROM screenings WHERE miner_id = ?", (miner_id,)
        ).fetchone()
    finally:
        conn.close()

    assert screening["outreach_visit_id"] is None


def test_screen_unknown_explicit_outreach_visit_id_degrades_to_none(client):
    miner_id = _register_miner(client, phone="+263700000017")

    with patch("routers.screening.assess_risk", return_value=FAKE_RESULT):
        resp = client.post(
            "/api/screen",
            json={
                "miner_id": miner_id,
                "outreach_visit_id": 999999,
                "answers": _ten_answers(),
                "channel": "APP",
            },
        )

    assert resp.status_code == 200  # never fails the screening over a bad reference
    conn = database.get_connection()
    try:
        screening = conn.execute(
            "SELECT outreach_visit_id FROM screenings WHERE miner_id = ?", (miner_id,)
        ).fetchone()
    finally:
        conn.close()

    assert screening["outreach_visit_id"] is None


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
