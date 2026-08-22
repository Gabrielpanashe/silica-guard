"""POST /api/education/broadcast — Teach Mode's SMS-channel demonstration,
22 August 2026. See services/education_messages.py's module docstring."""


def _login(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "hospital@silicaguard.health", "password": "hospital123"},
    )
    return resp.json()["access_token"]


def test_broadcast_requires_auth(client):
    resp = client.post(
        "/api/education/broadcast", json={"site": "Sherwood Mine", "topic": "mask_that_works"}
    )
    assert resp.status_code == 401


def test_broadcast_unknown_topic_422s(client):
    token = _login(client)
    resp = client.post(
        "/api/education/broadcast",
        json={"site": "Sherwood Mine", "topic": "not_a_real_topic"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_broadcast_sends_to_every_worker_at_site_case_insensitively(client):
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    client.post(
        "/api/workers", json={"name": "W1", "phone": "+263700666001", "site": "Sherwood Mine"}
    )
    client.post(
        "/api/workers", json={"name": "W2", "phone": "+263700666002", "site": "sherwood mine"}
    )
    client.post(
        "/api/workers", json={"name": "Other", "phone": "+263700666003", "site": "Other Mine"}
    )

    resp = client.post(
        "/api/education/broadcast",
        json={"site": "Sherwood Mine", "topic": "mask_that_works"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["recipient_count"] == 2
    assert body["sent_count"] == 2
    assert body["topic"] == "mask_that_works"
    assert body["message_preview"]  # non-empty Shona text


def test_broadcast_with_no_workers_at_site_sends_zero(client):
    token = _login(client)
    resp = client.post(
        "/api/education/broadcast",
        json={"site": "Empty Mine", "topic": "red_flag_signs"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["recipient_count"] == 0
    assert body["sent_count"] == 0
