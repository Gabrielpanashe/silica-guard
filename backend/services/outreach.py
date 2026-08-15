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
session and never raises.

`report_generated` is approximated as "the visit's scheduled_date has
passed" — there is no genuine mobile-app-finished-syncing signal anywhere
in the schema today. A known, deliberate simplification, not an oversight.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_fresh_session
from db_models import Miner, OutreachVisit, Referral, Screening
from models import OutreachVisitOut, ReferralListItem
from services import notifications

logger = logging.getLogger("silicaguard.outreach")

_SMS_1DAY_WINDOW = timedelta(days=1)
_SMS_3DAY_WINDOW = timedelta(days=3)
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
    still count). Lowest-id tiebreak on multiple matches.

    `visits` elements are accessed by ["site"]/["scheduled_date"]/["id"]
    subscript — deliberately left dict/Row-subscriptable rather than typed
    to the OutreachVisit ORM model, since the one caller (routers/screening.py)
    hasn't been converted to the ORM yet and still passes sqlite3.Row
    objects here. Convert this signature when that caller is converted."""
    if not mine_site:
        return None

    site_key = mine_site.strip().lower()
    screened_date = screened_at.date()
    candidates = []
    for visit in visits:
        if (visit["site"] or "").strip().lower() != site_key:
            continue
        scheduled = visit["scheduled_date"]
        if isinstance(scheduled, str):
            try:
                visit_date = datetime.strptime(scheduled, "%Y-%m-%d").date()
            except (TypeError, ValueError):
                continue
        elif isinstance(scheduled, date):
            visit_date = scheduled
        else:
            continue
        if visit_date <= screened_date <= visit_date + timedelta(days=1):
            candidates.append(visit)

    if not candidates:
        return None
    return sorted(candidates, key=lambda v: v["id"])[0]


def process_due_outreach_visits(db: Session, now: Optional[datetime] = None) -> None:
    """Checks every visit that still has something pending (an announcement
    not yet sent, or the report not yet marked ready) and applies whatever
    is due. Each row wrapped in its own try/except, same isolation as
    process_due_referrals — one bad row can't abort the batch."""
    now = now if now is not None else _utcnow()

    visits = db.scalars(
        select(OutreachVisit).where(
            (OutreachVisit.report_generated == 0)
            | (OutreachVisit.sms_3day_sent == 0)
            | (OutreachVisit.sms_1day_sent == 0)
        )
    ).all()

    for visit in visits:
        try:
            action = next_outreach_action(
                visit.scheduled_date,
                bool(visit.sms_3day_sent),
                bool(visit.sms_1day_sent),
                bool(visit.report_generated),
                now,
            )
            if action is None:
                continue

            if action["action"] in ("sms_3day", "sms_1day"):
                stage = "3day" if action["action"] == "sms_3day" else "1day"
                workers = db.scalars(
                    select(Miner).where(func.lower(Miner.mine_site) == func.lower(visit.site))
                ).all()
                for worker in workers:
                    notifications.send_outreach_announcement(
                        worker.id, worker.phone, visit.site, visit.scheduled_date.isoformat(), stage
                    )
                if stage == "3day":
                    visit.sms_3day_sent = 1
                else:
                    visit.sms_1day_sent = 1
            elif action["action"] == "mark_report_ready":
                visit.report_generated = 1
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed to process outreach visit id=%s", visit.id)


def run_scheduled_outreach() -> None:
    """The APScheduler job target (main.py) — same defensive shape as
    run_scheduled_cascade: owns its own session, never raises."""
    db = get_fresh_session()
    try:
        process_due_outreach_visits(db)
    except Exception:
        logger.exception("Outreach visit processing run failed")
    finally:
        db.close()


def build_visit_report(db: Session, visit: OutreachVisit) -> tuple[Optional[dict], Optional[list]]:
    """Used by GET /api/outreach. Returns (tier_distribution, referral_list),
    both None if the visit's report isn't ready yet — computed live from
    screenings/referrals joined on outreach_visit_id, not stored as a
    static blob, so it can't go stale if a referral's status changes after
    the visit date passes."""
    if not visit.report_generated:
        return None, None

    screenings = db.scalars(
        select(Screening).where(
            Screening.outreach_visit_id == visit.id, Screening.tier.is_not(None)
        )
    ).all()
    tier_counts: dict[str, int] = {}
    for s in screenings:
        tier_counts[s.tier] = tier_counts.get(s.tier, 0) + 1
    tier_distribution = {tier: tier_counts.get(tier, 0) for tier in _TIERS}

    referral_rows = db.execute(
        select(Miner.name, Screening.tier, Referral.status)
        .select_from(Screening)
        .join(Miner, Miner.id == Screening.miner_id)
        .join(Referral, Referral.screening_id == Screening.id)
        .where(Screening.outreach_visit_id == visit.id)
    ).all()
    referral_list = [
        {"miner_name": row[0], "tier": row[1], "status": row[2]} for row in referral_rows
    ]

    return tier_distribution, referral_list


def visit_to_out(db: Session, visit: OutreachVisit) -> OutreachVisitOut:
    """One shared mapping from an OutreachVisit to the API shape, used by
    both GET/POST /api/outreach (routers/outreach.py) and
    GET /api/dashboard/today (routers/dashboard.py) — factored out so the
    VHW's unauthenticated Outreach Stats view and the coordinator's
    authenticated /api/outreach view can never drift."""
    tier_distribution, referral_list = build_visit_report(db, visit)
    return OutreachVisitOut(
        id=visit.id,
        site=visit.site,
        scheduled_date=visit.scheduled_date.isoformat() if visit.scheduled_date else None,
        expected_headcount=visit.expected_headcount,
        screened_count=visit.screened_count,
        report_generated=bool(visit.report_generated),
        tier_distribution=tier_distribution,
        referral_list=[ReferralListItem(**item) for item in referral_list] if referral_list is not None else None,
    )
