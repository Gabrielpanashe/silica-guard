"""The v2 screening route, and closing a referral with its outcome.

Master Reference v1.0 §10.3 and §10.4.

**This route never calls a language model.** `docs/IMPLEMENTATION_PLAN.md` §7
step 2: "the v2 route is deterministic from its first commit". The tier of
record is the deterministic cascade on every channel, online and offline
(§9.1), and there is no configuration, flag or failure path here that puts a
model between a set of answers and a tier.

**Unauthenticated**, on the same deliberate precedent as `POST /api/screen`:
the village health worker's application never logs in, and a screening must
work in a gold-panning area with no dashboard session. The hospital-facing
referral close is unauthenticated for the same reason the v1 lookup page is —
facility staff have no account — and carries the same known weakness, which
§15.4 already records: no rate limiting and no lockout on a code-keyed public
endpoint. Item 1.13.

**A failure here never loses a screening.** The answers are committed before
scoring, so every error below returns with the session already saved. The
status codes say which kind of failure it was, because the mobile offline
queue has to tell "retry this" from "this will never work":

  `400` the request is wrong, or the screening is incomplete. Retrying the
        same body will fail the same way; the answers are saved either way
        and the session id is in the response.
  `403` consent for screening has not been recorded. Not retryable without
        going back to the worker.
  `503` the server is misconfigured — identity keys absent. Retryable.
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import format_datetime, get_db
from db_models import Referral
from models_v2 import (
    ConditionResultOut,
    MessagePlanOut,
    ReferralCloseIn,
    ReferralOut2,
    ReferralPlanOut,
    ScreeningOutcomeOut,
    ScreeningSubmitIn,
)
from services import audit, crypto, referrals_v2, screening_v2
from services.consent import ConsentMissing
from services.identity import IdentityError
from services.referrals_v2 import ReferralError
from services.rules_engine import InstrumentError
from services.screening_v2 import IncompleteScreening, ScreeningError, ScreeningRequest

router = APIRouter(prefix="/api/v2", tags=["screening"])


def _outcome_out(outcome: screening_v2.Outcome) -> ScreeningOutcomeOut:
    return ScreeningOutcomeOut(
        session_id=outcome.session_id,
        person_id=outcome.person_id,
        participant_code=outcome.participant_code,
        primary_tier=outcome.primary_tier,
        results=[
            ConditionResultOut(
                condition=r.condition,
                tier=r.tier,
                score=r.score,
                method=r.method,
                instrument_code=r.instrument_code,
                instrument_version=r.instrument_version,
                scored_tier=r.scored_tier,
                tier_rule_label=r.tier_rule_label,
                override_fired=r.override_fired,
                override_rule_codes=list(r.override_rule_codes),
                deterioration_compared=bool(r.deterioration and r.deterioration.compared),
                deterioration_changed=bool(r.deterioration and r.deterioration.changed),
                deterioration_summary=r.deterioration.summary if r.deterioration else None,
            )
            for r in outcome.results
        ],
        instrument_code=outcome.instrument_code,
        instrument_version=outcome.instrument_version,
        replayed=outcome.replayed,
        longitudinal_linked=outcome.longitudinal_linked,
        referrals=[
            ReferralPlanOut(
                referral_code=p.referral_code,
                condition=p.condition,
                tier=p.tier,
                facility=p.facility,
                deadline=p.deadline,
            )
            for p in outcome.referrals
        ],
        messages=[
            MessagePlanOut(
                code=m.code,
                available=m.available,
                language=m.language,
                text=m.text,
                reason=m.reason,
            )
            for m in outcome.messages
        ],
        not_sent_reason=outcome.not_sent_reason,
        started_at=outcome.started_at,
        completed_at=outcome.completed_at,
    )


@router.post("/screenings", response_model=ScreeningOutcomeOut)
def submit_screening(payload: ScreeningSubmitIn, db: Session = Depends(get_db)):
    """Run the §10.3 pipeline and return one result per condition.

    A repeat submission with the same `client_session_uuid` returns the first
    session's result with `replayed: true` and writes nothing — the structural
    fix for the 23 August duplicate-screening incident, where a model-flakiness
    window produced eighteen rows for one miner because every retry created a
    fresh screening.
    """
    if not crypto.keys_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "Identity keys are not configured on this server. Nothing was "
                "saved; retry once the server is configured."
            ),
        )

    started = None
    if payload.started_at:
        from datetime import datetime

        try:
            started = datetime.fromisoformat(payload.started_at.replace("Z", "+00:00"))
            if started.tzinfo is not None:
                from datetime import timezone

                started = started.astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="started_at must be an ISO-8601 timestamp"
            )

    request = ScreeningRequest(
        person_id=payload.person_id,
        client_session_uuid=payload.client_session_uuid,
        answers=payload.answers,
        channel=payload.channel,
        screened_by=payload.screened_by,
        site_id=payload.site_id,
        site_text=payload.site_text,
        programme_id=payload.programme_id,
        outreach_visit_id=payload.outreach_visit_id,
        instrument_code=payload.instrument_code,
        started_at=started,
        offline=payload.offline,
    )

    try:
        outcome = screening_v2.screen(db, request)
    except ConsentMissing as exc:
        # Not retryable without going back to the worker, which is why it is
        # a 403 and not a 400: the request was well formed and the answer is
        # that this person has not agreed to be screened.
        raise HTTPException(status_code=403, detail=str(exc))
    except IncompleteScreening as exc:
        # The answers ARE saved. The response says so and names the session,
        # because the caller must complete that session rather than resubmit
        # under the same idempotency key.
        raise HTTPException(
            status_code=400,
            detail={
                "message": str(exc),
                "session_id": exc.session_id,
                "missing": exc.missing,
                "answers_saved": True,
            },
        )
    except (IdentityError, ScreeningError, InstrumentError, ReferralError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return _outcome_out(outcome)


def _referral_out(referral: Referral) -> ReferralOut2:
    reasons = None
    if referral.contributing_reasons:
        try:
            reasons = json.loads(referral.contributing_reasons)
        except ValueError:
            reasons = None
    return ReferralOut2(
        referral_code=referral.referral_code,
        condition_code=referral.condition_code,
        person_id=referral.person_id,
        result_id=referral.result_id,
        facility=referral.hospital,
        deadline=format_datetime(referral.deadline),
        status=referral.status,
        attended_at=format_datetime(referral.attended_at),
        outcome=referral.outcome,
        outcome_notes=referral.outcome_notes,
        outcome_recorded_at=format_datetime(referral.outcome_recorded_at),
        outcome_recorded_by=referral.outcome_recorded_by,
        contributing_reasons=reasons,
    )


@router.get("/referrals/{referral_code}", response_model=ReferralOut2)
def get_referral(referral_code: str, db: Session = Depends(get_db)):
    """What a facility sees when staff key in the code.

    Carries `contributing_reasons` — the tier, the condition, whether an
    override fired and which rules — so the facility knows what to look for
    rather than receiving a bare instruction to investigate.
    """
    code = referral_code.upper()
    referral = db.scalar(select(Referral).where(Referral.referral_code == code))
    if referral is None:
        # Recorded as a refusal on its own session: unauthenticated, a
        # six-character code space, and rate limiting is Phase Two, so until
        # it exists the log is what makes a walk through that space visible.
        # See `routers/referral_lookup.py` for the reasoning in full.
        audit.record_refusal(
            audit.FACILITY_LOOKUP, "referral.read", object_type="referral",
            object_id=code, details={"reason": "unknown referral code"},
        )
        raise HTTPException(status_code=404, detail="No referral with that code")
    out = _referral_out(referral)
    audit.record(
        db, audit.FACILITY_LOOKUP, "referral.read",
        object_type="referral", object_id=referral.referral_code,
        person_id=referral.person_id,
        details={"condition": referral.condition_code, "status": referral.status},
    )
    db.commit()
    return out


@router.post("/referrals/{referral_code}/close", response_model=ReferralOut2)
def close_referral(
    referral_code: str, payload: ReferralCloseIn, db: Session = Depends(get_db)
):
    """Close a referral with what actually happened.

    §10.4: "closing a referral should capture the radiological or clinical
    outcome and return it to the person's record, not merely mark that they
    attended. Without that, the pilot produces an operational result and no
    labelled dataset."

    The outcome vocabulary is closed. A free-text field here would be easier
    for the person filling it in and would produce nothing a model can learn
    from, which is the one asset the pilot generates that nobody else in the
    country holds.
    """
    try:
        referral = referrals_v2.close_with_outcome(
            db,
            referral_code.upper(),
            payload.outcome,
            recorded_by=payload.recorded_by,
            notes=payload.notes,
        )
    except ReferralError as exc:
        status = 404 if "no referral" in str(exc) else 400
        audit.record_refusal(
            audit.FACILITY_LOOKUP, "referral.close", object_type="referral",
            object_id=referral_code.upper(),
            details={"reason": "unknown code" if status == 404 else "rejected outcome"},
        )
        raise HTTPException(status_code=status, detail=str(exc))
    # In the same transaction as the close it records. §10.4's structured
    # outcome is the pilot's labelled dataset, and an unauthenticated route
    # writing into it is exactly what §16.3's audit is for.
    audit.record(
        db, audit.FACILITY_LOOKUP, "referral.close",
        object_type="referral", object_id=referral.referral_code,
        person_id=referral.person_id,
        details={"outcome": payload.outcome, "condition": referral.condition_code},
    )
    db.commit()
    db.refresh(referral)
    return _referral_out(referral)


@router.get("/referrals/outcomes/vocabulary", response_model=list[str])
def referral_outcome_vocabulary():
    """The closed outcome set, served so the facility-facing page renders from
    the server's definition rather than a copy that can drift out of step with
    what the database will accept."""
    return list(referrals_v2.OUTCOMES)
