from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

import database
from db_models import Miner, Referral, Screening
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


# --- process_due_referrals: integration against a real ORM session ---


@pytest.fixture
def db(tmp_path):
    # Builds its own throwaway engine explicitly rather than monkeypatching
    # database.DATABASE_URL and calling database.SessionLocal() — see
    # tests/test_outreach.py's `db` fixture for why that pattern silently
    # leaks into the real dev database (SessionLocal is bound once at
    # import time and isn't affected by monkeypatching afterward).
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(
        f"sqlite:///{tmp_path / 'cascade_test.db'}", connect_args={"check_same_thread": False}
    )
    database.enable_sqlite_foreign_keys(engine)
    database.init_db(target_engine=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _seed_referral(db, tier, status, created_at, reminder_stage=0, phone="+263700111222"):
    miner = Miner(name="Cascade Test Miner", phone=phone, mine_site="Test Site")
    db.add(miner)
    db.flush()
    screening = Screening(miner_id=miner.id, tier=tier)
    db.add(screening)
    db.flush()
    referral = Referral(
        screening_id=screening.id,
        miner_id=miner.id,
        hospital="Kwekwe District Hospital",
        deadline=created_at,
        status=status,
        reminder_stage=reminder_stage,
        created_at=created_at,
    )
    db.add(referral)
    db.commit()
    return referral.id, miner.id


def test_process_due_referrals_sends_reminder_and_updates_row(db):
    referral_id, worker_id = _seed_referral(
        db, "RED", "pre_alerted", NOW - timedelta(hours=25), phone="+263700111001"
    )

    with patch("services.notifications.send_referral_reminder") as mock_remind:
        process_due_referrals(db, now=NOW)

    mock_remind.assert_called_once_with(worker_id, "+263700111001", "RED", 1)
    referral = db.get(Referral, referral_id)
    assert referral.status == "reminded"
    assert referral.reminder_stage == 1


def test_process_due_referrals_escalates_and_updates_row(db):
    referral_id, worker_id = _seed_referral(
        db, "RED", "reminded", NOW - timedelta(hours=50), reminder_stage=1, phone="+263700111002"
    )

    with patch("services.notifications.send_referral_escalation") as mock_escalate:
        process_due_referrals(db, now=NOW)

    mock_escalate.assert_called_once_with(worker_id, "Cascade Test Miner", "+263700111002", "RED")
    assert db.get(Referral, referral_id).status == "escalated"


def test_process_due_referrals_ignores_referrals_not_yet_due(db):
    referral_id, _ = _seed_referral(
        db, "ORANGE", "open", NOW - timedelta(hours=1), phone="+263700111003"
    )

    with patch("services.notifications.send_referral_reminder") as mock_remind, patch(
        "services.notifications.send_referral_escalation"
    ) as mock_escalate:
        process_due_referrals(db, now=NOW)

    mock_remind.assert_not_called()
    mock_escalate.assert_not_called()
    assert db.get(Referral, referral_id).status == "open"


def test_process_due_referrals_ignores_closed_referrals_even_if_overdue(db):
    _seed_referral(db, "RED", "closed", NOW - timedelta(days=10), phone="+263700111004")

    with patch("services.notifications.send_referral_escalation") as mock_escalate:
        process_due_referrals(db, now=NOW)

    mock_escalate.assert_not_called()


def test_one_bad_row_does_not_abort_the_batch(db):
    """A referral with an unparsable created_at shouldn't stop a second,
    valid referral in the same batch from being processed."""
    from sqlalchemy import text

    good_id, _ = _seed_referral(
        db, "RED", "open", NOW - timedelta(hours=25), phone="+263700111005"
    )
    bad_id, _ = _seed_referral(
        db, "RED", "open", NOW - timedelta(hours=25), phone="+263700111006"
    )
    # Bypasses the ORM deliberately — a raw UPDATE is the only way to get a
    # value this malformed into the column at all, since the ORM's own type
    # system would reject/convert it on a normal assignment.
    db.execute(
        text("UPDATE referrals SET created_at = 'not-a-real-timestamp' WHERE id = :id"),
        {"id": bad_id},
    )
    db.commit()
    db.expire_all()  # forget any cached row state so the bad value is re-read from the DB

    with patch("services.notifications.send_referral_reminder") as mock_remind:
        process_due_referrals(db, now=NOW)

    assert db.get(Referral, good_id).status == "reminded"
    mock_remind.assert_called_once()
