"""Production entry point: migrate, then serve — but not at any cost.

Set as the Render service's start command. Replaces
`python -m alembic upgrade head && uvicorn main:app ...`, which was right
about migrations and wrong about everything else.

**Why `&&` was wrong, and it is a regression I introduced on 2 November 2026.**
The free tier sleeps, and a wake restarts the container, which re-runs the
start command. The free Supabase project pauses after seven idle days — it has
done so twice, on 6 September and around 9 October. With `&&`, a wake while
the database is paused means the migration fails and **uvicorn never starts**:
no process, no `/api/health`, nothing from outside to say whether the API or
the database is the problem. That is exactly the total outage `be/survive-
db-outage` (PR #27) was written to prevent, traded in for protection against a
half-migrated schema that is now detected two other ways anyway.

So the two failures are told apart, because they want opposite responses:

  **The database is unreachable.** Log it loudly and serve anyway. Rule 7 —
  fail toward recording, never toward silence. `/api/health` reports
  `database: down`, DB-backed routes return a clean 503 from `get_db()`, and
  the service recovers on its own at the next wake once the database returns.
  Refusing to boot here helps nobody: there is nothing to migrate *to*.

  **The migration itself failed.** Exit non-zero and do not serve. A
  genuinely broken migration leaves a schema the code cannot use, and serving
  it produces the silent half-migrated state that caused the 2 November
  outage. This is the one place where refusing to boot beats booting degraded.

Render's `preDeployCommand` would be the right mechanism — migrations once per
deploy, never on a wake — and is not available on the free plan.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("silicaguard.start")


def migrate() -> bool:
    """Run `alembic upgrade head`. Returns whether the schema is usable.

    False means "the database is unreachable, serve degraded". A migration
    that fails for any other reason raises SystemExit rather than returning,
    because that must stop the boot.
    """
    from alembic import command
    from alembic.config import Config
    from sqlalchemy.exc import OperationalError

    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))

    try:
        command.upgrade(config, "head")
    except OperationalError:
        # Connection-level: the server is down, paused or unroutable. A
        # genuine migration bug raises ProgrammingError or IntegrityError
        # instead, which falls through to the branch below — the same
        # distinction `database.get_db()` makes when turning a failure into a
        # 503 rather than a 500.
        logger.warning(
            "Could not reach the database to migrate it. Starting anyway so "
            "that /api/health can report `database: down` and the service can "
            "recover on its own when the database returns. No schema change "
            "was made.",
            exc_info=True,
        )
        return False
    except Exception:
        logger.exception(
            "MIGRATION FAILED and the database is reachable, so this is the "
            "migration itself rather than connectivity. Refusing to start: "
            "serving a schema the code cannot use is what caused the "
            "2 November outage, and it fails silently, one route at a time."
        )
        raise SystemExit(1)

    logger.info("Database is at head.")
    return True


def main() -> None:
    migrate()

    port = os.getenv("PORT", "8000")
    logger.info("Starting uvicorn on port %s", port)
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=int(port))


if __name__ == "__main__":
    main()
