from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

import database
from services.referral_cascade import next_cascade_action, process_due_referrals

NOW = datetime(2026, 8, 10, 12, 0, 0)


# --- next_cascade_action: pure-function table of cases ---


def test_too_early_for_anything_returns_none():
    created = NOW - timedelta(hours=1)
    assert next_cascade_action("RED", "open", 0, created, NOW) is None


def test_red_reminder_due_at_24h():
    created = NOW - timedelta(hours=25)
    action = next_cascade_action("RED", "open", 0, created, NOW)
    assert action == {"action": "remind", "new_stage": 1}


def test_red_no_second_reminder_once_stage_1():
    created = NOW - timedelta(hours=30)
    assert next_cascade_action("RED", "reminded", 1, created, NOW) is None


def test_red_escalates_past_48h_regardless_of_reminder_stage():
    created = NOW - timedelta(hours=49)
    action = next_cascade_action("RED", "reminded", 1, created, NOW)
    assert action == {"action": "escalate"}


def test_red_escalates_even_if_never_reminded():
    created = NOW - timedelta(hours=49)
    action = next_cascade_action("RED", "open", 0, created, NOW)
    assert action == {"action": "escalate"}


def test_orange_first_reminder_due_at_day_3():
    created = NOW - timedelta(days=3, hours=1)
    action = next_cascade_action("ORANGE", "pre_alerted", 0, created, NOW)
    assert action == {"action": "remind", "new_stage": 1}


def test_orange_second_reminder_due_at_day_7():
    created = NOW - timedelta(days=7, hours=1)
    action = next_cascade_action("ORANGE", "reminded", 1, created, NOW)
    assert action == {"action": "remind", "new_stage": 2}


def test_orange_no_reminder_between_day_3_and_day_7_once_stage_1():
    created = NOW - timedelta(days=5)
    assert next_cascade_action("ORANGE", "reminded", 1, created, NOW) is None


def test_orange_escalates_at_day_14():
    created = NOW - timedelta(days=14, hours=1)
    action = next_cascade_action("ORANGE", "reminded", 2, created, NOW)
    assert action == {"action": "escalate"}


@pytest.mark.parametrize("status", ["attended", "closed", "escalated"])
def test_no_action_once_out_of_actionable_statuses(status):
    created = NOW - timedelta(days=30)  # would otherwise clearly be overdue
    assert next_cascade_action("RED", status, 0, created, NOW) is None
    assert next_cascade_action("ORANGE", status, 0, created, NOW) is None


def test_unknown_tier_returns_none():
    assert next_cascade_action("GREEN", "open", 0, NOW - timedelta(days=30), NOW) is None


# --- process_due_referrals: integration against a raw connection ---


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_URL", str(tmp_path / "cascade_test.db"))
    database.init_db()
    connection = database.get_connection()
    yield connection
    connection.close()


def _seed_referral(conn, tier, status, created_at, reminder_stage=0, phone="+263700111222"):
    conn.execute(
        "INSERT INTO miners (name, phone, mine_site) VALUES (?, ?, ?)",
        ("Cascade Test Miner", phone, "Test Site"),
    )
    miner_id = conn.execute("SELECT id FROM miners WHERE phone = ?", (phone,)).fetchone()["id"]
    cur = conn.execute(
        "INSERT INTO screenings (miner_id, tier) VALUES (?, ?)", (miner_id, tier)
    )
    screening_id = cur.lastrowid
    cur = conn.execute(
        """INSERT INTO referrals
           (screening_id, miner_id, hospital, deadline, status, reminder_stage, created_at)
           VALUES (?, ?, 'Kwekwe District Hospital', ?, ?, ?, ?)""",
        (
            screening_id,
            miner_id,
            created_at.strftime("%Y-%m-%d %H:%M:%S"),
            status,
            reminder_stage,
            created_at.strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    conn.commit()
    return cur.lastrowid


def test_process_due_referrals_sends_reminder_and_updates_row(conn):
    referral_id = _seed_referral(
        conn, "RED", "pre_alerted", NOW - timedelta(hours=25), phone="+263700111001"
    )

    with patch("services.notifications.send_referral_reminder") as mock_remind:
        process_due_referrals(conn, now=NOW)

    mock_remind.assert_called_once_with("+263700111001", "RED", 1)
    row = conn.execute("SELECT status, reminder_stage FROM referrals WHERE id = ?", (referral_id,)).fetchone()
    assert row["status"] == "reminded"
    assert row["reminder_stage"] == 1


def test_process_due_referrals_escalates_and_updates_row(conn):
    referral_id = _seed_referral(
        conn, "RED", "reminded", NOW - timedelta(hours=50), reminder_stage=1, phone="+263700111002"
    )

    with patch("services.notifications.send_referral_escalation") as mock_escalate:
        process_due_referrals(conn, now=NOW)

    mock_escalate.assert_called_once_with("Cascade Test Miner", "+263700111002", "RED")
    row = conn.execute("SELECT status FROM referrals WHERE id = ?", (referral_id,)).fetchone()
    assert row["status"] == "escalated"


def test_process_due_referrals_ignores_referrals_not_yet_due(conn):
    referral_id = _seed_referral(
        conn, "ORANGE", "open", NOW - timedelta(hours=1), phone="+263700111003"
    )

    with patch("services.notifications.send_referral_reminder") as mock_remind, patch(
        "services.notifications.send_referral_escalation"
    ) as mock_escalate:
        process_due_referrals(conn, now=NOW)

    mock_remind.assert_not_called()
    mock_escalate.assert_not_called()
    row = conn.execute("SELECT status FROM referrals WHERE id = ?", (referral_id,)).fetchone()
    assert row["status"] == "open"


def test_process_due_referrals_ignores_closed_referrals_even_if_overdue(conn):
    _seed_referral(conn, "RED", "closed", NOW - timedelta(days=10), phone="+263700111004")

    with patch("services.notifications.send_referral_escalation") as mock_escalate:
        process_due_referrals(conn, now=NOW)

    mock_escalate.assert_not_called()


def test_one_bad_row_does_not_abort_the_batch(conn):
    """A referral with an unparsable created_at shouldn't stop a second,
    valid referral in the same batch from being processed."""
    good_id = _seed_referral(
        conn, "RED", "open", NOW - timedelta(hours=25), phone="+263700111005"
    )
    bad_id = _seed_referral(
        conn, "RED", "open", NOW - timedelta(hours=25), phone="+263700111006"
    )
    conn.execute(
        "UPDATE referrals SET created_at = 'not-a-real-timestamp' WHERE id = ?", (bad_id,)
    )
    conn.commit()

    with patch("services.notifications.send_referral_reminder") as mock_remind:
        process_due_referrals(conn, now=NOW)

    good_row = conn.execute("SELECT status FROM referrals WHERE id = ?", (good_id,)).fetchone()
    assert good_row["status"] == "reminded"
    mock_remind.assert_called_once()
