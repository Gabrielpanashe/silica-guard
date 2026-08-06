"""Outreach Planner. SILICAGUARD.md Section 11: a coordinator schedules a
visit (site, date, expected headcount); the system bulk-SMSes registered
workers at that site 3 days and 1 day before; on the day the app tracks
screened count live against expected headcount; on sync, a post-visit
report (attendance, tier distribution, referral list) generates
automatically for the hospital dashboard.

Same shape as services/referral_cascade.py throughout: a pure decision
function with an injected `now` (next_outreach_action), a DB-driving
function that applies it (process_due_outreach_visits), and a thin
APScheduler-facing wrapper (run_scheduled_outreach) that owns its own
connection and never raises.

`report_generated` is approximated as "the visit's scheduled_date has
passed" — there is no genuine mobile-app-finished-syncing signal anywhere
in the schema today. A known, deliberate simplification, not an oversight.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Sequence

from database import get_connection
from services import notifications

logger = logging.getLogger("silicaguard.outreach")

_SMS_1DAY_WINDOW = timedelta(days=1)
_SMS_3DAY_WINDOW = timedelta(days=3)
_SCHEDULED_DATE_FORMAT = "%Y-%m-%d"
_TIERS = ("GREEN", "YELLOW", "ORANGE", "RED")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def next_outreach_action(
    scheduled_date: date,
    sms_3day_sent: bool,
    sms_1day_sent: bool,
    report_generated: bool,
    now: Optional[datetime] = None,
) -> Optional[dict]:
    """Pure decision function — no DB access, injected `now` (same pattern
    as services/referral_cascade.py's next_cascade_action). Once the visit
    date has passed, report-readiness takes priority over any still-pending
    SMS action (sending a "3 days before" reminder after the visit already
    happened makes no sense). Otherwise the 1-day threshold is checked
    before the 3-day one, so a very-overdue visit gets the more urgent
    action first."""
    now = now if now is not None else _utcnow()
    today = now.date()

    if today > scheduled_date:
        return None if report_generated else {"action": "mark_report_ready"}

    if not sms_1day_sent and today >= scheduled_date - _SMS_1DAY_WINDOW:
        return {"action": "sms_1day"}
    if not sms_3day_sent and today >= scheduled_date - _SMS_3DAY_WINDOW:
        return {"action": "sms_3day"}

    return None


def match_active_visit(mine_site: Optional[str], screened_at: datetime, visits: Sequence) -> Optional[dict]:
    """Pure, no DB access. Case-insensitive exact site match, within the
    visit day through visit day + 1 (tolerates offline sync lag — a
    screening captured on the visit day but synced the next morning should
    still count). Lowest-id tiebreak on multiple matches."""
    if not mine_site:
        return None

    site_key = mine_site.strip().lower()
    screened_date = screened_at.date()
    candidates = []
    for visit in visits:
        if (visit["site"] or "").strip().lower() != site_key:
            continue
        try:
            visit_date = datetime.strptime(visit["scheduled_date"], _SCHEDULED_DATE_FORMAT).date()
        except (TypeError, ValueError):
            continue
        if visit_date <= screened_date <= visit_date + timedelta(days=1):
            candidates.append(visit)

    if not candidates:
        return None
    return sorted(candidates, key=lambda v: v["id"])[0]


def process_due_outreach_visits(conn, now: Optional[datetime] = None) -> None:
    """Checks every visit that still has something pending (an announcement
    not yet sent, or the report not yet marked ready) and applies whatever
    is due. Each row wrapped in its own try/except, same isolation as
    process_due_referrals — one bad row can't abort the batch."""
    now = now if now is not None else _utcnow()

    rows = conn.execute(
        """SELECT id, site, scheduled_date, sms_3day_sent, sms_1day_sent, report_generated
           FROM outreach_visits
           WHERE report_generated = 0 OR sms_3day_sent = 0 OR sms_1day_sent = 0"""
    ).fetchall()

    for row in rows:
        try:
            scheduled = datetime.strptime(row["scheduled_date"], _SCHEDULED_DATE_FORMAT).date()
            action = next_outreach_action(
                scheduled,
                bool(row["sms_3day_sent"]),
                bool(row["sms_1day_sent"]),
                bool(row["report_generated"]),
                now,
            )
            if action is None:
                continue

            if action["action"] in ("sms_3day", "sms_1day"):
                stage = "3day" if action["action"] == "sms_3day" else "1day"
                column = "sms_3day_sent" if stage == "3day" else "sms_1day_sent"
                workers = conn.execute(
                    "SELECT id, phone FROM miners WHERE LOWER(mine_site) = LOWER(?)",
                    (row["site"],),
                ).fetchall()
                for worker in workers:
                    notifications.send_outreach_announcement(
                        worker["id"], worker["phone"], row["site"], row["scheduled_date"], stage
                    )
                conn.execute(
                    f"UPDATE outreach_visits SET {column} = 1 WHERE id = ?", (row["id"],)
                )
            elif action["action"] == "mark_report_ready":
                conn.execute(
                    "UPDATE outreach_visits SET report_generated = 1 WHERE id = ?", (row["id"],)
                )
            conn.commit()
        except Exception:
            logger.exception("Failed to process outreach visit id=%s", row["id"])


def run_scheduled_outreach() -> None:
    """The APScheduler job target (main.py) — same defensive shape as
    run_scheduled_cascade: owns its own connection, never raises."""
    conn = get_connection()
    try:
        process_due_outreach_visits(conn)
    except Exception:
        logger.exception("Outreach visit processing run failed")
    finally:
        conn.close()


def build_visit_report(conn, visit_row) -> tuple[Optional[dict], Optional[list]]:
    """Used by GET /api/outreach. Returns (tier_distribution, referral_list),
    both None if the visit's report isn't ready yet — computed live from
    screenings/referrals joined on outreach_visit_id, not stored as a
    static blob, so it can't go stale if a referral's status changes after
    the visit date passes."""
    if not visit_row["report_generated"]:
        return None, None

    tier_counts = {
        row["tier"]: row["count"]
        for row in conn.execute(
            """SELECT tier, COUNT(*) AS count FROM screenings
               WHERE outreach_visit_id = ? AND tier IS NOT NULL
               GROUP BY tier""",
            (visit_row["id"],),
        )
    }
    tier_distribution = {tier: tier_counts.get(tier, 0) for tier in _TIERS}

    referral_rows = conn.execute(
        """SELECT m.name AS miner_name, s.tier, r.status
           FROM screenings s
           JOIN miners m ON m.id = s.miner_id
           JOIN referrals r ON r.screening_id = s.id
           WHERE s.outreach_visit_id = ?""",
        (visit_row["id"],),
    ).fetchall()
    referral_list = [
        {"miner_name": row["miner_name"], "tier": row["tier"], "status": row["status"]}
        for row in referral_rows
    ]

    return tier_distribution, referral_list
