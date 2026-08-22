import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("HOSPITAL_EMAIL", "hospital@silicaguard.health")
os.environ.setdefault("HOSPITAL_PASSWORD", "hospital123")
os.environ.setdefault("CIMAS_EMAIL", "cimas@silicaguard.health")
os.environ.setdefault("CIMAS_PASSWORD", "cimas123")
# Plain configuration, not a "detect pytest" hack — no test should ever
# start a background scheduler thread (would leak across the per-test
# TestClient instances and slow the suite down for no benefit; the cascade
# logic itself is tested directly in test_referral_cascade.py).
os.environ.setdefault("SCHEDULER_ENABLED", "false")

import database  # noqa: E402
import main  # noqa: E402
from services import email_notifications, notifications  # noqa: E402


@pytest.fixture(autouse=True)
def _mock_notifications(monkeypatch):
    """services/notifications.py sends real SMS via Africa's Talking. Tests
    must never hit that live API — costs real quota, is non-deterministic,
    and would silently fail without a registered sandbox simulator number
    anyway. Every test gets this mocked automatically."""
    monkeypatch.setattr(notifications, "send_miner_result", lambda *a, **k: None)
    monkeypatch.setattr(
        notifications, "send_screening_result_sms", lambda *a, **k: True
    )
    monkeypatch.setattr(
        notifications, "send_hospital_prealert", lambda *a, **k: True
    )
    monkeypatch.setattr(
        notifications, "send_referral_reminder", lambda *a, **k: True
    )
    monkeypatch.setattr(
        notifications, "send_referral_escalation", lambda *a, **k: True
    )
    monkeypatch.setattr(
        notifications, "send_outreach_announcement", lambda *a, **k: True
    )
    monkeypatch.setattr(
        notifications, "send_education_tip", lambda *a, **k: True
    )
    # services/email_notifications.py (10 August) — same reasoning: without
    # this, every test that creates an ORANGE/RED referral would actually
    # run the real function (its own no-credentials guard means no network
    # call, since EMAIL_ADDRESS/EMAIL_APP_PASSWORD are never set in tests,
    # but it would still write a real 'skipped' row to `notifications`,
    # inconsistent with every other channel being fully mocked here).
    monkeypatch.setattr(
        email_notifications, "send_referral_alert_email", lambda *a, **k: True
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Points every test at a throwaway SQLite file, so we never touch
    backend/data/silicaguard.db (real dev/demo data) while testing.

    Two mechanisms cover the codebase during the ongoing SQLAlchemy ORM
    migration (see CLAUDE.md's "Current sprint status", 14 August 2026):
    modules already converted to `Depends(database.get_db)` get a real
    dependency override bound to a fresh per-test engine; modules not yet
    converted (still calling `database.get_connection()`) get the same
    result via a `DATABASE_URL` monkeypatch, since that legacy shim reads
    `DATABASE_URL` fresh on every call. Both point at the same file, so
    data is consistent no matter which style a given test's route uses.
    `database.engine` is also monkeypatched, so `init_db()` — called by
    main.py's lifespan on TestClient startup — creates tables on the test
    engine, not the real module-level one built at import time.

    Once every router/service is converted (tracked in the sprint status),
    delete the DATABASE_URL/engine monkeypatching and get_connection()
    itself, keeping only the dependency-override half of this fixture.
    """
    test_db_url = f"sqlite:///{tmp_path / 'test.db'}"
    test_engine = create_engine(test_db_url, connect_args={"check_same_thread": False})
    database.enable_sqlite_foreign_keys(test_engine)
    TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)

    monkeypatch.setattr(database, "DATABASE_URL", test_db_url)
    monkeypatch.setattr(database, "engine", test_engine)

    def _override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[database.get_db] = _override_get_db
    try:
        with TestClient(main.app) as test_client:
            yield test_client
    finally:
        main.app.dependency_overrides.pop(database.get_db, None)
