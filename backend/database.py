import os
import sqlite3

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from db_models import Base

# SQLAlchemy ORM migration (14 August 2026, master doc v6.0 Section 16.2).
# Replaces the previous raw-sqlite3 database.py — see git history for that
# version if you need it. Same tables, same column names (db_models.py is a
# schema-preserving rewrite), new access layer: every router/service is
# being converted, one module at a time, to take a `Session` via
# `Depends(get_db)` instead of calling `get_connection()` and writing raw
# SQL strings — see CLAUDE.md's "Current sprint status" for what's left.
#
# DATABASE_URL's MEANING CHANGED with this migration — it used to be a bare
# filesystem path ("./data/silicaguard.db"); it is now (preferably) a full
# SQLAlchemy engine URL, e.g. "sqlite:///./data/silicaguard.db" or, in
# production, a Supabase Postgres URL once Step B lands. A bare path with
# no "://" is still accepted and treated as SQLite (see
# `_normalize_database_url` below) purely for backward compatibility with
# a few test fixtures predating this migration — new code should always
# use the full URL form.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/silicaguard.db")


def _normalize_database_url(value: str) -> str:
    return value if "://" in value else f"sqlite:///{value}"


def _make_engine(url: str):
    normalized = _normalize_database_url(url)
    is_sqlite = normalized.startswith("sqlite")
    if is_sqlite:
        path = normalized.removeprefix("sqlite:///")
        if path and path != ":memory:":
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    new_engine = create_engine(
        normalized,
        # check_same_thread=False: FastAPI can service one Session's
        # requests from a different thread than created it; safe here
        # because each request gets its own Session (see get_db) that's
        # never shared across threads concurrently. Postgres via psycopg
        # needs no such flag.
        connect_args={"check_same_thread": False} if is_sqlite else {},
    )
    if is_sqlite:
        enable_sqlite_foreign_keys(new_engine)
    return new_engine


def enable_sqlite_foreign_keys(target_engine) -> None:
    """SQLite has foreign keys off by default per-connection; every sqlite3
    connection an engine opens needs this, same as the old
    `conn.execute("PRAGMA foreign_keys = ON")` did per-connection."""

    @event.listens_for(target_engine, "connect")
    def _pragma(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()


engine = _make_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Tables that existed under the pre-5-August-2026 enterprise-scope schema
# and are no longer part of db_models.py at all (see SILICAGUARD.md Section
# 13). Base.metadata.create_all() only ever creates missing tables, never
# drops ones absent from the models — so an old local .db file predating
# that pivot would otherwise keep carrying these forever. Explicit cleanup,
# same as the previous CLEANUP script, run every init_db() call.
_CLEANUP_STATEMENTS = (
    "DROP TABLE IF EXISTS campaigns",
    "DROP TABLE IF EXISTS employers",
)


def get_db():
    """FastAPI dependency — yields one Session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_connection() -> sqlite3.Connection:
    """MIGRATION-BRIDGE SHIM — do not use in new code.

    Every router/service is being converted from this raw-sqlite3 style to
    `Depends(get_db)` + the ORM, one module at a time (see CLAUDE.md's
    "Current sprint status", 14 August 2026 entry, for what's left). This
    function exists only so not-yet-converted callers keep working during
    that staged rollout — it's intentionally SQLite-only and reads
    `DATABASE_URL` fresh on every call (unlike `engine` above, which is
    built once at import time), which is also why tests can still isolate
    per-test state by monkeypatching `database.DATABASE_URL` for whichever
    callers haven't moved to the `get_db` dependency-override pattern yet.

    Delete this function, `_normalize_database_url`'s bare-path allowance,
    and the DATABASE_URL-monkeypatch fixtures in tests/, once every caller
    is converted — grep the codebase for `get_connection` to check. It
    raises loudly if pointed at Postgres rather than silently misbehaving,
    since it was never meant to survive the Step B cutover.
    """
    normalized = _normalize_database_url(DATABASE_URL)
    if not normalized.startswith("sqlite"):
        raise RuntimeError(
            "get_connection() is a SQLite-only migration-bridge shim. "
            "Convert this caller to Depends(get_db) before pointing "
            "DATABASE_URL at Postgres."
        )
    path = normalized.removeprefix("sqlite:///") or ":memory:"
    if path != ":memory:":
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(target_engine=None) -> None:
    """Defaults to the module-level `engine` — but if `DATABASE_URL` has
    been changed since that engine was built (e.g. a test monkeypatching
    it directly and then calling `init_db()` with no arguments, a pattern
    several test fixtures use), builds a fresh engine matching the
    *current* value instead of silently touching the original one. Mirrors
    `get_connection()`'s "read DATABASE_URL fresh every call" model, so
    both mechanisms agree during the migration. Pass `target_engine`
    explicitly to skip that lookup entirely (e.g. Step B's Alembic setup)."""
    if target_engine is None:
        if str(engine.url) == _normalize_database_url(DATABASE_URL):
            target_engine = engine
        else:
            target_engine = _make_engine(DATABASE_URL)
    with target_engine.begin() as conn:
        for statement in _CLEANUP_STATEMENTS:
            conn.execute(text(statement))
    Base.metadata.create_all(target_engine)
