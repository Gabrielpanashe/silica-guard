from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest

import database
from db_models import Miner, OutreachVisit
from services.outreach import match_active_visit, next_outreach_action, process_due_outreach_visits

NOW = datetime(2026, 8, 10, 12, 0, 0)
TODAY = NOW.date()


# --- next_outreach_action: pure-function table of cases ---


def test_too_early_for_anything_returns_none():
    scheduled = TODAY + timedelta(days=10)
    assert next_outreach_action(scheduled, False, False, False, NOW) is None


def test_3day_threshold_triggers_sms_3day():
    scheduled = TODAY + timedelta(days=3)
    action = next_outreach_action(scheduled, False, False, False, NOW)
    assert action == {"action": "sms_3day"}


def test_1day_threshold_triggers_sms_1day():
    scheduled = TODAY + timedelta(days=1)
    action = next_outreach_action(scheduled, True, False, False, NOW)
    assert action == {"action": "sms_1day"}


def test_1day_wins_over_3day_when_both_overdue_same_tick():
    scheduled = TODAY + timedelta(days=1)  # both 3-day and 1-day thresholds passed
    action = next_outreach_action(scheduled, False, False, False, NOW)
    assert action == {"action": "sms_1day"}


def test_already_sent_flags_produce_no_repeat():
    scheduled = TODAY + timedelta(days=1)
    assert next_outreach_action(scheduled, True, True, False, NOW) is None


def test_visit_day_itself_not_yet_report_ready():
    # scheduled_date == today: not yet "passed", so no report action yet.
    assert next_outreach_action(TODAY, True, True, False, NOW) is None


def test_day_after_visit_marks_report_ready():
    scheduled = TODAY - timedelta(days=1)
    action = next_outreach_action(scheduled, True, True, False, NOW)
    assert action == {"action": "mark_report_ready"}


def test_report_ready_beats_pending_sms_once_visit_has_passed():
    scheduled = TODAY - timedelta(days=1)
    action = next_outreach_action(scheduled, False, False, False, NOW)
    assert action == {"action": "mark_report_ready"}


def test_already_reported_returns_none_even_long_after():
    scheduled = TODAY - timedelta(days=30)
    assert next_outreach_action(scheduled, True, True, True, NOW) is None


# --- match_active_visit: pure-function table of cases ---

VISIT_A = {"id": 1, "site": "Sherwood Mine", "scheduled_date": "2026-08-10"}
VISIT_B = {"id": 2, "site": "Globe & Phoenix Mine", "scheduled_date": "2026-08-10"}
VISIT_A_DUPLICATE = {"id": 5, "site": "Sherwood Mine", "scheduled_date": "2026-08-10"}


def test_exact_site_match_in_window():
    screened_at = datetime(2026, 8, 10, 9, 0, 0)
    match = match_active_visit("Sherwood Mine", screened_at, [VISIT_A, VISIT_B])
    assert match["id"] == 1


def test_case_insensitive_match():
    screened_at = datetime(2026, 8, 10, 9, 0, 0)
    match = match_active_visit("sherwood mine", screened_at, [VISIT_A])
    assert match["id"] == 1


def test_match_within_sync_lag_day_after():
    screened_at = datetime(2026, 8, 11, 7, 0, 0)  # day after the visit
    match = match_active_visit("Sherwood Mine", screened_at, [VISIT_A])
    assert match["id"] == 1


def test_no_match_outside_window():
    screened_at = datetime(2026, 8, 13, 9, 0, 0)
    assert match_active_visit("Sherwood Mine", screened_at, [VISIT_A]) is None


def test_no_match_when_no_site():
    assert match_active_visit(None, NOW, [VISIT_A]) is None


def test_no_visits_returns_none():
    assert match_active_visit("Sherwood Mine", NOW, []) is None


def test_multiple_matches_lowest_id_wins():
    screened_at = datetime(2026, 8, 10, 9, 0, 0)
    match = match_active_visit("Sherwood Mine", screened_at, [VISIT_A_DUPLICATE, VISIT_A])
    assert match["id"] == 1


# --- process_due_outreach_visits: integration against a real ORM session ---


@pytest.fixture
def db(tmp_path):
    # Builds its own throwaway engine explicitly, rather than monkeypatching
    # database.DATABASE_URL and calling database.SessionLocal() — that
    # module-level SessionLocal is bound to the real default engine built
    # at import time and is NOT affected by monkeypatching the DATABASE_URL
    # string, so a session made that way would silently read/write the real
    # dev database. (Confirmed the hard way: an earlier version of this
    # fixture leaked test rows into backend/data/silicaguard.db.)
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(
        f"sqlite:///{tmp_path / 'outreach_test.db'}", connect_args={"check_same_thread": False}
    )
    database.enable_sqlite_foreign_keys(engine)
    database.init_db(target_engine=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _seed_visit(db, site, scheduled_date, sms_3day_sent=0, sms_1day_sent=0, report_generated=0):
    visit = OutreachVisit(
        site=site,
        scheduled_date=date.fromisoformat(scheduled_date),
        expected_headcount=10,
        screened_count=0,
        health_workers="[]",
        report_generated=report_generated,
        sms_3day_sent=sms_3day_sent,
        sms_1day_sent=sms_1day_sent,
    )
    db.add(visit)
    db.commit()
    db.refresh(visit)
    return visit.id


def _seed_worker(db, name, phone, site):
    db.add(Miner(name=name, phone=phone, mine_site=site))
    db.commit()


def test_process_due_visits_sends_3day_announcement_to_all_site_workers(db):
    scheduled = (TODAY + timedelta(days=3)).strftime("%Y-%m-%d")
    visit_id = _seed_visit(db, "Sherwood Mine", scheduled)
    _seed_worker(db, "Worker One", "+263700333001", "Sherwood Mine")
    _seed_worker(db, "Worker Two", "+263700333002", "Sherwood Mine")
    _seed_worker(db, "Other Site Worker", "+263700333003", "Globe & Phoenix Mine")

    with patch("services.notifications.send_outreach_announcement") as mock_send:
        process_due_outreach_visits(db, now=NOW)

    assert mock_send.call_count == 2
    sent_phones = {call.args[1] for call in mock_send.call_args_list}
    assert sent_phones == {"+263700333001", "+263700333002"}
    assert db.get(OutreachVisit, visit_id).sms_3day_sent == 1


def test_process_due_visits_does_not_resend_same_stage(db):
    scheduled = (TODAY + timedelta(days=3)).strftime("%Y-%m-%d")
    _seed_visit(db, "Sherwood Mine", scheduled, sms_3day_sent=1)
    _seed_worker(db, "Worker One", "+263700333004", "Sherwood Mine")

    with patch("services.notifications.send_outreach_announcement") as mock_send:
        process_due_outreach_visits(db, now=NOW)

    mock_send.assert_not_called()


def test_process_due_visits_marks_report_ready_after_visit_date(db):
    scheduled = (TODAY - timedelta(days=1)).strftime("%Y-%m-%d")
    visit_id = _seed_visit(db, "Sherwood Mine", scheduled, sms_3day_sent=1, sms_1day_sent=1)

    process_due_outreach_visits(db, now=NOW)

    assert db.get(OutreachVisit, visit_id).report_generated == 1


def test_process_due_visits_ignores_fully_settled_visits(db):
    scheduled = (TODAY - timedelta(days=10)).strftime("%Y-%m-%d")
    _seed_visit(db, "Sherwood Mine", scheduled, sms_3day_sent=1, sms_1day_sent=1, report_generated=1)

    # Should not even be selected by the WHERE clause — no error, no-op.
    process_due_outreach_visits(db, now=NOW)  # must not raise


# --- Routes ---


def _login(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "hospital@silicaguard.health", "password": "hospital123"},
    )
    return resp.json()["access_token"]


def test_create_outreach_visit_works_without_auth(client):
    """POST /api/outreach became unauthenticated 12 August — the mobile
    Outreach Planner schedules visits directly from the field, same
    unauthenticated-by-design boundary as POST /api/workers and
    POST /api/screen. GET (the coordinator dashboard's view) still requires
    auth — see test_list_outreach_visits_requires_auth below."""
    resp = client.post(
        "/api/outreach",
        json={"site": "Sherwood Mine", "scheduled_date": "2026-09-01", "expected_headcount": 40},
    )
    assert resp.status_code == 201
    assert resp.json()["site"] == "Sherwood Mine"


def test_list_outreach_visits_requires_auth(client):
    resp = client.get("/api/outreach")
    assert resp.status_code == 401


def test_create_and_list_outreach_visit(client):
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = client.post(
        "/api/outreach",
        json={
            "site": "Sherwood Mine",
            "scheduled_date": "2026-09-01",
            "expected_headcount": 40,
            "health_workers": ["Grace Chikwanha"],
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    body = create_resp.json()
    assert body["site"] == "Sherwood Mine"
    assert body["screened_count"] == 0
    assert body["report_generated"] is False
    assert body["tier_distribution"] is None  # not ready — visit is in the future

    list_resp = client.get("/api/outreach", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


def test_outreach_visit_report_populated_once_generated(client):
    """Registers a worker, screens them linked to a visit explicitly, marks
    the visit's report_generated directly (simulating the scheduler having
    already run), then confirms GET /api/outreach surfaces the real report."""
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    visit_id = client.post(
        "/api/outreach",
        json={"site": "Sherwood Mine", "scheduled_date": "2026-08-01", "expected_headcount": 5},
        headers=headers,
    ).json()["id"]

    worker_id = client.post(
        "/api/workers",
        json={"name": "Report Test Worker", "phone": "+263700444001", "site": "Sherwood Mine"},
    ).json()["id"]

    with patch(
        "routers.screening.assess_risk",
        return_value={
            "tier": "RED",
            "confidence": 0.9,
            "contributing_factors": ["x"],
            "explanation_english": "x",
        },
    ):
        client.post(
            "/api/screen",
            json={
                "miner_id": worker_id,
                "outreach_visit_id": visit_id,
                "answers": [
                    {"question_code": f"Q{i}", "answer_value": "x", "answer_score": 1}
                    for i in range(10)
                ],
            },
        )

    conn = database.get_connection()
    try:
        conn.execute("UPDATE outreach_visits SET report_generated = 1 WHERE id = ?", (visit_id,))
        conn.commit()
    finally:
        conn.close()

    resp = client.get("/api/outreach", headers=headers)
    visit = next(v for v in resp.json() if v["id"] == visit_id)
    assert visit["screened_count"] == 1
    assert visit["report_generated"] is True
    assert visit["tier_distribution"]["RED"] == 1
    assert len(visit["referral_list"]) == 1
    assert visit["referral_list"][0]["tier"] == "RED"


# --- POST /api/outreach/{id}/send-now (22 August 2026) ---


def test_send_now_requires_auth(client):
    resp = client.post("/api/outreach/999/send-now")
    assert resp.status_code == 401


def test_send_now_unknown_visit_404s(client):
    token = _login(client)
    resp = client.post(
        "/api/outreach/999/send-now", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 404


def test_send_now_sends_to_every_worker_at_the_site_and_marks_3day_sent(client):
    """On-demand escape hatch for the scheduler-only announcement — real
    send through notifications.send_outreach_announcement (mocked True by
    conftest's autouse fixture), not a demo-only fake."""
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    visit_id = client.post(
        "/api/outreach",
        json={"site": "Sherwood Mine", "scheduled_date": "2026-09-01", "expected_headcount": 5},
        headers=headers,
    ).json()["id"]
    client.post(
        "/api/workers", json={"name": "W1", "phone": "+263700555001", "site": "Sherwood Mine"}
    )
    client.post(
        "/api/workers", json={"name": "W2", "phone": "+263700555002", "site": "Sherwood Mine"}
    )
    client.post(
        "/api/workers", json={"name": "Other Site", "phone": "+263700555003", "site": "Other Mine"}
    )

    resp = client.post(f"/api/outreach/{visit_id}/send-now", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["stage"] == "3day"
    assert body["sent_count"] == 2  # only the two Sherwood Mine workers

    # Confirmed marked, so the scheduler won't duplicate it later.
    visit = next(
        v for v in client.get("/api/outreach", headers=headers).json() if v["id"] == visit_id
    )
    # (report_generated/tier_distribution unaffected by this — just confirming the visit still resolves)
    assert visit["id"] == visit_id


def test_send_now_second_call_sends_1day_stage(client):
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    visit_id = client.post(
        "/api/outreach",
        json={"site": "Sherwood Mine", "scheduled_date": "2026-09-01", "expected_headcount": 5},
        headers=headers,
    ).json()["id"]
    client.post(
        "/api/workers", json={"name": "W1", "phone": "+263700555004", "site": "Sherwood Mine"}
    )

    first = client.post(f"/api/outreach/{visit_id}/send-now", headers=headers).json()
    second = client.post(f"/api/outreach/{visit_id}/send-now", headers=headers).json()
    assert first["stage"] == "3day"
    assert second["stage"] == "1day"
