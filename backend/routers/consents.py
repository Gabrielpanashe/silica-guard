"""Consent capture over HTTP.

Master Reference v1.0 §8.5 and §14.2. Consent cannot be applied
retrospectively, so this exists before the first real record rather than
alongside it.

**Auth, and the one gap it leaves.** `POST /api/v2/consents` is
unauthenticated, on the same deliberate precedent as the screening path and
`POST /api/v2/persons/resolve`: the village health worker's application never
logs in, and a consent screen is part of a screening. Making consent capture
require a token while screening itself does not would be incoherent.

**Withdrawal requires a token**, and that is the gap. A worker's own
withdrawal should not need one — it is his decision about his own data — but
an open withdrawal endpoint keyed only by a person id would let anyone stop
anyone's referral reminders, which is a harm to the person it pretends to
serve. The worker-facing route is the USSD and SMS opt-out, which reaches
`services/consent.withdraw()` server-side through the gateway rather than
through this router, and that lands with item 1.9. Until then withdrawal is
staff-operated, which is honest but not what §14.2's "working and permanent
opt out" finally means.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import format_datetime, get_db
from db_models import ConsentRecord, ConsentText, Person
from models_v2 import (
    ConsentDecisionsIn,
    ConsentRecordOut,
    ConsentSummaryOut,
    ConsentTextOut,
    ConsentWithdrawIn,
    PermissionOut,
)
from routers.auth import request_id, require
from services import audit, consent, identity
from services.authz import Principal
from services.consent import ConsentError

router = APIRouter(prefix="/api/v2", tags=["consent"])


def _record_out(db: Session, row: ConsentRecord) -> ConsentRecordOut:
    text = db.get(ConsentText, row.consent_text_id) if row.consent_text_id else None
    return ConsentRecordOut(
        record_id=row.id,
        permission=row.permission,
        granted=bool(row.granted),
        consent_text_code=text.code if text else None,
        consent_text_version=text.version if text else None,
        channel=row.channel,
        recorded_at=format_datetime(row.recorded_at),
        recorded_by=row.recorded_by,
        withdrawn_at=format_datetime(row.withdrawn_at),
    )


@router.get("/consents/permissions", response_model=list[PermissionOut])
def list_permissions():
    """The six permissions and what each covers.

    Served so a consent screen renders from the server's definition rather
    than from a copy in the client — the same reasoning that moves the
    instrument and the patient-facing strings out of the application. A copy
    drifts, and a consent screen that drifts is asking for agreement to
    something other than what is recorded.
    """
    return [
        PermissionOut(
            code=p.code,
            scope=p.scope,
            required_to_screen=p.required_to_screen,
            future_phase=p.future_phase,
        )
        for p in consent.PERMISSIONS
    ]


@router.get("/consents/texts/{code}", response_model=ConsentTextOut)
def get_active_consent_text(code: str, db: Session = Depends(get_db)):
    """The approved consent text version to show, by code.

    `404` when none is approved — which is the state until the Clinical Lead
    approves one, and is why consent capture does not work before then. That
    is correct sequencing rather than a gap: nobody should be asked to agree
    to unreviewed wording.
    """
    try:
        text = consent.active_text(db, code)
    except ConsentError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return ConsentTextOut(
        consent_text_id=text.id,
        code=text.code,
        version=text.version,
        message_code=text.message_code,
        status=text.status,
        approved_by=text.approved_by,
        approved_at=format_datetime(text.approved_at),
    )


@router.post("/consents", response_model=ConsentSummaryOut)
def record_consent(payload: ConsentDecisionsIn, db: Session = Depends(get_db)):
    """Record a consent screen: grants and refusals together.

    A refusal is recorded as deliberately as a grant. "Asked and declined" is
    the answer an ethics committee wants, and it stops the same question being
    asked at every visit.

    All-or-nothing: a half-recorded consent screen is worse than a failed one,
    because afterwards the missing permissions are indistinguishable from
    refusals.
    """
    if not payload.decisions:
        raise HTTPException(status_code=400, detail="no decisions to record")
    try:
        consent.record_many(
            db,
            payload.person_id,
            payload.decisions,
            consent_text_id=payload.consent_text_id,
            channel=payload.channel,
            session_id=payload.session_id,
            recorded_by=payload.recorded_by,
        )
    except ConsentError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return _summary(db, payload.person_id)


@router.post("/consents/withdraw", response_model=ConsentSummaryOut)
def withdraw_consent(
    payload: ConsentWithdrawIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("consent.write")),
    rid: str = Depends(request_id),
):
    """Withdraw a standing grant.

    The original row is kept and stamped rather than deleted: §14.3 requires
    the withdrawal mechanism to be demonstrable, and "granted, then withdrawn
    on this date" is a different story from "never granted".

    Withdrawing something never granted is not an error — a worker opting out
    of what he never opted into should not get a failure.
    """
    try:
        consent.withdraw(
            db, payload.person_id, payload.permission, withdrawn_by=payload.withdrawn_by
        )
    except ConsentError as exc:
        audit.record_refusal(
            principal, "consent.withdraw", object_type="person",
            object_id=payload.person_id, person_id=payload.person_id,
            request_id=rid, details={"permission": payload.permission},
        )
        raise HTTPException(status_code=400, detail=str(exc))
    # §14.3 requires the withdrawal mechanism to be demonstrable, which means
    # a withdrawal has to be as recoverable from the log as a grant: "granted,
    # then withdrawn on this date" is a different story from "never granted",
    # and the audit is where an ethics committee reads it.
    audit.record(
        db, principal, "consent.withdraw", object_type="person",
        object_id=payload.person_id, person_id=payload.person_id,
        request_id=rid,
        details={"permission": payload.permission,
                 "withdrawn_by": payload.withdrawn_by},
    )
    db.commit()
    return _summary(db, payload.person_id)


def _summary(db: Session, person_id: int) -> ConsentSummaryOut:
    person = db.get(Person, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail=f"No person {person_id}")
    standing = consent.summary(db, person_id)
    return ConsentSummaryOut(
        person_id=person_id,
        participant_code=person.participant_code,
        standing=standing,
        may_screen=all(standing[p] for p in consent.REQUIRED_TO_SCREEN),
        may_keep_longitudinal_record=consent.may_keep_longitudinal_record(db, person_id),
        history=[_record_out(db, row) for row in consent.history(db, person_id)],
    )


@router.get("/persons/{participant_code}/consents", response_model=ConsentSummaryOut)
def get_person_consents(
    participant_code: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("consent.read")),
    rid: str = Depends(request_id),
):
    """Everything recorded for one person, by the code on their card.

    **`consent.read`, and audited.** It is about a named individual, so a
    token alone is not the boundary: §16.3's table gives this capability to
    the village health worker, who is the person who has to know whether a
    worker in front of them agreed to be screened. Until 3 November 2026 this
    used the plain token dependency, so any authenticated role reached it and
    no row was written.

    Follows a merge, so consent recorded against a record that later lost a
    merge is still found — a worker's decision must not be lost because a
    clerk joined two records.
    """
    person = identity.find_by_participant_code(db, participant_code)
    if person is None:
        audit.record_refusal(
            principal, "consent.read", object_type="person",
            object_id=participant_code, request_id=rid,
            details={"reason": "unknown participant code"},
        )
        raise HTTPException(status_code=404, detail="No person with that participant code")
    audit.record(
        db, principal, "consent.read", object_type="person",
        object_id=person.participant_code, person_id=person.id, request_id=rid,
    )
    db.commit()
    return _summary(db, person.id)
