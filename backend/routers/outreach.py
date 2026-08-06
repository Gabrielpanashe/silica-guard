import json

from fastapi import APIRouter, Depends

from database import get_connection
from models import OutreachVisitCreate, OutreachVisitOut, ReferralListItem
from routers.auth import get_current_user
from services.outreach import build_visit_report

router = APIRouter(prefix="/api", tags=["outreach"])

# Requires auth (get_current_user), unlike POST /api/workers or POST
# /api/screen — this is a coordinator/dashboard action, not a field action.
# A deliberate deviation from the unauthenticated shape drafted earlier in
# docs/API_CONTRACT.md's TARGET section for this route.


def _visit_row_to_out(conn, row) -> OutreachVisitOut:
    tier_distribution, referral_list = build_visit_report(conn, row)
    return OutreachVisitOut(
        id=row["id"],
        site=row["site"],
        scheduled_date=row["scheduled_date"],
        expected_headcount=row["expected_headcount"],
        screened_count=row["screened_count"],
        report_generated=bool(row["report_generated"]),
        tier_distribution=tier_distribution,
        referral_list=[ReferralListItem(**item) for item in referral_list] if referral_list is not None else None,
    )


@router.post("/outreach", response_model=OutreachVisitOut, status_code=201)
def create_outreach_visit(payload: OutreachVisitCreate, user: dict = Depends(get_current_user)):
    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO outreach_visits
               (site, scheduled_date, expected_headcount, screened_count, health_workers, report_generated)
               VALUES (?, ?, ?, 0, ?, 0)""",
            (payload.site, payload.scheduled_date, payload.expected_headcount, json.dumps(payload.health_workers)),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM outreach_visits WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return _visit_row_to_out(conn, row)
    finally:
        conn.close()


@router.get("/outreach", response_model=list[OutreachVisitOut])
def list_outreach_visits(user: dict = Depends(get_current_user)):
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM outreach_visits ORDER BY scheduled_date DESC"
        ).fetchall()
        return [_visit_row_to_out(conn, row) for row in rows]
    finally:
        conn.close()
