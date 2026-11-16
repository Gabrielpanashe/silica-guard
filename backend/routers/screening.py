import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import format_datetime, get_db
from db_models import Miner, OutreachVisit, Screening, ScreeningAnswer
from models import DeteriorationResult, ScreeningCreate, ScreeningResult
from services import identity, notifications, v1_compat
from services.advice_engine import personalised_advice_line
from services.ai_risk_engine import assess_risk
from services.deterioration import compare_to_previous, escalate_tier_if_worsened
from services.explanation_shona import personalised_explanation_shona
from services.outreach import match_active_visit
from services.referrals import create_referral_and_notify
from services.safety_overrides import apply_safety_overrides
from services.tier_messages import TIER_MESSAGES

router = APIRouter(prefix="/api", tags=["screening"])

# Worker registration/lookup lives in routers/workers.py (POST /api/workers,
# GET /api/workers/{phone}) — this router is screening only, as of 5 August
# 2026 (previously also had POST /api/miners).


def _screen_via_v2(db: Session, payload: ScreeningCreate, miner: Miner) -> ScreeningResult:
    """Run the deterministic pipeline and answer in the v1 shape.

    **No delete-on-failure block, and it is not an omission.**
    `docs/IMPLEMENTATION_PLAN.md` §7 step 6: that block exists because the v1
    path persists answers, then makes an external call, then persists a tier
    — so a failed model call left a row with a NULL tier that nothing would
    ever complete. Between persisting answers and persisting results here
    there is **no external call**, so there is nothing for it to guard; and
    `client_session_uuid` handles the retry case it was compensating for,
    which is the 23 August incident where eighteen rows accumulated for one
    miner.

    A screening that cannot be completed keeps its answers and says so,
    rather than being deleted — rule 7 in the direction the master document
    means it.
    """
    import uuid

    from services import screening_v2
    from services.consent import ConsentMissing
    from services.identity import IdentityBundle
    from services.screening_v2 import IncompleteScreening, ScreeningError

    # **Refused, not fallen back from.** §7 step 3 forbids running the new
    # engine for the requests that look ready and the old one for the rest:
    # that is two instruments in the field at once. So the client must send a
    # participant code before the adapter is switched on, and a request
    # without one fails loudly.
    if not payload.participant_code:
        raise HTTPException(status_code=400, detail=(
            "participant_code is required: identity can only be resolved "
            "deterministically from the code on the worker's card. A name "
            "and a number queue a probable match rather than applying it "
            "(§8.2), which would create a new person for every screening."
        ))

    resolution = identity.resolve(
        db,
        IdentityBundle(
            participant_code=payload.participant_code,
            name=miner.name, phone=miner.phone, site_text=miner.mine_site,
        ),
        channel=payload.channel or "APP",
    )

    try:
        outcome = screening_v2.screen(db, screening_v2.ScreeningRequest(
            person_id=resolution.person_id,
            client_session_uuid=str(uuid.uuid4()),
            answers=v1_compat.to_v2_answers(payload.answers),
            channel=payload.channel or "APP",
            screened_by=payload.screened_by,
            site_text=miner.mine_site,
            outreach_visit_id=payload.outreach_visit_id,
            offline=bool(payload.offline_fallback_used),
        ))
    except ConsentMissing as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except IncompleteScreening as exc:
        raise HTTPException(status_code=400, detail={
            "message": str(exc), "session_id": exc.session_id,
            "missing": exc.missing, "answers_saved": True,
        })
    except ScreeningError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    referral = outcome.referrals[0] if outcome.referrals else None
    return ScreeningResult(
        tier=outcome.primary_tier,
        confidence=1.0,
        # Kept by name for the mobile ResultScreen and populated from the
        # content store, never from model output (§8.4). `readiness()` has
        # already established that approved text exists in both languages,
        # which is why these cannot be None here -- the v1 contract declares
        # them non-null and a worker is given the Shona one.
        explanation_english=v1_compat.result_text(db, outcome.primary_tier, "en"),
        explanation_shona=v1_compat.result_text(db, outcome.primary_tier, "sn"),
        contributing_factors=v1_compat.contributing_factors(outcome.results),
        advice_line=None,
        previous_screening_id=None,
        provisional=bool(payload.offline_fallback_used),
        deterioration=DeteriorationResult(
            # The v1 field names a v1 screening id, and a v2 session has
            # none: the comparison was against a `screening_sessions` row.
            # Left null rather than filled with an id from a different
            # table, which would resolve to the wrong screening.
            compared_to_screening_id=None,
            changed=any(
                r.deterioration and r.deterioration.changed for r in outcome.results
            ),
            summary=next(
                (r.deterioration.summary for r in outcome.results
                 if r.deterioration and r.deterioration.summary), None
            ),
        ),
        referral_code=referral.referral_code if referral else None,
        facility_name=referral.facility if referral else None,
        deadline=referral.deadline if referral else None,
    )


@router.post("/screen", response_model=ScreeningResult)
def screen_miner(
    payload: ScreeningCreate,
    db: Session = Depends(get_db),
    x_silicaguard_client: str | None = Header(default=None),
):
    """Screen a worker.

    **The adapter is here and dormant.** `docs/IMPLEMENTATION_PLAN.md` §7
    step 3 is explicit that this route switches to the deterministic engine
    at the same moment as every other caller, so that there is never a window
    in which two clients get two classifiers — a per-client rollout of a
    clinical classifier is two instruments in the field at once.

    `services/v1_compat.readiness()` holds the conditions and reports which
    are unmet; `GET /api/health` shows them from outside. Until all are met
    this route behaves exactly as it has, including the model call, so the
    demonstration is unaffected. When they are met it runs the §10.3 pipeline
    and maps the result back into this same response shape, so no client has
    to change on the day.
    """
    v1_compat.log_client(x_silicaguard_client, "POST /api/screen")

    miner = db.get(Miner, payload.miner_id)
    if miner is None:
        raise HTTPException(status_code=404, detail="Miner not found")

    ready = v1_compat.readiness(db)
    if ready.active:  # pragma: no cover - covered with an injected readiness
        return _screen_via_v2(db, payload, miner)

    # Outreach Planner (5 August 2026): link this screening to a visit for
    # live screened_count tracking + the post-visit report. Explicit id is
    # trusted if it exists (never fail the screening over a bad reference —
    # same philosophy as "a failed AI call doesn't corrupt the screening
    # record"); otherwise infer it for APP-channel screenings via
    # services/outreach.py's match_active_visit. USSD self-screens never
    # auto-link — not a coordinated site visit.
    outreach_visit_id = None
    if payload.outreach_visit_id is not None:
        visit = db.get(OutreachVisit, payload.outreach_visit_id)
        outreach_visit_id = visit.id if visit else None
    elif payload.channel == "APP" and miner.mine_site:
        candidate_visits = db.scalars(
            select(OutreachVisit).where(func.lower(OutreachVisit.site) == miner.mine_site.lower())
        ).all()
        # match_active_visit() is pure dict-subscript logic (services/outreach.py)
        # — pass plain dicts rather than changing that module to expect ORM
        # attribute access, same reasoning as facility_matching's dict interface.
        candidate_dicts = [
            {"id": v.id, "site": v.site, "scheduled_date": v.scheduled_date} for v in candidate_visits
        ]
        matched_visit = match_active_visit(
            miner.mine_site, datetime.now(timezone.utc), candidate_dicts
        )
        outreach_visit_id = matched_visit["id"] if matched_visit else None

    # Most recent prior screening for this worker, if any.
    previous_screening = db.scalar(
        select(Screening)
        .where(Screening.miner_id == payload.miner_id)
        .order_by(Screening.created_at.desc(), Screening.id.desc())
        .limit(1)
    )
    previous_screening_id = previous_screening.id if previous_screening else None
    provisional = 1 if payload.offline_fallback_used else 0

    # Answers from that previous screening, for Longitudinal Deterioration
    # Detection. Empty list (not an error) if this is the worker's first.
    previous_answer_dicts = (
        [
            {"question_code": a.question_code, "answer_score": a.answer_score}
            for a in db.scalars(
                select(ScreeningAnswer).where(ScreeningAnswer.screening_id == previous_screening_id)
            ).all()
        ]
        if previous_screening_id
        else []
    )

    screening = Screening(
        miner_id=payload.miner_id,
        previous_screening_id=previous_screening_id,
        screened_by=payload.screened_by,
        channel=payload.channel,
        fallback_used=1 if payload.offline_fallback_used else 0,
        provisional=provisional,
        outreach_visit_id=outreach_visit_id,
    )
    db.add(screening)
    db.flush()  # need screening.id for the answers below, before commit

    if outreach_visit_id is not None:
        visit = db.get(OutreachVisit, outreach_visit_id)
        visit.screened_count = (visit.screened_count or 0) + 1

    for answer in payload.answers:
        db.add(
            ScreeningAnswer(
                screening_id=screening.id,
                question_code=answer.question_code,
                question_text=answer.question_text,
                answer_value=answer.answer_value,
                answer_score=answer.answer_score,
            )
        )
    db.commit()

    try:
        result = assess_risk(payload.answers)
    except Exception:
        # 23 August 2026 — this used to leave the just-committed screening
        # + answers permanently orphaned (tier stays NULL forever, nothing
        # ever completes it), on the assumption that "a retry" would
        # somehow finish this same row. No such mechanism exists: a mobile
        # retry (services/offlineQueue.js, on every HomeScreen focus) calls
        # POST /api/screen fresh, creating a BRAND NEW screening every
        # single attempt. During a real Gemini flakiness window this
        # produced double-digit duplicate rows per miner (confirmed live:
        # one miner accumulated 18), each inflating screened_today/the
        # dashboard's Activity Log/Miners screening_count, and kept the
        # mobile app's offline-sync banner (and SyncPill, fixed the same
        # day) permanently "pending" since the client never received a
        # success response to clear it. A null-tier row has no audit value
        # anyway (no AI output ever landed) — cleanly undoing the persist
        # step here means a retry starts from a blank slate and produces
        # exactly one real row once the AI actually succeeds, matching
        # what "sync cleanly" is supposed to mean.
        db.query(ScreeningAnswer).filter(ScreeningAnswer.screening_id == screening.id).delete()
        if outreach_visit_id is not None:
            visit = db.get(OutreachVisit, outreach_visit_id)
            if visit is not None and visit.screened_count:
                visit.screened_count -= 1
        db.delete(screening)
        db.commit()
        raise HTTPException(status_code=502, detail="AI risk engine unavailable, please retry")

    # Longitudinal Deterioration Detection: escalate one tier on any
    # adverse trajectory, before the hard safety override gets the final
    # word — see services/deterioration.py and services/safety_overrides.py.
    deterioration = compare_to_previous(payload.answers, previous_screening_id, previous_answer_dicts)
    result["tier"] = escalate_tier_if_worsened(result["tier"], deterioration["changed"])
    result = apply_safety_overrides(payload.answers, result)

    advice_line = personalised_advice_line(payload.answers)
    explanation_shona = personalised_explanation_shona(payload.answers)

    screening.tier = result["tier"]
    screening.risk_confidence = result["confidence"]
    screening.ai_explanation_english = result["explanation_english"]
    screening.ai_explanation_shona = explanation_shona
    screening.ai_contributing_factors = json.dumps(result["contributing_factors"])
    screening.advice_line = advice_line
    db.commit()

    # Result notification, per tier (CLAUDE.md: "Everyone receives their
    # result... by SMS"). ORANGE/RED go through create_referral_and_notify
    # (referral + facility match + hospital pre-alert + miner SMS);
    # GREEN/YELLOW never get a referral but still get a result-only SMS —
    # see services/notifications.send_screening_result_sms.
    shona_message = TIER_MESSAGES[result["tier"]][0]
    referral = None
    if result["tier"] in ("ORANGE", "RED"):
        referral = create_referral_and_notify(
            db,
            screening_id=screening.id,
            miner_id=payload.miner_id,
            miner_name=miner.name,
            phone_number=miner.phone,
            mine_site=miner.mine_site,
            tier=result["tier"],
            shona_message=shona_message,
            contributing_factors=result["contributing_factors"],
        )
    else:
        notifications.send_screening_result_sms(payload.miner_id, miner.phone, result["tier"], shona_message)

    return ScreeningResult(
        tier=result["tier"],
        confidence=result["confidence"],
        explanation_english=result["explanation_english"],
        explanation_shona=explanation_shona,
        contributing_factors=result["contributing_factors"],
        advice_line=advice_line,
        previous_screening_id=previous_screening_id,
        provisional=bool(provisional),
        deterioration=DeteriorationResult(**deterioration),
        # Real referral_code (not the mobile app's client-side-fabricated
        # placeholder) — see ScreeningResult's field docstring in models.py.
        referral_code=referral.referral_code if referral else None,
        facility_name=referral.hospital if referral else None,
        deadline=format_datetime(referral.deadline) if referral else None,
    )
