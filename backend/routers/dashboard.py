import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from database import get_connection
from models import (
    DashboardTodayOut,
    MinerSummary,
    ReferNowItem,
    ReferNowSection,
    ReferralNotifyOut,
    ReferralNotifyRequest,
    ReferralOut,
    ReferralStatusUpdate,
    ScreeningLogItem,
    TodaysLogItem,
    WatchItem,
    WatchSection,
)
from routers.auth import get_current_user
from services import email_notifications
from services.outreach import visit_to_out
from services.population_intelligence import generate_weekly_narrative

router = APIRouter(prefix="/api", tags=["dashboard"])

_VALID_REFERRAL_STATUSES = {"open", "pre_alerted", "reminded", "attended", "closed", "escalated"}
_TIERS = ("GREEN", "YELLOW", "ORANGE", "RED")
# "Refer Now" = a referral that hasn't been resolved yet (attended or closed
# both mean action was already taken — they drop off this list). Includes
# 'escalated', which is still more, not less, in need of follow-up.
_OPEN_REFERRAL_STATUSES = ("open", "pre_alerted", "reminded", "escalated")


def _referral_row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "miner_name": row["miner_name"],
        "mine_site": row["mine_site"],
        "tier": row["tier"],
        "status": row["status"],
        "deadline": row["deadline"],
        "pre_alert_sent": bool(row["pre_alert_sent"]),
        "facility_id": row["facility_id"],
        "facility_name": row["facility_name"],
        "reminder_stage": row["reminder_stage"],
        "attended_at": row["attended_at"],
        "closed_at": row["closed_at"],
        "created_at": row["created_at"],
    }


_REFERRAL_SELECT = """
    SELECT r.id, m.name AS miner_name, m.mine_site, s.tier,
           r.status, r.deadline, r.pre_alert_sent,
           r.facility_id, f.name AS facility_name, r.reminder_stage,
           r.attended_at, r.closed_at, r.created_at
    FROM referrals r
    JOIN miners m ON m.id = r.miner_id
    JOIN screenings s ON s.id = r.screening_id
    LEFT JOIN facilities f ON f.id = r.facility_id
"""


@router.get("/dashboard/today", response_model=DashboardTodayOut)
def dashboard_today(site: Optional[str] = None):
    """Powers the mobile Home screen's live numbers (Screened Today / Refer
    Now / Watch / Today's Log) — previously all hardcoded to 0 client-side.
    Unauthenticated, same VHW-in-the-field precedent as POST /api/screen and
    GET /api/workers/{phone} — and the same tradeoff as that route: this
    returns miner names/phone numbers/tiers without a login, a materially
    bigger exposure than a write-only route, accepted here for the same
    reason (a field worker has no dashboard session, and needs to actually
    call a miner back to follow up).

    'Today' = server UTC calendar date (SQLite's date('now')) — Zimbabwe is
    UTC+2 (CAT), so a screening in the last ~2 hours before UTC midnight can
    appear on the 'wrong' day. A known simplification, not a bug — same
    class of approximation as outreach_visits.report_generated.

    'Refer Now' is a live worklist, not scoped to today — a referral from
    three days ago that's still open belongs on it; it drops off once its
    status becomes 'attended' or 'closed', which is how "have they taken
    action" gets answered by re-polling this endpoint. 12 August: narrowed
    to RED only (was any open referral, i.e. ORANGE or RED) — a VHW-facing
    scope decision for Home's worklist specifically; ORANGE referrals are
    still created and tracked exactly as before, still visible on the web
    dashboard's full referral queue (GET /api/referrals, unfiltered by
    tier) — they just no longer surface on this specific mobile worklist.

    'Watch' = miners whose most recent screening is ORANGE (12 August, was
    YELLOW) — "keep an eye on them, not yet critical" per this same Home
    worklist's new tier split (RED = act now, ORANGE = watch). Still
    sourced from screenings, not referrals, same as before — an ORANGE
    miner appearing here doesn't mean they lack a referral (they still get
    one), it's this list's own membership rule.
    'outreach_visits' (10 August) reuses services/outreach.visit_to_out —
    the same per-visit shape (screened/expected headcount, report-ready
    tier_distribution/referral_list) GET /api/outreach returns to a
    logged-in coordinator, here unauthenticated for the VHW's Outreach
    Stats screen.

    optional ?site= filters all five sections by miners.mine_site /
    outreach_visits.site (case-insensitive), matching the VHW's current
    outreach site."""
    conn = get_connection()
    try:
        site_filter = "AND LOWER(m.mine_site) = LOWER(?)" if site else ""
        site_args = (site,) if site else ()

        todays_log_rows = conn.execute(
            f"""SELECT s.id AS screening_id, m.name AS miner_name, m.phone,
                       m.mine_site, s.tier, s.created_at
                FROM screenings s
                JOIN miners m ON m.id = s.miner_id
                WHERE date(s.created_at) = date('now') {site_filter}
                ORDER BY s.created_at DESC""",
            site_args,
        ).fetchall()
        todays_log = [TodaysLogItem(**dict(row)) for row in todays_log_rows]

        refer_now_rows = conn.execute(
            f"""SELECT r.id AS referral_id, m.name AS miner_name, m.phone,
                       m.mine_site, s.tier, r.status, r.deadline
                FROM referrals r
                JOIN miners m ON m.id = r.miner_id
                JOIN screenings s ON s.id = r.screening_id
                WHERE r.status IN ({",".join("?" * len(_OPEN_REFERRAL_STATUSES))})
                  AND s.tier = 'RED'
                {site_filter}
                ORDER BY r.deadline ASC""",
            (*_OPEN_REFERRAL_STATUSES, *site_args),
        ).fetchall()
        refer_now_items = [ReferNowItem(**dict(row)) for row in refer_now_rows]

        watch_rows = conn.execute(
            f"""SELECT s.id AS screening_id, m.name AS miner_name, m.phone,
                       m.mine_site, s.tier, s.created_at
                FROM screenings s
                JOIN miners m ON m.id = s.miner_id
                WHERE s.tier = 'ORANGE'
                  AND s.id = (
                      SELECT s2.id FROM screenings s2
                      WHERE s2.miner_id = m.id
                      ORDER BY s2.created_at DESC, s2.id DESC LIMIT 1
                  )
                  {site_filter}
                ORDER BY s.created_at DESC""",
            site_args,
        ).fetchall()
        watch_items = [WatchItem(**dict(row)) for row in watch_rows]

        # Outreach Stats (10 August) — same shared mapping GET /api/outreach
        # uses, so a VHW with no login sees exactly the same visit data a
        # logged-in coordinator would, just scoped to their current site.
        outreach_filter = "WHERE LOWER(site) = LOWER(?)" if site else ""
        outreach_rows = conn.execute(
            f"SELECT * FROM outreach_visits {outreach_filter} ORDER BY scheduled_date DESC",
            site_args,
        ).fetchall()
        outreach_visits = [visit_to_out(conn, row) for row in outreach_rows]

        return DashboardTodayOut(
            screened_today=len(todays_log),
            todays_log=todays_log,
            refer_now=ReferNowSection(count=len(refer_now_items), items=refer_now_items),
            watch=WatchSection(count=len(watch_items), items=watch_items),
            outreach_visits=outreach_visits,
        )
    finally:
        conn.close()


@router.get("/dashboard/week")
def dashboard_week(user: dict = Depends(get_current_user)):
    """Real counts from the database. ai_narrative is now a real Gemini call
    (services/population_intelligence.py, Population Health Intelligence —
    SILICAGUARD.md Section 10 AI module 4), not the old hardcoded placeholder;
    it falls back to a deterministic string on any AI failure so this
    endpoint can never 500 because of it. Requires a valid JWT."""
    conn = get_connection()
    try:
        total_screened = conn.execute("SELECT COUNT(*) FROM screenings").fetchone()[0]
        high_risk_count = conn.execute(
            "SELECT COUNT(*) FROM screenings WHERE tier IN ('ORANGE', 'RED')"
        ).fetchone()[0]

        total_referrals = conn.execute("SELECT COUNT(*) FROM referrals").fetchone()[0]
        completed_referrals = conn.execute(
            "SELECT COUNT(*) FROM referrals WHERE status = 'closed'"
        ).fetchone()[0]
        referral_completion_rate = (
            completed_referrals / total_referrals if total_referrals else 0.0
        )

        site_breakdown = [
            {"mine_site": row["mine_site"] or "Unknown", "count": row["count"]}
            for row in conn.execute(
                """SELECT m.mine_site AS mine_site, COUNT(*) AS count
                   FROM screenings s
                   JOIN miners m ON m.id = s.miner_id
                   GROUP BY m.mine_site"""
            )
        ]

        tier_counts = {row["tier"]: row["count"] for row in conn.execute(
            """SELECT tier, COUNT(*) AS count FROM screenings
               WHERE tier IS NOT NULL GROUP BY tier"""
        )}
        tier_distribution = {tier: tier_counts.get(tier, 0) for tier in _TIERS}

        ai_narrative = generate_weekly_narrative(
            total_screened,
            high_risk_count,
            referral_completion_rate,
            tier_distribution,
            site_breakdown,
        )

        return {
            "total_screened": total_screened,
            "high_risk_count": high_risk_count,
            "referral_completion_rate": referral_completion_rate,
            "ai_narrative": ai_narrative,
            "tier_distribution": tier_distribution,
            "site_breakdown": site_breakdown,
        }
    finally:
        conn.close()


@router.get("/referrals", response_model=list[ReferralOut])
def list_referrals(user: dict = Depends(get_current_user)):
    conn = get_connection()
    try:
        rows = conn.execute(
            _REFERRAL_SELECT + " ORDER BY r.created_at DESC"
        ).fetchall()
        return [_referral_row_to_dict(row) for row in rows]
    finally:
        conn.close()


@router.patch("/referrals/{referral_id}", response_model=ReferralOut)
def update_referral_status(
    referral_id: int,
    payload: ReferralStatusUpdate,
    user: dict = Depends(get_current_user),
):
    if payload.status not in _VALID_REFERRAL_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"status must be one of {sorted(_VALID_REFERRAL_STATUSES)}",
        )

    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM referrals WHERE id = ?", (referral_id,)
        ).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Referral not found")

        timestamp_clause = ""
        if payload.status == "attended":
            timestamp_clause = ", attended_at = CURRENT_TIMESTAMP"
        elif payload.status == "closed":
            timestamp_clause = ", closed_at = CURRENT_TIMESTAMP"
        conn.execute(
            f"UPDATE referrals SET status = ?{timestamp_clause} WHERE id = ?",
            (payload.status, referral_id),
        )
        conn.commit()

        row = conn.execute(
            _REFERRAL_SELECT + " WHERE r.id = ?", (referral_id,)
        ).fetchone()
        return _referral_row_to_dict(row)
    finally:
        conn.close()


@router.post("/referrals/notify-email", response_model=ReferralNotifyOut)
def notify_referral_email(payload: ReferralNotifyRequest):
    """Unauthenticated (mobile-facing), 12 August — fires when the VHW taps
    'Generate Referral Card' on the app, giving the demo a live, watchable
    email moment tied to that exact tap rather than a silent send that
    already happened at referral-creation time inside POST /api/screen
    (services/referrals.create_referral_and_notify). This is a deliberate
    re-send of the same email, not the only time it fires — the automatic
    one still fires too, since a hospital shouldn't wait on a miner to tap
    a button to be pre-alerted."""
    conn = get_connection()
    try:
        miner = conn.execute(
            "SELECT * FROM miners WHERE phone = ?", (payload.phone,)
        ).fetchone()
        if miner is None:
            raise HTTPException(status_code=404, detail="Worker not found")

        row = conn.execute(
            """SELECT r.deadline, r.facility_id, f.name AS facility_name,
                      s.tier, s.ai_contributing_factors
               FROM referrals r
               JOIN screenings s ON s.id = r.screening_id
               LEFT JOIN facilities f ON f.id = r.facility_id
               WHERE r.miner_id = ?
               ORDER BY r.created_at DESC, r.id DESC
               LIMIT 1""",
            (miner["id"],),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="No referral found for this worker")

        factors = json.loads(row["ai_contributing_factors"]) if row["ai_contributing_factors"] else []
        sent = email_notifications.send_referral_alert_email(
            miner["id"],
            miner["name"],
            miner["phone"],
            miner["mine_site"],
            row["tier"],
            row["facility_name"] or "Kwekwe District Hospital",
            row["deadline"] or "",
            factors,
        )
        return ReferralNotifyOut(sent=sent, tier=row["tier"], facility_name=row["facility_name"])
    finally:
        conn.close()


@router.get("/miners", response_model=list[MinerSummary])
def list_miners(user: dict = Depends(get_current_user)):
    """Every registered miner, most recently active first — the dashboard's
    Miners directory (10 August). Distinct from GET /api/workers/{phone}
    (unauthenticated, single-miner lookup for the VHW re-screen flow): this
    is the full roster for a logged-in coordinator, so it's authenticated
    like /api/referrals and /api/dashboard/week."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT m.id, m.name, m.phone, m.mine_site AS site, m.created_at,
                      COUNT(s.id) AS screening_count,
                      MAX(s.created_at) AS last_screened_at,
                      (SELECT s2.tier FROM screenings s2
                       WHERE s2.miner_id = m.id
                       ORDER BY s2.created_at DESC, s2.id DESC LIMIT 1) AS latest_tier
               FROM miners m
               LEFT JOIN screenings s ON s.miner_id = m.id
               GROUP BY m.id
               ORDER BY COALESCE(MAX(s.created_at), m.created_at) DESC"""
        ).fetchall()
        return [MinerSummary(**dict(row)) for row in rows]
    finally:
        conn.close()


@router.get("/screenings", response_model=list[ScreeningLogItem])
def list_screenings(limit: int = 200, user: dict = Depends(get_current_user)):
    """Every screening across every miner and channel (APP/USSD), most
    recent first — the dashboard's All Screenings activity log (10 August).
    `limit` (default 200) caps the response; the demo dataset is small
    enough this rarely matters, but a growing pilot deployment shouldn't
    return an unbounded list to a browser tab."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT s.id, s.miner_id, m.name AS miner_name, m.phone,
                      m.mine_site AS site, s.tier, s.channel, s.advice_line, s.created_at
               FROM screenings s
               JOIN miners m ON m.id = s.miner_id
               ORDER BY s.created_at DESC, s.id DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return [ScreeningLogItem(**dict(row)) for row in rows]
    finally:
        conn.close()
