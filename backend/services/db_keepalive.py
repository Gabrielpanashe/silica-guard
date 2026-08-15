"""Supabase free-tier keep-alive (master doc v6.0 Section 16.2): a free
Supabase project pauses automatically after 7 days with no database activity
and takes about 30 seconds to wake. Submission is 24 August, the final
showcase is 28 August — if nobody touches the database in between, it could
be asleep exactly when a judge asks for a live demonstration.

This job upserts one fixed row (id=1) on the same APScheduler cadence as the
referral cascade (every SCHEDULER_INTERVAL_MINUTES, default 10 minutes) —
far more often than the 7-day window strictly needs, but it's the same
scheduler infrastructure already running, so there's no reason to build
anything lower-frequency. Same fail-quiet design as the other scheduled jobs
in this codebase (see services/referral_cascade.py): a keep-alive that
itself crashes the scheduler thread would be worse than no keep-alive at
all.

This does NOT replace the master doc's other recommended mitigation —
upgrading the Supabase project to Pro ($25 for the critical month) removes
pausing entirely. That's a one-time manual dashboard/billing action, not
something this code can do.
"""

import logging
from datetime import datetime, timezone

from database import get_fresh_session
from db_models import KeepAlivePing

logger = logging.getLogger("silicaguard.db_keepalive")


def ping_database() -> None:
    db = get_fresh_session()
    try:
        row = db.get(KeepAlivePing, 1)
        if row is None:
            row = KeepAlivePing(id=1)
            db.add(row)
        row.pinged_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
        logger.info("Supabase keep-alive ping written")
    except Exception:
        logger.exception("Supabase keep-alive ping failed")
        db.rollback()
    finally:
        db.close()


def run_scheduled_keepalive() -> None:
    """APScheduler job target — see main.py's lifespan."""
    ping_database()
