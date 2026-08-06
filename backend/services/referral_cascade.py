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

from database import get_connection
from services import notifications
from services.referrals import _URGENCY_WINDOW

logger = logging.getLogger("silicaguard.referral_cascade")

_ACTIONABLE_STATUSES = ("open", "pre_alerted", "reminded")
_RED_REMINDER_OFFSET = timedelta(hours=24)
_ORANGE_REMINDER_OFFSETS = (timedelta(days=3), timedelta(days=7))

_CREATED_AT_FORMAT = "%Y-%m-%d %H:%M:%S"


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


def process_due_referrals(conn, now: Optional[datetime] = None) -> None:
    """Checks every referral still in an actionable status and applies
    whatever cascade action is due. Each row is wrapped in its own
    try/except so one bad row can't abort the batch — mirrors
    notifications.py's own "failures are logged, not raised" convention."""
    now = now if now is not None else _utcnow()

    rows = conn.execute(
        """SELECT r.id, r.status, r.reminder_stage, r.created_at,
                  s.tier, m.id AS worker_id, m.name AS miner_name, m.phone
           FROM referrals r
           JOIN screenings s ON s.id = r.screening_id
           JOIN miners m ON m.id = r.miner_id
           WHERE r.status IN ('open', 'pre_alerted', 'reminded')"""
    ).fetchall()

    for row in rows:
        try:
            created_at = datetime.strptime(row["created_at"], _CREATED_AT_FORMAT)
            action = next_cascade_action(
                row["tier"], row["status"], row["reminder_stage"], created_at, now
            )
            if action is None:
                continue

            if action["action"] == "remind":
                notifications.send_referral_reminder(
                    row["worker_id"], row["phone"], row["tier"], action["new_stage"]
                )
                conn.execute(
                    "UPDATE referrals SET status = 'reminded', reminder_stage = ? WHERE id = ?",
                    (action["new_stage"], row["id"]),
                )
            elif action["action"] == "escalate":
                notifications.send_referral_escalation(
                    row["worker_id"], row["miner_name"], row["phone"], row["tier"]
                )
                conn.execute(
                    "UPDATE referrals SET status = 'escalated' WHERE id = ?",
                    (row["id"],),
                )
            conn.commit()
        except Exception:
            logger.exception("Failed to process referral cascade for referral id=%s", row["id"])


def run_scheduled_cascade() -> None:
    """The APScheduler job target (main.py) — opens and closes its own
    connection, never raises (a scheduler job that raises can kill the
    scheduler thread depending on misfire config, so this is defensive)."""
    conn = get_connection()
    try:
        process_due_referrals(conn)
    except Exception:
        logger.exception("Referral cascade run failed")
    finally:
        conn.close()
