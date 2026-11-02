"""A worker's history, and the day, with per-condition results.

Master Reference v1.0 §8.1 and §10.5. The shape change that runs through all
of v2: **a session produces a list of results, not a tier.**

The v1 dashboard counts tiers, which works only while there is one condition.
`high_risk_count` becomes ambiguous the day tuberculosis is added — high risk
of *what*? — so v2 reports the pair, condition and tier. That is the whole
point of the result-rows decision, finally visible to a reader.

**Both routes need a token and a capability**, because both return clinical
detail about identifiable people (§16.3). That is a change from v1, where
`GET /api/dashboard/today` is unauthenticated so the mobile Home screen can
show its numbers. The v2 equivalent cannot be: it names conditions per person
once a second condition exists, and an open endpoint returning that is a
disclosure. The mobile application needs a device credential — item 1.13 —
and `routers/persons.py` records the same gap for the identity lookup.

**Incomplete sessions are counted rather than hidden.** A session that
produced no result because an applicable question was unanswered (§13.1) is
absent from every tier count, so without a separate number a channel that
keeps producing them looks like a channel nobody is using.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import format_datetime, get_db
from db_models import Person, Referral, ScreeningResult, ScreeningSession, Site
from models_v2 import (
    ConditionResultOut,
    ConditionTierCountOut,
    DashboardV2Out,
    PersonHistoryOut,
    SessionSummaryOut,
)
from routers.auth import request_id, require
from services import audit, authz, consent, identity
from services.authz import Principal
from services.rules_engine import TIER_ORDER

router = APIRouter(prefix="/api/v2", tags=["dashboard"])

PERIODS = {"today": 1, "week": 7, "month": 30}


def _site_label(db: Session, session: ScreeningSession) -> str | None:
    if session.site_id:
        site = db.get(Site, session.site_id)
        if site is not None:
            return site.name
    return session.site_text


def _session_summary(db: Session, session: ScreeningSession) -> SessionSummaryOut:
    rows = list(
        db.scalars(
            select(ScreeningResult)
            .where(ScreeningResult.session_id == session.id)
            .order_by(ScreeningResult.condition_code)
        ).all()
    )
    tiers = [r.tier for r in rows]
    primary = max(tiers, key=lambda t: TIER_ORDER.index(t)) if tiers else None

    referrals = db.scalars(
        select(Referral.referral_code).where(
            Referral.result_id.in_([r.id for r in rows] or [-1])
        )
    ).all()

    return SessionSummaryOut(
        session_id=session.id,
        channel=session.channel,
        screened_by=session.screened_by,
        site=_site_label(db, session),
        instrument_code=session.instrument_code,
        instrument_version=session.instrument_version,
        started_at=format_datetime(session.started_at),
        completed_at=format_datetime(session.completed_at),
        previous_session_id=session.previous_session_id,
        primary_tier=primary,
        results=[
            ConditionResultOut(
                condition=r.condition_code,
                tier=r.tier,
                score=r.score or 0,
                method=r.method,
                instrument_code=r.instrument_code or "",
                instrument_version=r.instrument_version or 0,
                scored_tier=r.scored_tier or r.tier,
                override_fired=bool(r.override_fired),
                override_rule_codes=[
                    c for c in (r.override_rule_codes or "").split(",") if c
                ],
                deterioration_changed=bool(r.deterioration_changed),
            )
            for r in rows
        ],
        referral_codes=[c for c in referrals if c],
    )


@router.get("/persons/{participant_code}/sessions", response_model=PersonHistoryOut)
def person_history(
    participant_code: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("screening.read")),
    rid: str = Depends(request_id),
):
    """A worker's encounters, newest first, with per-condition results.

    Follows a merge, so a card printed before one still finds the history the
    merge joined — which is the reason to perform a merge at all.

    Audited, because this is a clinical read of an identified person and
    §16.3 requires every one of those to write a row.
    """
    person = identity.find_by_participant_code(db, participant_code)
    if person is None:
        raise HTTPException(status_code=404, detail="No person with that participant code")

    sessions = list(
        db.scalars(
            select(ScreeningSession)
            .where(ScreeningSession.person_id == person.id)
            .order_by(ScreeningSession.created_at.desc(), ScreeningSession.id.desc())
        ).all()
    )

    audit.record(
        db, principal, "screening.read", object_type="person",
        object_id=person.id, person_id=person.id, request_id=rid,
        details={"sessions": len(sessions)},
    )
    db.commit()

    return PersonHistoryOut(
        person_id=person.id,
        participant_code=person.participant_code,
        longitudinal_consent=consent.may_keep_longitudinal_record(db, person.id),
        session_count=len(sessions),
        sessions=[_session_summary(db, s) for s in sessions],
    )


@router.get("/dashboard/{period}", response_model=DashboardV2Out)
def dashboard(
    period: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("aggregate.read")),
    rid: str = Depends(request_id),
    limit: int = Query(200, ge=1, le=2000),
):
    """Counts per condition and tier for `today`, `week` or `month`.

    Reports **no identified record** — only counts — so it sits behind
    `aggregate.read`, which is the capability a district coordinator, a
    national stakeholder and a programme sponsor all hold while none of them
    may read a person (§16.3).
    """
    if period not in PERIODS:
        raise HTTPException(
            status_code=400, detail=f"period must be one of {', '.join(PERIODS)}"
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    since = now - timedelta(days=PERIODS[period])

    # §16.3: a programme sponsor is refused "anything outside their cohort",
    # which is stronger than every other scope line in the table -- a district
    # coordinator is refused *identified* records outside their district and
    # may still see national aggregates, while a sponsor is refused the
    # aggregate too. §14.4 is why: an employer or insurer paying for screening
    # must not be handed a picture of anybody else's workforce with their own.
    # Narrows to nothing for a sponsor with no programme, never to everything.
    statement = authz.for_aggregate_sessions(
        select(ScreeningSession).where(ScreeningSession.created_at >= since),
        ScreeningSession.programme_id,
        principal,
    )
    sessions = list(
        db.scalars(
            statement.order_by(ScreeningSession.created_at.desc()).limit(limit)
        ).all()
    )
    session_ids = [s.id for s in sessions] or [-1]

    counts: dict[tuple[str, str], int] = {}
    worsened = 0
    with_results: set[int] = set()
    for row in db.scalars(
        select(ScreeningResult).where(ScreeningResult.session_id.in_(session_ids))
    ).all():
        counts[(row.condition_code, row.tier)] = counts.get((row.condition_code, row.tier), 0) + 1
        with_results.add(row.session_id)
        if row.deterioration_changed:
            worsened += 1

    # Scoped by the referral's OWN timestamps, not by the sessions in the
    # window. A referral attended today was usually raised last week, so
    # counting attendance by the session's date reports the wrong day -- and
    # counting every referral in the database, which is what this did until
    # 2 November 2026, reported an all-time figure under a `period: "today"`
    # label.
    v2 = Referral.result_id.isnot(None)
    # A sponsor's referral numbers must come from their cohort's sessions
    # only, for the same reason as the counts above -- keyed through the
    # sessions in scope, because `referrals` carries no programme of its own.
    in_scope = (
        [Referral.result_id.in_(
            select(ScreeningResult.id).where(ScreeningResult.session_id.in_(session_ids))
        )]
        if authz.scoped_to_a_cohort(principal) else []
    )

    def _count(*conditions) -> int:
        return int(db.scalar(
            select(func.count(Referral.id)).where(v2, *in_scope, *conditions)
        ) or 0)

    referrals_raised = _count(Referral.created_at >= since)
    referrals_attended = _count(Referral.attended_at >= since)
    referrals_closed = _count(Referral.outcome_recorded_at >= since)
    # The exception, and it is not an oversight: an open referral from three
    # weeks ago still needs chasing, so the backlog is the standing total.
    referrals_open_now = _count(
        Referral.status.in_(("open", "pre_alerted", "reminded"))
    )

    audit.record(
        db, principal, "aggregate.read", object_type="dashboard",
        object_id=period, request_id=rid,
        details={"sessions": len(sessions)},
    )
    db.commit()

    return DashboardV2Out(
        period=period,
        from_date=format_datetime(since),
        to_date=format_datetime(now),
        sessions=len(sessions),
        people=len({s.person_id for s in sessions}),
        incomplete_sessions=len([s for s in sessions if s.id not in with_results]),
        by_condition_and_tier=[
            ConditionTierCountOut(condition=condition, tier=tier, count=count)
            for (condition, tier), count in sorted(
                counts.items(), key=lambda kv: (kv[0][0], TIER_ORDER.index(kv[0][1]))
            )
        ],
        referrals_raised=referrals_raised,
        referrals_attended=referrals_attended,
        referrals_closed_with_outcome=referrals_closed,
        referrals_open_now=referrals_open_now,
        worsened=worsened,
    )
