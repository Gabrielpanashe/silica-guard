from typing import List, Optional

from pydantic import BaseModel, Field


class WorkerCreate(BaseModel):
    name: str
    phone: str
    site: Optional[str] = None


class WorkerOut(BaseModel):
    id: int
    name: str
    phone: str
    site: Optional[str] = None


class WorkerScreeningSummary(BaseModel):
    id: int
    tier: Optional[str] = None
    created_at: str
    advice_line: Optional[str] = None
    # 22 August 2026 — days between this screening and the miner's previous
    # one (None for a miner's first screening, or the oldest in the list).
    # Powers the dashboard's per-miner trend chart and "how long since last
    # screened" framing; computed in Python from created_at, no schema
    # change (routers/workers.py::get_worker_by_phone).
    days_since_previous: Optional[int] = None


class WorkerDetail(BaseModel):
    id: int
    name: str
    phone: str
    site: Optional[str] = None
    screenings: List[WorkerScreeningSummary]


class ScreeningAnswerIn(BaseModel):
    question_code: str
    question_text: Optional[str] = None
    answer_value: str
    answer_score: int


class ScreeningCreate(BaseModel):
    miner_id: int
    answers: List[ScreeningAnswerIn] = Field(..., min_length=1)
    channel: str = "APP"
    screened_by: Optional[str] = None
    offline_fallback_used: bool = False
    outreach_visit_id: Optional[int] = None


class DeteriorationResult(BaseModel):
    compared_to_screening_id: Optional[int] = None
    changed: bool
    summary: str


class ScreeningResult(BaseModel):
    tier: str
    confidence: float
    explanation_english: str
    explanation_shona: str
    contributing_factors: List[str]
    advice_line: Optional[str] = None
    previous_screening_id: Optional[int] = None
    provisional: bool = False
    deterioration: Optional[DeteriorationResult] = None
    # New 16 August 2026 — real, previously-missing bug: ORANGE/RED referrals
    # have always generated a real referral_code (14 August, master doc
    # v6.0 Section 1.1), but this response never carried it, so the only
    # unauthenticated caller with no login (the VHW mobile app) had no way
    # to get the real code at screening time and was fabricating its own
    # client-side instead — a code that could never actually be looked up
    # at a hospital. None for GREEN/YELLOW, where no referral is created.
    referral_code: Optional[str] = None
    facility_name: Optional[str] = None
    deadline: Optional[str] = None


class ReferralOut(BaseModel):
    id: int
    miner_name: str
    mine_site: Optional[str] = None
    tier: str
    status: str
    deadline: Optional[str] = None
    pre_alert_sent: bool
    facility_id: Optional[int] = None
    facility_name: Optional[str] = None
    # New 14 August 2026, master doc v6.0 Section 1.1 — surfaced here too
    # (not just the SMS/lookup-page path) so the dashboard's coordinator
    # view can see/copy the same code a hospital would look up.
    referral_code: Optional[str] = None
    reminder_stage: int = 0
    attended_at: Optional[str] = None
    closed_at: Optional[str] = None
    created_at: str


class ReferralStatusUpdate(BaseModel):
    status: str


class ReferralNotifyRequest(BaseModel):
    """POST /api/referrals/notify-email (12 August) — fired when the VHW
    taps 'Generate Referral Card' on the mobile app, so the email pre-alert
    has a visible, on-demand trigger tied to that exact moment in the demo,
    not just a silent send that already happened at screening time."""
    phone: str


class ReferralNotifyOut(BaseModel):
    sent: bool
    tier: str
    facility_name: Optional[str] = None


class ReferralLookupOut(BaseModel):
    """GET /api/referrals/lookup/{code} (14 August 2026, master doc v6.0
    Section 1.1) — the referral-code pivot. Unauthenticated: hospital staff
    have no login, same precedent as POST /api/screen and
    GET /api/workers/{phone}."""
    referral_code: str
    tier: str
    status: str
    deadline: Optional[str] = None
    miner_name: str
    mine_site: Optional[str] = None
    facility_name: Optional[str] = None
    advice_line: Optional[str] = None
    contributing_factors: List[str] = []
    attended_at: Optional[str] = None


class ReferralConfirmAttendanceOut(BaseModel):
    referral_code: str
    status: str
    attended_at: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    role: str


class OutreachVisitCreate(BaseModel):
    site: str
    scheduled_date: str  # "YYYY-MM-DD"
    expected_headcount: int
    health_workers: List[str] = []


class ReferralListItem(BaseModel):
    miner_name: str
    tier: str
    status: str


class OutreachVisitOut(BaseModel):
    id: int
    site: str
    scheduled_date: str
    expected_headcount: int
    screened_count: int
    report_generated: bool
    tier_distribution: Optional[dict] = None
    referral_list: Optional[List[ReferralListItem]] = None


class MineCreate(BaseModel):
    name: str
    district: Optional[str] = None
    province: str = "Midlands"


class MineOut(BaseModel):
    id: int
    name: str
    district: Optional[str] = None
    province: str


class FacilityOut(BaseModel):
    """GET /api/facilities (12 August) — powers the mobile Outreach
    Planner's "nearest hospital" preview when scheduling a visit. Same
    rows services/facility_matching.py already uses internally for
    referral routing, just exposed read-only now."""
    id: int
    name: str
    level: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class TodaysLogItem(BaseModel):
    screening_id: int
    miner_name: str
    phone: str
    mine_site: Optional[str] = None
    tier: Optional[str] = None
    created_at: str


class ReferNowItem(BaseModel):
    referral_id: int
    miner_name: str
    phone: str
    mine_site: Optional[str] = None
    tier: str
    status: str
    deadline: Optional[str] = None
    # New 21 August 2026 — same motivation as ScreeningResult's referral_code
    # (see models.py above): the mobile app has no login, so PATCH
    # /api/referrals/{id} (auth-gated) is unreachable from it. Surfacing the
    # code here lets it instead confirm attendance via the already-
    # unauthenticated POST /api/referrals/lookup/{code}/confirm-attendance.
    referral_code: Optional[str] = None
    facility_name: Optional[str] = None


class WatchItem(BaseModel):
    screening_id: int
    miner_name: str
    phone: str
    mine_site: Optional[str] = None
    tier: str
    created_at: str


class ReferNowSection(BaseModel):
    count: int
    items: List[ReferNowItem]


class WatchSection(BaseModel):
    count: int
    items: List[WatchItem]


class DashboardTodayOut(BaseModel):
    screened_today: int
    todays_log: List[TodaysLogItem]
    refer_now: ReferNowSection
    watch: WatchSection
    # 10 August: powers the mobile app's Outreach Stats screen, previously
    # a "coming soon" placeholder because GET /api/outreach requires auth
    # and the VHW mobile flow has no login. Same OutreachVisitOut shape as
    # that authenticated route — see services/outreach.visit_to_out, the
    # single shared mapping both endpoints use.
    outreach_visits: List[OutreachVisitOut] = []


class MinerSummary(BaseModel):
    """One row per registered miner, for the dashboard's Miners directory —
    10 August. Distinct from WorkerDetail (routers/workers.py): that's a
    single-miner deep lookup by phone for the unauthenticated VHW re-screen
    flow; this is the full roster for a logged-in coordinator."""
    id: int
    name: str
    phone: str
    site: Optional[str] = None
    latest_tier: Optional[str] = None
    screening_count: int
    last_screened_at: Optional[str] = None
    created_at: str


class ScreeningLogItem(BaseModel):
    """One row per screening, across every miner and channel — the
    dashboard's All Screenings activity log, 10 August."""
    id: int
    miner_id: int
    miner_name: str
    phone: str
    site: Optional[str] = None
    tier: Optional[str] = None
    channel: str
    advice_line: Optional[str] = None
    created_at: str


class OutreachSendNowOut(BaseModel):
    """22 August 2026 — POST /api/outreach/{id}/send-now. On-demand escape
    hatch for the outreach 3-day/1-day announcement, which otherwise only
    fires from the APScheduler job (up to a 10-minute wait, and only once
    the visit is genuinely inside its window) — added so this can actually
    be demonstrated live rather than waited out."""
    visit_id: int
    site: str
    stage: str
    sent_count: int


class EducationBroadcastRequest(BaseModel):
    """22 August 2026 — Teach Mode's SMS-channel demonstration (master doc
    Section 1's six illustrated in-app cards remain unbuilt; this is a
    pragmatic stand-in, documented as such in docs/DEMO_GUIDE.md). One of
    services/education_messages.TOPICS."""
    site: str
    topic: str


class EducationBroadcastOut(BaseModel):
    site: str
    topic: str
    message_preview: str
    sent_count: int
    recipient_count: int
