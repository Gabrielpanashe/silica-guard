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
