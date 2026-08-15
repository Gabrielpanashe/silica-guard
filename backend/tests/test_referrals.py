import re
from unittest.mock import patch

import database

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
        "/api/workers",
        json={"name": "Referral Test Miner", "phone": phone, "site": "Test Site"},
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


def test_referral_falls_back_to_default_hospital_name_when_no_facilities_seeded(client):
    """No facilities table rows in this test's throwaway DB — facility
    matching should degrade to the same literal default the old hardcoded
    behaviour used, not crash or leave the field oddly blank."""
    miner_id = _register_miner(client, phone="+263711110008")

    with patch("routers.screening.assess_risk", return_value=RED_RESULT):
        client.post("/api/screen", json={"miner_id": miner_id, "answers": _ten_answers()})

    token = _login(client)
    referral = client.get(
        "/api/referrals", headers={"Authorization": f"Bearer {token}"}
    ).json()[0]
    assert referral["facility_id"] is None
    assert referral["mine_site"] == "Test Site"
    assert referral["reminder_stage"] == 0


def test_referral_matches_seeded_facility(client):
    conn = database.get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO facilities (name, level) VALUES (?, ?)",
            ("Kwekwe District Hospital", "district_hospital"),
        )
        hospital_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    miner_id = _register_miner(client, phone="+263711110009")
    with patch("routers.screening.assess_risk", return_value=RED_RESULT):
        client.post("/api/screen", json={"miner_id": miner_id, "answers": _ten_answers()})

    token = _login(client)
    referral = client.get(
        "/api/referrals", headers={"Authorization": f"Bearer {token}"}
    ).json()[0]
    assert referral["facility_id"] == hospital_id
    assert referral["facility_name"] == "Kwekwe District Hospital"


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


# --- Referral code (14 August 2026, master doc v6.0 Section 1.1) ---

_CODE_PATTERN = re.compile(r"^SG-[A-Z0-9]{4}$")


def test_referral_gets_a_code_matching_the_sg_format(client):
    miner_id = _register_miner(client, phone="+263711110010")
    with patch("routers.screening.assess_risk", return_value=RED_RESULT):
        client.post("/api/screen", json={"miner_id": miner_id, "answers": _ten_answers()})

    token = _login(client)
    referral = client.get(
        "/api/referrals", headers={"Authorization": f"Bearer {token}"}
    ).json()[0]
    assert _CODE_PATTERN.match(referral["referral_code"])


def test_lookup_referral_by_code_unauthenticated(client):
    miner_id = _register_miner(client, phone="+263711110011")
    with patch("routers.screening.assess_risk", return_value=RED_RESULT):
        client.post("/api/screen", json={"miner_id": miner_id, "answers": _ten_answers()})

    token = _login(client)
    referral = client.get(
        "/api/referrals", headers={"Authorization": f"Bearer {token}"}
    ).json()[0]
    code = referral["referral_code"]

    # No Authorization header at all — this is the point.
    resp = client.get(f"/api/referrals/lookup/{code}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["referral_code"] == code
    assert body["tier"] == "RED"
    assert body["miner_name"] == "Referral Test Miner"
    assert body["status"] == "pre_alerted"
    assert body["attended_at"] is None


def test_lookup_unknown_code_404(client):
    resp = client.get("/api/referrals/lookup/SG-ZZZZ")
    assert resp.status_code == 404


def test_confirm_attendance_marks_referral_attended(client):
    miner_id = _register_miner(client, phone="+263711110012")
    with patch("routers.screening.assess_risk", return_value=RED_RESULT):
        client.post("/api/screen", json={"miner_id": miner_id, "answers": _ten_answers()})

    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    referral = client.get("/api/referrals", headers=headers).json()[0]
    code = referral["referral_code"]

    resp = client.post(f"/api/referrals/lookup/{code}/confirm-attendance")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "attended"
    assert body["attended_at"] is not None

    # Confirmed on the authenticated view too, not just the response echo.
    updated = client.get("/api/referrals", headers=headers).json()[0]
    assert updated["status"] == "attended"
    assert updated["attended_at"] is not None


def test_confirm_attendance_twice_returns_409(client):
    miner_id = _register_miner(client, phone="+263711110013")
    with patch("routers.screening.assess_risk", return_value=RED_RESULT):
        client.post("/api/screen", json={"miner_id": miner_id, "answers": _ten_answers()})

    token = _login(client)
    referral = client.get(
        "/api/referrals", headers={"Authorization": f"Bearer {token}"}
    ).json()[0]
    code = referral["referral_code"]

    first = client.post(f"/api/referrals/lookup/{code}/confirm-attendance")
    assert first.status_code == 200
    second = client.post(f"/api/referrals/lookup/{code}/confirm-attendance")
    assert second.status_code == 409


def test_confirm_attendance_unknown_code_404(client):
    resp = client.post("/api/referrals/lookup/SG-ZZZZ/confirm-attendance")
    assert resp.status_code == 404
