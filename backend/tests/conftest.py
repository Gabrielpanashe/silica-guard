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

import database  # noqa: E402
import main  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Points database.py at a throwaway SQLite file per test, so we never
    touch backend/data/silicaguard.db (real dev/demo data) while testing."""
    monkeypatch.setattr(database, "DATABASE_URL", str(tmp_path / "test.db"))
    with TestClient(main.app) as test_client:
        yield test_client
