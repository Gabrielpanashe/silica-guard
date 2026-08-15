"""Smart Referral Router — reminder/escalation cascade. SILICAGUARD.md
Section 10, AI module 3: "schedules the reminder cascade (day 3, day 7) and
the day-14 escalation task". Triggered periodically by the APScheduler job
in main.py (see run_scheduled_cascade), never called synchronously from a
request — so it's a background process, not part of any request/response
cycle.

Cadence (reusing the fixed urgency windows from services/referrals.py's
_URGENCY_WINDOW, not re-hardcoded here):
- RED (48h window): one reminder at the 24h mark, escalate at 48h.
- ORANGE (14-day window): reminder at day 3, second reminder at day 7,
  escalate at day 14. (The doc's "day 3, day 7, day 14" cadence is
  ORANGE-shaped; RED's single 24h reminder is this project's own
  extension for its much tighter emergency window — flagged as a
  judgment call, not dictated by the reference doc.)

Escalation always takes priority over a reminder check — a referral that's
badly overdue should escalate, not receive a stale reminder first.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_fresh_session
from db_models import Miner, Referral, Screening
from services import notifications
from services.referrals import _URGENCY_WINDOW

logger = logging.getLogger("silicaguard.referral_cascade")

_ACTIONABLE_STATUSES = ("open", "pre_alerted", "reminded")
_RED_REMINDER_OFFSET = timedelta(hours=24)
_ORANGE_REMINDER_OFFSETS = (timedelta(days=3), timedelta(days=7))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def next_cascade_action(
    tier: str,
    status: str,
    reminder_stage: int,
    created_at: datetime,
    now: Optional[datetime] = None,
) -> Optional[dict]:
    """Pure decision function — no DB access, injected `now` for testability
    (same pattern as services/deterioration.py). Returns None if nothing is
    due yet, {"action": "remind", "new_stage": N}, or {"action": "escalate"}.
    """
    if status not in _ACTIONABLE_STATUSES or tier not in _URGENCY_WINDOW:
        return None

    now = now if now is not None else _utcnow()

    if now >= created_at + _URGENCY_WINDOW[tier]:
        return {"action": "escalate"}

    if tier == "RED":
        if reminder_stage < 1 and now >= created_at + _RED_REMINDER_OFFSET:
            return {"action": "remind", "new_stage": 1}
    elif tier == "ORANGE":
        for stage, offset in enumerate(_ORANGE_REMINDER_OFFSETS, start=1):
            if reminder_stage < stage and now >= created_at + offset:
                return {"action": "remind", "new_stage": stage}

    return None


def process_due_referrals(db: Session, now: Optional[datetime] = None) -> None:
    """Checks every referral still in an actionable status and applies
    whatever cascade action is due. Each row is wrapped in its own
    try/except so one bad row can't abort the batch — mirrors
    notifications.py's own "failures are logged, not raised" convention.

    Fetches IDs first, in a query that only touches the `status` column,
    then loads each full row (which does deserialize `created_at` into a
    real datetime, and can raise on a corrupted value) INSIDE the
    try/except — deliberately, so a single row with unparsable data still
    can't abort the batch. A single `select(Referral)` for everything up
    front would hydrate every row's `created_at` during that one call,
    outside any per-row try/except, and one bad value would fail the
    entire fetch before the loop even started."""
    now = now if now is not None else _utcnow()

    referral_ids = db.scalars(
        select(Referral.id).where(Referral.status.in_(_ACTIONABLE_STATUSES))
    ).all()

    for referral_id in referral_ids:
        try:
            referral = db.get(Referral, referral_id)
            screening = referral.screening
            miner = referral.miner
            action = next_cascade_action(
                screening.tier, referral.status, referral.reminder_stage, referral.created_at, now
            )
            if action is None:
                continue

            if action["action"] == "remind":
                notifications.send_referral_reminder(
                    miner.id, miner.phone, screening.tier, action["new_stage"]
                )
                referral.status = "reminded"
                referral.reminder_stage = action["new_stage"]
            elif action["action"] == "escalate":
                notifications.send_referral_escalation(
                    miner.id, miner.name, miner.phone, screening.tier
                )
                referral.status = "escalated"
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed to process referral cascade for referral id=%s", referral_id)


def run_scheduled_cascade() -> None:
    """The APScheduler job target (main.py) — opens and closes its own
    session, never raises (a scheduler job that raises can kill the
    scheduler thread depending on misfire config, so this is defensive)."""
    db = get_fresh_session()
    try:
        process_due_referrals(db)
    except Exception:
        logger.exception("Referral cascade run failed")
    finally:
        db.close()
