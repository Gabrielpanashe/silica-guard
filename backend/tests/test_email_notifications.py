"""Dedicated coverage of services/email_notifications.py, same pattern as
tests/test_notifications.py: imports the real function by name at
collection time so conftest.py's autouse _mock_notifications fixture (which
now also mocks email_notifications.send_referral_alert_email for every
other test) doesn't swallow this file's own tests.

Never touches a real SMTP server — smtplib.SMTP itself is mocked, so these
tests are deterministic and offline regardless of EMAIL_ADDRESS/
EMAIL_APP_PASSWORD being set in the environment.
"""

from unittest.mock import MagicMock, patch

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


def test_skips_and_logs_when_credentials_missing(conn, worker_id, monkeypatch):
    monkeypatch.delenv("EMAIL_ADDRESS", raising=False)
    monkeypatch.delenv("EMAIL_APP_PASSWORD", raising=False)

    with patch("services.email_notifications.smtplib.SMTP") as mock_smtp:
        ok = send_referral_alert_email(
            worker_id, "Email Test Worker", "+263700333001", "Test Site",
            "RED", "Kwekwe District Hospital", "2026-08-13 10:00 UTC", ["Factor A"],
        )

    assert ok is False
    mock_smtp.assert_not_called()  # never even tries to connect without credentials
    rows = _notification_rows(conn)
    assert len(rows) == 1
    assert rows[0]["delivery_status"] == "skipped"
    assert rows[0]["worker_id"] == worker_id


def test_sends_and_logs_on_success(conn, worker_id, monkeypatch):
    monkeypatch.setenv("EMAIL_ADDRESS", "demo@example.com")
    monkeypatch.setenv("EMAIL_APP_PASSWORD", "fake-app-password")
    # main.py's load_dotenv() at import time may have already pulled a real
    # EMAIL_TO into os.environ from backend/.env — clear it explicitly so
    # this test's "EMAIL_TO unset, defaults to sender" scenario is
    # deterministic regardless of what's in the real local .env.
    monkeypatch.delenv("EMAIL_TO", raising=False)

    mock_smtp_instance = MagicMock()
    with patch("services.email_notifications.smtplib.SMTP") as mock_smtp:
        mock_smtp.return_value.__enter__.return_value = mock_smtp_instance
        ok = send_referral_alert_email(
            worker_id, "Email Test Worker", "+263700333001", "Test Site",
            "RED", "Kwekwe District Hospital", "2026-08-13 10:00 UTC", ["Factor A"],
        )

    assert ok is True
    mock_smtp_instance.starttls.assert_called_once()
    mock_smtp_instance.login.assert_called_once_with("demo@example.com", "fake-app-password")
    mock_smtp_instance.send_message.assert_called_once()
    sent_msg = mock_smtp_instance.send_message.call_args[0][0]
    assert sent_msg["To"] == "demo@example.com"  # defaults to sender when EMAIL_TO unset
    assert "RED" in sent_msg["Subject"]

    rows = _notification_rows(conn)
    assert len(rows) == 1
    assert rows[0]["delivery_status"] == "sent"


def test_uses_separate_email_to_when_set(conn, worker_id, monkeypatch):
    monkeypatch.setenv("EMAIL_ADDRESS", "demo@example.com")
    monkeypatch.setenv("EMAIL_APP_PASSWORD", "fake-app-password")
    monkeypatch.setenv("EMAIL_TO", "hospital-inbox@example.com")

    mock_smtp_instance = MagicMock()
    with patch("services.email_notifications.smtplib.SMTP") as mock_smtp:
        mock_smtp.return_value.__enter__.return_value = mock_smtp_instance
        send_referral_alert_email(
            worker_id, "Email Test Worker", "+263700333001", "Test Site",
            "ORANGE", "Kwekwe District Hospital", "2026-08-20 10:00 UTC", [],
        )

    sent_msg = mock_smtp_instance.send_message.call_args[0][0]
    assert sent_msg["To"] == "hospital-inbox@example.com"


def test_logs_failed_on_smtp_exception(conn, worker_id, monkeypatch):
    monkeypatch.setenv("EMAIL_ADDRESS", "demo@example.com")
    monkeypatch.setenv("EMAIL_APP_PASSWORD", "fake-app-password")

    with patch("services.email_notifications.smtplib.SMTP", side_effect=Exception("connection refused")):
        ok = send_referral_alert_email(
            worker_id, "Email Test Worker", "+263700333001", "Test Site",
            "RED", "Kwekwe District Hospital", "2026-08-13 10:00 UTC", None,
        )

    assert ok is False
    rows = _notification_rows(conn)
    assert len(rows) == 1
    assert rows[0]["delivery_status"] == "failed"
