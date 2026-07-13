from fastapi import APIRouter, Depends

from database import get_connection
from routers.auth import get_current_user

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard/week")
def dashboard_week(user: dict = Depends(get_current_user)):
    """Real counts from the database; ai_narrative is a placeholder until the
    weekly Claude/Gemini narrative service (SILICAGUARD.md Section 9.3-equivalent)
    is built. Requires a valid JWT — first real consumer of get_current_user."""
    conn = get_connection()
    try:
        total_screened = conn.execute("SELECT COUNT(*) FROM screenings").fetchone()[0]
        high_risk_count = conn.execute(
            "SELECT COUNT(*) FROM screenings WHERE risk_level = 'REFER_NOW'"
        ).fetchone()[0]

        total_referrals = conn.execute("SELECT COUNT(*) FROM referrals").fetchone()[0]
        completed_referrals = conn.execute(
            "SELECT COUNT(*) FROM referrals WHERE status = 'COMPLETE'"
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

        return {
            "total_screened": total_screened,
            "high_risk_count": high_risk_count,
            "referral_completion_rate": referral_completion_rate,
            "ai_narrative": "Weekly AI narrative not yet implemented.",
            "site_breakdown": site_breakdown,
        }
    finally:
        conn.close()
