"""The API must survive an unreachable database.

11 September 2026: the free-tier Supabase project auto-paused after 7 idle
days (Render had slept, so services/db_keepalive.py stopped pinging it).
`init_db()` raised inside main.py's lifespan, FastAPI startup never
completed, Render marked the deploy `update_failed`, and the result was a
total outage — no instance serving anything, including /api/health, and no
way to tell from outside whether the API or the database was at fault.

These tests pin the degraded-mode behaviour that replaced it:
  - a failed init_db() must not stop the app from serving
  - /api/health must still answer, and must say which half is broken
  - DB-backed routes must return 503 (retry me), not an opaque 500
"""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError, ProgrammingError

import database
import main


def test_health_reports_database_up_when_reachable(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["database"] == "up"


def test_health_reports_database_down_when_probe_fails(client, monkeypatch):
    monkeypatch.setattr(main, "database_reachable", lambda: False)
    body = client.get("/api/health").json()
    # Still 200/ok: the process IS serving. Only `database` flips — that
    # distinction is the whole point of the field.
    assert body["status"] == "ok"
    assert body["database"] == "down"


def test_database_reachable_is_false_when_engine_cannot_connect(monkeypatch):
    """Faked rather than pointed at a dead host on purpose: a real
    unreachable Postgres URL spends ~130s in psycopg's connection retries
    before failing, which would dominate the whole suite's runtime while
    testing psycopg's timeouts instead of this function's except branch."""
    class _DeadEngine:
        def connect(self):
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(database, "_current_engine", lambda: _DeadEngine())
    assert database.database_reachable() is False


def test_app_still_serves_when_init_db_fails(monkeypatch, tmp_path):
    """The regression that caused the outage: startup must complete even
    when init_db() raises, so there is still something alive to report the
    problem and to recover on its own once the database returns."""
    def _boom():
        raise OperationalError("SELECT 1", {}, Exception("database paused"))

    monkeypatch.setattr(main, "init_db", _boom)
    monkeypatch.setattr(main, "database_reachable", lambda: False)

    with TestClient(main.app) as degraded_client:
        body = degraded_client.get("/api/health").json()

    assert body == {"status": "ok", "database": "down"}


def test_auto_seed_is_skipped_when_database_is_unreachable(monkeypatch):
    """AUTO_SEED_ON_BOOT must not fire against a database that just failed
    to initialise — it would raise a second time and re-break startup."""
    monkeypatch.setenv("AUTO_SEED_ON_BOOT", "true")
    monkeypatch.setattr(main, "init_db", lambda: (_ for _ in ()).throw(OperationalError("x", {}, Exception())))
    monkeypatch.setattr(main, "database_reachable", lambda: False)

    seeded = []
    import scripts.seed_demo_data as seed_module

    monkeypatch.setattr(seed_module, "seed", lambda: seeded.append(True))

    with TestClient(main.app) as degraded_client:
        assert degraded_client.get("/api/health").status_code == 200

    assert seeded == [], "seed() ran against an unreachable database"


def test_get_db_converts_connection_failure_to_503():
    """A connection-level failure raised by a route is a 503, not a 500 —
    it tells the mobile app's offline queue to retry rather than treating
    the screening as permanently rejected.

    Driven through the generator directly (gen.throw) because that is
    exactly how FastAPI surfaces a route's exception to a yield-dependency,
    and because tests/conftest.py's client fixture overrides get_db, so the
    real one is never exercised through the TestClient."""
    gen = database.get_db()
    next(gen)
    with pytest.raises(HTTPException) as excinfo:
        gen.throw(OperationalError("SELECT 1", {}, Exception("server closed")))

    assert excinfo.value.status_code == 503
    assert "retry" in excinfo.value.detail.lower()


def test_get_db_leaves_real_query_errors_as_500():
    """Only connection failures degrade to 503. A genuine bug in a query
    must keep surfacing as a 500 — silently calling that "unavailable"
    would hide real breakage behind a retry banner."""
    gen = database.get_db()
    next(gen)
    with pytest.raises(ProgrammingError):
        gen.throw(ProgrammingError("SELECT nope", {}, Exception("no such column")))
