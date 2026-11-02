"""Outreach visits, with what each one actually produced.

Master Reference v1.0 §13.3, and the last entry on `docs/
IMPLEMENTATION_PLAN.md` §5's list of the v2 surface the clients need.

**Why this exists when the v1 route works.** The v1 shape reports
`screened_count` and nothing about outcomes, which answers "did people turn
up" and not "what did we find" — and the second is the question a district
coordinator asks about a visit. Without it, the dashboard rebuild (item 1.15)
would have to call v1 for outreach and v2 for everything else, mixing a
single-tier shape with a per-condition one in the same view.

**The count comes from the sessions, not from the column.**
`outreach_visits.screened_count` is incremented by the screening route, which
makes it a running tally rather than a fact: a session reassigned to another
visit, or one that produced no result, leaves it wrong. This counts the
sessions actually linked through `screening_sessions.outreach_visit_id`, and
reports the stored column alongside as `recorded_screened_count` so a
divergence is **visible rather than hidden** by whichever number a caller
happens to read.

**Read-only.** Planning a visit and sending its announcements stay on the v1
routes until the adapter (item 1.11): they write to `outreach_visits`, which
v2 does not replace, and duplicating a write path is how two code paths start
disagreeing about the same row.

Behind `aggregate.read`, like the dashboard: a visit rollup names no
individual. §16.3's district coordinator holds exactly this.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db
from db_models import OutreachVisit, Referral, ScreeningResult, ScreeningSession
from models_v2 import ConditionTierCountOut, OutreachVisitOut2
from routers.auth import request_id, require
from services import audit
from services.authz import Principal
from services.rules_engine import TIER_ORDER

router = APIRouter(prefix="/api/v2", tags=["outreach"])


def _rollup(db: Session, visit: OutreachVisit) -> OutreachVisitOut2:
    sessions = list(
        db.scalars(
            select(ScreeningSession).where(
                ScreeningSession.outreach_visit_id == visit.id
            )
        ).all()
    )
    session_ids = [s.id for s in sessions] or [-1]

    counts: dict[tuple[str, str], int] = {}
    with_results: set[int] = set()
    result_ids: list[int] = []
    for row in db.scalars(
        select(ScreeningResult).where(ScreeningResult.session_id.in_(session_ids))
    ).all():
        key = (row.condition_code, row.tier)
        counts[key] = counts.get(key, 0) + 1
        with_results.add(row.session_id)
        result_ids.append(row.id)

    referrals = db.scalar(
        select(func.count(Referral.id)).where(
            Referral.result_id.in_(result_ids or [-1])
        )
    )

    return OutreachVisitOut2(
        visit_id=visit.id,
        site=visit.site,
        # A Date column, so a plain date -- `format_datetime` would append a
        # 00:00:00 that was never recorded, and v1's `GET /api/outreach`
        # already serves this field as "YYYY-MM-DD".
        scheduled_date=(
            visit.scheduled_date.isoformat() if visit.scheduled_date else None
        ),
        expected_headcount=visit.expected_headcount,
        health_workers=visit.health_workers,
        sessions=len(sessions),
        people=len({s.person_id for s in sessions}),
        incomplete_sessions=len([s for s in sessions if s.id not in with_results]),
        by_condition_and_tier=[
            ConditionTierCountOut(condition=condition, tier=tier, count=count)
            for (condition, tier), count in sorted(
                counts.items(), key=lambda kv: (kv[0][0], TIER_ORDER.index(kv[0][1]))
            )
        ],
        referrals=int(referrals or 0),
        recorded_screened_count=visit.screened_count,
        announcements_sent={
            "three_day": bool(visit.sms_3day_sent),
            "one_day": bool(visit.sms_1day_sent),
        },
        report_generated=bool(visit.report_generated),
    )


@router.get("/outreach", response_model=list[OutreachVisitOut2])
def list_visits(
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("aggregate.read")),
    rid: str = Depends(request_id),
):
    """Planned visits, soonest-scheduled last, each with its rollup."""
    visits = list(
        db.scalars(
            select(OutreachVisit)
            .order_by(OutreachVisit.scheduled_date.desc(), OutreachVisit.id.desc())
            .limit(limit)
        ).all()
    )
    audit.record(
        db, principal, "aggregate.read", object_type="outreach",
        request_id=rid, details={"visits": len(visits)},
    )
    db.commit()
    return [_rollup(db, v) for v in visits]


@router.get("/outreach/{visit_id}", response_model=OutreachVisitOut2)
def get_visit(
    visit_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("aggregate.read")),
    rid: str = Depends(request_id),
):
    visit = db.get(OutreachVisit, visit_id)
    if visit is None:
        raise HTTPException(status_code=404, detail="No such outreach visit")
    audit.record(
        db, principal, "aggregate.read", object_type="outreach",
        object_id=visit_id, request_id=rid,
    )
    db.commit()
    return _rollup(db, visit)
