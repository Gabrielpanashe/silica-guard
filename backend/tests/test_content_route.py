"""GET /api/v2/content — the snapshot a client caches so the words it shows
offline are the reviewed ones.

Master Reference v1.0 §8.4 and §10.1. The first `/api/v2` route to land. What
matters here is the boundary rather than the plumbing: only approved content
leaves the server, the language asked for is the language reported, and an
empty store answers cleanly rather than erroring — because until the Clinical
Lead approves version one, empty is the correct state.
"""

import pytest
from sqlalchemy.orm import Session

import database
from services import content_store


def _store(client, *, status="approved"):
    """Write one message of each channel through the real loader, on the same
    session the route will read from."""
    gen = client.app.dependency_overrides[database.get_db]()
    db: Session = next(gen)
    doc = {
        "area": "route_test",
        "messages": [
            {
                "code": "route.sms.one",
                "channel": "sms",
                "status": status,
                "purpose": "Route test, SMS channel.",
                "placeholders": ["code"],
                "text": {
                    "en": "ROUTE TEST en, reference {code}.",
                    "sn": "ROUTE TEST sn, reference {code}.",
                    "nd": "ROUTE TEST nd, reference {code}.",
                },
            },
            {
                "code": "route.app.two",
                "channel": "app",
                "status": status,
                "purpose": "Route test, app channel, English only.",
                "text": {"en": "ROUTE TEST en app only."},
            },
        ],
    }
    if status == "approved":
        for message in doc["messages"]:
            message["approved_by"] = "Clinical Lead"
            message["approved_at"] = "2026-11-01"
        # An approved message needs all three languages, so the English-only
        # one is stored at review and promoted in the row, which is how the
        # fallback path gets exercised at all (see content_store.load).
        doc["messages"][1]["status"] = "review"
        doc["messages"][1].pop("approved_by")
        doc["messages"][1].pop("approved_at")

    content_store.load(db, doc)
    if status == "approved":
        from datetime import datetime

        from db_models import Message
        from sqlalchemy import select

        row = db.scalar(select(Message).where(Message.code == "route.app.two"))
        row.status = "approved"
        row.approved_by = "Clinical Lead"
        row.approved_at = datetime(2026, 11, 1)
    db.commit()
    db.close()


def test_an_empty_store_answers_cleanly(client):
    """Until version one is approved the store is empty, and that is the
    correct state rather than a failure."""
    response = client.get("/api/v2/content")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 0 and body["messages"] == []
    assert body["language"] == "en"


def test_approved_content_is_served(client):
    _store(client)
    body = client.get("/api/v2/content").json()
    assert body["count"] == 2
    assert [m["code"] for m in body["messages"]] == ["route.app.two", "route.sms.one"]
    assert body["messages"][1]["text"].startswith("ROUTE TEST en")


def test_draft_content_is_never_served(client):
    """The one assertion that matters. An unapproved string in this response
    is an unreviewed string cached on a handset in a gold-panning area."""
    _store(client, status="draft")
    body = client.get("/api/v2/content").json()
    assert body["count"] == 0


def test_a_language_is_served_when_it_exists(client):
    _store(client)
    body = client.get("/api/v2/content?language=nd").json()
    served = {m["code"]: m for m in body["messages"]}
    assert served["route.sms.one"]["language"] == "nd"
    assert served["route.sms.one"]["text"].startswith("ROUTE TEST nd")


def test_a_missing_language_falls_back_and_says_which_it_used(client):
    """There is no machine translation anywhere in this system, so an
    unauthored language falls back to the authored English and the row reports
    `en` — the client can see it has an authoring gap."""
    _store(client)
    body = client.get("/api/v2/content?language=nd").json()
    served = {m["code"]: m for m in body["messages"]}
    assert served["route.app.two"]["language"] == "en"
    assert body["language"] == "nd", "the request's language is echoed at the top"


@pytest.mark.parametrize("language", ["fr", "sw", "", "EN", "en-ZW"])
def test_an_unsupported_language_is_rejected(client, language):
    """An unsupported language is an error, not a fallback: a silent fallback
    would be indistinguishable from a translation having happened."""
    response = client.get(f"/api/v2/content?language={language}")
    assert response.status_code == 400
    assert "machine translation" in response.json()["detail"]


def test_the_channel_filter_narrows_the_snapshot(client):
    """The USSD gateway and the handset need different subsets, and neither
    needs to download the other's."""
    _store(client)
    body = client.get("/api/v2/content?channel=sms").json()
    assert [m["code"] for m in body["messages"]] == ["route.sms.one"]


def test_an_unknown_channel_is_rejected(client):
    response = client.get("/api/v2/content?channel=whatsapp")
    assert response.status_code == 400


def test_the_watermark_supports_an_incremental_refresh(client):
    _store(client)
    assert client.get("/api/v2/content").json()["count"] == 2
    body = client.get("/api/v2/content?since=2099-01-01T00:00:00Z").json()
    assert body["count"] == 0


def test_a_malformed_watermark_is_rejected(client):
    response = client.get("/api/v2/content?since=last-tuesday")
    assert response.status_code == 400


def test_the_placeholder_contract_travels_with_the_message(client):
    """The client substitutes offline, so it has to know what to supply."""
    _store(client)
    served = {m["code"]: m for m in client.get("/api/v2/content").json()["messages"]}
    assert served["route.sms.one"]["placeholders"] == ["code"]
    assert served["route.app.two"]["placeholders"] == []


def test_the_route_needs_no_token(client):
    """Deliberate, on the same precedent as the screening path: the mobile
    application never logs in, and this returns nothing about any person."""
    assert client.get("/api/v2/content").status_code == 200
    assert client.get(
        "/api/v2/content", headers={"Authorization": "Bearer nonsense"}
    ).status_code == 200
