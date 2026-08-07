"""Dedicated coverage of services/notifications.py itself. Every other test
in this suite replaces its public functions wholesale via conftest.py's
autouse _mock_notifications fixture, so the real send-then-log pipeline
(including the _log_notification audit write) has never actually run in a
test until this file. Patches httpx.post one level lower than the public
functions so that pipeline executes for real against a temp DB.

Imports the real functions directly by name (captured at module load,
i.e. collection time) rather than calling them via `notifications.send_x`
— conftest.py's autouse _mock_notifications fixture monkeypatches those
module attributes to no-op lambdas for every test in this suite, which
would otherwise silently swallow this file's own tests too. A name bound
at import time is unaffected by a later monkeypatch.setattr on the module
attribute of the same name.
"""

from unittest.mock import Mock, patch

import pytest

import database
from services.notifications import (
    send_hospital_prealert,
    send_miner_result,
    send_outreach_announcement,
    send_referral_escalation,
    send_referral_reminder,
    send_screening_result_sms,
)


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_URL", str(tmp_path / "notifications_test.db"))
    database.init_db()
    connection = database.get_connection()
    yield connection
    connection.close()


@pytest.fixture
def worker_id(conn):
    conn.execute(
        "INSERT INTO miners (name, phone, mine_site) VALUES (?, ?, ?)",
        ("Notif Test Worker", "+263700222001", "Test Site"),
    )
    conn.commit()
    return conn.execute("SELECT id FROM miners WHERE phone = ?", ("+263700222001",)).fetchone()["id"]


def _notification_rows(conn):
    return conn.execute("SELECT * FROM notifications ORDER BY id").fetchall()


def _mock_success_response():
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.text = '{"status": "ok"}'
    return resp


def test_send_miner_result_logs_sent_row_on_success(conn, worker_id, monkeypatch):
    monkeypatch.setenv("AT_API_KEY", "fake")
    with patch("services.notifications.httpx.post", return_value=_mock_success_response()):
        ok = send_miner_result(worker_id, "+263700222001", "RED", "Shona message")

    assert ok is True
    rows = _notification_rows(conn)
    assert len(rows) == 1
    assert rows[0]["worker_id"] == worker_id
    assert rows[0]["template"] == "miner_result"
    assert "Shona message" in rows[0]["payload"]
    assert rows[0]["delivery_status"] == "sent"
    assert rows[0]["channel"] == "sms"


def test_send_miner_result_logs_failed_row_on_httpx_error(conn, worker_id, monkeypatch):
    monkeypatch.setenv("AT_API_KEY", "fake")
    with patch("services.notifications.httpx.post", side_effect=RuntimeError("network down")):
        ok = send_miner_result(worker_id, "+263700222001", "RED", "Shona message")

    assert ok is False
    rows = _notification_rows(conn)
    assert len(rows) == 1
    assert rows[0]["delivery_status"] == "failed"


def test_send_screening_result_sms_logs_sent_row_on_success(conn, worker_id, monkeypatch):
    monkeypatch.setenv("AT_API_KEY", "fake")
    with patch("services.notifications.httpx.post", return_value=_mock_success_response()):
        ok = send_screening_result_sms(worker_id, "+263700222001", "GREEN", "Shona result message")

    assert ok is True
    rows = _notification_rows(conn)
    assert len(rows) == 1
    assert rows[0]["worker_id"] == worker_id
    assert rows[0]["template"] == "screening_result"
    assert "Shona result message" in rows[0]["payload"]
    assert rows[0]["delivery_status"] == "sent"
    # Unlike send_miner_result, no facility-visit instruction — there's no
    # referral to show up for.
    assert "nurse" not in rows[0]["payload"].lower()


def test_send_hospital_prealert_logs_skipped_row_when_nurse_phone_unset(conn, worker_id, monkeypatch):
    monkeypatch.delenv("HOSPITAL_NURSE_PHONE", raising=False)
    with patch("services.notifications.httpx.post") as mock_post:
        ok = send_hospital_prealert(
            worker_id, "Test Miner", "+263700222001", "Test Site", "RED", "factor summary"
        )

    assert ok is False
    mock_post.assert_not_called()
    rows = _notification_rows(conn)
    assert len(rows) == 1
    assert rows[0]["template"] == "hospital_prealert"
    assert rows[0]["delivery_status"] == "skipped"


def test_send_hospital_prealert_logs_sent_row_when_configured(conn, worker_id, monkeypatch):
    monkeypatch.setenv("HOSPITAL_NURSE_PHONE", "+263700999000")
    monkeypatch.setenv("AT_API_KEY", "fake")
    with patch("services.notifications.httpx.post", return_value=_mock_success_response()):
        ok = send_hospital_prealert(
            worker_id, "Test Miner", "+263700222001", "Test Site", "RED", "factor summary"
        )

    assert ok is True
    rows = _notification_rows(conn)
    assert rows[0]["delivery_status"] == "sent"


def test_send_referral_reminder_logs_row(conn, worker_id, monkeypatch):
    monkeypatch.setenv("AT_API_KEY", "fake")
    with patch("services.notifications.httpx.post", return_value=_mock_success_response()):
        send_referral_reminder(worker_id, "+263700222001", "ORANGE", 1)

    rows = _notification_rows(conn)
    assert rows[0]["template"] == "referral_reminder"
    assert rows[0]["worker_id"] == worker_id


def test_send_referral_escalation_logs_skipped_without_nurse_phone(conn, worker_id, monkeypatch):
    monkeypatch.delenv("HOSPITAL_NURSE_PHONE", raising=False)
    ok = send_referral_escalation(worker_id, "Test Miner", "+263700222001", "RED")

    assert ok is False
    rows = _notification_rows(conn)
    assert rows[0]["template"] == "referral_escalation"
    assert rows[0]["delivery_status"] == "skipped"


def test_send_outreach_announcement_logs_row_per_stage(conn, worker_id, monkeypatch):
    monkeypatch.setenv("AT_API_KEY", "fake")
    with patch("services.notifications.httpx.post", return_value=_mock_success_response()):
        send_outreach_announcement(
            worker_id, "+263700222001", "Sherwood Mine", "2026-08-15", "3day"
        )
        send_outreach_announcement(
            worker_id, "+263700222001", "Sherwood Mine", "2026-08-15", "1day"
        )

    rows = _notification_rows(conn)
    assert len(rows) == 2
    assert rows[0]["template"] == "outreach_announcement_3day"
    assert rows[1]["template"] == "outreach_announcement_1day"
    assert "Sherwood Mine" in rows[0]["payload"]
