"""The v2 read surface: the active instrument, a worker's history, the day.

Master Reference v1.0 §10.1, §8.1, §16.3. Three things carry the weight:

  **The instrument is served whole.** A channel-filtered subset would be the
  obvious optimisation and would silently disarm any safety rule of the form
  `{"unknown": "Q"}` — the §12.2 item 10 protection that stops an unanswered
  red flag reading as a negative. The `channel` parameter annotates rather
  than filters, so the device's interpreter and the server's are given
  identical input, which is the only way "channels are equivalent" can be
  guaranteed rather than asserted.

  **A session reports a list of results, not a tier.** The v1 dashboard
  counts tiers, which works only while there is one condition.

  **Both clinical reads need a capability and write an audit row**, because
  §16.3 requires every clinical read to be recorded.
"""

import copy
import uuid
from datetime import datetime
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


def _login(client, email, password):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _user(client, email, role, **scope):
    db = _session(client)
    authz.create_user(db, email, "password123", role, **scope)
    db.commit()
    db.close()
    return _login(client, email, "password123")


@pytest.fixture
def loaded(client):
    """An approved instrument, a facility, a consented person, and three
    screenings. Returns the participant code."""
    from db_models import Facility, Message, MessageText

    doc = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    approved = copy.deepcopy(doc)
    approved.update(status="approved", approved_by="Clinical Lead", approved_at="2026-11-01")

    db = _session(client)
    instrument_store.load(db, approved)
    db.add(Facility(name="Test District Hospital", level="district"))
    message = Message(
        code="consent.core.v1", version=1, channel="app", status="approved",
        approved_by="Clinical Lead", approved_at=datetime(2026, 11, 1),
        purpose="Stands in for approved consent wording.",
    )
    db.add(message)
    db.flush()
    db.add(MessageText(message_id=message.id, language="en", text_value="TEST wording."))
    text = consent.register_text(
        db, "CORE", message.code, status="approved",
        approved_by="Clinical Lead", approved_at=datetime(2026, 11, 1),
    )
    db.commit()
    text_id = text.id
    db.close()

    person = client.post(
        "/api/v2/persons/resolve", json={"name": "Tendai Moyo", "phone": "0771234567"}
    ).json()
    client.post("/api/v2/consents", json={
        "person_id": person["person_id"], "consent_text_id": text_id,
        "decisions": {"screening_and_referral": True, "longitudinal_record": True},
    })

    for answers in (BASELINE, BASELINE, OVERRIDE):
        client.post("/api/v2/screenings", json={
            "person_id": person["person_id"],
            "client_session_uuid": str(uuid.uuid4()),
            "answers": answers,
        })
    return person["participant_code"]


# -------------------------------------------------- the instrument, whole

def test_the_active_instrument_is_served_whole(client, loaded):
    """**The assertion that matters most here.** Every question stays in the
    document, including ones this channel does not ask, because a question
    absent from the document can never be `unknown` — and a safety rule of
    the form `{"unknown": "Q"}` would stop firing."""
    body = client.get("/api/v2/instrument/active?channel=ussd").json()
    codes = {q["code"] for q in body["instrument"]["questions"]}
    assert codes == {"T1", "T2", "T3"}, "T3 is app-only but must still be present"
    assert body["instrument"]["safety_rules"]
    assert any(
        rule["predicate"].get("unknown") for rule in body["instrument"]["safety_rules"]
    ), "the unknown-escalation rule must survive the trip"


def test_the_channel_annotates_rather_than_filters(client, loaded):
    """T3 carries `channels: [app]`, so USSD does not ask it — but the rules
    still see it."""
    app_body = client.get("/api/v2/instrument/active?channel=app").json()
    ussd_body = client.get("/api/v2/instrument/active?channel=ussd").json()

    assert set(app_body["channel_questions"]) == {"T1", "T2", "T3"}
    assert set(ussd_body["channel_questions"]) == {"T1", "T2"}
    # Same document either way.
    assert app_body["instrument"] == ussd_body["instrument"]


def test_the_document_is_the_shape_the_rules_engine_consumes(client, loaded):
    """Which is what lets the device's JavaScript interpreter be a port rather
    than a reimplementation."""
    from services.rules_engine import Screening, classify, primary_tier

    body = client.get("/api/v2/instrument/active?channel=app").json()
    results = classify(body["instrument"], Screening(answers=BASELINE))
    assert results and primary_tier(results) in ("GREEN", "YELLOW", "ORANGE", "RED")


def test_the_response_names_the_ruleset_version(client, loaded):
    """The value stamped on every session and result row, so a device can
    record what it screened against."""
    body = client.get("/api/v2/instrument/active").json()
    assert body["ruleset_version"] == f"{body['code']}-v{body['version']}"


def test_only_an_approved_version_is_served(client):
    """A device must never be handed a draft to screen against."""
    doc = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    draft = copy.deepcopy(doc)
    draft["status"] = "draft"
    db = _session(client)
    instrument_store.load(db, draft)
    db.commit()
    db.close()

    response = client.get("/api/v2/instrument/active")
    assert response.status_code == 404
    assert "approved" in response.json()["detail"]


def test_no_instrument_at_all_is_a_clean_404(client):
    """The state until version one lands, and correct rather than a fault."""
    response = client.get("/api/v2/instrument/active")
    assert response.status_code == 404
    assert "Clinical Lead's deliverable" in response.json()["detail"]


def test_the_instrument_is_never_guessed_when_several_exist(client, loaded):
    doc = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    second = copy.deepcopy(doc)
    second.update(code="OTHER-INSTRUMENT", status="approved",
                  approved_by="Clinical Lead", approved_at="2026-11-01")
    db = _session(client)
    instrument_store.load(db, second)
    db.commit()
    db.close()

    response = client.get("/api/v2/instrument/active")
    assert response.status_code == 400
    assert "chosen deliberately" in response.json()["detail"]
    assert client.get("/api/v2/instrument/active?code=TEST-INSTRUMENT").status_code == 200


def test_an_unknown_channel_is_a_400(client, loaded):
    assert client.get("/api/v2/instrument/active?channel=whatsapp").status_code == 400


def test_the_instrument_route_needs_no_token(client, loaded):
    """Offline is the normal case: the application fetches this before an
    outreach visit and it never logs in."""
    assert client.get("/api/v2/instrument/active").status_code == 200


def test_the_versions_route_answers_which_instrument_this_server_serves(client, loaded):
    """Provenance without database access — the question §10.1 says every
    clinical output must be traceable to."""
    rows = client.get("/api/v2/instrument/versions").json()
    assert rows and rows[0]["code"] == "TEST-INSTRUMENT"
    assert rows[0]["status"] == "approved"
    assert "questions" not in rows[0], "provenance only, no clinical content"


# ------------------------------------------------------ a worker's history

def test_a_history_reports_results_per_condition(client, loaded):
    headers = _user(client, "v@example.org", "village_health_worker", site_ids=[3])
    body = client.get(f"/api/v2/persons/{loaded}/sessions", headers=headers).json()

    assert body["session_count"] == 3
    assert body["longitudinal_consent"] is True
    assert len(body["sessions"]) == 3
    for session in body["sessions"]:
        assert session["results"], "a session reports a list, not a tier"
        assert session["instrument_code"] == "TEST-INSTRUMENT"
        assert session["primary_tier"]


def test_the_history_is_newest_first(client, loaded):
    headers = _user(client, "v@example.org", "village_health_worker", site_ids=[3])
    sessions = client.get(f"/api/v2/persons/{loaded}/sessions", headers=headers).json()["sessions"]
    ids = [s["session_id"] for s in sessions]
    assert ids == sorted(ids, reverse=True)


def test_the_history_carries_the_referral_codes(client, loaded):
    headers = _user(client, "v@example.org", "village_health_worker", site_ids=[3])
    sessions = client.get(f"/api/v2/persons/{loaded}/sessions", headers=headers).json()["sessions"]
    assert any(s["referral_codes"] for s in sessions), "the RED screening referred"


def test_the_history_shows_the_longitudinal_link(client, loaded):
    headers = _user(client, "v@example.org", "village_health_worker", site_ids=[3])
    sessions = client.get(f"/api/v2/persons/{loaded}/sessions", headers=headers).json()["sessions"]
    assert any(s["previous_session_id"] for s in sessions)


def test_a_history_read_is_audited(client, loaded):
    """§16.3: every clinical read of an identified person writes a row."""
    from db_models import AuditLog

    headers = _user(client, "v@example.org", "village_health_worker", site_ids=[3])
    client.get(f"/api/v2/persons/{loaded}/sessions", headers=headers)

    db = _session(client)
    rows = db.scalars(
        select(AuditLog).where(AuditLog.action == "screening.read")
    ).all()
    assert rows and rows[-1].actor_email == "v@example.org"
    assert rows[-1].person_id
    db.close()


def test_a_history_follows_a_merge(client, loaded):
    """A card printed before a merge still finds the history the merge
    joined — which is the reason to perform one."""
    headers = _user(client, "admin@example.org", "administrator")
    other = client.post(
        "/api/v2/persons/resolve", json={"name": "Tendai Moyo", "phone": "0789999999"}
    ).json()

    db = _session(client)
    from db_models import Person
    winner = db.scalar(select(Person).where(Person.participant_code == loaded))
    winner_id = winner.id
    db.close()

    client.post("/api/v2/persons/merges", json={
        "winner_person_id": winner_id,
        "loser_person_id": other["person_id"],
        "merged_by": "clerk",
    }, headers=headers)

    worker = _user(client, "v@example.org", "village_health_worker", site_ids=[3])
    body = client.get(
        f"/api/v2/persons/{other['participant_code']}/sessions", headers=worker
    ).json()
    assert body["person_id"] == winner_id


@pytest.mark.parametrize("role", [
    "national_stakeholder",
    "researcher",
    "programme_sponsor",
    "administrator",
])
def test_roles_that_may_not_read_a_record_are_refused_the_history(client, loaded, role):
    """§16.3's "cannot see" column, at the route rather than in the unit
    tests. An administrator is refused too: administrative access is not a
    licence to read records."""
    scope = {}
    if role == "programme_sponsor":
        from db_models import Programme

        db = _session(client)
        db.add(Programme(code="P1", name="Cohort one", kind="employer"))
        db.commit()
        scope = {"programme_id": db.scalar(select(Programme.id))}
        db.close()
    headers = _user(client, f"{role}@example.org", role, **scope)
    response = client.get(f"/api/v2/persons/{loaded}/sessions", headers=headers)
    assert response.status_code == 403


def test_the_history_needs_a_token(client, loaded):
    assert client.get(f"/api/v2/persons/{loaded}/sessions").status_code == 401


def test_an_unknown_card_is_a_404(client, loaded):
    headers = _user(client, "v@example.org", "village_health_worker", site_ids=[3])
    assert client.get("/api/v2/persons/ZZZZZZ/sessions", headers=headers).status_code == 404


# ------------------------------------------------------------- the day

def test_the_dashboard_counts_per_condition_and_tier(client, loaded):
    """**The shape change.** `high_risk_count` becomes ambiguous the day
    tuberculosis is added — high risk of what? — so v2 reports the pair."""
    headers = _user(client, "d@example.org", "district_coordinator", district="Kwekwe")
    body = client.get("/api/v2/dashboard/today", headers=headers).json()

    assert body["sessions"] == 3
    assert body["people"] == 1
    assert body["by_condition_and_tier"]
    for row in body["by_condition_and_tier"]:
        assert row["condition"] in ("condition_a", "condition_b")
        assert row["tier"] in ("GREEN", "YELLOW", "ORANGE", "RED")
        assert row["count"] >= 1


def test_the_dashboard_counts_referrals_by_state(client, loaded):
    headers = _user(client, "d@example.org", "district_coordinator", district="Kwekwe")
    body = client.get("/api/v2/dashboard/today", headers=headers).json()
    assert body["referrals_raised"] >= 1
    assert body["referrals_open_now"] >= 1
    assert body["referrals_attended"] == 0
    assert body["referrals_closed_with_outcome"] == 0


def test_referral_counts_are_scoped_to_the_period_except_the_backlog(client, loaded):
    """**The correction this replaced.** Until 2 November 2026 all three
    referral numbers counted every referral in the database, so
    `/dashboard/today` reported an all-time figure under a `period: "today"`
    label. Each is now counted by its own timestamp — and the backlog
    deliberately is not, because a referral still open from three weeks ago
    still needs chasing."""
    from datetime import datetime, timedelta, timezone

    from db_models import Referral

    db = _session(client)
    referrals = list(db.scalars(select(Referral)).all())
    assert referrals, "the RED screening referred"
    long_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=90)
    for referral in referrals:
        referral.created_at = long_ago
        referral.attended_at = long_ago
    db.commit()
    db.close()

    body = client.get("/api/v2/dashboard/today", headers=_user(
        client, "d2@example.org", "district_coordinator", district="Kwekwe")).json()

    assert body["referrals_raised"] == 0, "raised 90 days ago, not today"
    assert body["referrals_attended"] == 0, "attended 90 days ago, not today"
    assert body["referrals_open_now"] >= 1, (
        "still open, so still on the worklist regardless of the period"
    )


def test_the_dashboard_reports_worsening(client, loaded):
    headers = _user(client, "d@example.org", "district_coordinator", district="Kwekwe")
    body = client.get("/api/v2/dashboard/today", headers=headers).json()
    assert body["worsened"] >= 0


def test_incomplete_sessions_are_counted_rather_than_hidden(client, loaded):
    """A session that produced no result is absent from every tier count, so
    without a separate number a channel that keeps producing them looks like
    a channel nobody is using."""
    db = _session(client)
    from db_models import Person
    person = db.scalar(select(Person).where(Person.participant_code == loaded))
    person_id = person.id
    db.close()

    client.post("/api/v2/screenings", json={
        "person_id": person_id,
        "client_session_uuid": str(uuid.uuid4()),
        "answers": {"T1": "some", "T2": "mid"},  # T3 applicable and missing
    })

    headers = _user(client, "d@example.org", "district_coordinator", district="Kwekwe")
    body = client.get("/api/v2/dashboard/today", headers=headers).json()
    assert body["incomplete_sessions"] == 1
    assert body["sessions"] == 4


def test_the_dashboard_returns_no_identified_record(client, loaded):
    """It sits behind `aggregate.read`, the capability a national stakeholder
    holds while being refused every identified record."""
    headers = _user(client, "n@example.org", "national_stakeholder")
    body = client.get("/api/v2/dashboard/today", headers=headers)
    assert body.status_code == 200
    serialised = str(body.json())
    assert "Tendai" not in serialised
    assert "771234567" not in serialised
    assert loaded not in serialised


def test_a_dashboard_read_is_audited(client, loaded):
    from db_models import AuditLog

    headers = _user(client, "n@example.org", "national_stakeholder")
    client.get("/api/v2/dashboard/week", headers=headers)

    db = _session(client)
    rows = db.scalars(select(AuditLog).where(AuditLog.action == "aggregate.read")).all()
    assert rows and rows[-1].actor_email == "n@example.org"
    db.close()


@pytest.mark.parametrize("period", ["today", "week", "month"])
def test_every_period_works(client, loaded, period):
    headers = _user(client, "n@example.org", "national_stakeholder")
    assert client.get(f"/api/v2/dashboard/{period}", headers=headers).status_code == 200


def test_an_unknown_period_is_a_400(client, loaded):
    headers = _user(client, "n@example.org", "national_stakeholder")
    assert client.get("/api/v2/dashboard/year", headers=headers).status_code == 400


def test_a_role_without_aggregate_read_is_refused(client, loaded):
    """A facility user sees referrals directed to them, not national
    counts."""
    db = _session(client)
    from db_models import Facility
    facility_id = db.scalar(select(Facility.id))
    db.close()
    headers = _user(client, "f@example.org", "facility_user", facility_id=facility_id)
    assert client.get("/api/v2/dashboard/today", headers=headers).status_code == 403


def test_the_dashboard_needs_a_token(client, loaded):
    """A change from v1, where GET /api/dashboard/today is open for the
    mobile Home screen. The v2 equivalent names conditions per person once a
    second condition exists, and an open endpoint returning that is a
    disclosure. The application needs a device credential — item 1.13."""
    assert client.get("/api/v2/dashboard/today").status_code == 401
