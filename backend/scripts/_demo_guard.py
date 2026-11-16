"""Refuse to run a destructive demonstration script against a real database.

`CLAUDE.md`: **production data is never copied to staging or a developer
machine**, and the converse matters just as much — a seeding script must
never run against production. Both seeders begin by deleting every row in
the tables they own, and neither checked where it was pointed.

That is not a theoretical hazard. There is no staging (`ARCHITECTURE.md`
lists it as a Phase One correction), so the one Supabase database is both
production and the demonstration target, and `backend/.env` on a developer
machine holds its URL. One `python scripts/seed_demo_data.py` with that file
loaded deletes the demonstration history the team has been presenting
against, and after the pilot starts it would delete real screenings.

So the rule is the plain one: a destructive script runs against SQLite or a
local host, and against anything else only when the operator says so in a
way they cannot type by accident.
"""

from __future__ import annotations

import os
import sys

#: Hosts a destructive script may point at without an override.
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "0.0.0.0")

#: The operator has to type this exactly. Not a flag, not a `-y`: the point
#: is that it cannot be reached by pressing return at a prompt or by leaving
#: an old argument in a shell history line.
OVERRIDE_PHRASE = "yes-delete-rows-in-this-database"


class RefusedError(SystemExit):
    """Raised as SystemExit so a script exits non-zero without a traceback."""


def _target(url: str) -> str:
    """A human description of where this URL points, with no credentials."""
    if url.startswith("sqlite"):
        return f"SQLite file ({url.split('///')[-1] or 'in memory'})"
    host = url.split("@")[-1].split("/")[0] if "@" in url else url.split("//")[-1].split("/")[0]
    return f"host {host}"


def _is_local(url: str) -> bool:
    if url.startswith("sqlite") or not url:
        return True
    remainder = url.split("@")[-1] if "@" in url else url.split("//")[-1]
    host = remainder.split("/")[0].split(":")[0]
    return host in LOCAL_HOSTS


def refuse_unless_local(script_name: str, argv: list[str] | None = None) -> str:
    """Return the database URL, or exit if it is not safe to delete from.

    Called before the first delete, not after: a script that checks halfway
    through has already done the damage it was checking for.
    """
    url = os.getenv("DATABASE_URL", "") or ""
    argv = sys.argv[1:] if argv is None else argv

    if _is_local(url):
        return url

    if OVERRIDE_PHRASE in argv:
        print(
            f"WARNING: {script_name} is deleting rows in {_target(url)}, which "
            f"is not a local database. You passed the override, so this is "
            f"deliberate.",
            file=sys.stderr,
        )
        return url

    raise RefusedError(
        f"\n{script_name} REFUSED TO RUN.\n\n"
        f"  DATABASE_URL points at {_target(url)}, which is not local.\n\n"
        f"This script DELETES every row in the tables it owns before seeding.\n"
        f"There is no staging, so that URL may well be production -- the same\n"
        f"database the demonstrations run against, and the one that will hold\n"
        f"real screenings once the pilot starts.\n\n"
        f"If a local database is what you meant, unset DATABASE_URL or point\n"
        f"it at a SQLite file:\n\n"
        f"    set DATABASE_URL=sqlite:///./data/silicaguard.db\n\n"
        f"If you genuinely mean to delete rows in that database, say so:\n\n"
        f"    python scripts/{script_name} {OVERRIDE_PHRASE}\n"
    )
