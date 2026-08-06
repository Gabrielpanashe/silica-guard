import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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
from services import notifications  # noqa: E402


@pytest.fixture(autouse=True)
def _mock_notifications(monkeypatch):
    """services/notifications.py sends real SMS via Africa's Talking. Tests
    must never hit that live API — costs real quota, is non-deterministic,
    and would silently fail without a registered sandbox simulator number
    anyway. Every test gets this mocked automatically."""
    monkeypatch.setattr(notifications, "send_miner_result", lambda *a, **k: None)
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


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Points database.py at a throwaway SQLite file per test, so we never
    touch backend/data/silicaguard.db (real dev/demo data) while testing."""
    monkeypatch.setattr(database, "DATABASE_URL", str(tmp_path / "test.db"))
    with TestClient(main.app) as test_client:
        yield test_client
