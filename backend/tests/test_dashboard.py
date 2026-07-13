def _login(client, email="hospital@silicaguard.health", password="hospital123"):
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    return resp.json()["access_token"]


def test_dashboard_requires_auth(client):
    resp = client.get("/api/dashboard/week")
    assert resp.status_code == 401


def test_dashboard_with_no_data(client):
    token = _login(client)
    resp = client.get(
        "/api/dashboard/week", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_screened"] == 0
    assert body["high_risk_count"] == 0
    assert body["referral_completion_rate"] == 0.0
    assert body["site_breakdown"] == []
