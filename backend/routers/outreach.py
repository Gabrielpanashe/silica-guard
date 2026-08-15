import json
from datetime import date as date_type

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from db_models import OutreachVisit
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
def create_outreach_visit(payload: OutreachVisitCreate, db: Session = Depends(get_db)):
    visit = OutreachVisit(
        site=payload.site,
        scheduled_date=date_type.fromisoformat(payload.scheduled_date),
        expected_headcount=payload.expected_headcount,
        screened_count=0,
        # health_workers was stored as a JSON-encoded TEXT column by the
        # legacy raw-SQL insert; preserved as-is rather than adding a real
        # list column, since nothing reads it back structured yet.
        health_workers=json.dumps(payload.health_workers),
        report_generated=0,
    )
    db.add(visit)
    db.commit()
    db.refresh(visit)
    return visit_to_out(db, visit)


@router.get("/outreach", response_model=list[OutreachVisitOut])
def list_outreach_visits(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    visits = db.scalars(select(OutreachVisit).order_by(OutreachVisit.scheduled_date.desc())).all()
    return [visit_to_out(db, v) for v in visits]
