import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import format_datetime, get_db
from db_models import Facility, Miner, OutreachVisit, Referral, Screening
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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _referral_to_out(referral: Referral) -> ReferralOut:
    return ReferralOut(
        id=referral.id,
        miner_name=referral.miner.name,
        mine_site=referral.miner.mine_site,
        tier=referral.screening.tier,
        status=referral.status,
        deadline=format_datetime(referral.deadline),
        pre_alert_sent=bool(referral.pre_alert_sent),
        facility_id=referral.facility_id,
        facility_name=referral.facility.name if referral.facility else None,
        referral_code=referral.referral_code,
        reminder_stage=referral.reminder_stage,
        attended_at=format_datetime(referral.attended_at),
        closed_at=format_datetime(referral.closed_at),
        created_at=format_datetime(referral.created_at),
    )


@router.get("/dashboard/today", response_model=DashboardTodayOut)
def dashboard_today(site: Optional[str] = None, db: Session = Depends(get_db)):
    """Powers the mobile Home screen's live numbers (Screened Today / Refer
    Now / Watch / Today's Log) — previously all hardcoded to 0 client-side.
    Unauthenticated, same VHW-in-the-field precedent as POST /api/screen and
    GET /api/workers/{phone} — and the same tradeoff as that route: this
    returns miner names/phone numbers/tiers without a login, a materially
    bigger exposure than a write-only route, accepted here for the same
    reason (a field worker has no dashboard session, and needs to actually
    call a miner back to follow up).

    'Today' = server UTC calendar date (computed in Python, not a
    dialect-specific SQL date function, so this stays portable to Postgres
    ahead of the Step B cutover) — Zimbabwe is UTC+2 (CAT), so a screening
    in the last ~2 hours before UTC midnight can appear on the 'wrong' day.
    A known simplification, not a bug — same class of approximation as
    outreach_visits.report_generated.

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
    site_key = site.strip().lower() if site else None

    today_start = _utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    todays_log_stmt = (
        select(Screening, Miner)
        .join(Miner, Miner.id == Screening.miner_id)
        .where(Screening.created_at >= today_start, Screening.created_at < today_end)
        .order_by(Screening.created_at.desc())
    )
    if site_key:
        todays_log_stmt = todays_log_stmt.where(func.lower(Miner.mine_site) == site_key)
    todays_log = [
        TodaysLogItem(
            screening_id=s.id,
            miner_name=m.name,
            phone=m.phone,
            mine_site=m.mine_site,
            tier=s.tier,
            created_at=format_datetime(s.created_at),
        )
        for s, m in db.execute(todays_log_stmt).all()
    ]

    refer_now_stmt = (
        select(Referral, Miner, Screening)
        .join(Miner, Miner.id == Referral.miner_id)
        .join(Screening, Screening.id == Referral.screening_id)
        .where(Referral.status.in_(_OPEN_REFERRAL_STATUSES), Screening.tier == "RED")
        .order_by(Referral.deadline.asc())
    )
    if site_key:
        refer_now_stmt = refer_now_stmt.where(func.lower(Miner.mine_site) == site_key)
    refer_now_items = [
        ReferNowItem(
            referral_id=r.id,
            miner_name=m.name,
            phone=m.phone,
            mine_site=m.mine_site,
            tier=s.tier,
            status=r.status,
            deadline=format_datetime(r.deadline),
            referral_code=r.referral_code,
            facility_name=r.hospital,
        )
        for r, m, s in db.execute(refer_now_stmt).all()
    ]

    latest_screening_id_subq = (
        select(Screening.id)
        .where(Screening.miner_id == Miner.id)
        .order_by(Screening.created_at.desc(), Screening.id.desc())
        .limit(1)
        .correlate(Miner)
        .scalar_subquery()
    )
    watch_stmt = (
        select(Screening, Miner)
        .join(Miner, Miner.id == Screening.miner_id)
        .where(Screening.tier == "ORANGE", Screening.id == latest_screening_id_subq)
        .order_by(Screening.created_at.desc())
    )
    if site_key:
        watch_stmt = watch_stmt.where(func.lower(Miner.mine_site) == site_key)
    watch_items = [
        WatchItem(
            screening_id=s.id,
            miner_name=m.name,
            phone=m.phone,
            mine_site=m.mine_site,
            tier=s.tier,
            created_at=format_datetime(s.created_at),
        )
        for s, m in db.execute(watch_stmt).all()
    ]

    # Outreach Stats (10 August) — same shared mapping GET /api/outreach
    # uses, so a VHW with no login sees exactly the same visit data a
    # logged-in coordinator would, just scoped to their current site.
    outreach_stmt = select(OutreachVisit).order_by(OutreachVisit.scheduled_date.desc())
    if site_key:
        outreach_stmt = outreach_stmt.where(func.lower(OutreachVisit.site) == site_key)
    outreach_visits = [visit_to_out(db, v) for v in db.scalars(outreach_stmt).all()]

    return DashboardTodayOut(
        screened_today=len(todays_log),
        todays_log=todays_log,
        refer_now=ReferNowSection(count=len(refer_now_items), items=refer_now_items),
        watch=WatchSection(count=len(watch_items), items=watch_items),
        outreach_visits=outreach_visits,
    )


@router.get("/dashboard/week")
def dashboard_week(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """Real counts from the database. ai_narrative is now a real Gemini call
    (services/population_intelligence.py, Population Health Intelligence —
    SILICAGUARD.md Section 10 AI module 4), not the old hardcoded placeholder;
    it falls back to a deterministic string on any AI failure so this
    endpoint can never 500 because of it. Requires a valid JWT."""
    total_screened = db.scalar(select(func.count()).select_from(Screening))
    high_risk_count = db.scalar(
        select(func.count()).select_from(Screening).where(Screening.tier.in_(("ORANGE", "RED")))
    )

    total_referrals = db.scalar(select(func.count()).select_from(Referral))
    completed_referrals = db.scalar(
        select(func.count()).select_from(Referral).where(Referral.status == "closed")
    )
    referral_completion_rate = completed_referrals / total_referrals if total_referrals else 0.0

    site_breakdown = [
        {"mine_site": mine_site or "Unknown", "count": count}
        for mine_site, count in db.execute(
            select(Miner.mine_site, func.count())
            .select_from(Screening)
            .join(Miner, Miner.id == Screening.miner_id)
            .group_by(Miner.mine_site)
        ).all()
    ]

    tier_counts = dict(
        db.execute(
            select(Screening.tier, func.count())
            .select_from(Screening)
            .where(Screening.tier.is_not(None))
            .group_by(Screening.tier)
        ).all()
    )
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


@router.get("/referrals", response_model=list[ReferralOut])
def list_referrals(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    referrals = db.scalars(select(Referral).order_by(Referral.created_at.desc())).all()
    return [_referral_to_out(r) for r in referrals]


@router.patch("/referrals/{referral_id}", response_model=ReferralOut)
def update_referral_status(
    referral_id: int,
    payload: ReferralStatusUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    if payload.status not in _VALID_REFERRAL_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"status must be one of {sorted(_VALID_REFERRAL_STATUSES)}",
        )

    referral = db.get(Referral, referral_id)
    if referral is None:
        raise HTTPException(status_code=404, detail="Referral not found")

    referral.status = payload.status
    if payload.status == "attended":
        referral.attended_at = _utcnow()
    elif payload.status == "closed":
        referral.closed_at = _utcnow()
    db.commit()
    db.refresh(referral)
    return _referral_to_out(referral)


@router.post("/referrals/notify-email", response_model=ReferralNotifyOut)
def notify_referral_email(payload: ReferralNotifyRequest, db: Session = Depends(get_db)):
    """Unauthenticated (mobile-facing), 12 August — fires when the VHW taps
    'Generate Referral Card' on the app, giving the demo a live, watchable
    email moment tied to that exact tap rather than a silent send that
    already happened at referral-creation time inside POST /api/screen
    (services/referrals.create_referral_and_notify). This is a deliberate
    re-send of the same email, not the only time it fires — the automatic
    one still fires too, since a hospital shouldn't wait on a miner to tap
    a button to be pre-alerted."""
    miner = db.scalar(select(Miner).where(Miner.phone == payload.phone))
    if miner is None:
        raise HTTPException(status_code=404, detail="Worker not found")

    referral = db.scalar(
        select(Referral)
        .where(Referral.miner_id == miner.id)
        .order_by(Referral.created_at.desc(), Referral.id.desc())
        .limit(1)
    )
    if referral is None:
        raise HTTPException(status_code=404, detail="No referral found for this worker")

    screening = referral.screening
    factors = json.loads(screening.ai_contributing_factors) if screening.ai_contributing_factors else []
    facility_name = referral.facility.name if referral.facility else None
    sent = email_notifications.send_referral_alert_email(
        miner.id,
        miner.name,
        miner.phone,
        miner.mine_site,
        screening.tier,
        facility_name or "Kwekwe District Hospital",
        format_datetime(referral.deadline) or "",
        factors,
    )
    return ReferralNotifyOut(sent=sent, tier=screening.tier, facility_name=facility_name)


@router.get("/miners", response_model=list[MinerSummary])
def list_miners(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """Every registered miner, most recently active first — the dashboard's
    Miners directory (10 August). Distinct from GET /api/workers/{phone}
    (unauthenticated, single-miner lookup for the VHW re-screen flow): this
    is the full roster for a logged-in coordinator, so it's authenticated
    like /api/referrals and /api/dashboard/week."""
    latest_tier_subq = (
        select(Screening.tier)
        .where(Screening.miner_id == Miner.id)
        .order_by(Screening.created_at.desc(), Screening.id.desc())
        .limit(1)
        .correlate(Miner)
        .scalar_subquery()
    )
    stmt = (
        select(
            Miner.id,
            Miner.name,
            Miner.phone,
            Miner.mine_site,
            Miner.created_at,
            func.count(Screening.id),
            func.max(Screening.created_at),
            latest_tier_subq,
        )
        .select_from(Miner)
        .outerjoin(Screening, Screening.miner_id == Miner.id)
        .group_by(Miner.id)
        .order_by(func.coalesce(func.max(Screening.created_at), Miner.created_at).desc())
    )
    return [
        MinerSummary(
            id=row[0],
            name=row[1],
            phone=row[2],
            site=row[3],
            created_at=format_datetime(row[4]),
            screening_count=row[5],
            last_screened_at=format_datetime(row[6]),
            latest_tier=row[7],
        )
        for row in db.execute(stmt).all()
    ]


@router.get("/screenings", response_model=list[ScreeningLogItem])
def list_screenings(limit: int = 200, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """Every screening across every miner and channel (APP/USSD), most
    recent first — the dashboard's All Screenings activity log (10 August).
    `limit` (default 200) caps the response; the demo dataset is small
    enough this rarely matters, but a growing pilot deployment shouldn't
    return an unbounded list to a browser tab."""
    stmt = (
        select(Screening, Miner)
        .join(Miner, Miner.id == Screening.miner_id)
        .order_by(Screening.created_at.desc(), Screening.id.desc())
        .limit(limit)
    )
    return [
        ScreeningLogItem(
            id=s.id,
            miner_id=s.miner_id,
            miner_name=m.name,
            phone=m.phone,
            site=m.mine_site,
            tier=s.tier,
            channel=s.channel,
            advice_line=s.advice_line,
            created_at=format_datetime(s.created_at),
        )
        for s, m in db.execute(stmt).all()
    ]
