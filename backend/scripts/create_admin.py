"""Create the first administrator.

    ./venv/Scripts/python.exe scripts/create_admin.py admin@example.org
    ./venv/Scripts/python.exe scripts/create_admin.py admin@example.org --role administrator

Master Reference v1.0 §16.3, §16.6.

**Why this is a script and not a route.** Creating a user needs
`admin.manage`, and on a fresh database nobody holds it — the two prototype
accounts deliberately do not, because widening a credential that exists only
to be retired is the opposite of the point. That leaves a bootstrap deadlock,
and there are exactly three ways out:

  1. Give the prototype accounts `admin.manage`. Rejected: it widens the
     credential this whole item exists to replace, and a prototype password
     from an environment variable would then be able to create a real
     administrator.
  2. Let `POST /api/v2/users` run unauthenticated while the table is empty.
     Rejected: an unauthenticated user-creation endpoint, however briefly, is
     a window in which whoever reaches a fresh instance first owns it. On a
     public URL that window is measured in minutes.
  3. Require database access for the first administrator. **Chosen**, and it
     is also how every system that takes this seriously does it: the person
     who can run a command against the production database is already the
     person who could create an administrator by hand.

Running this **retires the two prototype environment-variable accounts**,
because they authenticate only while the `users` table is empty. That is the
intended effect, not a side effect, and the script says so before it exits.

The password is read from the terminal and never taken as an argument: an
argument lands in shell history and in the process table.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import get_fresh_session  # noqa: E402
from services import audit, authz  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create the first administrator, retiring the prototype accounts."
    )
    parser.add_argument("email")
    parser.add_argument(
        "--role",
        default="administrator",
        help="Defaults to administrator. Any role in services/authz.ROLES.",
    )
    parser.add_argument("--name", default=None)
    parser.add_argument("--facility-id", type=int, default=None)
    parser.add_argument("--district", default=None)
    parser.add_argument("--programme-id", type=int, default=None)
    parser.add_argument(
        "--site-ids",
        default=None,
        help="Comma-separated site ids, for a village health worker.",
    )
    args = parser.parse_args(argv)

    password = os.getenv("SILICAGUARD_ADMIN_PASSWORD") or getpass.getpass(
        "Password (at least 8 characters, not echoed): "
    )
    if not password:
        print("No password given; nothing was created.", file=sys.stderr)
        return 2

    db = get_fresh_session()
    try:
        already = authz.any_user_exists(db)
        user = authz.create_user(
            db,
            args.email,
            password,
            args.role,
            name=args.name,
            facility_id=args.facility_id,
            site_ids=[int(s) for s in args.site_ids.split(",")] if args.site_ids else None,
            district=args.district,
            programme_id=args.programme_id,
        )
        audit.record(
            db,
            authz.principal_for(user),
            "admin.user_create",
            object_type="user",
            object_id=user.id,
            details={"role": user.role, "via": "create_admin.py", "bootstrap": not already},
        )
        db.commit()
    except authz.AuthzError as exc:
        db.rollback()
        print(f"Refused: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()

    print(f"Created {args.email} as {args.role}.")
    if not already:
        print(
            "\nThe two prototype environment-variable accounts "
            "(HOSPITAL_EMAIL, CIMAS_EMAIL) have just stopped working. They "
            "authenticate only while the users table is empty, which is what "
            "makes the fallback self-disarming rather than a flag somebody "
            "has to remember to turn off.\n\n"
            "The dashboard will need real credentials from now on."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
