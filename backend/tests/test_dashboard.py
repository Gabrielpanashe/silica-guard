from unittest.mock import patch

import database
from services.population_intelligence import _fallback_narrative


def _seed_outreach_visit(site, scheduled_date, report_generated=0, screened_count=0, expected_headcount=10):
    conn = database.get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO outreach_visits
               (site, scheduled_date, expected_headcount, screened_count, health_workers, report_generated)
               VALUES (?, ?, ?, ?, '[]', ?)""",
            (site, scheduled_date, expected_headcount, screened_count, report_generated),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _login(client, email="hospital@silicaguard.health", password="hospital123"):
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    return resp.json()["access_token"]


def _register(client, phone, site="Test Site"):
    resp = client.post(
        "/api/workers", json={"name": f"Worker {phone[-3:]}", "phone": phone, "site": site}
    )
    return resp.json()["id"]


def _screen(client, miner_id, result):
    with patch("routers.screening.assess_risk", return_value=result):
        return client.post(
            "/api/screen",
            json={
                "miner_id": miner_id,
                "answers": [
                    {"question_code": f"Q{i}", "answer_value": "x", "answer_score": 1}
                    for i in range(10)
                ],
                "channel": "APP",
            },
        ).json()


def test_dashboard_today_unauthenticated(client):
    resp = client.get("/api/dashboard/today")
    assert resp.status_code != 401


def test_dashboard_today_empty(client):
    resp = client.get("/api/dashboard/today")
    body = resp.json()
    assert body["screened_today"] == 0
    assert body["todays_log"] == []
    assert body["refer_now"] == {"count": 0, "items": []}
    assert body["watch"] == {"count": 0, "items": []}


def test_dashboard_today_counts_screening_and_refer_now(client):
    miner_id = _register(client, "+263791000001")
    _screen(
        client,
        miner_id,
        {"tier": "RED", "confidence": 0.9, "contributing_factors": ["x"], "explanation_english": "x"},
    )

    body = client.get("/api/dashboard/today").json()
    assert body["screened_today"] == 1
    assert len(body["todays_log"]) == 1
    assert body["todays_log"][0]["phone"] == "+263791000001"
    assert body["refer_now"]["count"] == 1
    assert body["refer_now"]["items"][0]["tier"] == "RED"
    assert body["refer_now"]["items"][0]["phone"] == "+263791000001"


def test_dashboard_today_watch_reflects_yellow_tier(client):
    miner_id = _register(client, "+263791000002")
    _screen(
        client,
        miner_id,
        {"tier": "YELLOW", "confidence": 0.8, "contributing_factors": ["x"], "explanation_english": "x"},
    )

    body = client.get("/api/dashboard/today").json()
    assert body["watch"]["count"] == 1
    assert body["watch"]["items"][0]["tier"] == "YELLOW"
    assert body["refer_now"]["count"] == 0  # YELLOW never creates a referral


def test_dashboard_today_referral_drops_off_after_attended(client):
    miner_id = _register(client, "+263791000003")
    _screen(
        client,
        miner_id,
        {"tier": "RED", "confidence": 0.9, "contributing_factors": ["x"], "explanation_english": "x"},
    )
    body = client.get("/api/dashboard/today").json()
    referral_id = body["refer_now"]["items"][0]["referral_id"]

    token = _login(client)
    client.patch(
        f"/api/referrals/{referral_id}",
        json={"status": "attended"},
        headers={"Authorization": f"Bearer {token}"},
    )

    body = client.get("/api/dashboard/today").json()
    assert body["refer_now"]["count"] == 0  # taken action -> off the worklist


def test_dashboard_today_site_filter(client):
    a = _register(client, "+263791000004", site="Site A")
    _register(client, "+263791000005", site="Site B")
    _screen(
        client, a,
        {"tier": "GREEN", "confidence": 0.9, "contributing_factors": ["x"], "explanation_english": "x"},
    )

    body = client.get("/api/dashboard/today", params={"site": "site a"}).json()
    assert body["screened_today"] == 1

    body = client.get("/api/dashboard/today", params={"site": "Site B"}).json()
    assert body["screened_today"] == 0


def test_dashboard_today_includes_outreach_visits(client):
    _seed_outreach_visit("Sherwood Mine", "2026-08-20", expected_headcount=15, screened_count=3)

    body = client.get("/api/dashboard/today").json()

    assert len(body["outreach_visits"]) == 1
    visit = body["outreach_visits"][0]
    assert visit["site"] == "Sherwood Mine"
    assert visit["expected_headcount"] == 15
    assert visit["screened_count"] == 3
    assert visit["report_generated"] is False
    assert visit["tier_distribution"] is None  # not ready yet


def test_dashboard_today_outreach_visit_report_matches_get_outreach(client):
    """Same shared mapping (services.outreach.visit_to_out) — the
    unauthenticated dashboard/today view and the authenticated /api/outreach
    view must never disagree about a completed visit's report."""
    miner_id = _register(client, "+263791000006", site="Sherwood Mine")
    visit_id = _seed_outreach_visit("Sherwood Mine", "2026-07-01", report_generated=1)

    with patch("routers.screening.assess_risk", return_value={
        "tier": "RED", "confidence": 0.9, "contributing_factors": ["x"], "explanation_english": "x",
    }):
        client.post(
            "/api/screen",
            json={
                "miner_id": miner_id,
                "outreach_visit_id": visit_id,
                "answers": [
                    {"question_code": f"Q{i}", "answer_value": "x", "answer_score": 1}
                    for i in range(10)
                ],
                "channel": "APP",
            },
        )

    today_body = client.get("/api/dashboard/today", params={"site": "Sherwood Mine"}).json()
    today_visit = next(v for v in today_body["outreach_visits"] if v["id"] == visit_id)

    token = _login(client)
    outreach_body = client.get(
        "/api/outreach", headers={"Authorization": f"Bearer {token}"}
    ).json()
    auth_visit = next(v for v in outreach_body if v["id"] == visit_id)

    assert today_visit["tier_distribution"] == auth_visit["tier_distribution"] == {"GREEN": 0, "YELLOW": 0, "ORANGE": 0, "RED": 1}
    assert today_visit["referral_list"] == auth_visit["referral_list"]


def test_dashboard_today_outreach_visits_site_filtered(client):
    _seed_outreach_visit("Site A", "2026-08-20")
    _seed_outreach_visit("Site B", "2026-08-21")

    body = client.get("/api/dashboard/today", params={"site": "site a"}).json()
    assert [v["site"] for v in body["outreach_visits"]] == ["Site A"]


def test_dashboard_requires_auth(client):
    resp = client.get("/api/dashboard/week")
    assert resp.status_code == 401


def test_dashboard_with_no_data(client):
    token = _login(client)
    with patch(
        "routers.dashboard.generate_weekly_narrative", return_value="mocked narrative"
    ):
        resp = client.get(
            "/api/dashboard/week", headers={"Authorization": f"Bearer {token}"}
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_screened"] == 0
    assert body["high_risk_count"] == 0
    assert body["referral_completion_rate"] == 0.0
    assert body["site_breakdown"] == []
    assert body["ai_narrative"] == "mocked narrative"
    assert body["tier_distribution"] == {"GREEN": 0, "YELLOW": 0, "ORANGE": 0, "RED": 0}


def test_dashboard_tier_distribution_reflects_real_screenings(client):
    with patch(
        "routers.screening.assess_risk",
        return_value={
            "tier": "RED",
            "confidence": 0.9,
            "contributing_factors": ["x"],
            "explanation_english": "x",
        },
    ):
        worker = client.post(
            "/api/workers",
            json={"name": "Dash Test", "phone": "+263790000001", "site": "Test Site"},
        ).json()
        client.post(
            "/api/screen",
            json={
                "miner_id": worker["id"],
                "answers": [
                    {"question_code": f"Q{i}", "answer_value": "x", "answer_score": 1}
                    for i in range(10)
                ],
            },
        )

    token = _login(client)
    with patch(
        "routers.dashboard.generate_weekly_narrative", return_value="mocked narrative"
    ) as mock_narrative:
        resp = client.get(
            "/api/dashboard/week", headers={"Authorization": f"Bearer {token}"}
        )

    body = resp.json()
    assert body["tier_distribution"]["RED"] == 1
    assert body["total_screened"] == 1
    assert body["high_risk_count"] == 1
    # Real stats were passed through to the narrative generator, not just called.
    mock_narrative.assert_called_once()
    call_args = mock_narrative.call_args[0]
    assert call_args[0] == 1  # total_screened
    assert call_args[1] == 1  # high_risk_count


def test_fallback_narrative_is_deterministic_and_mentions_top_site():
    text = _fallback_narrative(
        total_screened=10,
        high_risk_count=3,
        referral_completion_rate=0.5,
        site_breakdown=[
            {"mine_site": "Small Site", "count": 2},
            {"mine_site": "Big Site", "count": 8},
        ],
    )
    assert "10" in text
    assert "3" in text
    assert "Big Site" in text
    assert "50%" in text


def test_fallback_narrative_handles_empty_site_breakdown():
    text = _fallback_narrative(
        total_screened=0, high_risk_count=0, referral_completion_rate=0.0, site_breakdown=[]
    )
    assert "no site data" in text
