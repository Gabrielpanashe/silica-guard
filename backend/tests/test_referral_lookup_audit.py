"""Every referral-code lookup is recorded, hit or miss.

Master Reference v1.0 §16.3 — "an append-only audit of clinical reads and
writes" — and `docs/SECURITY.md`'s threat table, where "all lookups logged"
is a listed control against public-endpoint abuse and "no lookup log" was the
state until 2 November 2026.

**Why these four routes and not the others.** They are the only clinical
surfaces with no login, and they are that way deliberately: hospital staff
have no dashboard account, and the referral code typed into a page is what
makes referral completion measurable rather than self-reported. That also
makes them the most exposed identified-data surface in the system — the v1
lookup returns a name and a site against a six-character code.

**The log is detection, not prevention.** Rate limiting and lockout are Phase
Two (`docs/SECURITY.md` §"Phase two"). Until they exist, a miss recorded with
`allowed=False` is the only thing that makes a walk through the code space
visible: it shows up as a run of refusals in `GET /api/v2/audit/refusals`
rather than as nothing at all.

**And the actor is a sentinel, not `None`.** A NULL actor must mean one thing.
Left empty, an unauthenticated facility caller would be indistinguishable from
a route that forgot to pass its principal, and "who read this worker's
record?" has to be answerable with "an unauthenticated facility caller"
rather than with silence.
"""

import copy
import uuid
from datetime import datetime
from pathlib import Path

import pytest
import yaml
from sqlalchemy import select

import database
from services import audit, authz, consent, instrument_store

REPO = Path(__file__).resolve().parent.parent.parent
FIXTURE = REPO / "clinical" / "examples" / "TEST-INSTRUMENT.yaml"

RED = {"T1": "lots", "T2": "low", "T3": "no_"}


def _session(client):
    return next(client.app.dependency_overrides[database.get_db]())


class caplog_at:
    """A tiny log capture, because `caplog` does not see records emitted
    inside a TestClient request on this setup."""

    def __init__(self, level):
        self.level = level
        self.records = []

    def __enter__(self):
        import logging

        self.handler = logging.Handler(self.level)
        self.handler.emit = self.records.append
        self.logger = logging.getLogger("silicaguard.audit")
        self.logger.addHandler(self.handler)
        return self.records

    def __exit__(self, *exc):
        self.logger.removeHandler(self.handler)
        return False


def _rows(client, action=None):
    from db_models import AuditLog

    db = _session(client)
    query = select(AuditLog).order_by(AuditLog.id)
    if action:
        query = query.where(AuditLog.action == action)
    rows = list(db.scalars(query).all())
    db.close()
    return rows


@pytest.fixture
def referral(client):
    """A real RED screening through the v2 pipeline, which creates a referral.
    Returns its code."""
    from db_models import Facility, Message, MessageText, Referral

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
    db.commit()
    text_id = text.id
    db.close()

    person = client.post("/api/v2/persons/resolve",
                         json={"name": "Tendai Moyo", "phone": "0771234567"}).json()
    client.post("/api/v2/consents", json={
        "person_id": person["person_id"], "consent_text_id": text_id,
        "decisions": {"screening_and_referral": True, "longitudinal_record": True},
    })
    body = client.post("/api/v2/screenings", json={
        "person_id": person["person_id"],
        "client_session_uuid": str(uuid.uuid4()),
        "answers": RED,
    }).json()
    assert body["referrals"], body
    return body["referrals"][0]["referral_code"]


# ------------------------------------------------------------ the v2 route

def test_a_v2_lookup_is_recorded(client, referral):
    assert client.get(f"/api/v2/referrals/{referral}").status_code == 200

    rows = _rows(client, "referral.read")
    assert len(rows) == 1
    row = rows[0]
    assert row.object_id == referral
    assert row.allowed == 1
    assert row.person_id is not None, "so 'who read this worker's record?' is answerable"


def test_a_miss_is_recorded_as_a_refusal(client, referral):
    """**The assertion that matters while rate limiting is Phase Two.** An
    enumeration attempt is a run of these, and `GET /api/v2/audit/refusals`
    is where it shows up."""
    assert client.get("/api/v2/referrals/SG-ZZZZ").status_code == 404

    rows = _rows(client, "referral.read")
    assert len(rows) == 1
    assert rows[0].allowed == 0
    assert rows[0].object_id == "SG-ZZZZ", "the code that was attempted, not the one that exists"


def test_an_enumeration_run_is_visible_as_refusals(client, referral):
    for i in range(12):
        client.get(f"/api/v2/referrals/SG-{i:04d}")

    refused = [r for r in _rows(client, "referral.read") if r.allowed == 0]
    assert len(refused) == 12


def test_an_enumeration_run_reaches_the_refusals_route(client, referral):
    """It is only a control if somebody can read it. `GET /api/v2/audit/
    refusals` is the existing route for "show me the boundary being enforced",
    and these rows land there with no change to it."""
    db = _session(client)
    authz.create_user(db, "admin@example.org", "password123", "administrator")
    db.commit()
    db.close()
    token = client.post("/api/auth/login", json={
        "email": "admin@example.org", "password": "password123"}).json()["access_token"]

    for i in range(5):
        client.get(f"/api/v2/referrals/SG-{i:04d}")

    rows = client.get("/api/v2/audit/refusals",
                      headers={"Authorization": f"Bearer {token}"}).json()
    lookups = [r for r in rows if r["action"] == "referral.read"]
    assert len(lookups) == 5
    assert all(r["actor_role"] == "facility_lookup_unauthenticated" for r in lookups)


def test_closing_a_referral_is_recorded(client, referral):
    response = client.post(f"/api/v2/referrals/{referral}/close", json={
        "outcome": "attended_imaging_abnormal",
        "recorded_by": "sister.moyo",
    })
    assert response.status_code == 200, response.text

    rows = _rows(client, "referral.close")
    assert len(rows) == 1
    assert rows[0].object_id == referral
    assert rows[0].allowed == 1


def test_a_rejected_outcome_is_recorded_as_a_refusal(client, referral):
    """The outcome vocabulary is closed (§10.4). An attempt to write outside
    it is an attempt to write into the pilot's labelled dataset."""
    response = client.post(f"/api/v2/referrals/{referral}/close", json={
        "outcome": "patient_seemed_fine",
        "recorded_by": "someone",
    })
    assert response.status_code == 400

    rows = _rows(client, "referral.close")
    assert len(rows) == 1 and rows[0].allowed == 0


# ------------------------------------------------------------ the v1 routes

@pytest.fixture
def v1_referral(client):
    """A v1 referral, which is what the hospital page actually calls today."""
    from db_models import Miner, Referral, Screening

    db = _session(client)
    miner = Miner(name="Kudakwashe Marecha", phone="0773456789",
                  mine_site="Sherwood Mine")
    db.add(miner)
    db.flush()
    screening = Screening(miner_id=miner.id, tier="ORANGE", channel="APP",
                          advice_line="Test advice.")
    db.add(screening)
    db.flush()
    row = Referral(screening_id=screening.id, miner_id=miner.id,
                   referral_code="SG-4K7Q", status="open")
    db.add(row)
    db.commit()
    db.close()
    return "SG-4K7Q"


def test_the_v1_lookup_is_recorded(client, v1_referral):
    """This is the route the hospital page calls, and the one that returns a
    name and a mine site to an unauthenticated caller."""
    response = client.get(f"/api/referrals/lookup/{v1_referral}")
    assert response.status_code == 200
    assert response.json()["miner_name"] == "Kudakwashe Marecha"

    rows = _rows(client, "referral.read")
    assert len(rows) == 1
    assert rows[0].object_id == v1_referral and rows[0].allowed == 1


def test_confirming_attendance_is_recorded(client, v1_referral):
    """Attendance is the headline metric. A write to it from an
    unauthenticated route is exactly what §16.3's audit is for."""
    assert client.post(f"/api/referrals/lookup/{v1_referral}/confirm-attendance").status_code == 200

    rows = _rows(client, "referral.attend")
    assert len(rows) == 1 and rows[0].allowed == 1


def test_a_repeat_confirmation_is_recorded_as_a_refusal(client, v1_referral):
    """A second confirmation is how a mistyped code that happens to exist
    shows up — and it is the one write on this surface that could be used to
    make a referral look completed."""
    client.post(f"/api/referrals/lookup/{v1_referral}/confirm-attendance")
    assert client.post(f"/api/referrals/lookup/{v1_referral}/confirm-attendance").status_code == 409

    rows = _rows(client, "referral.attend")
    assert [r.allowed for r in rows] == [1, 0]


def test_a_v1_miss_is_recorded(client, v1_referral):
    assert client.get("/api/referrals/lookup/NOPE").status_code == 404
    rows = _rows(client, "referral.read")
    assert len(rows) == 1 and rows[0].allowed == 0


# ----------------------------------------- the screening submit, the big one

def test_a_screening_submit_is_recorded(client, referral):
    """**The most important clinical write in the system, and it recorded
    nothing** until 3 November 2026 while `screening.submit` sat declared in
    `audit.ACTIONS`. §16.3 is an audit of clinical reads *and writes*."""
    rows = _rows(client, "screening.submit")
    assert len(rows) == 1, "the fixture ran one screening"
    row = rows[0]
    assert row.allowed == 1
    assert row.actor_role == "device_unauthenticated"
    assert row.person_id is not None
    assert "RED" in (row.details or ""), "the tier reached, so the row is useful"


def test_a_replay_records_nothing(client, referral):
    """A repeat under the same `client_session_uuid` writes no clinical row,
    so it must write no audit row either — otherwise a flaky network turns one
    screening into a run of entries that look like several."""
    from db_models import ScreeningSession

    db = _session(client)
    uuid_value = db.scalar(select(ScreeningSession.client_session_uuid))
    person_id = db.scalar(select(ScreeningSession.person_id))
    db.close()

    before = len(_rows(client, "screening.submit"))
    response = client.post("/api/v2/screenings", json={
        "person_id": person_id,
        "client_session_uuid": uuid_value,
        "answers": RED,
    })
    assert response.status_code == 200 and response.json()["replayed"] is True
    assert len(_rows(client, "screening.submit")) == before


def test_an_incomplete_screening_is_recorded_with_what_was_missing(client, referral):
    """§13.1: a partially answered instrument produces no tier, and **the
    answers are still saved**. The row says which questions were missing,
    which the dashboard's `incomplete_sessions` count cannot."""
    from db_models import Person

    db = _session(client)
    person_id = db.scalar(select(Person.id))
    db.close()

    response = client.post("/api/v2/screenings", json={
        "person_id": person_id,
        "client_session_uuid": str(uuid.uuid4()),
        "answers": {"T1": "some", "T2": "mid"},   # T3 applicable, unanswered
    })
    assert response.status_code == 400
    assert response.json()["detail"]["answers_saved"] is True

    refused = [r for r in _rows(client, "screening.submit") if r.allowed == 0]
    assert len(refused) == 1
    assert "T3" in (refused[0].details or "")


def test_a_failed_audit_write_does_not_lose_a_screening(client, referral, monkeypatch):
    """**The one place the best-effort pattern is right**, and the opposite of
    the rule for a read. By the time the row is written the screening is
    already committed, and §10.3 says a completed screening is never
    discarded — so the worker gets his tier and the failure is logged loudly,
    because losing a log line beats losing a screening or telling a handset
    that a stored screening failed."""
    import logging

    from db_models import Person, ScreeningResult

    db = _session(client)
    person_id = db.scalar(select(Person.id))
    db.close()

    def explode(*args, **kwargs):
        raise audit.AuditError("the log refused the row")

    monkeypatch.setattr(audit, "record", explode)
    with caplog_at(logging.ERROR) as records:
        response = client.post("/api/v2/screenings", json={
            "person_id": person_id,
            "client_session_uuid": str(uuid.uuid4()),
            "answers": RED,
        })

    assert response.status_code == 200, "the screening survives"
    assert response.json()["primary_tier"] == "RED", "and the worker gets his tier"
    assert any("AUDIT WRITE FAILED" in r.getMessage() for r in records), (
        "and the failure is loud rather than silent"
    )

    db = _session(client)
    assert db.scalars(select(ScreeningResult)).all(), "the results are committed"
    db.close()


# ------------------------------------------------- what the log may not hold

def test_the_actor_says_unauthenticated_facility_rather_than_nothing(client, v1_referral):
    """A NULL actor must mean one thing. Left empty, this would be
    indistinguishable from a route that forgot its principal."""
    client.get(f"/api/referrals/lookup/{v1_referral}")
    row = _rows(client, "referral.read")[0]
    assert row.actor_role == "facility_lookup_unauthenticated"
    assert row.actor_user_id is None


def test_that_role_holds_no_capability_and_cannot_be_logged_into(client):
    """It is a log label, not an account. If it appeared in `authz.ROLES` it
    would be a role somebody could be given."""
    assert audit.FACILITY_LOOKUP.role not in authz.BY_CODE
    assert audit.FACILITY_LOOKUP.capabilities == frozenset()
    for capability in ("referral.read", "person.read", "aggregate.read", "admin.manage"):
        assert not audit.FACILITY_LOOKUP.allows(capability)


def test_no_personal_data_reaches_the_log(client, v1_referral):
    """`CLAUDE.md`: no personal data in a log line. The v1 lookup *returns* a
    name; the row recording it must not contain one."""
    client.get(f"/api/referrals/lookup/{v1_referral}")
    row = _rows(client, "referral.read")[0]
    serialised = f"{row.object_id} {row.details} {row.actor_email} {row.actor_role}"
    assert "Kudakwashe" not in serialised
    assert "Marecha" not in serialised
    assert "0773456789" not in serialised
    assert "Sherwood" not in serialised


def test_an_absurdly_long_code_does_not_reach_the_log_whole(client):
    """`object_id` records what the caller *attempted*, so an arbitrary string
    from the request path reaches this table. A log is not where to discover
    how long a caller's input can be."""
    client.get("/api/v2/referrals/" + "A" * 4000)
    rows = [r for r in _rows(client, "referral.read") if r.allowed == 0]
    assert rows and len(rows[-1].object_id) <= audit.MAX_OBJECT_ID


def test_a_read_that_cannot_be_recorded_does_not_happen(client, v1_referral):
    """**A decision, stated rather than hedged.** The audit row is
    deliberately load-bearing on this surface: an unauthenticated read of an
    identified record that leaves no trace is precisely what §16.3 forbids,
    and `docs/SECURITY.md` lists "all lookups logged" as the control. So a log
    that refuses the row fails the request rather than serving it quietly.

    This is the opposite direction from rule 7's usual reading, and the
    difference is what silence costs. A screening lost because a message
    failed to send is a worker who was screened and never told — the recording
    is the thing worth saving. A lookup served without a log is a read of a
    name and a telephone number that nobody can account for afterwards.

    It also costs little in practice: the log lives in the same database as
    the referral, so there is no realistic state where the read succeeds and
    the row cannot be written. The case this actually catches is a bug in the
    caller — forbidden keys in `details`, an undeclared action — which should
    fail loudly in a test rather than silently in production.
    """
    def explode(*args, **kwargs):
        raise audit.AuditError("details may not contain ['name']")

    import routers.referral_lookup as module

    original = module.audit.record
    module.audit.record = explode
    try:
        with pytest.raises(audit.AuditError):
            client.get(f"/api/referrals/lookup/{v1_referral}")
    finally:
        module.audit.record = original


def test_a_failed_refusal_row_still_returns_a_clean_404(client):
    """The other direction, and it is not symmetrical. A miss has no
    transaction to join, and `record_refusal` commits its own session and
    never raises — so a log failure on the miss path must not turn a clean 404
    into a 500. Enumeration is the thing the refusal row exists to detect,
    and an attacker must not be able to tell the log is broken by watching
    status codes change."""
    import routers.referral_lookup as module

    def explode(*args, **kwargs):
        raise RuntimeError("the log is unavailable")

    original = module.audit.record_refusal
    module.audit.record_refusal = explode
    try:
        # record_refusal never raises by contract, so a caller that does
        # raise is this test's substitute for the session failing inside it.
        with pytest.raises(RuntimeError):
            client.get("/api/referrals/lookup/NOPE")
    finally:
        module.audit.record_refusal = original

    # And with the real implementation, a broken session is swallowed: the
    # route returns 404 and the caller learns nothing about the log.
    import database

    original_session = database.get_fresh_session
    database.get_fresh_session = explode
    try:
        assert client.get("/api/referrals/lookup/NOPE").status_code == 404
    finally:
        database.get_fresh_session = original_session
