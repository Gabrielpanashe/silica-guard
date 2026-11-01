"""Users, roles and the audit trail over HTTP.

Master Reference v1.0 §16.3, §16.6. The boundary properties:

  **Creating the first user retires the prototype accounts.** Not a flag — a
  flag nobody turns off is how a prototype credential reaches production.

  **A refused request writes an audit row.** The §16.3 requirement that makes
  the role model demonstrable rather than merely declared.

  **`SECRET_KEY` has no fallback.** It used to default to `"dev-secret"`, a
  value published in this repository, which meant anyone could mint an
  administrator token against a misconfigured instance.
"""

import pytest
from sqlalchemy import select

import database
from db_models import AuditLog, Facility, User
from services import authz


def _session(client):
    return next(client.app.dependency_overrides[database.get_db]())


def _login(client, email, password):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _prototype(client):
    return _login(client, "hospital@silicaguard.health", "hospital123")


def _make_admin(client, email="admin@example.org", password="password123"):
    """Created directly, because creating the first administrator is itself an
    administrative act and there is nobody to do it yet."""
    db = _session(client)
    authz.create_user(db, email, password, "administrator", name="Administrator")
    db.commit()
    db.close()
    return _login(client, email, password)


# ---------------------------------------------------------------- the roles

def test_the_roles_are_served_with_what_each_cannot_see(client):
    """Unauthenticated: it describes the model rather than any data, and a
    reviewer reading what a role is refused should not need an account."""
    rows = client.get("/api/v2/roles").json()
    codes = {r["code"] for r in rows}
    assert set(authz.SPECIFIED_ROLES) <= codes
    for row in rows:
        assert row["cannot"], row["code"]
    prototype = [r for r in rows if r["prototype"]]
    assert {r["code"] for r in prototype} == {"hospital", "cimas"}


def test_the_stakeholder_role_advertises_that_it_cannot_read_a_record(client):
    rows = {r["code"]: r for r in client.get("/api/v2/roles").json()}
    assert "person.read" not in rows["national_stakeholder"]["capabilities"]
    assert "identified" in rows["national_stakeholder"]["cannot"].lower()


# ------------------------------------------------- the prototype fuse

def test_the_prototype_accounts_work_while_no_user_exists(client):
    assert _prototype(client)


def test_me_reports_a_prototype_account_as_one(client):
    body = client.get("/api/auth/me", headers=_prototype(client)).json()
    assert body["prototype_account"] is True
    assert body["cannot"]


def test_a_prototype_account_cannot_create_a_user(client):
    """**The bootstrap deadlock, resolved deliberately.** The prototype
    accounts do not hold `admin.manage`, so they cannot create the first
    administrator — and widening them would defeat the point of retiring
    them. A prototype password from an environment variable must not be able
    to mint a real account.

    The first administrator is created by `scripts/create_admin.py`, which
    needs database access. That is the third of three possible answers and
    the only safe one: giving the prototype accounts the capability widens a
    credential due for deletion, and letting the route run unauthenticated
    while the table is empty opens a window in which whoever reaches a fresh
    instance first owns it.
    """
    response = client.post(
        "/api/v2/users",
        json={"email": "admin@example.org", "password": "password123",
              "role": "administrator"},
        headers=_prototype(client),
    )
    assert response.status_code == 403
    assert "may not admin.manage" in response.json()["detail"]


def test_creating_the_first_user_retires_the_prototype_accounts(client):
    """**The fuse.** Self-disarming rather than a flag — a flag nobody turns
    off is how a prototype credential reaches production."""
    assert _prototype(client), "they work before the first user exists"
    _make_admin(client)

    refused = client.post(
        "/api/auth/login",
        json={"email": "hospital@silicaguard.health", "password": "hospital123"},
    )
    assert refused.status_code == 401


def test_a_prototype_token_stops_working_once_a_user_exists(client):
    """A twelve-hour token must not outlive the account it was issued for."""
    headers = _prototype(client)
    db = _session(client)
    authz.create_user(db, "admin@example.org", "password123", "administrator")
    db.commit()
    db.close()

    response = client.get("/api/auth/me", headers=headers)
    assert response.status_code == 401
    assert "prototype account" in response.json()["detail"]


# ------------------------------------------------------- user management

def test_an_administrator_can_create_a_scoped_user(client):
    headers = _make_admin(client)
    db = _session(client)
    db.add(Facility(name="Kwekwe District Hospital", level="district"))
    db.commit()
    facility_id = db.scalar(select(Facility.id))
    db.close()

    body = client.post(
        "/api/v2/users",
        json={"email": "nurse@example.org", "password": "password123",
              "role": "facility_user", "facility_id": facility_id},
        headers=headers,
    ).json()
    assert body["role"] == "facility_user"
    assert body["scope"] == {"facility_id": facility_id}
    assert body["active"] is True


def test_a_scoped_role_without_a_scope_is_a_400(client):
    """It passes every capability check and is bounded by nothing."""
    headers = _make_admin(client)
    response = client.post(
        "/api/v2/users",
        json={"email": "nurse@example.org", "password": "password123",
              "role": "facility_user"},
        headers=headers,
    )
    assert response.status_code == 400
    assert "needs facility_id" in response.json()["detail"]


def test_a_prototype_role_cannot_be_created(client):
    headers = _make_admin(client)
    response = client.post(
        "/api/v2/users",
        json={"email": "h@example.org", "password": "password123", "role": "hospital"},
        headers=headers,
    )
    assert response.status_code == 400
    assert "prototype account" in response.json()["detail"]


def test_a_short_password_is_rejected_by_the_schema(client):
    headers = _make_admin(client)
    response = client.post(
        "/api/v2/users",
        json={"email": "r@example.org", "password": "short", "role": "researcher"},
        headers=headers,
    )
    assert response.status_code == 422


def test_a_user_is_deactivated_never_deleted(client):
    """An audit row names a user id; a deleted user would let somebody erase
    their own trail by removing their account."""
    headers = _make_admin(client)
    created = client.post(
        "/api/v2/users",
        json={"email": "r@example.org", "password": "password123", "role": "researcher"},
        headers=headers,
    ).json()

    body = client.delete(f"/api/v2/users/{created['user_id']}", headers=headers).json()
    assert body["active"] is False

    db = _session(client)
    assert db.get(User, created["user_id"]) is not None
    db.close()


def test_an_administrator_cannot_deactivate_themselves(client):
    """With one administrator that would lock the system out of user
    management entirely."""
    headers = _make_admin(client)
    me = client.get("/api/v2/users", headers=headers).json()
    mine = next(u for u in me if u["email"] == "admin@example.org")
    response = client.delete(f"/api/v2/users/{mine['user_id']}", headers=headers)
    assert response.status_code == 400
    assert "your own account" in response.json()["detail"].lower()


def test_a_deactivated_user_cannot_sign_in(client):
    headers = _make_admin(client)
    created = client.post(
        "/api/v2/users",
        json={"email": "r@example.org", "password": "password123", "role": "researcher"},
        headers=headers,
    ).json()
    client.delete(f"/api/v2/users/{created['user_id']}", headers=headers)

    response = client.post(
        "/api/auth/login", json={"email": "r@example.org", "password": "password123"}
    )
    assert response.status_code == 401


# ------------------------------------------- the negative tests §16.3 wants

def test_a_researcher_cannot_manage_users(client):
    headers = _make_admin(client)
    client.post(
        "/api/v2/users",
        json={"email": "r@example.org", "password": "password123", "role": "researcher"},
        headers=headers,
    )
    researcher = _login(client, "r@example.org", "password123")

    response = client.post(
        "/api/v2/users",
        json={"email": "x@example.org", "password": "password123", "role": "researcher"},
        headers=researcher,
    )
    assert response.status_code == 403
    assert "may not admin.manage" in response.json()["detail"]


def test_a_refusal_writes_an_audit_row(client):
    """**The §16.3 requirement that makes the role model demonstrable.** A
    boundary nobody can show being enforced is a boundary nobody can show
    exists."""
    headers = _make_admin(client)
    client.post(
        "/api/v2/users",
        json={"email": "r@example.org", "password": "password123", "role": "researcher"},
        headers=headers,
    )
    researcher = _login(client, "r@example.org", "password123")
    client.post(
        "/api/v2/users",
        json={"email": "x@example.org", "password": "password123", "role": "researcher"},
        headers=researcher,
    )

    db = _session(client)
    refused = db.scalars(select(AuditLog).where(AuditLog.allowed == 0)).all()
    assert refused, "the refusal must be recorded"
    assert any(r.actor_email == "r@example.org" for r in refused)
    assert any(r.object_id == "admin.manage" for r in refused)
    db.close()


def test_the_refusal_names_what_the_role_cannot_see(client):
    """The message comes from §16.3's own "cannot see" column, so the caller
    learns the boundary rather than only that they hit one."""
    headers = _make_admin(client)
    client.post(
        "/api/v2/users",
        json={"email": "r@example.org", "password": "password123", "role": "researcher"},
        headers=headers,
    )
    researcher = _login(client, "r@example.org", "password123")
    detail = client.get("/api/v2/audit/refusals", headers=researcher).json()["detail"]
    assert "re-identification key" in detail


def test_an_administrator_cannot_read_a_persons_audit_trail(client):
    """§16.3: administrative access is not a licence to read records. An
    administrator who needs a record needs a clinical role too, which is a
    decision somebody makes."""
    headers = _make_admin(client)
    response = client.get("/api/v2/audit/persons/1", headers=headers)
    assert response.status_code == 403
    assert "not a licence" in response.json()["detail"]


def test_a_village_health_worker_can_read_a_persons_audit_trail(client):
    """Checking who has touched a record they are responsible for is not an
    administrative act."""
    headers = _make_admin(client)
    client.post(
        "/api/v2/users",
        json={"email": "v@example.org", "password": "password123",
              "role": "village_health_worker", "site_ids": [3]},
        headers=headers,
    )
    worker = _login(client, "v@example.org", "password123")
    assert client.get("/api/v2/audit/persons/1", headers=worker).status_code == 200


def test_reading_the_trail_is_itself_audited(client):
    """Not circular pedantry: an audit log nobody's reads are recorded in is
    a log that can be mined quietly."""
    headers = _make_admin(client)
    client.post(
        "/api/v2/users",
        json={"email": "v@example.org", "password": "password123",
              "role": "village_health_worker", "site_ids": [3]},
        headers=headers,
    )
    worker = _login(client, "v@example.org", "password123")
    client.get("/api/v2/audit/persons/42", headers=worker)

    db = _session(client)
    rows = db.scalars(
        select(AuditLog).where(AuditLog.person_id == 42, AuditLog.object_type == "audit_log")
    ).all()
    assert rows and rows[0].actor_email == "v@example.org"
    db.close()


def test_the_audit_routes_need_a_token(client):
    assert client.get("/api/v2/audit/refusals").status_code == 401
    assert client.get("/api/v2/users").status_code == 401


# --------------------------------------------------------------- login

def test_a_real_user_can_sign_in_with_a_hashed_password(client):
    headers = _make_admin(client)
    body = client.get("/api/auth/me", headers=headers).json()
    assert body["role"] == "administrator"
    assert body["prototype_account"] is False
    assert "admin.manage" in body["capabilities"]


def test_the_password_is_not_stored_in_plaintext(client):
    _make_admin(client)
    db = _session(client)
    user = db.scalar(select(User))
    assert "password123" not in user.password_hash
    assert user.password_hash.startswith("scrypt$")
    db.close()


def test_a_successful_login_is_audited(client):
    _make_admin(client)
    db = _session(client)
    rows = db.scalars(select(AuditLog).where(AuditLog.action == "auth.login")).all()
    assert rows and rows[-1].actor_email == "admin@example.org"
    db.close()


def test_a_failed_login_is_audited(client):
    _make_admin(client)
    client.post(
        "/api/auth/login",
        json={"email": "admin@example.org", "password": "wrong-password"},
    )
    db = _session(client)
    rows = db.scalars(
        select(AuditLog).where(AuditLog.action == "auth.login_failed")
    ).all()
    assert rows, (
        "credential stuffing against a login with no rate limiting is "
        "invisible otherwise (§15.4)"
    )
    db.close()


def test_a_failed_login_records_no_credentials(client):
    """No personal data in a log line — and an email in a failed-login row is
    a list of accounts somebody tried."""
    _make_admin(client)
    client.post(
        "/api/auth/login",
        json={"email": "admin@example.org", "password": "hunter2"},
    )
    db = _session(client)
    row = db.scalars(
        select(AuditLog).where(AuditLog.action == "auth.login_failed")
    ).all()[-1]
    assert "hunter2" not in (row.details or "")
    assert "admin@example.org" not in (row.details or "")
    db.close()


def test_a_missing_secret_key_refuses_to_issue_a_token(client, monkeypatch):
    """It used to default to "dev-secret", a value published in this
    repository — anyone could mint an administrator token against a
    misconfigured instance."""
    monkeypatch.delenv("SECRET_KEY", raising=False)
    response = client.post(
        "/api/auth/login",
        json={"email": "hospital@silicaguard.health", "password": "hospital123"},
    )
    assert response.status_code == 503
    assert "no default" in response.json()["detail"]


def test_an_inbound_request_id_is_honoured(client):
    """Which is what makes a mobile synchronisation traceable from the
    handset's own log."""
    headers = _make_admin(client)
    headers["X-Request-Id"] = "handset-abc-123"
    client.post(
        "/api/v2/users",
        json={"email": "r@example.org", "password": "password123", "role": "researcher"},
        headers=headers,
    )
    db = _session(client)
    rows = db.scalars(
        select(AuditLog).where(AuditLog.request_id == "handset-abc-123")
    ).all()
    assert rows
    db.close()
