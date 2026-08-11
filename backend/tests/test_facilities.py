def test_list_facilities_empty_by_default(client):
    resp = client.get("/api/facilities")
    assert resp.status_code == 200
    assert resp.json() == []


def test_facilities_endpoint_unauthenticated(client):
    """No login required — same precedent as GET /api/mines, powers the
    mobile Outreach Planner's nearest-hospital preview, which has no
    dashboard session."""
    resp = client.get("/api/facilities")
    assert resp.status_code != 401


def test_list_facilities_returns_seeded_rows(client):
    import database

    conn = database.get_connection()
    try:
        conn.execute(
            "INSERT INTO facilities (name, level, address, phone, latitude, longitude) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("Kwekwe District Hospital", "district_hospital", "Corner Robert Mugabe / Sixth Ave", "055-24000", -18.9281, 29.8149),
        )
        conn.execute(
            "INSERT INTO facilities (name, level, address, phone, latitude, longitude) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("Sherwood Clinic", "clinic", "Sherwood Mine, Kwekwe", "055-24101", None, None),
        )
        conn.commit()
    finally:
        conn.close()

    resp = client.get("/api/facilities")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    levels = {f["level"] for f in body}
    assert levels == {"district_hospital", "clinic"}
