"""Identity resolution over HTTP.

Master Reference v1.0 §8.2. What matters at this boundary, beyond the service
behaviour already covered in `test_identity.py`:

  * **`POST /persons/resolve` carries no direct identifier in its response.**
    It is unauthenticated, on the same precedent as the screening path, so a
    name or a number in the body would be a public identifier endpoint.
  * **Every route that returns or changes an identifier needs a capability**,
    not merely a token. The person lookup decrypts a name and a number and
    needs `person.read`; merge, unmerge and the queued-match decision change
    who a clinical history belongs to and need `person.merge`, which the
    administrator role alone holds. `_auth` is the prototype `hospital`
    account, which holds the first and not the second, so the merge tests
    below use `_admin` -- the boundary itself is covered in
    `test_identity_route_authz.py`.
  * **A missing identity key is a retryable 503, not a 500.** The screening is
    already on the handset and must not be thrown away because the server is
    misconfigured (rule 7).
"""

import pytest

from services import crypto


def _login(client, email, password="password123"):
    response = client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _account(client, role, email):
    """A real `users` row in `role`.

    **Real accounts rather than the prototype ones**, because the prototype
    credentials self-disarm the moment a real user exists -- the fuse in
    `services/authz.any_user_exists`. A file that needs two different roles
    therefore cannot use them at all, and these tests need two: `person.read`
    to look a person up and `person.merge` to join two records.
    """
    from sqlalchemy import select

    import database
    from db_models import Facility, User
    from services import authz

    db = next(client.app.dependency_overrides[database.get_db]())
    if not db.scalar(select(User).where(User.email == email)):
        facility = db.scalar(select(Facility))
        if facility is None:
            facility = Facility(name="Test District Hospital", level="district")
            db.add(facility)
            db.flush()
        scope = {"facility_id": facility.id} if role == "facility_user" else {}
        authz.create_user(db, email, "password123", role, **scope)
        db.commit()
    db.close()
    return {"Authorization": f"Bearer {_login(client, email)}"}


def _auth(client):
    """A facility user: holds `person.read`, not `person.merge`."""
    return _account(client, "facility_user", "facility@example.org")


def _admin(client):
    """An administrator, the one role §16.3 trusts with a merge -- and which
    holds no `person.read`, because "administrative access is not a licence to
    read records"."""
    return _account(client, "administrator", "admin@example.org")


def _resolve(client, **bundle):
    return client.post("/api/v2/persons/resolve", json=bundle)


# ------------------------------------------------------------------ resolve

def test_resolving_creates_a_person_with_a_participant_code(client):
    response = _resolve(client, name="Tendai Moyo", phone="0771234567")
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "created"
    assert len(body["participant_code"]) == 6
    assert body["person_id"] > 0


def test_resolve_needs_no_token(client):
    """Deliberate: the village health worker's application never logs in."""
    assert _resolve(client, name="Tendai Moyo", phone="0771234567").status_code == 200


def test_the_resolve_response_carries_no_name_or_number(client):
    """It is unauthenticated, so a name or a number here would be a public
    identifier endpoint."""
    body = _resolve(client, name="Tendai Moyo", phone="0771234567").json()
    serialised = str(body)
    assert "Tendai" not in serialised
    assert "771234567" not in serialised


def test_a_card_resolves_to_the_same_person(client):
    first = _resolve(client, name="Tendai Moyo", phone="0771234567").json()
    again = _resolve(client, participant_code=first["participant_code"]).json()
    assert again["person_id"] == first["person_id"]
    assert again["outcome"] == "matched_participant_code"


def test_a_probable_match_comes_back_queued_not_applied(client):
    first = _resolve(client, name="Tendai Moyo", phone="0771234567").json()
    second = _resolve(client, name="Tendai Moyo", phone="0771234567").json()

    assert second["person_id"] != first["person_id"]
    assert second["outcome"] == "created_pending_review"
    assert [c["person_id"] for c in second["candidates"]] == [first["person_id"]]
    assert second["queued_match_ids"]


def test_a_candidate_is_identified_by_code_not_by_name(client):
    """A reviewer opens each side by participant code, so the scoring response
    stays free of direct identifiers."""
    _resolve(client, name="Tendai Moyo", phone="0771234567")
    second = _resolve(client, name="Tendai Moyo", phone="0771234567").json()
    candidate = second["candidates"][0]
    assert candidate["participant_code"]
    assert "name" not in candidate and "phone" not in candidate
    assert candidate["reasons"]


def test_a_ussd_caller_with_no_code_is_provisional(client):
    body = _resolve(client, phone="0771234567", channel="USSD").json()
    assert body["outcome"] == "created_provisional"
    assert body["provisional"] is True
    assert body["provisional_reason"] == "ussd_no_participant_code"


def test_an_empty_bundle_is_a_400(client):
    response = _resolve(client, age_band="30-39", sex="male")
    assert response.status_code == 400
    assert "participant code" in response.json()["detail"]


def test_an_unknown_card_on_the_app_is_a_400(client):
    response = _resolve(client, participant_code="ZZZZZZ", name="Tendai Moyo")
    assert response.status_code == 400
    assert "matches no person" in response.json()["detail"]


def test_a_missing_identity_key_is_a_retryable_503(client, monkeypatch):
    """Not a 500. The screening is already on the handset, and the offline
    queue must treat this as worth retrying rather than as a bad request."""
    monkeypatch.delenv(crypto.HMAC_KEY_VAR, raising=False)
    response = _resolve(client, name="Tendai Moyo", phone="0771234567")
    assert response.status_code == 503
    assert "Nothing was saved" in response.json()["detail"]


# ------------------------------------------------------------------- lookup

def test_the_person_lookup_needs_a_token(client):
    """It decrypts a name and a number. Public, it would let anyone walk the
    code space and harvest both."""
    code = _resolve(client, name="Tendai Moyo", phone="0771234567").json()[
        "participant_code"
    ]
    assert client.get(f"/api/v2/persons/{code}").status_code == 401


def test_the_person_lookup_returns_the_identifiers_to_an_authorised_caller(client):
    """A health worker confirming "is this the right person?" at the next
    outreach, and a referral letter, both need the name."""
    code = _resolve(
        client, name="Tendai Moyo", phone="0771234567", age_band="30-39", sex="male"
    ).json()["participant_code"]

    body = client.get(f"/api/v2/persons/{code}", headers=_auth(client)).json()
    assert body["name"] == "Tendai Moyo"
    assert body["phone"] == "+263771234567"
    assert body["age_band"] == "30-39" and body["sex"] == "male"
    assert body["has_national_id"] is False
    assert body["session_count"] == 0


def test_the_lookup_reports_a_national_id_without_returning_it(client):
    """Stored as a keyed hash only, so there is nothing to return — but
    whether one was given is useful to a reviewer."""
    code = _resolve(
        client, name="Tendai Moyo", national_id="63-123456-A-00"
    ).json()["participant_code"]
    body = client.get(f"/api/v2/persons/{code}", headers=_auth(client)).json()
    assert body["has_national_id"] is True
    assert "63123456" not in str(body)


def test_an_unknown_card_is_a_404(client):
    assert (
        client.get("/api/v2/persons/ZZZZZZ", headers=_auth(client)).status_code == 404
    )


def test_a_card_printed_before_a_merge_still_works(client):
    """Which is the point of printing one."""
    winner = _resolve(client, name="Tendai Moyo", phone="0771234567").json()
    loser = _resolve(client, name="Tendai Moyo", phone="0789999999").json()
    client.post(
        "/api/v2/persons/merges",
        json={
            "winner_person_id": winner["person_id"],
            "loser_person_id": loser["person_id"],
            "merged_by": "clerk",
        },
        headers=_admin(client),
    )
    body = client.get(
        f"/api/v2/persons/{loser['participant_code']}", headers=_auth(client)
    ).json()
    assert body["person_id"] == winner["person_id"]


# -------------------------------------------------------------- the queue

def test_the_queue_needs_a_token(client):
    assert client.get("/api/v2/persons/matches/queue").status_code == 401


def test_the_queue_lists_a_pending_pair_without_identifiers(client):
    _resolve(client, name="Tendai Moyo", phone="0771234567")
    _resolve(client, name="Tendai Moyo", phone="0771234567")

    rows = client.get("/api/v2/persons/matches/queue", headers=_auth(client)).json()
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == "pending" and row["score"] >= 0.5
    assert row["participant_code"] and row["candidate_participant_code"]
    assert "shares a contact number" in row["reasons"]
    assert "Tendai" not in str(row)


def test_deciding_merge_applies_it(client):
    first = _resolve(client, name="Tendai Moyo", phone="0771234567").json()
    second = _resolve(client, name="Tendai Moyo", phone="0771234567").json()

    match_id = second["queued_match_ids"][0]
    row = client.post(
        f"/api/v2/persons/matches/{match_id}",
        json={"decision": "merge", "decided_by": "clerk"},
        headers=_admin(client),
    ).json()
    assert row["status"] == "merged"

    # The loser's card now resolves to the winner. Read with the account that
    # holds `person.read`: an administrator may merge and may not browse
    # records, which is §16.3's "administrative access is not a licence to
    # read records" and not an accident of this test.
    body = client.get(
        f"/api/v2/persons/{second['participant_code']}", headers=_auth(client)
    ).json()
    assert body["person_id"] == first["person_id"]


def test_deciding_reject_clears_the_queue_without_merging(client):
    first = _resolve(client, name="Tendai Moyo", phone="0771234567").json()
    second = _resolve(client, name="Tendai Moyo", phone="0771234567").json()

    client.post(
        f"/api/v2/persons/matches/{second['queued_match_ids'][0]}",
        json={"decision": "reject", "decided_by": "clerk"},
        headers=_admin(client),
    )
    headers = _auth(client)
    assert client.get("/api/v2/persons/matches/queue", headers=headers).json() == []
    body = client.get(
        f"/api/v2/persons/{second['participant_code']}", headers=headers
    ).json()
    assert body["person_id"] == second["person_id"] != first["person_id"]


def test_an_unknown_decision_is_a_400(client):
    _resolve(client, name="Tendai Moyo", phone="0771234567")
    second = _resolve(client, name="Tendai Moyo", phone="0771234567").json()
    response = client.post(
        f"/api/v2/persons/matches/{second['queued_match_ids'][0]}",
        json={"decision": "maybe", "decided_by": "clerk"},
        headers=_admin(client),
    )
    assert response.status_code == 400


# ----------------------------------------------------------- merge, unmerge

def test_merging_needs_a_token(client):
    first = _resolve(client, name="Tendai Moyo").json()
    second = _resolve(client, name="Farai Moyo").json()
    response = client.post(
        "/api/v2/persons/merges",
        json={
            "winner_person_id": first["person_id"],
            "loser_person_id": second["person_id"],
            "merged_by": "anyone",
        },
    )
    assert response.status_code == 401


def test_a_merge_is_recorded_and_reversible(client):
    winner = _resolve(client, name="Tendai Moyo", phone="0771234567").json()
    loser = _resolve(client, name="Tendai Moyo", phone="0789999999").json()
    headers = _admin(client)

    merged = client.post(
        "/api/v2/persons/merges",
        json={
            "winner_person_id": winner["person_id"],
            "loser_person_id": loser["person_id"],
            "merged_by": "sister.moyo",
            "reason": "presented the same card",
        },
        headers=headers,
    ).json()
    assert merged["merged_by"] == "sister.moyo" and merged["merged_at"]
    assert merged["reversed_at"] is None

    reversed_record = client.delete(
        f"/api/v2/persons/merges/{merged['merge_id']}?reversed_by=supervisor",
        headers=headers,
    ).json()
    assert reversed_record["reversed_by"] == "supervisor"
    assert reversed_record["reversed_at"]

    body = client.get(
        f"/api/v2/persons/{loser['participant_code']}", headers=_auth(client)
    ).json()
    assert body["person_id"] == loser["person_id"], "the identity is restored"


def test_merging_a_person_into_themselves_is_a_400(client):
    person = _resolve(client, name="Tendai Moyo").json()
    response = client.post(
        "/api/v2/persons/merges",
        json={
            "winner_person_id": person["person_id"],
            "loser_person_id": person["person_id"],
            "merged_by": "clerk",
        },
        headers=_admin(client),
    )
    assert response.status_code == 400


def test_unmerging_something_unmerged_is_a_400(client):
    assert (
        client.delete(
            "/api/v2/persons/merges/999?reversed_by=supervisor", headers=_admin(client)
        ).status_code
        == 400
    )


def test_the_session_count_reflects_a_merge(client):
    """A merge joins the clinical history, which is the reason to do it."""
    winner = _resolve(client, name="Tendai Moyo", phone="0771234567").json()
    loser = _resolve(client, name="Tendai Moyo", phone="0789999999").json()

    gen = client.app.dependency_overrides
    from db_models import ScreeningSession
    import database

    db = next(gen[database.get_db]())
    db.add(ScreeningSession(person_id=loser["person_id"], channel="APP"))
    db.commit()
    db.close()

    client.post(
        "/api/v2/persons/merges",
        json={
            "winner_person_id": winner["person_id"],
            "loser_person_id": loser["person_id"],
            "merged_by": "clerk",
        },
        headers=_admin(client),
    )
    body = client.get(
        f"/api/v2/persons/{winner['participant_code']}", headers=_auth(client)
    ).json()
    assert body["session_count"] == 1
