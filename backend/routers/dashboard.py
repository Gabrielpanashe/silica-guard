from fastapi import APIRouter, Depends, HTTPException

from database import get_connection
from models import ReferralOut, ReferralStatusUpdate
from routers.auth import get_current_user

router = APIRouter(prefix="/api", tags=["dashboard"])

_VALID_REFERRAL_STATUSES = {"PENDING", "XRAY_UPLOADED", "COMPLETE"}


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


@router.get("/referrals", response_model=list[ReferralOut])
def list_referrals(user: dict = Depends(get_current_user)):
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT r.id, m.name AS miner_name, m.mine_site, s.risk_level,
                      r.status, r.created_at
               FROM referrals r
               JOIN miners m ON m.id = r.miner_id
               JOIN screenings s ON s.id = r.screening_id
               ORDER BY r.created_at DESC"""
        ).fetchall()
        return [dict(row) for row in rows]
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

        completed_at_clause = (
            ", completed_at = CURRENT_TIMESTAMP" if payload.status == "COMPLETE" else ""
        )
        conn.execute(
            f"UPDATE referrals SET status = ?{completed_at_clause} WHERE id = ?",
            (payload.status, referral_id),
        )
        conn.commit()

        row = conn.execute(
            """SELECT r.id, m.name AS miner_name, m.mine_site, s.risk_level,
                      r.status, r.created_at
               FROM referrals r
               JOIN miners m ON m.id = r.miner_id
               JOIN screenings s ON s.id = r.screening_id
               WHERE r.id = ?""",
            (referral_id,),
        ).fetchone()
        return dict(row)
    finally:
        conn.close()
