"""Schema drift, detected at boot and reported on /api/health.

Written in response to a real production outage on 2 November 2026, and
reproducing it exactly.

**What happened.** `init_db()` calls `Base.metadata.create_all()`, which
creates a missing *table* and can never add a missing *column* to a table that
already exists. Production does not run `alembic upgrade head` on deploy — the
start command is `uvicorn main:app`. So when Phase One's rebuild merged, the
new tables appeared and the new columns on `referrals` and
`screening_answers` did not. Every SQLAlchemy query selecting those models
then failed, which took down `GET /api/referrals/lookup/{code}` — the surface
that makes referral completion measurable at all — and `GET
/api/dashboard/today`, the mobile Home screen's numbers.

**Why nothing noticed.** The routes returned 500 one at a time, and
`/api/health` reported `{"status": "ok", "database": "up"}` throughout,
because the database genuinely was up. "Up" and "up and matching the code" are
different states with different fixes, and from outside they were
indistinguishable — the same class of problem as the 11 September outage,
where "the API is down" and "the database is unreachable" looked identical.

So: one legible line at boot, and a `schema` field on `/api/health`.

It **reports rather than raises**. Rule 7 — boot degraded, never refuse to
start: a server that will not boot is harder to diagnose than one that says
what is wrong.
"""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import database
from db_models import Base


@pytest.fixture
def engine(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'drift.db'}"
    eng = create_engine(url)
    database.enable_sqlite_foreign_keys(eng)
    Base.metadata.create_all(eng)
    monkeypatch.setattr(database, "DATABASE_URL", url)
    monkeypatch.setattr(database, "engine", eng)
    return eng


def drop_columns(engine, table: str, columns: set[str]) -> None:
    """Rebuild a table without some of its columns.

    `ALTER TABLE ... DROP COLUMN` cannot do this on SQLite when the column is
    indexed, and `referrals.result_id` is. Recreating the table from the
    model's own definition minus those columns is also closer to the real
    failure: production's `referrals` was *created* without them, by a
    `create_all()` that ran before those columns existed.
    """
    from sqlalchemy import Table, MetaData

    original = Base.metadata.tables[table]
    trimmed = MetaData()
    Table(
        table,
        trimmed,
        *[c._copy() for c in original.columns if c.name not in columns],
    )
    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE {table}"))
    trimmed.create_all(engine)


# ---------------------------------------------------------- the clean case

def test_a_matching_schema_reports_no_gaps(engine):
    assert database.missing_schema() == {}


def test_a_matching_schema_logs_nothing(engine, caplog):
    database.log_schema_drift()
    assert "SCHEMA DRIFT" not in caplog.text


# ------------------------------------------- the production failure, exactly

def test_a_missing_column_on_an_existing_table_is_detected(engine):
    """**The bug.** This is what create_all() cannot fix and what nothing
    noticed: `referrals` existed, so create_all left it alone, and every
    query selecting a Referral failed on the eight columns `0009` adds."""
    drop_columns(engine, "referrals", {"result_id", "outcome"})

    gaps = database.missing_schema()
    assert "referrals" in gaps
    assert set(gaps["referrals"]) == {"result_id", "outcome"}


def test_create_all_does_not_repair_a_missing_column(engine):
    """The precise reason the outage was possible, asserted so nobody has to
    rediscover it: `create_all()` is not a migration."""
    drop_columns(engine, "screening_answers", {"session_id"})

    Base.metadata.create_all(engine)  # what boot does
    assert database.missing_schema() == {"screening_answers": ["session_id"]}


def test_a_missing_table_is_detected_and_named_as_a_whole(engine):
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE audit_log"))
    assert database.missing_schema()["audit_log"] == ["(whole table)"]


def test_drift_is_logged_with_the_fix(engine, caplog):
    """Whoever reads the log should not have to work out what to run."""
    import logging

    drop_columns(engine, "referrals", {"person_id"})

    with caplog.at_level(logging.ERROR):
        gaps = database.log_schema_drift()

    assert gaps
    assert "SCHEMA DRIFT" in caplog.text
    assert "alembic upgrade head" in caplog.text
    assert "referrals: person_id" in caplog.text


def test_detection_never_raises_on_an_unreachable_database(monkeypatch):
    """It runs at boot, where raising would turn a diagnosable degraded start
    into no server at all.

    Uses a fake engine rather than a real unreachable host: pointing a test at
    a dead PostgreSQL address makes psycopg retry, which cost this suite a
    130-second test once already (`test_db_outage.py` fixed it the same way).
    """
    from sqlalchemy.exc import OperationalError

    class _DeadEngine:
        def connect(self):
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(database, "_current_engine", lambda: _DeadEngine())
    assert database.missing_schema() == {}


# ------------------------------------------------------------- /api/health

def test_health_reports_the_schema_as_ok(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["database"] == "up"
    assert body["schema"] == "ok"
    assert "schema_missing" not in body


def test_health_reports_drift_and_names_what_is_missing(client, monkeypatch):
    """**The field that would have made the outage visible in one request.**
    `database: up` was true throughout and told nobody anything.

    Served from the boot-time check, so this sets that value directly — which
    is what a real deploy against a behind database produces. The next test
    covers the live recheck.
    """
    import main

    monkeypatch.setattr(main, "schema_gaps", {"referrals": ["contributing_reasons"]})

    body = client.get("/api/health").json()
    assert body["status"] == "ok", "the process is still serving"
    assert body["database"] == "up", "the database is genuinely up"
    assert body["schema"] == "drifted"
    assert body["schema_missing"]["referrals"] == ["contributing_reasons"]


def test_health_is_cheap_by_default_and_fresh_on_demand(client, monkeypatch):
    """The default answer comes from boot, because `/api/health` is also what
    wakes a sleeping free-tier instance and inspecting thirty-five tables on
    every call would make it slow for no benefit — drift only changes when a
    migration runs. `?recheck=1` is what you want after running one."""
    import main

    inspections = {"count": 0}
    real = main.missing_schema

    def counting():
        inspections["count"] += 1
        return real()

    monkeypatch.setattr(main, "missing_schema", counting)
    monkeypatch.setattr(main, "schema_gaps", {})

    client.get("/api/health")
    assert inspections["count"] == 0, "the default must not inspect the schema"

    assert client.get("/api/health?recheck=1").json()["schema"] == "ok"
    assert inspections["count"] == 1, "recheck inspects"


def test_health_still_answers_when_the_database_is_down(client, monkeypatch):
    """The 11 September behaviour is unchanged: the schema field is simply
    absent, because there is nothing to compare against."""
    monkeypatch.setattr(database, "database_reachable", lambda: False)
    import main

    monkeypatch.setattr(main, "database_reachable", lambda: False)
    body = client.get("/api/health").json()
    assert body == {"status": "ok", "database": "down"}
