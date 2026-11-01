"""The v2 screening route and the referral close, over HTTP.

Master Reference v1.0 §10.3, §10.4. The service behaviour is covered in
`test_screening_v2.py`; what matters at this boundary is that the status codes
tell a mobile offline queue what to do, because "retry this" and "this will
never work" are different instructions and the v1 path conflated them.

  `200` with `replayed: true` — a retry is safe and writes nothing.
  `400` — the request is wrong, or the screening is incomplete. **The answers
         are saved either way**, and the body says so and names the session.
  `403` — consent has not been recorded. Not retryable without going back to
         the worker.
  `503` — the server is misconfigured. Retryable.
"""

import copy
import uuid
from datetime import datetime
from pathlib import Path

import pytest
import yaml

import database
from services import consent, crypto, identity, instrument_store, referrals_v2

REPO = Path(__file__).resolve().parent.parent.parent
FIXTURE = REPO / "clinical" / "examples" / "TEST-INSTRUMENT.yaml"

BASELINE = {"T1": "none", "T2": "low"}
OVERRIDE = {"T1": "lots", "T2": "low", "T3": "no_"}


def _session(client):
    return next(client.app.dependency_overrides[database.get_db]())


@pytest.fixture
def ready(client):
    """An approved instrument, an approved consent text, a facility, and a
    person who has consented. Returns the person id."""
    from db_models import Facility, Message, MessageText

    doc = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    approved = copy.deepcopy(doc)
    approved.update(status="approved", approved_by="Clinical Lead",
                    approved_at="2026-11-01")

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
    client.post(
        "/api/v2/consents",
        json={
            "person_id": person["person_id"],
            "consent_text_id": text_id,
            "decisions": {"screening_and_referral": True, "longitudinal_record": True},
        },
    )
    return person["person_id"]


def _submit(client, person_id, answers, **extra):
    body = {
        "person_id": person_id,
        "client_session_uuid": extra.pop("key", str(uuid.uuid4())),
        "answers": answers,
    }
    body.update(extra)
    return client.post("/api/v2/screenings", json=body)


# --------------------------------------------------------- the happy path

def test_a_screening_returns_one_result_per_condition(client, ready):
    response = _submit(client, ready, BASELINE)
    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) >= 1
    assert body["primary_tier"] in ("GREEN", "YELLOW", "ORANGE", "RED")
    assert body["session_id"] > 0
    assert body["replayed"] is False


def test_the_route_needs_no_token(client, ready):
    """A screening must work in a gold-panning area with no dashboard
    session — the same precedent as POST /api/screen."""
    assert _submit(client, ready, BASELINE).status_code == 200


def test_each_result_carries_its_provenance(client, ready):
    body = _submit(client, ready, BASELINE).json()
    for result in body["results"]:
        assert result["instrument_code"] == "TEST-INSTRUMENT"
        assert result["instrument_version"] == 1
        assert result["method"] == "deterministic_rules"
        assert result["scored_tier"]
        assert "override_fired" in result


def test_the_clock_is_reported(client, ready):
    body = _submit(client, ready, BASELINE).json()
    assert body["started_at"] and body["completed_at"]


def test_a_supplied_start_time_is_honoured(client, ready):
    """The device knows when the session started; the server knows when it
    arrived. Screening duration is a pilot indicator (§13.3)."""
    body = _submit(client, ready, BASELINE, started_at="2026-11-01T08:00:00Z").json()
    assert body["started_at"].startswith("2026-11-01T08:00")


def test_a_malformed_start_time_is_a_400(client, ready):
    assert _submit(client, ready, BASELINE, started_at="this morning").status_code == 400


# --------------------------------------------------------- idempotency

def test_a_retry_returns_the_same_session_and_writes_nothing(client, ready):
    key = str(uuid.uuid4())
    first = _submit(client, ready, BASELINE, key=key).json()
    for _ in range(3):
        again = _submit(client, ready, BASELINE, key=key).json()
        assert again["replayed"] is True
        assert again["session_id"] == first["session_id"]

    db = _session(client)
    from db_models import ScreeningSession

    assert db.query(ScreeningSession).count() == 1
    db.close()


def test_a_short_idempotency_key_is_rejected_by_the_schema(client, ready):
    response = client.post(
        "/api/v2/screenings",
        json={"person_id": ready, "client_session_uuid": "abc", "answers": BASELINE},
    )
    assert response.status_code == 422


def test_no_answers_is_rejected_by_the_schema(client, ready):
    response = client.post(
        "/api/v2/screenings",
        json={"person_id": ready, "client_session_uuid": str(uuid.uuid4()), "answers": {}},
    )
    assert response.status_code == 422


# ------------------------------------------------- failures that keep data

def test_an_incomplete_screening_is_a_400_that_says_the_answers_are_saved(
    client, ready
):
    """The one status code a mobile queue must not misread. The answers are on
    disk; resubmitting the same body will fail the same way; the session needs
    completing, not retrying."""
    response = _submit(client, ready, {"T1": "some", "T2": "mid"})
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["answers_saved"] is True
    assert detail["session_id"] > 0
    assert "T3" in detail["missing"]

    db = _session(client)
    from db_models import ScreeningAnswer, ScreeningResult

    assert db.query(ScreeningAnswer).count() == 2
    assert db.query(ScreeningResult).count() == 0
    db.close()


def test_a_screening_without_consent_is_a_403(client, ready):
    """Not a 400: the request was well formed, and the answer is that this
    person has not agreed to be screened. A queue must not retry it."""
    other = client.post(
        "/api/v2/persons/resolve", json={"name": "Farai Moyo", "phone": "0789999999"}
    ).json()
    response = _submit(client, other["person_id"], BASELINE)
    assert response.status_code == 403
    assert "screening_and_referral" in response.json()["detail"]


def test_a_missing_identity_key_is_a_retryable_503(client, ready, monkeypatch):
    monkeypatch.delenv(crypto.HMAC_KEY_VAR, raising=False)
    response = _submit(client, ready, BASELINE)
    assert response.status_code == 503
    assert "Nothing was saved" in response.json()["detail"]


def test_an_unknown_person_is_a_400(client, ready):
    assert _submit(client, 9999, BASELINE).status_code == 400


# ---------------------------------------------------------- the referral

def test_a_referring_tier_returns_a_code_and_a_deadline(client, ready):
    body = _submit(client, ready, OVERRIDE).json()
    assert body["primary_tier"] in ("ORANGE", "RED")
    assert body["referrals"]
    referral = body["referrals"][0]
    assert referral["referral_code"].startswith("SG-")
    assert referral["deadline"] and referral["condition"] and referral["facility"]


def test_a_facility_can_read_the_referral_by_code(client, ready):
    code = _submit(client, ready, OVERRIDE).json()["referrals"][0]["referral_code"]
    body = client.get(f"/api/v2/referrals/{code}").json()
    assert body["status"] == "open"
    assert body["result_id"] and body["person_id"]
    assert body["contributing_reasons"]["instrument"] == "TEST-INSTRUMENT v1"


def test_the_referral_says_why_so_staff_know_what_to_look_for(client, ready):
    code = _submit(client, ready, OVERRIDE).json()["referrals"][0]["referral_code"]
    reasons = client.get(f"/api/v2/referrals/{code}").json()["contributing_reasons"]
    assert reasons["tier"] in ("ORANGE", "RED")
    assert "override_rule_codes" in reasons
    assert "deterioration_changed" in reasons


def test_an_unknown_referral_code_is_a_404(client):
    assert client.get("/api/v2/referrals/SG-ZZZZ").status_code == 404


def test_the_outcome_vocabulary_is_served(client):
    """So the facility page renders from the server's definition rather than a
    copy that can drift out of step with what the database accepts."""
    assert client.get("/api/v2/referrals/outcomes/vocabulary").json() == list(
        referrals_v2.OUTCOMES
    )


def test_closing_a_referral_records_the_outcome(client, ready):
    """§10.4: the finding, not merely attendance. This is what turns the pilot
    into a labelled dataset."""
    code = _submit(client, ready, OVERRIDE).json()["referrals"][0]["referral_code"]
    body = client.post(
        f"/api/v2/referrals/{code}/close",
        json={
            "outcome": "attended_imaging_abnormal",
            "recorded_by": "nurse",
            "notes": "Upper zones.",
        },
    ).json()
    assert body["status"] == "closed"
    assert body["outcome"] == "attended_imaging_abnormal"
    assert body["outcome_recorded_by"] == "nurse"
    assert body["attended_at"], "an attended outcome is attendance"


def test_a_not_attended_outcome_closes_without_attendance(client, ready):
    code = _submit(client, ready, OVERRIDE).json()["referrals"][0]["referral_code"]
    body = client.post(
        f"/api/v2/referrals/{code}/close",
        json={"outcome": "not_attended", "recorded_by": "nurse"},
    ).json()
    assert body["status"] == "closed" and body["attended_at"] is None


def test_an_unknown_outcome_is_a_400(client, ready):
    code = _submit(client, ready, OVERRIDE).json()["referrals"][0]["referral_code"]
    response = client.post(
        f"/api/v2/referrals/{code}/close",
        json={"outcome": "he seemed fine", "recorded_by": "nurse"},
    )
    assert response.status_code == 400
    assert "unknown outcome" in response.json()["detail"]


def test_closing_an_unknown_code_is_a_404(client):
    response = client.post(
        "/api/v2/referrals/SG-ZZZZ/close",
        json={"outcome": "not_attended", "recorded_by": "nurse"},
    )
    assert response.status_code == 404


# ------------------------------------------------------------- the text

def test_the_response_says_nothing_was_sent_and_why(client, ready):
    """§10.3: a messaging failure is recorded, never a lost screening. There
    is no fallback sentence, because a placeholder shipped "for now" is how
    unreviewed text reaches people."""
    body = _submit(client, ready, BASELINE).json()
    assert body["not_sent_reason"]
    assert all(m["available"] is False and m["text"] is None for m in body["messages"])


# ------------------------------------------------- consent changes behaviour

def test_declined_retention_is_reported_on_the_outcome(client, ready):
    """§14.2's own example. A caller has to know the session has no history
    attached before it draws a trend."""
    from sqlalchemy import select

    from db_models import ConsentText

    other = client.post(
        "/api/v2/persons/resolve", json={"name": "Nyasha Chirwa", "phone": "0712222222"}
    ).json()

    db = _session(client)
    text_id = db.scalar(select(ConsentText.id))
    db.close()

    client.post(
        "/api/v2/consents",
        json={
            "person_id": other["person_id"],
            "consent_text_id": text_id,
            "decisions": {"screening_and_referral": True, "longitudinal_record": False},
        },
    )
    _submit(client, other["person_id"], BASELINE)
    second = _submit(client, other["person_id"], BASELINE).json()
    assert second["longitudinal_linked"] is False
