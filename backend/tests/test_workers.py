from datetime import datetime
from unittest.mock import patch

import database
from db_models import Miner, Screening

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


def test_lookup_worker_screenings_carry_days_since_previous(client):
    """22 August 2026 — WorkerScreeningSummary.days_since_previous, computed
    from created_at. Seeds two screenings with a real 14-day gap directly
    via the ORM (POST /api/screen always stamps "now", which can't exercise
    real day arithmetic in a fast test) using database.get_fresh_session(),
    which — unlike database.SessionLocal() — actually honours this
    fixture's monkeypatched test engine (see get_fresh_session's own
    docstring for why that distinction matters)."""
    client.post(
        "/api/workers",
        json={"name": "Trend Worker", "phone": "+263780000005", "site": "Test Site"},
    )

    db = database.get_fresh_session()
    try:
        miner = db.query(Miner).filter_by(phone="+263780000005").one()
        db.add(Screening(miner_id=miner.id, tier="YELLOW", created_at=datetime(2026, 8, 1, 9, 0, 0)))
        db.add(Screening(miner_id=miner.id, tier="ORANGE", created_at=datetime(2026, 8, 15, 9, 0, 0)))
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/workers/+263780000005")
    assert resp.status_code == 200
    screenings = resp.json()["screenings"]
    assert len(screenings) == 2
    # Most recent first (existing ordering) — the newer one's gap is vs. the older one.
    assert screenings[0]["tier"] == "ORANGE"
    assert screenings[0]["days_since_previous"] == 14
    assert screenings[1]["tier"] == "YELLOW"
    assert screenings[1]["days_since_previous"] is None  # nothing earlier to compare to
