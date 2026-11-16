"""What each `aggregate.read` role may actually see.

Master Reference v1.0 §16.3's "cannot see" column, and §14.4 — "an employer or
programme sponsor never receives individual results without separate,
specific, refusable consent".

**The hole this closes.** Four roles hold `aggregate.read`: district
coordinator, national stakeholder, researcher, programme sponsor, plus the
administrator. `authz` has had scoped query helpers since the role model
landed, and until 2 November 2026 **no route applied one** — so a programme
sponsor reading `GET /api/v2/dashboard/today` was handed every cohort's
numbers and the community outreach ones alongside their own.

**Why the sponsor and not the others.** §16.3's rows are not equivalent:

  district coordinator → "Identified records **outside their district**"
  programme sponsor    → "Individual results; **anything** outside their
                          cohort"

A coordinator is refused identified records outside their district and may
still see the national picture; a sponsor is refused the aggregate too. A
national stakeholder's and a researcher's whole purpose is the national
picture. So one role is narrowed here and the rest deliberately are not —
asserted below from the sentences themselves rather than from my reading of
them.

**Whether aggregates should also be narrowed by district is open**, and left
open on purpose: the role declares a district scope that no aggregate route
applies, and the master document does not require it. That is a question for
the team, not a gap to close quietly in a pull request.
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
GREEN = {"T1": "none", "T2": "low"}


def _session(client):
    return next(client.app.dependency_overrides[database.get_db]())


def _login(client, email, role, **scope):
    db = _session(client)
    authz.create_user(db, email, "password123", role, **scope)
    db.commit()
    db.close()
    token = client.post("/api/auth/login", json={
        "email": email, "password": "password123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def two_cohorts(client):
    """Two programmes with one screening each, plus one community screening
    that belongs to neither. Returns the two programme ids."""
    from db_models import Facility, Message, MessageText, Programme

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
    ours = Programme(code="MINECO", name="Mine Co", kind="employer",
                     payer="Mine Co", data_owner="Mine Co",
                     consent_text_code="CORE")
    theirs = Programme(code="OTHERCO", name="Other Co", kind="employer",
                       payer="Other Co", data_owner="Other Co",
                       consent_text_code="CORE")
    db.add_all([ours, theirs])
    db.commit()
    text_id, ours_id, theirs_id = text.id, ours.id, theirs.id
    db.close()

    for i, (programme, answers) in enumerate((
        (ours_id, GREEN), (theirs_id, RED), (None, RED),
    )):
        person = client.post("/api/v2/persons/resolve", json={
            "name": f"Worker {i}", "phone": f"07712345{i:02d}"}).json()
        client.post("/api/v2/consents", json={
            "person_id": person["person_id"], "consent_text_id": text_id,
            "decisions": {"screening_and_referral": True, "longitudinal_record": True},
        })
        body = {
            "person_id": person["person_id"],
            "client_session_uuid": str(uuid.uuid4()),
            "answers": answers,
        }
        if programme is not None:
            body["programme_id"] = programme
        response = client.post("/api/v2/screenings", json=body)
        assert response.status_code == 200, response.text

    return ours_id, theirs_id


# ------------------------------------------------- the sentence, per role

def test_the_sponsor_sees_only_their_own_cohort(client, two_cohorts):
    """**The assertion that closes the hole.** Three screenings exist: one in
    this sponsor's programme, one in a competitor's, one community. The
    sponsor must count one."""
    ours, _ = two_cohorts
    headers = _login(client, "sponsor@mineco.example", "programme_sponsor",
                     programme_id=ours)
    body = client.get("/api/v2/dashboard/month", headers=headers).json()

    assert body["sessions"] == 1, "their cohort, not everybody's"
    assert body["people"] == 1
    assert sum(r["count"] for r in body["by_condition_and_tier"]) == 2, (
        "one session, two conditions"
    )


def test_a_sponsors_referral_numbers_are_their_cohort_too(client, two_cohorts):
    """Half a boundary is not a boundary: the competitor's RED screening
    generated referrals, and they must not appear here. This sponsor's one
    screening is GREEN, so their referral count is zero."""
    ours, _ = two_cohorts
    headers = _login(client, "sponsor@mineco.example", "programme_sponsor",
                     programme_id=ours)
    body = client.get("/api/v2/dashboard/month", headers=headers).json()

    assert body["referrals_raised"] == 0
    assert body["referrals_open_now"] == 0, (
        "the backlog is a standing total and still must not cross a cohort"
    )


def test_the_other_sponsor_sees_the_other_cohort(client, two_cohorts):
    """Symmetry, so the test above is not passing for the wrong reason."""
    _, theirs = two_cohorts
    headers = _login(client, "sponsor@otherco.example", "programme_sponsor",
                     programme_id=theirs)
    body = client.get("/api/v2/dashboard/month", headers=headers).json()

    assert body["sessions"] == 1
    assert body["referrals_raised"] >= 1, "their RED screening referred"


def test_a_sponsor_with_no_programme_cannot_be_created(client):
    """Defended twice, and the outer one was already there: `create_user`
    refuses a scoped role with no scope, because such an account "passes every
    capability check and is bounded by nothing"."""
    db = _session(client)
    with pytest.raises(authz.AuthzError) as raised:
        authz.create_user(db, "unscoped@example.org", "password123",
                          "programme_sponsor")
    db.rollback()
    db.close()
    assert "needs programme_id" in str(raised.value)


def test_and_the_narrowing_itself_fails_closed(client):
    """The inner defence, tested directly because the account above cannot
    exist to exercise it through a route. The failure mode of a missing scope
    must be an empty result, never an unfiltered one — the whole reason
    `authz`'s helpers exist instead of an inline `if`."""
    from db_models import ScreeningSession

    principal = authz.Principal(
        user_id=1, email="x@example.org", role="programme_sponsor", scope={})
    statement = authz.for_aggregate_sessions(
        select(ScreeningSession), ScreeningSession.programme_id, principal)

    db = _session(client)
    assert db.scalars(statement).all() == []
    db.close()


@pytest.mark.parametrize("role", ["national_stakeholder", "researcher", "administrator"])
def test_an_unscoped_aggregate_role_still_sees_the_whole_picture(client, two_cohorts, role):
    """Deliberately not narrowed. A national stakeholder's purpose is the
    national picture and a researcher's is the population; narrowing them
    would be inventing a restriction the master document does not make."""
    headers = _login(client, f"{role}@example.org", role)
    body = client.get("/api/v2/dashboard/month", headers=headers).json()
    assert body["sessions"] == 3


def test_the_district_coordinator_is_not_narrowed_and_that_is_the_open_question(
    client, two_cohorts
):
    """§16.3 refuses this role *identified* records outside its district, and
    an aggregate names nobody — so the current behaviour matches the document.
    Asserted so that narrowing it later is a deliberate change with a failing
    test, rather than something that drifts."""
    headers = _login(client, "coord@example.org", "district_coordinator",
                     district="Kwekwe")
    body = client.get("/api/v2/dashboard/month", headers=headers).json()
    assert body["sessions"] == 3


def test_the_rule_is_read_from_the_role_table_not_hardcoded(client):
    """`scoped_to_a_cohort` must follow §16.3's sentences. If a role gains a
    `programme_id` scope later it is narrowed automatically; if this test
    fails, the table and the behaviour have diverged."""
    for role in authz.ROLES:
        principal = authz.Principal(
            user_id=1, email="x@example.org", role=role.code, scope={})
        expected = role.scope_field == "programme_id"
        assert authz.scoped_to_a_cohort(principal) is expected, role.code
        if expected:
            assert "outside their cohort" in role.cannot, (
                "the narrowing exists because the sentence says so"
            )


# ---------------------------------------------- the outreach rollup refuses

def test_the_outreach_rollup_refuses_a_sponsor(client, two_cohorts):
    """`outreach_visits` carries no programme — its `site` is free text by
    deliberate design — so there is no column a cohort scope could narrow on.
    Serving the rollup anyway would hand a sponsor every other site's numbers,
    so it refuses. Deny by default."""
    ours, _ = two_cohorts
    headers = _login(client, "sponsor@mineco.example", "programme_sponsor",
                     programme_id=ours)

    for path in ("/api/v2/outreach", "/api/v2/outreach/1"):
        response = client.get(path, headers=headers)
        assert response.status_code == 403, path
        assert "outside its cohort" in response.json()["detail"]


def test_that_refusal_is_recorded(client, two_cohorts):
    """A boundary nobody can show being enforced is a boundary nobody can
    show exists."""
    from db_models import AuditLog

    ours, _ = two_cohorts
    headers = _login(client, "sponsor@mineco.example", "programme_sponsor",
                     programme_id=ours)
    client.get("/api/v2/outreach", headers=headers)

    db = _session(client)
    rows = db.scalars(
        select(AuditLog).where(AuditLog.object_type == "outreach", AuditLog.allowed == 0)
    ).all()
    db.close()
    assert rows and rows[-1].actor_email == "sponsor@mineco.example"


def test_the_outreach_rollup_still_serves_a_coordinator(client, two_cohorts):
    """The refusal must be the narrow one it claims to be: a district
    coordinator is who outreach planning is for."""
    from db_models import OutreachVisit

    db = _session(client)
    db.add(OutreachVisit(site="Globe & Phoenix"))
    db.commit()
    db.close()

    headers = _login(client, "coord@example.org", "district_coordinator",
                     district="Kwekwe")
    assert client.get("/api/v2/outreach", headers=headers).status_code == 200


# ------------------------------------------------------- nothing identified

def test_a_sponsors_role_does_not_permit_reading_a_person(client, two_cohorts):
    """§14.4, and the one rule in `CLAUDE.md` that names this role. Scoping an
    aggregate must not be mistaken for permission to read a person.

    **The role is right and one route does not consult it.** `GET /api/v2/
    persons/{code}` and the merge routes still use the plain token dependency
    rather than a capability, so they serve an identified record to any
    authenticated role — found while writing this file and fixed separately,
    because it is a different subject from cohort scoping. The assertions
    here are about the role model, which is correct; the route assertions
    belong with the fix.
    """
    ours, _ = two_cohorts
    sponsor = authz.Principal(user_id=1, email="s@example.org",
                              role="programme_sponsor",
                              scope={"programme_id": ours})
    assert not authz.may_read_identified(sponsor)
    assert not sponsor.allows("person.read")
    assert not sponsor.allows("person.merge")
    assert not sponsor.allows("screening.read")

    # And the one it does hold is bounded, which is what the rest of this
    # file tests.
    assert sponsor.allows("aggregate.read")


def test_the_scoped_response_names_nobody(client, two_cohorts):
    ours, _ = two_cohorts
    headers = _login(client, "sponsor@mineco.example", "programme_sponsor",
                     programme_id=ours)
    serialised = str(client.get("/api/v2/dashboard/month", headers=headers).json())
    assert "Worker" not in serialised and "0771234" not in serialised
