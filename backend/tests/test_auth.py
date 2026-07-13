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
    assert resp.json() == {"email": "cimas@silicaguard.health", "role": "cimas"}
