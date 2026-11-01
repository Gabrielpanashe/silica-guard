def test_login_success(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "hospital@silicaguard.health", "password": "hospital123"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "hospital"
    assert resp.json()["access_token"]


def test_login_bad_password(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "hospital@silicaguard.health", "password": "wrong"},
    )
    assert resp.status_code == 401


def test_login_unknown_email(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": "whatever"},
    )
    assert resp.status_code == 401


def test_me_without_token_is_rejected(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401  # HTTPBearer rejects a missing header before our code runs
    assert resp.json()["detail"] == "Not authenticated"


def test_me_with_invalid_token_is_rejected(client):
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"})
    assert resp.status_code == 401


def test_me_with_valid_token(client):
    login = client.post(
        "/api/auth/login",
        json={"email": "cimas@silicaguard.health", "password": "cimas123"},
    )
    token = login.json()["access_token"]
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    # Additive as of item 1.13: the response gained `scope`, `capabilities`,
    # `cannot` (§16.3's own "cannot see" column) and `prototype_account`, so
    # a client renders the boundary from the server's definition rather than
    # from a copy. The original two fields are unchanged.
    assert body["email"] == "cimas@silicaguard.health"
    assert body["role"] == "cimas"
    assert body["prototype_account"] is True, (
        "these are the environment-variable accounts, and they stop working "
        "the moment a real user exists"
    )
    assert "aggregate.read" in body["capabilities"]
    assert body["cannot"]
