"""Consent capture over HTTP.

Master Reference v1.0 §8.5 and §14.2. The boundary properties, beyond the
service behaviour covered in `test_consent.py`:

  * **Recording is unauthenticated** and withdrawal is not, for reasons the
    router documents and this file pins down.
  * **A consent screen can be rendered from the server's definition**, so a
    copy in the client cannot drift away from what is recorded.
  * **The summary always names all six permissions**, including the ones
    nobody asked about, so a client never has to decide what a missing key
    means.
"""

from datetime import datetime

import pytest

import database
from db_models import Message, MessageText
from services import consent


def _login(client, email="hospital@silicaguard.health", password="hospital123"):
    return client.post(
        "/api/auth/login", json={"email": email, "password": password}
    ).json()["access_token"]


def _auth(client):
    return {"Authorization": f"Bearer {_login(client)}"}


def _session(client):
    return next(client.app.dependency_overrides[database.get_db]())


def _person(client, **bundle):
    bundle.setdefault("name", "Tendai Moyo")
    bundle.setdefault("phone", "0771234567")
    return client.post("/api/v2/persons/resolve", json=bundle).json()


def _consent_text(client, *, status="approved"):
    """An approved consent text, with its wording in the content store."""
    db = _session(client)
    message = Message(
        code="consent.core.v1",
        version=1,
        channel="app",
        status="approved",
        approved_by="Clinical Lead",
        approved_at=datetime(2026, 11, 1),
        purpose="Stands in for the approved consent wording.",
    )
    db.add(message)
    db.flush()
    db.add(MessageText(message_id=message.id, language="en", text_value="TEST wording."))
    text = consent.register_text(
        db,
        "CORE",
        message.code,
        status=status,
        approved_by="Clinical Lead" if status == "approved" else None,
        approved_at=datetime(2026, 11, 1) if status == "approved" else None,
    )
    db.commit()
    text_id = text.id
    db.close()
    return text_id


# --------------------------------------------------- rendering the screen

def test_the_six_permissions_are_served_for_the_consent_screen(client):
    """So a consent screen renders from the server's definition rather than a
    copy in the client. A copy drifts, and a consent screen that drifts asks
    for agreement to something other than what is recorded."""
    rows = client.get("/api/v2/consents/permissions").json()
    assert [r["code"] for r in rows] == [p.code for p in consent.PERMISSIONS]
    assert rows[0]["required_to_screen"] is True
    assert rows[-1]["code"] == "employer_disclosure"
    assert rows[-1]["future_phase"] is True
    assert all(len(r["scope"]) > 30 for r in rows)


def test_the_permissions_list_needs_no_token(client):
    """It is part of a screening, and the VHW application never logs in."""
    assert client.get("/api/v2/consents/permissions").status_code == 200


def test_the_active_consent_text_is_served(client):
    _consent_text(client)
    body = client.get("/api/v2/consents/texts/CORE").json()
    assert body["code"] == "CORE" and body["version"] == 1
    assert body["status"] == "approved"
    assert body["message_code"] == "consent.core.v1"


def test_the_consent_text_response_carries_a_message_code_not_wording(client):
    """The words live in the content store, so consent text goes through the
    same review, three languages and GSM-7 checks as everything else (§8.4)."""
    _consent_text(client)
    body = client.get("/api/v2/consents/texts/CORE").json()
    assert "text" not in body and "wording" not in body
    assert body["message_code"]


def test_an_unapproved_consent_text_is_a_404(client):
    """Which is the state until the Clinical Lead approves one, and is why
    consent capture does not work before then."""
    _consent_text(client, status="draft")
    response = client.get("/api/v2/consents/texts/CORE")
    assert response.status_code == 404
    assert "no version is approved" in response.json()["detail"]


def test_an_unknown_consent_text_is_a_404(client):
    assert client.get("/api/v2/consents/texts/NOPE").status_code == 404


# ------------------------------------------------------------- recording

def test_a_consent_screen_is_recorded_and_summarised(client):
    person = _person(client)
    text_id = _consent_text(client)

    body = client.post(
        "/api/v2/consents",
        json={
            "person_id": person["person_id"],
            "consent_text_id": text_id,
            "channel": "APP",
            "recorded_by": "sister.moyo",
            "decisions": {
                "screening_and_referral": True,
                "longitudinal_record": True,
                "contact_by_message": True,
                "education_broadcast": False,
                "research_and_statistics": False,
            },
        },
    ).json()

    assert body["may_screen"] is True
    assert body["may_keep_longitudinal_record"] is True
    assert body["standing"]["education_broadcast"] is False
    assert len(body["history"]) == 5


def test_recording_needs_no_token(client):
    """Deliberate, and on the same precedent as the screening path: requiring
    a token for consent while screening itself is open would be incoherent."""
    person = _person(client)
    text_id = _consent_text(client)
    response = client.post(
        "/api/v2/consents",
        json={
            "person_id": person["person_id"],
            "consent_text_id": text_id,
            "decisions": {"screening_and_referral": True},
        },
    )
    assert response.status_code == 200


def test_the_summary_always_names_all_six_permissions(client):
    """A client must never have to decide what a missing key means."""
    person = _person(client)
    text_id = _consent_text(client)
    body = client.post(
        "/api/v2/consents",
        json={
            "person_id": person["person_id"],
            "consent_text_id": text_id,
            "decisions": {"screening_and_referral": True},
        },
    ).json()
    assert set(body["standing"]) == {p.code for p in consent.PERMISSIONS}
    assert body["standing"]["research_and_statistics"] is False


def test_a_declined_retention_is_reported_to_the_caller(client):
    """§14.2's own example. The screening still happens; it simply has no
    history attached, and the caller has to know that before it links one."""
    person = _person(client)
    text_id = _consent_text(client)
    body = client.post(
        "/api/v2/consents",
        json={
            "person_id": person["person_id"],
            "consent_text_id": text_id,
            "decisions": {"screening_and_referral": True, "longitudinal_record": False},
        },
    ).json()
    assert body["may_screen"] is True
    assert body["may_keep_longitudinal_record"] is False


def test_the_history_names_the_consent_text_version(client):
    person = _person(client)
    text_id = _consent_text(client)
    body = client.post(
        "/api/v2/consents",
        json={
            "person_id": person["person_id"],
            "consent_text_id": text_id,
            "decisions": {"screening_and_referral": True},
        },
    ).json()
    entry = body["history"][0]
    assert entry["consent_text_code"] == "CORE"
    assert entry["consent_text_version"] == 1
    assert entry["recorded_at"]


def test_an_employer_grant_is_a_400_and_records_nothing(client):
    """§14.4. record_many validates everything before writing anything, so a
    disallowed grant in the set does not leave the rest recorded."""
    person = _person(client)
    text_id = _consent_text(client)
    response = client.post(
        "/api/v2/consents",
        json={
            "person_id": person["person_id"],
            "consent_text_id": text_id,
            "decisions": {"screening_and_referral": True, "employer_disclosure": True},
        },
    )
    assert response.status_code == 400
    assert "future-phase" in response.json()["detail"]

    db = _session(client)
    from db_models import ConsentRecord

    assert db.query(ConsentRecord).count() == 0
    db.close()


def test_an_unapproved_text_cannot_be_used_to_record(client):
    person = _person(client)
    text_id = _consent_text(client, status="draft")
    response = client.post(
        "/api/v2/consents",
        json={
            "person_id": person["person_id"],
            "consent_text_id": text_id,
            "decisions": {"screening_and_referral": True},
        },
    )
    assert response.status_code == 400
    assert "not approved" in response.json()["detail"]


def test_an_empty_decision_set_is_a_400(client):
    person = _person(client)
    text_id = _consent_text(client)
    response = client.post(
        "/api/v2/consents",
        json={"person_id": person["person_id"], "consent_text_id": text_id, "decisions": {}},
    )
    assert response.status_code == 400


def test_an_unknown_person_is_a_400(client):
    text_id = _consent_text(client)
    response = client.post(
        "/api/v2/consents",
        json={
            "person_id": 9999,
            "consent_text_id": text_id,
            "decisions": {"screening_and_referral": True},
        },
    )
    assert response.status_code == 400


# ------------------------------------------------------------ withdrawal

def test_withdrawal_needs_a_token(client):
    """The gap the router names: a worker's own withdrawal should not need
    one, but an open endpoint keyed on a person id would let anyone stop
    anyone's referral reminders. The worker-facing route is the USSD opt-out,
    which lands with item 1.9."""
    person = _person(client)
    response = client.post(
        "/api/v2/consents/withdraw",
        json={
            "person_id": person["person_id"],
            "permission": "education_broadcast",
            "withdrawn_by": "worker",
        },
    )
    assert response.status_code == 401


def test_a_withdrawal_takes_effect_and_keeps_the_record(client):
    person = _person(client)
    text_id = _consent_text(client)
    client.post(
        "/api/v2/consents",
        json={
            "person_id": person["person_id"],
            "consent_text_id": text_id,
            "decisions": {"education_broadcast": True},
        },
    )
    body = client.post(
        "/api/v2/consents/withdraw",
        json={
            "person_id": person["person_id"],
            "permission": "education_broadcast",
            "withdrawn_by": "supervisor",
        },
        headers=_auth(client),
    ).json()

    assert body["standing"]["education_broadcast"] is False
    assert len(body["history"]) == 1, "the original row is kept, not deleted"
    assert body["history"][0]["granted"] is True
    assert body["history"][0]["withdrawn_at"]


def test_withdrawing_something_never_granted_succeeds_quietly(client):
    person = _person(client)
    response = client.post(
        "/api/v2/consents/withdraw",
        json={
            "person_id": person["person_id"],
            "permission": "education_broadcast",
            "withdrawn_by": "supervisor",
        },
        headers=_auth(client),
    )
    assert response.status_code == 200
    assert response.json()["standing"]["education_broadcast"] is False


def test_an_unknown_permission_on_withdrawal_is_a_400(client):
    person = _person(client)
    response = client.post(
        "/api/v2/consents/withdraw",
        json={
            "person_id": person["person_id"],
            "permission": "everything",
            "withdrawn_by": "supervisor",
        },
        headers=_auth(client),
    )
    assert response.status_code == 400


# ------------------------------------------------------- reading by card

def test_consents_can_be_read_by_participant_code(client):
    person = _person(client)
    text_id = _consent_text(client)
    client.post(
        "/api/v2/consents",
        json={
            "person_id": person["person_id"],
            "consent_text_id": text_id,
            "decisions": {"screening_and_referral": True},
        },
    )
    body = client.get(
        f"/api/v2/persons/{person['participant_code']}/consents", headers=_auth(client)
    ).json()
    assert body["person_id"] == person["person_id"]
    assert body["may_screen"] is True


def test_reading_consents_by_card_needs_a_token(client):
    person = _person(client)
    assert (
        client.get(f"/api/v2/persons/{person['participant_code']}/consents").status_code
        == 401
    )


def test_consent_follows_a_merge(client):
    """A worker's decision must not be lost because a clerk joined two
    records — the bug this surfaced in `identity.merge()`."""
    winner = _person(client, phone="0771234567")
    loser = _person(client, phone="0789999999")
    text_id = _consent_text(client)
    headers = _auth(client)

    client.post(
        "/api/v2/consents",
        json={
            "person_id": loser["person_id"],
            "consent_text_id": text_id,
            "decisions": {"screening_and_referral": True, "longitudinal_record": True},
        },
    )
    client.post(
        "/api/v2/persons/merges",
        json={
            "winner_person_id": winner["person_id"],
            "loser_person_id": loser["person_id"],
            "merged_by": "clerk",
        },
        headers=headers,
    )

    body = client.get(
        f"/api/v2/persons/{winner['participant_code']}/consents", headers=headers
    ).json()
    assert body["may_screen"] is True
    assert body["may_keep_longitudinal_record"] is True


def test_an_unknown_card_is_a_404(client):
    assert (
        client.get("/api/v2/persons/ZZZZZZ/consents", headers=_auth(client)).status_code
        == 404
    )
