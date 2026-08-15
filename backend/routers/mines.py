from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from db_models import Mine
from models import MineCreate, MineOut

router = APIRouter(prefix="/api", tags=["mines"])

# Unauthenticated, same deliberate precedent as POST /api/workers and
# POST /api/screen — a VHW in the field selecting (or adding) the mine
# they're screening at has no dashboard login. Powers the mobile app's
# outreach-site dropdown (7 August 2026), replacing the hardcoded
# "Globe & Phoenix Mine" default that was baked directly into the UI.


@router.get("/mines", response_model=list[MineOut])
def list_mines(db: Session = Depends(get_db)):
    mines = db.scalars(select(Mine).order_by(Mine.district, Mine.name)).all()
    return [MineOut.model_validate(m, from_attributes=True) for m in mines]


@router.post("/mines", response_model=MineOut, status_code=201)
def create_mine(payload: MineCreate, db: Session = Depends(get_db)):
    """For the case where a VHW's site genuinely isn't in the seeded list —
    lets the dropdown grow rather than forcing a hardcoded set. Deliberately
    not a foreign key target for miners.mine_site/outreach_visits.site (both
    stay free TEXT) — a full migration tying those to mines.id is a bigger,
    riskier change than the freeze deadline allows; this table is a curated
    suggestion list for the UI, not yet a hard constraint."""
    mine = Mine(name=payload.name, district=payload.district, province=payload.province)
    db.add(mine)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Mine already registered")
    db.refresh(mine)
    return MineOut.model_validate(mine, from_attributes=True)
