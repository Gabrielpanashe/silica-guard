from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import format_datetime, get_db
from db_models import Miner, Screening
from models import WorkerCreate, WorkerDetail, WorkerOut, WorkerScreeningSummary

router = APIRouter(prefix="/api", tags=["workers"])

# Unauthenticated on purpose, same as /api/screen and the old /api/miners —
# see routers/auth.py's get_current_user docstring: these are called by
# VHWs in the field and by USSD, neither of which holds a dashboard login.
# GET /api/workers/{phone} returns clinical history (tier, advice_line) by
# phone number alone, which is a materially bigger exposure than the
# write-only POST route it sits next to — flagged in the implementation
# plan as an explicit, not-silently-inherited decision, not an oversight.


@router.post("/workers", response_model=WorkerOut)
def create_worker(worker: WorkerCreate, db: Session = Depends(get_db)):
    miner = Miner(name=worker.name, phone=worker.phone, mine_site=worker.site)
    db.add(miner)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Phone number already registered")
    return WorkerOut(id=miner.id, name=worker.name, phone=worker.phone, site=worker.site)


@router.get("/workers/{phone}", response_model=WorkerDetail)
def get_worker_by_phone(phone: str, db: Session = Depends(get_db)):
    """Look up a worker by phone and return their full screening history —
    this is what turns a visit into a re-screen (SILICAGUARD.md Section 8)."""
    miner = db.scalar(select(Miner).where(Miner.phone == phone))
    if miner is None:
        raise HTTPException(status_code=404, detail="Worker not found")

    screenings = db.scalars(
        select(Screening)
        .where(Screening.miner_id == miner.id)
        .order_by(Screening.created_at.desc(), Screening.id.desc())
    ).all()

    # days_since_previous (22 August 2026): screenings are newest-first, so
    # each row's "previous" screening is the next one in this list, not the
    # one before it. None for the oldest/only screening — there's nothing
    # earlier to measure against. Pure Python datetime diff, no schema
    # change; feeds the dashboard's per-miner trend chart.
    screening_summaries = []
    for i, s in enumerate(screenings):
        days_since_previous = None
        older = screenings[i + 1] if i + 1 < len(screenings) else None
        if older is not None and s.created_at and older.created_at:
            days_since_previous = (s.created_at - older.created_at).days
        screening_summaries.append(
            WorkerScreeningSummary(
                id=s.id,
                tier=s.tier,
                created_at=format_datetime(s.created_at),
                advice_line=s.advice_line,
                days_since_previous=days_since_previous,
            )
        )

    return WorkerDetail(
        id=miner.id,
        name=miner.name,
        phone=miner.phone,
        site=miner.mine_site,
        screenings=screening_summaries,
    )
