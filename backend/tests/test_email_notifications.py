"""Dedicated coverage of services/email_notifications.py, same pattern as
tests/test_notifications.py: imports the real function by name at
collection time so conftest.py's autouse _mock_notifications fixture (which
now also mocks email_notifications.send_referral_alert_email for every
other test) doesn't swallow this file's own tests.

12 August: rewritten for the Resend HTTP API swap (was Gmail SMTP —
Render's free tier blocks outbound SMTP entirely, confirmed live). Patches
httpx.post, same one level of mocking test_notifications.py already uses
for Africa's Talking, so these tests never touch a real network regardless
of RESEND_API_KEY being set in the environment.
"""

from unittest.mock import Mock, patch

import pytest

import database
from services.email_notifications import send_referral_alert_email


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_URL", str(tmp_path / "email_notifications_test.db"))
    database.init_db()
    connection = database.get_connection()
    yield connection
    connection.close()


@pytest.fixture
def worker_id(conn):
    conn.execute(
        "INSERT INTO miners (name, phone, mine_site) VALUES (?, ?, ?)",
        ("Email Test Worker", "+263700333001", "Test Site"),
    )
    conn.commit()
    return conn.execute(
        "SELECT id FROM miners WHERE phone = ?", ("+263700333001",)
    ).fetchone()["id"]


def _notification_rows(conn):
    return conn.execute(
        "SELECT * FROM notifications WHERE channel = 'email' ORDER BY id"
    ).fetchall()


def _mock_success_response():
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.text = '{"id": "fake-resend-id"}'
    return resp


def test_skips_and_logs_when_credentials_missing(conn, worker_id, monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("EMAIL_TO", raising=False)
    monkeypatch.delenv("EMAIL_ADDRESS", raising=False)

    with patch("services.email_notifications.httpx.post") as mock_post:
        ok = send_referral_alert_email(
            worker_id, "Email Test Worker", "+263700333001", "Test Site",
            "RED", "Kwekwe District Hospital", "2026-08-13 10:00 UTC", ["Factor A"],
        )

    assert ok is False
    mock_post.assert_not_called()  # never even tries the API call without credentials
    rows = _notification_rows(conn)
    assert len(rows) == 1
    assert rows[0]["delivery_status"] == "skipped"
    assert rows[0]["worker_id"] == worker_id


def test_sends_and_logs_on_success(conn, worker_id, monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_fake_key")
    monkeypatch.setenv("EMAIL_TO", "demo@example.com")
    monkeypatch.delenv("RESEND_FROM_EMAIL", raising=False)

    with patch("services.email_notifications.httpx.post", return_value=_mock_success_response()) as mock_post:
        ok = send_referral_alert_email(
            worker_id, "Email Test Worker", "+263700333001", "Test Site",
            "RED", "Kwekwe District Hospital", "2026-08-13 10:00 UTC", ["Factor A"],
        )

    assert ok is True
    mock_post.assert_called_once()
    call = mock_post.call_args
    assert call[0][0] == "https://api.resend.com/emails"
    assert call.kwargs["headers"]["Authorization"] == "Bearer re_fake_key"
    payload = call.kwargs["json"]
    assert payload["to"] == ["demo@example.com"]
    assert payload["from"] == "SilicaGuard <onboarding@resend.dev>"  # default, no domain verified
    assert "RED" in payload["subject"]

    rows = _notification_rows(conn)
    assert len(rows) == 1
    assert rows[0]["delivery_status"] == "sent"


def test_falls_back_to_email_address_when_email_to_unset(conn, worker_id, monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_fake_key")
    monkeypatch.delenv("EMAIL_TO", raising=False)
    monkeypatch.setenv("EMAIL_ADDRESS", "fallback@example.com")

    with patch("services.email_notifications.httpx.post", return_value=_mock_success_response()) as mock_post:
        send_referral_alert_email(
            worker_id, "Email Test Worker", "+263700333001", "Test Site",
            "ORANGE", "Kwekwe District Hospital", "2026-08-20 10:00 UTC", [],
        )

    assert mock_post.call_args.kwargs["json"]["to"] == ["fallback@example.com"]


def test_uses_custom_from_when_domain_verified(conn, worker_id, monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_fake_key")
    monkeypatch.setenv("EMAIL_TO", "hospital-inbox@example.com")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "SilicaGuard <alerts@silicaguard.health>")

    with patch("services.email_notifications.httpx.post", return_value=_mock_success_response()) as mock_post:
        send_referral_alert_email(
            worker_id, "Email Test Worker", "+263700333001", "Test Site",
            "RED", "Kwekwe District Hospital", "2026-08-13 10:00 UTC", None,
        )

    payload = mock_post.call_args.kwargs["json"]
    assert payload["from"] == "SilicaGuard <alerts@silicaguard.health>"
    assert payload["to"] == ["hospital-inbox@example.com"]


def test_logs_failed_on_api_exception(conn, worker_id, monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_fake_key")
    monkeypatch.setenv("EMAIL_TO", "demo@example.com")

    with patch("services.email_notifications.httpx.post", side_effect=Exception("network unreachable")):
        ok = send_referral_alert_email(
            worker_id, "Email Test Worker", "+263700333001", "Test Site",
            "RED", "Kwekwe District Hospital", "2026-08-13 10:00 UTC", None,
        )

    assert ok is False
    rows = _notification_rows(conn)
    assert len(rows) == 1
    assert rows[0]["delivery_status"] == "failed"
