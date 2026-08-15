from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from db_models import Facility
from models import FacilityOut

router = APIRouter(prefix="/api", tags=["facilities"])

# Unauthenticated, same precedent as GET /api/mines — powers the mobile
# Outreach Planner's "nearest hospital" preview (12 August 2026) when a VHW
# schedules a visit, so read-only access needs no dashboard login. The
# actual referral-time facility matching logic stays in
# services/facility_matching.py; this is just a read view of the same rows.


@router.get("/facilities", response_model=list[FacilityOut])
def list_facilities(db: Session = Depends(get_db)):
    facilities = db.scalars(select(Facility).order_by(Facility.level, Facility.name)).all()
    return [FacilityOut.model_validate(f, from_attributes=True) for f in facilities]
