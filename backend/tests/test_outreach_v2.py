"""Outreach visits, with what each one actually produced.

Master Reference v1.0 §13.3, and the last entry on the plan's §5 list of the
v2 surface.

Two things carry the weight:

  **The count comes from the sessions, not from the column.**
  `outreach_visits.screened_count` is incremented by the screening route,
  which makes it a running tally rather than a fact. Reporting both, and
  letting a divergence show, is the point — hiding it behind whichever number
  a caller happens to read is how an operational metric quietly stops meaning
  anything.

  **Counts are per condition AND tier.** A single tier count is ambiguous the
  day a second condition exists, which is the same reason the v2 dashboard
  reports the pair.
"""

import copy
import uuid
from datetime import date, datetime
from pathlib import Path

import pytest
import yaml
from sqlalchemy import select

import database
from services import authz, consent, instrument_store

REPO = Path(__file__).resolve().parent.parent.parent
FIXTURE = REPO / "clinical" / "examples" / "TEST-INSTRUMENT.yaml"

BASELINE = {"T1": "none", "T2": "low"}
OVERRIDE = {"T1": "lots", "T2": "low", "T3": "no_"}


def _session(client):
    return next(client.app.dependency_overrides[database.get_db]())


def _coordinator(client):
    db = _session(client)
    authz.create_user(db, "d@example.org", "password123", "district_coordinator",
                      district="Kwekwe")
    db.commit()
    db.close()
    r = client.post("/api/auth/login",
                    json={"email": "d@example.org", "password": "password123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def visit(client):
    """An approved instrument, a consented person, an outreach visit, and
    three screenings linked to it. Returns the visit id."""
    from db_models import Facility, Message, MessageText, OutreachVisit

    doc = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    approved = copy.deepcopy(doc)
    approved.update(status="approved", approved_by="Clinical Lead",
                    approved_at="2026-11-01")

    db = _session(client)
    instrument_store.load(db, approved)
    db.add(Facility(name="Test District Hospital", level="district"))
    message = Message(code="consent.core.v1", version=1, channel="app",
                      status="approved", approved_by="Clinical Lead",
                      approved_at=datetime(2026, 11, 1), purpose="Test wording.")
    db.add(message)
    db.flush()
    db.add(MessageText(message_id=message.id, language="en", text_value="TEST."))
    text = consent.register_text(db, "CORE", message.code, status="approved",
                                 approved_by="Clinical Lead",
                                 approved_at=datetime(2026, 11, 1))
    v = OutreachVisit(site="Globe & Phoenix", scheduled_date=date(2026, 11, 10),
                      expected_headcount=40, health_workers="sister.moyo")
    db.add(v)
    db.commit()
    text_id, visit_id = text.id, v.id
    db.close()

    person = client.post("/api/v2/persons/resolve",
                         json={"name": "Tendai Moyo", "phone": "0771234567"}).json()
    client.post("/api/v2/consents", json={
        "person_id": person["person_id"], "consent_text_id": text_id,
        "decisions": {"screening_and_referral": True, "longitudinal_record": True},
    })
    for answers in (BASELINE, BASELINE, OVERRIDE):
        client.post("/api/v2/screenings", json={
            "person_id": person["person_id"],
            "client_session_uuid": str(uuid.uuid4()),
            "answers": answers,
            "outreach_visit_id": visit_id,
        })
    return visit_id


# ---------------------------------------------------------- the rollup

def test_a_visit_reports_what_it_produced(client, visit):
    headers = _coordinator(client)
    body = client.get(f"/api/v2/outreach/{visit}", headers=headers).json()

    assert body["site"] == "Globe & Phoenix"
    assert body["expected_headcount"] == 40
    assert body["scheduled_date"] == "2026-11-10", (
        "a Date column serves a date; v1 serves this field the same way"
    )
    assert body["sessions"] == 3
    assert body["people"] == 1
    assert body["by_condition_and_tier"], "a visit reports outcomes, not just a headcount"
    assert body["referrals"] >= 1, "the RED screening referred"


def test_counts_are_per_condition_and_tier(client, visit):
    """The same reason as the dashboard: a single tier count is ambiguous the
    day a second condition exists."""
    headers = _coordinator(client)
    rows = client.get(f"/api/v2/outreach/{visit}", headers=headers).json()["by_condition_and_tier"]
    assert {r["condition"] for r in rows} <= {"condition_a", "condition_b"}
    assert all(r["tier"] in ("GREEN", "YELLOW", "ORANGE", "RED") for r in rows)
    assert sum(r["count"] for r in rows) >= 3


def test_the_session_count_comes_from_the_sessions_not_the_column(client, visit):
    """**The assertion that matters.** `screened_count` is a running tally the
    screening route increments; a session reassigned elsewhere leaves it
    wrong. Both numbers are reported so a divergence shows."""
    from db_models import OutreachVisit

    db = _session(client)
    row = db.get(OutreachVisit, visit)
    row.screened_count = 99          # as if the tally had drifted
    db.commit()
    db.close()

    body = client.get(f"/api/v2/outreach/{visit}", headers=_coordinator(client)).json()
    assert body["sessions"] == 3, "counted from the linked sessions"
    assert body["recorded_screened_count"] == 99, "and the stored tally is shown too"


def test_incomplete_sessions_are_counted(client, visit):
    """A visit generating many is a usability finding, and invisible if
    incomplete sessions are simply absent from the tier counts."""
    db = _session(client)
    from db_models import Person

    person_id = db.scalar(select(Person.id))
    db.close()

    client.post("/api/v2/screenings", json={
        "person_id": person_id,
        "client_session_uuid": str(uuid.uuid4()),
        "answers": {"T1": "some", "T2": "mid"},   # T3 applicable, missing
        "outreach_visit_id": visit,
    })
    body = client.get(f"/api/v2/outreach/{visit}", headers=_coordinator(client)).json()
    assert body["incomplete_sessions"] == 1
    assert body["sessions"] == 4


def test_announcement_state_is_reported(client, visit):
    body = client.get(f"/api/v2/outreach/{visit}", headers=_coordinator(client)).json()
    assert body["announcements_sent"] == {"three_day": False, "one_day": False}
    assert body["report_generated"] is False


def test_a_visit_with_no_screenings_reports_zeroes(client):
    from db_models import OutreachVisit

    db = _session(client)
    v = OutreachVisit(site="Empty Working", scheduled_date=date(2026, 12, 1))
    db.add(v)
    db.commit()
    vid = v.id
    db.close()

    body = client.get(f"/api/v2/outreach/{vid}", headers=_coordinator(client)).json()
    assert body["sessions"] == 0 and body["people"] == 0
    assert body["by_condition_and_tier"] == [] and body["referrals"] == 0


def test_the_list_returns_every_visit(client, visit):
    rows = client.get("/api/v2/outreach", headers=_coordinator(client)).json()
    assert len(rows) >= 1
    assert any(r["visit_id"] == visit for r in rows)


def test_an_unknown_visit_is_a_404(client):
    assert client.get("/api/v2/outreach/9999",
                      headers=_coordinator(client)).status_code == 404


# ----------------------------------------------------------- the boundary

def test_the_routes_need_a_token(client, visit):
    assert client.get("/api/v2/outreach").status_code == 401
    assert client.get(f"/api/v2/outreach/{visit}").status_code == 401


def test_a_role_without_aggregate_read_is_refused(client, visit):
    """A village health worker screens; they do not read a district's visit
    rollup (§16.3)."""
    db = _session(client)
    authz.create_user(db, "v@example.org", "password123", "village_health_worker",
                      site_ids=[3])
    db.commit()
    db.close()
    r = client.post("/api/auth/login",
                    json={"email": "v@example.org", "password": "password123"})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/v2/outreach", headers=headers).status_code == 403


def test_the_rollup_names_no_individual(client, visit):
    """It sits behind `aggregate.read`, the capability a national stakeholder
    holds while being refused every identified record."""
    body = client.get(f"/api/v2/outreach/{visit}", headers=_coordinator(client))
    serialised = str(body.json())
    assert "Tendai" not in serialised
    assert "771234567" not in serialised


def test_a_read_is_audited(client, visit):
    from db_models import AuditLog

    client.get(f"/api/v2/outreach/{visit}", headers=_coordinator(client))
    db = _session(client)
    rows = db.scalars(
        select(AuditLog).where(AuditLog.object_type == "outreach")
    ).all()
    assert rows and rows[-1].actor_email == "d@example.org"
    db.close()


def test_there_is_no_v2_write_route(client, visit):
    """Planning and announcements stay on v1 until the adapter: duplicating a
    write path is how two of them start disagreeing about the same row."""
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert client.request(method, "/api/v2/outreach").status_code in (401, 405)
