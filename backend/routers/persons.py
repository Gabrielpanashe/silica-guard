"""Identity resolution over HTTP.

Master Reference v1.0 §8.2. Six routes: resolve a bundle to a person, look a
person up by the code on their card, work the match review queue, and merge or
unmerge two records.

**Auth, and an honest gap.** `POST /api/v2/persons/resolve` is
unauthenticated, on the same deliberate precedent as the screening path: the
village health worker's application never logs in, and resolving returns a
person id, an outcome and candidate participant codes -- no name and no
number.

Everything that returns or changes a direct identifier requires a Bearer
token: the person lookup (it decrypts a name and a number), the queue, and
merge/unmerge. That is weaker than it should be in one direction and stronger
than is convenient in another, and both are worth saying out loud:

  * **The VHW application cannot yet confirm an identity at the next
    outreach.** A worker presents his card, the health worker types the code,
    and the right next step is to show "is this the person?" -- which needs
    the name this route will not give an unauthenticated caller. Making it
    public instead would let anyone walk the code space and harvest names and
    telephone numbers, which is strictly worse than the open referral lookup
    (§15.4 already lists that one's missing rate limiting and lockout as a
    gap). The application needs a device credential; that is item 1.13, and
    this flow waits for it rather than being bought with a public identifier
    endpoint.

  * **Any dashboard login can merge two people today.** There are two flat
    accounts (§16.6), so Bearer is the only boundary available. A merge is a
    clinical safety event and belongs to one named role; item 1.13 scopes it.
    Named here so nobody discovers it in the pilot.
"""

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import format_datetime, get_db
from db_models import Person, PersonMatchQueue, PersonMerge, ScreeningSession
from models_v2 import (
    IdentityBundleIn,
    MatchCandidateOut,
    MatchDecisionIn,
    MergeIn,
    MergeOut,
    PersonOut,
    QueuedMatchOut,
    ResolutionOut,
)
from routers.auth import get_current_user
from services import crypto, identity
from services.identity import IdentityBundle, IdentityError

router = APIRouter(prefix="/api/v2", tags=["identity"])


def _bundle(payload: IdentityBundleIn) -> IdentityBundle:
    return IdentityBundle(
        participant_code=payload.participant_code,
        national_id=payload.national_id,
        name=payload.name,
        phone=payload.phone,
        age_band=payload.age_band,
        sex=payload.sex,
        site_id=payload.site_id,
        site_text=payload.site_text,
        language=payload.language,
    )


def _person_out(db: Session, person: Person, *, include_identifiers: bool) -> PersonOut:
    sessions = db.scalar(
        select(func.count(ScreeningSession.id)).where(
            ScreeningSession.person_id == person.id
        )
    )
    return PersonOut(
        person_id=person.id,
        participant_code=person.participant_code,
        name=crypto.decrypt(person.name_encrypted) if include_identifiers else None,
        phone=identity.primary_phone(db, person.id) if include_identifiers else None,
        age_band=person.age_band,
        sex=person.sex,
        language=person.language or "en",
        provisional=bool(person.provisional),
        provisional_reason=person.provisional_reason,
        has_national_id=bool(person.national_id_hash),
        session_count=int(sessions or 0),
        merged_into_person_id=person.merged_into_id,
    )


def _reasons(row: PersonMatchQueue) -> list[str]:
    if not row.evidence:
        return []
    try:
        return list(json.loads(row.evidence).get("reasons") or [])
    except (ValueError, AttributeError):
        return []


def _keys_or_503():
    """A missing identity key is a configuration failure, not a client error.

    503 rather than 500 so the mobile application's offline queue treats it as
    retryable: the screening is already on the handset and must not be thrown
    away because the server is misconfigured (rule 7).
    """
    if not crypto.keys_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "Identity keys are not configured on this server, so no "
                "identifier can be stored. Nothing was saved; retry once the "
                "server is configured."
            ),
        )


@router.post("/persons/resolve", response_model=ResolutionOut)
def resolve_person(payload: IdentityBundleIn, db: Session = Depends(get_db)):
    """§8.2's matching order. Always returns a person a screening can be
    written against: a probable match is queued for a human, never applied,
    and never blocks the screening."""
    _keys_or_503()
    try:
        resolution = identity.resolve(db, _bundle(payload), channel=payload.channel)
    except IdentityError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()

    person = db.get(Person, resolution.person_id)
    return ResolutionOut(
        person_id=resolution.person_id,
        participant_code=resolution.participant_code,
        outcome=resolution.outcome,
        provisional=resolution.provisional,
        provisional_reason=person.provisional_reason if person else None,
        candidates=[
            MatchCandidateOut(
                person_id=c.person_id,
                participant_code=c.participant_code,
                score=c.score,
                reasons=list(c.reasons),
            )
            for c in resolution.candidates
        ],
        queued_match_ids=list(resolution.queued_match_ids),
    )


# The literal paths are declared before "/persons/{participant_code}" so a
# code can never shadow one. FastAPI matches in declaration order.
@router.get("/persons/matches/queue", response_model=list[QueuedMatchOut])
def list_pending_matches(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """Probable matches awaiting a human decision — §8.2's "never merged
    automatically", as a worklist.

    No name or number: a reviewer opens each side by participant code, so the
    list itself carries no direct identifier.
    """
    out: list[QueuedMatchOut] = []
    for row in identity.pending_matches(db, limit=limit):
        incoming = db.get(Person, row.incoming_person_id)
        candidate = db.get(Person, row.candidate_person_id)
        out.append(
            QueuedMatchOut(
                person_id=row.incoming_person_id,
                participant_code=incoming.participant_code if incoming else None,
                candidate_person_id=row.candidate_person_id,
                candidate_participant_code=candidate.participant_code if candidate else None,
                match_id=row.id,
                score=row.score,
                reasons=_reasons(row),
                status=row.status,
                created_at=format_datetime(row.created_at),
            )
        )
    return out


@router.get("/persons/{participant_code}", response_model=PersonOut)
def get_person(
    participant_code: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """The card in the worker's pocket, resolved to the surviving record.

    Follows a merge rather than returning a dead row, so a card printed before
    a merge still works -- which is the point of printing one.
    """
    _keys_or_503()
    person = identity.find_by_participant_code(db, participant_code)
    if person is None:
        raise HTTPException(status_code=404, detail="No person with that participant code")
    return _person_out(db, person, include_identifiers=True)


@router.post("/persons/matches/{match_id}", response_model=QueuedMatchOut)
def decide_match(
    match_id: int,
    payload: MatchDecisionIn,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """Apply or reject one queued pair. A rejection is recorded rather than
    discarded, or the same pair returns at the next screening."""
    try:
        row = identity.decide_match(
            db, match_id, decision=payload.decision, decided_by=payload.decided_by
        )
    except IdentityError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    db.refresh(row)

    incoming = db.get(Person, row.incoming_person_id)
    candidate = db.get(Person, row.candidate_person_id)
    return QueuedMatchOut(
        person_id=row.incoming_person_id,
        participant_code=incoming.participant_code if incoming else None,
        candidate_person_id=row.candidate_person_id,
        candidate_participant_code=candidate.participant_code if candidate else None,
        match_id=row.id,
        score=row.score,
        reasons=_reasons(row),
        status=row.status,
        created_at=format_datetime(row.created_at),
    )


def _merge_out(record: PersonMerge) -> MergeOut:
    return MergeOut(
        merge_id=record.id,
        winner_person_id=record.winner_person_id,
        loser_person_id=record.loser_person_id,
        merged_by=record.merged_by,
        merged_at=format_datetime(record.merged_at),
        reversed_by=record.reversed_by,
        reversed_at=format_datetime(record.reversed_at),
    )


@router.post("/persons/merges", response_model=MergeOut)
def merge_persons(
    payload: MergeIn,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """Apply a merge a human decided on. The losing record is kept and
    flagged, never deleted, so this is reversible from the first day."""
    try:
        record = identity.merge(
            db,
            winner_person_id=payload.winner_person_id,
            loser_person_id=payload.loser_person_id,
            merged_by=payload.merged_by,
            evidence={"reason": payload.reason} if payload.reason else {},
        )
    except IdentityError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    db.refresh(record)
    return _merge_out(record)


@router.delete("/persons/merges/{merge_id}", response_model=MergeOut)
def unmerge_persons(
    merge_id: int,
    reversed_by: str = Query(..., min_length=2),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """Undo a merge. Both the merge and the reversal stay in the audit.

    Contacts and sessions are **not** moved back: which rows belonged to which
    record before the merge is not recoverable from the surviving data, and
    guessing would be worse than the honest answer. The reversal restores the
    two identities and a health worker reassigns the encounters.
    """
    try:
        record = identity.unmerge(db, merge_id, reversed_by=reversed_by)
    except IdentityError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    db.refresh(record)
    return _merge_out(record)
