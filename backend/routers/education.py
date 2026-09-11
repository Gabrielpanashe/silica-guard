"""Teach Mode's SMS-channel demonstration — see
services/education_messages.py's module docstring for the full context on
why this exists and what it deliberately is not (the master doc's in-app
illustrated cards)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db
from db_models import Miner
from models import EducationBroadcastOut, EducationBroadcastRequest
from routers.auth import get_current_user
from services import notifications
from services.education_messages import TOPICS

router = APIRouter(prefix="/api", tags=["education"])


@router.post("/education/broadcast", response_model=EducationBroadcastOut)
def broadcast_education_tip(
    payload: EducationBroadcastRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Authenticated like the rest of the coordinator/dashboard-facing
    outreach routes — a broadcast action, not a field action. Sends the
    chosen topic's Shona SMS to every miner registered at `site`
    (case-insensitive, same matching rule as the Outreach Planner's own
    announcement send)."""
    topic = TOPICS.get(payload.topic)
    if topic is None:
        raise HTTPException(
            status_code=422, detail=f"topic must be one of {sorted(TOPICS)}"
        )

    workers = db.scalars(
        select(Miner).where(func.lower(Miner.mine_site) == payload.site.strip().lower())
    ).all()

    sent_count = sum(
        1
        for worker in workers
        if notifications.send_education_tip(worker.id, worker.phone, payload.topic, topic.message_shona)
    )

    return EducationBroadcastOut(
        site=payload.site,
        topic=payload.topic,
        message_preview=topic.message_shona,
        sent_count=sent_count,
        recipient_count=len(workers),
    )
