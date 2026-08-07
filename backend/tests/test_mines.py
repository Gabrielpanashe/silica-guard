def test_list_mines_empty_by_default(client):
    resp = client.get("/api/mines")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_and_list_mine(client):
    resp = client.post(
        "/api/mines", json={"name": "Test Mine", "district": "Kwekwe"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Test Mine"
    assert body["district"] == "Kwekwe"
    assert body["province"] == "Midlands"  # default

    listed = client.get("/api/mines").json()
    assert len(listed) == 1
    assert listed[0]["name"] == "Test Mine"


def test_duplicate_mine_name_returns_409(client):
    client.post("/api/mines", json={"name": "Dup Mine", "district": "Gweru"})
    resp = client.post("/api/mines", json={"name": "Dup Mine", "district": "Gweru"})
    assert resp.status_code == 409


def test_mines_endpoint_unauthenticated(client):
    """No login required — matches POST /api/workers / POST /api/screen,
    a VHW in the field has no dashboard session."""
    resp = client.get("/api/mines")
    assert resp.status_code != 401
