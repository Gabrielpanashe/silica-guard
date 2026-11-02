"""The production entry point: migrate, then serve — but not at any cost.

`scripts/start.py` replaces the start command
`python -m alembic upgrade head && uvicorn main:app ...`, which was right
about migrations and wrong about everything else.

**The regression that `&&` introduced, and that these tests exist to keep
out.** The free tier sleeps, and a wake restarts the container, which re-runs
the start command. The free Supabase project pauses after seven idle days —
twice so far, on 6 September and around 9 October. With `&&`, a wake while the
database is paused means the migration fails and **uvicorn never starts**: no
process, no `/api/health`, nothing from outside to say whether the API or the
database is the problem. That is precisely the outage PR #27 was written to
prevent.

So the two failures are told apart, because they want opposite responses:

  database unreachable  → serve anyway; `/api/health` reports it and the
                          service recovers on its own at the next wake
  migration broken      → refuse to start; serving a schema the code cannot
                          use is what caused the 2 November outage, and it
                          fails silently, one route at a time
"""

import sys
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND / "scripts"))

import start  # noqa: E402


def _raise(exc):
    def _inner(*args, **kwargs):
        raise exc

    return _inner


# ------------------------------------------------- the database is unreachable

def test_an_unreachable_database_does_not_stop_the_server(monkeypatch, caplog):
    """**The assertion that keeps PR #27's property alive.** There is nothing
    to migrate *to*, so refusing to boot helps nobody — and a server that is
    not running cannot tell anyone why."""
    import logging

    from alembic import command

    monkeypatch.setattr(
        command, "upgrade", _raise(OperationalError("SELECT 1", {}, Exception("paused")))
    )
    with caplog.at_level(logging.WARNING):
        assert start.migrate() is False

    assert "Starting anyway" in caplog.text
    assert "database: down" in caplog.text
    assert "No schema change" in caplog.text


def test_main_still_starts_uvicorn_when_the_database_is_unreachable(monkeypatch):
    """The whole point: the process comes up regardless."""
    from alembic import command

    monkeypatch.setattr(
        command, "upgrade", _raise(OperationalError("SELECT 1", {}, Exception("paused")))
    )
    started = {}

    class _FakeUvicorn:
        @staticmethod
        def run(app, host, port):
            started.update(app=app, host=host, port=port)

    monkeypatch.setitem(sys.modules, "uvicorn", _FakeUvicorn)
    monkeypatch.setenv("PORT", "10000")

    start.main()
    assert started == {"app": "main:app", "host": "0.0.0.0", "port": 10000}


# --------------------------------------------------- the migration is broken

@pytest.mark.parametrize(
    "exc",
    [
        ProgrammingError("CREATE TABLE x", {}, Exception("relation already exists")),
        IntegrityError("ALTER TABLE x", {}, Exception("constraint violated")),
        RuntimeError("a data migration raised"),
    ],
)
def test_a_broken_migration_refuses_to_start(monkeypatch, exc):
    """The one place refusing to boot beats booting degraded. Serving a schema
    the code cannot use is what caused the 2 November outage, and it fails
    silently — one route at a time, with `/api/health` reporting everything
    fine."""
    from alembic import command

    monkeypatch.setattr(command, "upgrade", _raise(exc))
    with pytest.raises(SystemExit) as raised:
        start.migrate()
    assert raised.value.code == 1


def test_the_refusal_says_it_is_the_migration_and_not_connectivity(monkeypatch, caplog):
    """Whoever reads a failed deploy should not have to guess which of the two
    failures they are looking at."""
    import logging

    from alembic import command

    monkeypatch.setattr(
        command, "upgrade", _raise(ProgrammingError("x", {}, Exception("broken")))
    )
    with caplog.at_level(logging.ERROR), pytest.raises(SystemExit):
        start.migrate()
    assert "rather than connectivity" in caplog.text
    assert "Refusing to start" in caplog.text


def test_main_does_not_start_uvicorn_when_the_migration_is_broken(monkeypatch):
    from alembic import command

    monkeypatch.setattr(
        command, "upgrade", _raise(ProgrammingError("x", {}, Exception("broken")))
    )

    class _FakeUvicorn:
        @staticmethod
        def run(*args, **kwargs):
            raise AssertionError("uvicorn must not start on a broken migration")

    monkeypatch.setitem(sys.modules, "uvicorn", _FakeUvicorn)
    with pytest.raises(SystemExit):
        start.main()


# ------------------------------------------------------------- the happy path

def test_a_successful_migration_reports_head_and_serves(monkeypatch, caplog):
    import logging

    from alembic import command

    monkeypatch.setattr(command, "upgrade", lambda config, rev: None)
    with caplog.at_level(logging.INFO):
        assert start.migrate() is True
    assert "at head" in caplog.text


def test_the_alembic_config_points_at_this_backend(monkeypatch):
    """Render runs it from an arbitrary working directory, so the paths must
    be absolute rather than relative to wherever the process started."""
    captured = {}
    from alembic import command

    def fake_upgrade(config, rev):
        captured["script_location"] = config.get_main_option("script_location")

    monkeypatch.setattr(command, "upgrade", fake_upgrade)
    start.migrate()
    assert Path(captured["script_location"]).is_absolute()
    assert Path(captured["script_location"]).name == "alembic"


def test_the_port_defaults_when_render_does_not_set_one(monkeypatch):
    from alembic import command

    monkeypatch.setattr(command, "upgrade", lambda config, rev: None)
    monkeypatch.delenv("PORT", raising=False)
    seen = {}

    class _FakeUvicorn:
        @staticmethod
        def run(app, host, port):
            seen["port"] = port

    monkeypatch.setitem(sys.modules, "uvicorn", _FakeUvicorn)
    start.main()
    assert seen["port"] == 8000
