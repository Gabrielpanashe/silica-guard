from unittest.mock import patch

RED_RESULT = {
    "tier": "RED",
    "confidence": 0.95,
    "contributing_factors": ["over 10 years exposure", "no PPE"],
    "explanation_english": "Urgent referral needed.",
}

ORANGE_RESULT = {
    "tier": "ORANGE",
    "confidence": 0.85,
    "contributing_factors": ["10+ years exposure"],
    "explanation_english": "Routine referral needed.",
}

GREEN_RESULT = {
    "tier": "GREEN",
    "confidence": 0.9,
    "contributing_factors": ["minimal exposure"],
    "explanation_english": "No concerns.",
}


def _login(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "hospital@silicaguard.health", "password": "hospital123"},
    )
    return resp.json()["access_token"]


def _register_miner(client, phone="+263711110001"):
    resp = client.post(
        "/api/miners",
        json={"name": "Referral Test Miner", "phone": phone, "mine_site": "Test Site"},
    )
    return resp.json()["id"]


def _ten_answers():
    return [
        {"question_code": f"Q{i}", "answer_value": "x", "answer_score": 1}
        for i in range(10)
    ]


def test_red_screening_creates_referral(client):
    miner_id = _register_miner(client, phone="+263711110002")

    with patch("routers.screening.assess_risk", return_value=RED_RESULT):
        resp = client.post(
            "/api/screen", json={"miner_id": miner_id, "answers": _ten_answers()}
        )
    assert resp.status_code == 200

    token = _login(client)
    referrals = client.get(
        "/api/referrals", headers={"Authorization": f"Bearer {token}"}
    ).json()
    assert len(referrals) == 1
    assert referrals[0]["miner_name"] == "Referral Test Miner"
    assert referrals[0]["tier"] == "RED"
    # conftest mocks the hospital pre-alert SMS to always succeed, so status
    # advances past "open" to "pre_alerted" as part of referral creation.
    assert referrals[0]["status"] == "pre_alerted"
    assert referrals[0]["pre_alert_sent"] is True
    assert referrals[0]["deadline"] is not None


def test_orange_screening_creates_referral(client):
    miner_id = _register_miner(client, phone="+263711110007")

    with patch("routers.screening.assess_risk", return_value=ORANGE_RESULT):
        resp = client.post(
            "/api/screen", json={"miner_id": miner_id, "answers": _ten_answers()}
        )
    assert resp.status_code == 200

    token = _login(client)
    referrals = client.get(
        "/api/referrals", headers={"Authorization": f"Bearer {token}"}
    ).json()
    assert len(referrals) == 1
    assert referrals[0]["tier"] == "ORANGE"


def test_green_screening_does_not_create_referral(client):
    miner_id = _register_miner(client, phone="+263711110003")

    with patch("routers.screening.assess_risk", return_value=GREEN_RESULT):
        resp = client.post(
            "/api/screen", json={"miner_id": miner_id, "answers": _ten_answers()}
        )
    assert resp.status_code == 200

    token = _login(client)
    referrals = client.get(
        "/api/referrals", headers={"Authorization": f"Bearer {token}"}
    ).json()
    assert referrals == []


def test_ussd_red_creates_referral(client):
    session_id = "ussd-referral-test"
    phone = "+263711110004"
    url = "/api/ussd"

    def post(text):
        return client.post(
            url,
            data={
                "sessionId": session_id,
                "phoneNumber": phone,
                "serviceCode": "*384*1#",
                "text": text,
            },
        ).text

    post("")
    # Q1=1, Q2=4, Q3=1, Q4=1, Q5=1, Q6=3 (severe breathlessness -> dangerous trigger -> RED)
    choices = ["1", "4", "1", "1", "1", "3", "1", "1", "1", "1"]
    accumulated = []
    reply = ""
    for choice in choices:
        accumulated.append(choice)
        reply = post("*".join(accumulated))

    assert reply.startswith("END ")

    token = _login(client)
    referrals = client.get(
        "/api/referrals", headers={"Authorization": f"Bearer {token}"}
    ).json()
    assert len(referrals) == 1
    assert referrals[0]["tier"] == "RED"


def test_referrals_requires_auth(client):
    resp = client.get("/api/referrals")
    assert resp.status_code == 401


def test_patch_referral_status_to_closed(client):
    miner_id = _register_miner(client, phone="+263711110005")
    with patch("routers.screening.assess_risk", return_value=RED_RESULT):
        client.post("/api/screen", json={"miner_id": miner_id, "answers": _ten_answers()})

    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    referral_id = client.get("/api/referrals", headers=headers).json()[0]["id"]

    resp = client.patch(
        f"/api/referrals/{referral_id}", json={"status": "closed"}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "closed"
    assert resp.json()["closed_at"] is not None


def test_patch_referral_invalid_status_rejected(client):
    miner_id = _register_miner(client, phone="+263711110006")
    with patch("routers.screening.assess_risk", return_value=RED_RESULT):
        client.post("/api/screen", json={"miner_id": miner_id, "answers": _ten_answers()})

    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    referral_id = client.get("/api/referrals", headers=headers).json()[0]["id"]

    resp = client.patch(
        f"/api/referrals/{referral_id}", json={"status": "BOGUS"}, headers=headers
    )
    assert resp.status_code == 422


def test_patch_unknown_referral_404(client):
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.patch(
        "/api/referrals/999999", json={"status": "closed"}, headers=headers
    )
    assert resp.status_code == 404
