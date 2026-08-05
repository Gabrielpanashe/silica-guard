from fastapi import APIRouter, Depends, HTTPException

from database import get_connection
from models import ReferralOut, ReferralStatusUpdate
from routers.auth import get_current_user
from services.population_intelligence import generate_weekly_narrative

router = APIRouter(prefix="/api", tags=["dashboard"])

_VALID_REFERRAL_STATUSES = {"open", "pre_alerted", "reminded", "attended", "closed", "escalated"}
_TIERS = ("GREEN", "YELLOW", "ORANGE", "RED")


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
