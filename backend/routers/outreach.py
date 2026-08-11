import json

from fastapi import APIRouter, Depends

from database import get_connection
from models import OutreachVisitCreate, OutreachVisitOut
from routers.auth import get_current_user
from services.outreach import visit_to_out

router = APIRouter(prefix="/api", tags=["outreach"])

# GET stays authenticated — the web dashboard's coordinator view. POST was
# authenticated too until 12 August: originally a deliberate deviation from
# docs/API_CONTRACT.md's TARGET section (a coordinator/dashboard action, not
# a field action), but the demo needed a VHW to schedule a visit straight
# from the mobile app, which has no login. Explicit scope call: demonstrate
# the functionality now, revisit the auth boundary later — not a decision
# to make silently, flagged in CLAUDE.md's sprint status.
#
# The row->response mapping (previously a private _visit_row_to_out here)
# moved to services/outreach.visit_to_out on 10 August, shared with
# GET /api/dashboard/today's new outreach_visits field.


@router.post("/outreach", response_model=OutreachVisitOut, status_code=201)
def create_outreach_visit(payload: OutreachVisitCreate):
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
        return visit_to_out(conn, row)
    finally:
        conn.close()


@router.get("/outreach", response_model=list[OutreachVisitOut])
def list_outreach_visits(user: dict = Depends(get_current_user)):
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM outreach_visits ORDER BY scheduled_date DESC"
        ).fetchall()
        return [visit_to_out(conn, row) for row in rows]
    finally:
        conn.close()
