from database import get_connection
from fastapi import APIRouter
from models import FacilityOut

router = APIRouter(prefix="/api", tags=["facilities"])

# Unauthenticated, same precedent as GET /api/mines — powers the mobile
# Outreach Planner's "nearest hospital" preview (12 August 2026) when a VHW
# schedules a visit, so read-only access needs no dashboard login. The
# actual referral-time facility matching logic stays in
# services/facility_matching.py; this is just a read view of the same rows.


@router.get("/facilities", response_model=list[FacilityOut])
def list_facilities():
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM facilities ORDER BY level, name").fetchall()
        return [FacilityOut(**dict(row)) for row in rows]
    finally:
        conn.close()
