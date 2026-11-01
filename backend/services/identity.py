"""Identity resolution: matching a worker to his own earlier record.

Master Reference v1.0 §8.2 -- "the hardest problem in the system and the one
most likely to quietly destroy the headline metric, because both deterioration
detection and referral completion depend on reliably matching a worker to his
own earlier record."

The four-part approach from §8.2, and where each part lives:

  1. **A telephone number is never an identity.** It is a `Contact` row with
     validity dates. Nothing in this module treats a number as a key; it is
     one signal among several, and on its own it is never enough.

  2. **Every person gets a participant code**, six characters from the same
     unambiguous alphabet as the referral codes, printed on a card the worker
     keeps. In a low-resource setting the cheapest reliable identity
     technology is a card in a pocket: he presents it at the next outreach,
     keys it into USSD, and a hospital clerk can read it aloud.

  3. **Matching is done on a bundle and never merged automatically.** A
     deterministic match on the hashed national identity number is applied;
     everything else is scored, queued for a human, and *not applied*.
     Duplicates are an annoyance that can be fixed later. A false merge is a
     clinical safety event: two clinical histories are mixed and there is no
     way to detect it by inspection.

  4. **The anonymous USSD case is explicit.** A participant code attaches to
     that person. No code creates a provisional identity flagged unverified
     for a health worker to resolve at the next contact. Never -- and
     `ussd_handler._find_or_create_miner` does exactly this today -- attach a
     screening to whoever the number was last seen with.

**`resolve()` always returns a person a screening can be written against.**
That is deliberate and it is what keeps rule 7 (a completed screening is
never discarded) and identity review from fighting each other: an uncertain
match produces a new person plus a queue entry, never a blocked screening. The
worst case is a duplicate, which is the failure §8.2 says to prefer.

**On the scoring weights below.** They are engineering, not clinical content,
and they are safe to choose here for one specific reason: *no score causes a
merge*. A score decides only whether a human is asked to look at a pair. Set
them too low and a reviewer sees noise; too high and a duplicate survives
until someone notices. Neither mixes two people's histories, which is the
only outcome that cannot be undone.
"""

from __future__ import annotations

import difflib
import json
import secrets
import string
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from db_models import (
    ConsentRecord,
    Contact,
    ExposureProfile,
    Person,
    PersonMatchQueue,
    PersonMerge,
    ScreeningSession,
)
from services import crypto

#: Same alphabet as the referral codes (`services/referrals.py`): no 0/O or
#: 1/I, because a code read off a phone screen or handwritten at a nurse's
#: desk must not hinge on telling those apart.
CODE_ALPHABET = "".join(c for c in string.ascii_uppercase + string.digits if c not in "0O1I")
#: Six, not the referral format's four. Thirty-two symbols to the sixth power
#: is about a billion codes against a million; this one addresses a register
#: intended for more than 500,000 people, and a collision here mixes two
#: clinical histories rather than confusing one hospital visit
#: (docs/IMPLEMENTATION_PLAN.md §12 item 4).
CODE_LENGTH = 6
_CODE_MAX_ATTEMPTS = 40

#: Closed vocabulary for `persons.provisional_reason`, enforced here rather
#: than by a CHECK constraint -- SQLite cannot add one by ALTER, and a
#: constraint only PostgreSQL applies is the divergence §16.2 warns about.
PROVISIONAL_REASONS = (
    "ussd_no_participant_code",
    "ussd_unrecognised_code",
    "awaiting_review",
)

#: What `resolve()` did. Recorded on the response so a client and an auditor
#: can tell an applied deterministic match from a queued probable one.
OUTCOMES = (
    #: The worker presented his card. Applied.
    "matched_participant_code",
    #: Deterministic match on the hashed national identity number. Applied.
    "matched_national_id",
    #: Nothing looked like him; a clean new record.
    "created",
    #: A new record, with one or more probable matches queued for a human.
    #: Kept distinct from `created_provisional`: the identity is unsettled for
    #: a different reason and is resolved by a different person.
    "created_pending_review",
    #: §8.2 part four. A USSD caller with no usable participant code.
    "created_provisional",
)

#: Scored signals. See the module docstring for why these numbers are safe to
#: pick: none of them merges anything.
WEIGHT_NAME_EXACT = 0.45
WEIGHT_NAME_FUZZY = 0.30
WEIGHT_SHARED_CONTACT = 0.35
WEIGHT_SAME_SITE = 0.15
WEIGHT_SAME_AGE_BAND = 0.10
WEIGHT_SAME_SEX = 0.05

#: Below this, a pair is not worth a reviewer's attention. Above it, the pair
#: is queued -- never merged.
QUEUE_THRESHOLD = 0.50
#: Name similarity counting as a fuzzy match. 0.85 on difflib's ratio is
#: roughly one or two characters' difference in a short name, which is the
#: common case: a transcription slip, not a different person.
NAME_SIMILARITY = 0.85

#: Everything that belongs to a person and therefore follows them through a
#: merge. Enumerated in one place rather than inlined in `merge()`, because
#: the failure mode of forgetting one is silent: the rows stay pointing at the
#: losing record, every read goes to the winner, and the data is simply gone
#: from view. `ConsentRecord` and `ExposureProfile` were both missing from the
#: first version of `merge()` -- consent in particular, which would have meant
#: a worker's recorded decisions vanishing because a clerk joined two records.
#:
#: Deliberately NOT here: `person_merges` (the audit of the merge itself, which
#: must keep naming the original two records) and `person_match_queue` (handled
#: separately, because a queued pair is resolved by the merge rather than
#: carried over).
MERGE_FOLLOWS = (
    (Contact, "person_id"),
    (ScreeningSession, "person_id"),
    (ConsentRecord, "person_id"),
    (ExposureProfile, "person_id"),
)

#: A merge chain should be one hop. The guard exists because a cycle created
#: by two merges in opposite directions would otherwise spin forever, and an
#: infinite loop in identity resolution takes the screening route down.
_MAX_MERGE_HOPS = 16


class IdentityError(ValueError):
    """The request cannot be carried out: an unknown person, a merge that
    would mix a record with itself, or an unmerge of something not merged."""


@dataclass(frozen=True)
class IdentityBundle:
    """What is known about the person in front of you, or on the other end of
    the USSD session. Every field is optional except that something must
    identify them -- `resolve()` rejects a bundle with nothing in it at all.

    `site_id`/`site_text` are the *session's* site, carried here because site
    is one of §8.2's bundle fields even though it lives on the session rather
    than on the person.
    """

    participant_code: str | None = None
    national_id: str | None = None
    name: str | None = None
    phone: str | None = None
    age_band: str | None = None
    sex: str | None = None
    site_id: int | None = None
    site_text: str | None = None
    language: str = "en"

    def is_empty(self) -> bool:
        return not any(
            (self.participant_code, self.national_id, self.name, self.phone)
        )


@dataclass(frozen=True)
class Candidate:
    """A person who might be the same person, with why. The reasons travel
    with the score because a reviewer deciding a merge needs the evidence, not
    a number -- and `person_merges.evidence` keeps them afterwards."""

    person_id: int
    participant_code: str | None
    score: float
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class Resolution:
    """What `resolve()` settled on. `person_id` is always usable."""

    person_id: int
    participant_code: str | None
    outcome: str
    provisional: bool = False
    #: Scored above the threshold and queued for a human. Never applied.
    candidates: tuple[Candidate, ...] = ()
    queued_match_ids: tuple[int, ...] = field(default_factory=tuple)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --------------------------------------------------------- participant codes

def generate_participant_code(db: Session) -> str:
    """Six characters, collision-checked against the register.

    Raises rather than returning a colliding code: a duplicate participant
    code points two workers at one clinical history, which is the same failure
    as a false merge and is worse than a failed registration.
    """
    for _ in range(_CODE_MAX_ATTEMPTS):
        candidate = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if db.scalar(select(Person).where(Person.participant_code == candidate)) is None:
            return candidate
    raise IdentityError(
        f"could not generate an unused participant code in {_CODE_MAX_ATTEMPTS} "
        "attempts. With a ~32^6 space this means something is wrong with the "
        "register, not that the space is exhausted."
    )


# ------------------------------------------------------------ merge following

def effective_person(db: Session, person_id: int) -> Person:
    """The surviving record for a person, following any merge.

    A losing record is kept rather than deleted (§8.2, merges reversible from
    the first day), so every read has to follow the pointer. Hop-limited: a
    cycle from two merges in opposite directions would otherwise loop forever
    inside the screening route.
    """
    person = db.get(Person, person_id)
    if person is None:
        raise IdentityError(f"no person {person_id}")
    seen = {person.id}
    hops = 0
    while person.merged_into_id is not None:
        hops += 1
        if hops > _MAX_MERGE_HOPS or person.merged_into_id in seen:
            raise IdentityError(
                f"merge chain from person {person_id} does not terminate "
                f"(stopped at {person.id}). Two merges in opposite directions "
                "can do this; unmerge one of them."
            )
        seen.add(person.merged_into_id)
        nxt = db.get(Person, person.merged_into_id)
        if nxt is None:
            raise IdentityError(
                f"person {person.id} is merged into {person.merged_into_id}, "
                "which does not exist"
            )
        person = nxt
    return person


# ---------------------------------------------------------- deterministic hits

def find_by_participant_code(db: Session, code: str) -> Person | None:
    """The card in the worker's pocket. Case- and space-insensitive, because
    it is read aloud and typed on a numeric keypad."""
    if not code:
        return None
    normalised = "".join(str(code).upper().split())
    person = db.scalar(select(Person).where(Person.participant_code == normalised))
    return effective_person(db, person.id) if person else None


def find_by_national_id(db: Session, national_id: str) -> Person | None:
    """The one field §8.2 permits a deterministic, directly-applied match on."""
    if not national_id:
        return None
    digest = crypto.keyed_hash(national_id, "national_id")
    person = db.scalar(select(Person).where(Person.national_id_hash == digest))
    return effective_person(db, person.id) if person else None


# -------------------------------------------------------------- probable hits

def _latest_site(db: Session, person_id: int) -> tuple[int | None, str | None]:
    session = db.scalar(
        select(ScreeningSession)
        .where(ScreeningSession.person_id == person_id)
        .order_by(ScreeningSession.created_at.desc(), ScreeningSession.id.desc())
        .limit(1)
    )
    return (session.site_id, session.site_text) if session else (None, None)


def _same_site(bundle: IdentityBundle, site_id: int | None, site_text: str | None) -> bool:
    if bundle.site_id is not None and site_id is not None:
        return bundle.site_id == site_id
    if bundle.site_text and site_text:
        return bundle.site_text.strip().casefold() == site_text.strip().casefold()
    return False


def _narrow(db: Session, bundle: IdentityBundle, exclude_id: int | None) -> set[int]:
    """Cheap deterministic narrowing before any decryption.

    This step is what makes fuzzy name matching possible at all. The name is
    encrypted at rest, so similarity cannot be computed in SQL; the answer is
    to reduce the register to a handful of plausible rows using indexed
    hashes, then decrypt only those, in memory. A phonetic key would allow
    indexed fuzzy matching and was rejected: Soundex-family algorithms are
    tuned for English and produce confident nonsense on Shona and Ndebele
    names, and a confident wrong candidate is worse than no candidate.
    """
    ids: set[int] = set()

    if bundle.phone:
        digest = crypto.keyed_hash(bundle.phone, "phone")
        ids.update(
            db.scalars(
                select(Contact.person_id).where(Contact.number_hmac == digest)
            ).all()
        )

    if bundle.name:
        digest = crypto.keyed_hash(bundle.name, "name")
        ids.update(
            db.scalars(select(Person.id).where(Person.name_hmac == digest)).all()
        )

    # Demographics alone are far too broad to be a signal, but combined with a
    # site they narrow usefully -- and a worker screened twice at the same
    # working is the common duplicate.
    if bundle.age_band and bundle.sex and (bundle.site_id or bundle.site_text):
        for person_id in db.scalars(
            select(Person.id).where(
                Person.age_band == bundle.age_band, Person.sex == bundle.sex
            )
        ).all():
            if _same_site(bundle, *_latest_site(db, person_id)):
                ids.add(person_id)

    ids.discard(exclude_id)
    return ids


def _score(db: Session, bundle: IdentityBundle, person: Person) -> Candidate:
    score = 0.0
    reasons: list[str] = []

    if bundle.name and person.name_hmac:
        if crypto.hashes_match(person.name_hmac, bundle.name, "name"):
            score += WEIGHT_NAME_EXACT
            reasons.append("name matches exactly")
        elif person.name_encrypted:
            # Decrypted here and nowhere else: the plaintext is compared in
            # memory and never indexed, logged or returned.
            stored = crypto.decrypt(person.name_encrypted)
            if stored:
                ratio = difflib.SequenceMatcher(
                    None, crypto.normalise_name(bundle.name), crypto.normalise_name(stored)
                ).ratio()
                if ratio >= NAME_SIMILARITY:
                    score += WEIGHT_NAME_FUZZY
                    reasons.append(f"name similar ({ratio:.2f})")

    if bundle.phone:
        digest = crypto.keyed_hash(bundle.phone, "phone")
        shared = db.scalar(
            select(Contact.id).where(
                Contact.person_id == person.id, Contact.number_hmac == digest
            )
        )
        if shared:
            score += WEIGHT_SHARED_CONTACT
            reasons.append("shares a contact number")

    site_id, site_text = _latest_site(db, person.id)
    if _same_site(bundle, site_id, site_text):
        score += WEIGHT_SAME_SITE
        reasons.append("same site")

    if bundle.age_band and person.age_band == bundle.age_band:
        score += WEIGHT_SAME_AGE_BAND
        reasons.append("same age band")

    if bundle.sex and person.sex == bundle.sex:
        score += WEIGHT_SAME_SEX
        reasons.append("same sex")

    return Candidate(
        person_id=person.id,
        participant_code=person.participant_code,
        score=round(min(score, 1.0), 3),
        reasons=tuple(reasons),
    )


def candidates_for(
    db: Session, bundle: IdentityBundle, exclude_id: int | None = None
) -> list[Candidate]:
    """Probable matches, scored, highest first. Nothing is applied."""
    out: list[Candidate] = []
    for person_id in _narrow(db, bundle, exclude_id):
        person = db.get(Person, person_id)
        if person is None or person.merged_into_id is not None:
            continue
        candidate = _score(db, bundle, person)
        if candidate.score >= QUEUE_THRESHOLD:
            out.append(candidate)
    out.sort(key=lambda c: (-c.score, c.person_id))
    return out


# ------------------------------------------------------------------- contacts

def attach_contact(
    db: Session, person: Person, phone: str, *, verified: bool = False
) -> Contact:
    """Record a number against a person, or re-verify the one already there.

    Many people may share a number and one person may hold several over time,
    so this never replaces and never deduplicates across people (§8.2). It is
    the row that makes a number an attribute with history rather than a key.
    """
    digest = crypto.keyed_hash(phone, "phone")
    existing = db.scalar(
        select(Contact).where(
            Contact.person_id == person.id,
            Contact.number_hmac == digest,
            Contact.valid_to.is_(None),
        )
    )
    if existing is not None:
        if verified and not existing.verified:
            existing.verified = 1
            existing.verified_at = _utcnow()
        return existing

    contact = Contact(
        person_id=person.id,
        number_hmac=digest,
        number_encrypted=crypto.encrypt(crypto.normalise_phone(phone)),
        is_primary=1
        if db.scalar(select(Contact.id).where(Contact.person_id == person.id)) is None
        else 0,
        verified=1 if verified else 0,
        verified_at=_utcnow() if verified else None,
    )
    db.add(contact)
    db.flush()
    return contact


def primary_phone(db: Session, person_id: int) -> str | None:
    """The number to send to, decrypted. The only place a stored number
    becomes plaintext again, and it exists because a result has to reach a
    handset."""
    contact = db.scalar(
        select(Contact)
        .where(Contact.person_id == person_id, Contact.valid_to.is_(None))
        .order_by(Contact.is_primary.desc(), Contact.id.desc())
        .limit(1)
    )
    return crypto.decrypt(contact.number_encrypted) if contact else None


def display_name(db: Session, person_id: int) -> str | None:
    """Decrypted name, for a health worker's screen or a referral letter."""
    person = db.get(Person, person_id)
    return crypto.decrypt(person.name_encrypted) if person else None


# ------------------------------------------------------------------- resolving

def _create_person(
    db: Session, bundle: IdentityBundle, *, provisional_reason: str | None
) -> Person:
    if provisional_reason is not None and provisional_reason not in PROVISIONAL_REASONS:
        raise IdentityError(
            f"unknown provisional reason {provisional_reason!r}; expected one "
            f"of {PROVISIONAL_REASONS}"
        )
    person = Person(
        participant_code=generate_participant_code(db),
        national_id_hash=crypto.keyed_hash(bundle.national_id, "national_id")
        if bundle.national_id
        else None,
        name_hmac=crypto.keyed_hash(bundle.name, "name") if bundle.name else None,
        name_encrypted=crypto.encrypt(bundle.name) if bundle.name else None,
        age_band=bundle.age_band,
        sex=bundle.sex,
        language=bundle.language or "en",
        provisional=1 if provisional_reason else 0,
        provisional_reason=provisional_reason,
    )
    db.add(person)
    db.flush()
    if bundle.phone:
        attach_contact(db, person, bundle.phone)
    return person


def queue_candidates(
    db: Session, incoming_person_id: int, candidates: list[Candidate]
) -> list[int]:
    """Park probable matches for a human decision. Returns the queue row ids.

    This is the whole of §8.2's "never merged automatically". The queue is a
    table and not a log line because somebody has to work through it, and
    because "this pair was reviewed and rejected" is an answer that must
    survive.
    """
    ids: list[int] = []
    for candidate in candidates:
        already = db.scalar(
            select(PersonMatchQueue).where(
                PersonMatchQueue.incoming_person_id == incoming_person_id,
                PersonMatchQueue.candidate_person_id == candidate.person_id,
                PersonMatchQueue.status == "pending",
            )
        )
        if already is not None:
            ids.append(already.id)
            continue
        row = PersonMatchQueue(
            incoming_person_id=incoming_person_id,
            candidate_person_id=candidate.person_id,
            score=candidate.score,
            evidence=json.dumps({"reasons": list(candidate.reasons)}, sort_keys=True),
        )
        db.add(row)
        db.flush()
        ids.append(row.id)
    return ids


def resolve(
    db: Session,
    bundle: IdentityBundle,
    *,
    channel: str = "APP",
) -> Resolution:
    """§8.2's matching order, and the only entry point a screening should use.

    1. A participant code attaches to that person, full stop. It is the card
       in his pocket and he presented it.
    2. Otherwise a hashed national identity number is a deterministic match
       and is applied.
    3. Otherwise the remainder is scored. Probable matches are **queued** and
       a new person is created, so the screening has somewhere to go. On USSD
       with no code, that new person is flagged provisional.

    Never: attach to whoever a telephone number was last seen with.
    """
    if bundle.is_empty():
        raise IdentityError(
            "an identity bundle needs at least a participant code, a national "
            "identity number, a name or a contact number"
        )

    if bundle.participant_code:
        person = find_by_participant_code(db, bundle.participant_code)
        if person is not None:
            if bundle.phone:
                attach_contact(db, person, bundle.phone)
            return Resolution(
                person_id=person.id,
                participant_code=person.participant_code,
                outcome="matched_participant_code",
                provisional=bool(person.provisional),
            )
        # A code that matches nobody is a mis-key or a card from another
        # programme. On USSD there is no one to ask, so it becomes a
        # provisional identity with the reason recorded rather than being
        # silently ignored.
        if channel.upper() == "USSD":
            person = _create_person(
                db, bundle, provisional_reason="ussd_unrecognised_code"
            )
            return Resolution(
                person_id=person.id,
                participant_code=person.participant_code,
                outcome="created_provisional",
                provisional=True,
            )
        raise IdentityError(
            f"participant code {bundle.participant_code!r} matches no person. "
            "Check the card rather than creating a second record for someone "
            "who already has one."
        )

    if bundle.national_id:
        person = find_by_national_id(db, bundle.national_id)
        if person is not None:
            if bundle.phone:
                attach_contact(db, person, bundle.phone)
            return Resolution(
                person_id=person.id,
                participant_code=person.participant_code,
                outcome="matched_national_id",
                provisional=bool(person.provisional),
            )

    candidates = candidates_for(db, bundle)
    provisional_reason = (
        "ussd_no_participant_code"
        if channel.upper() == "USSD"
        else ("awaiting_review" if candidates else None)
    )
    person = _create_person(db, bundle, provisional_reason=provisional_reason)
    queued = queue_candidates(db, person.id, candidates)

    if channel.upper() == "USSD":
        outcome = "created_provisional"
    elif candidates:
        outcome = "created_pending_review"
    else:
        outcome = "created"

    return Resolution(
        person_id=person.id,
        participant_code=person.participant_code,
        outcome=outcome,
        provisional=bool(provisional_reason),
        candidates=tuple(candidates),
        queued_match_ids=tuple(queued),
    )


# --------------------------------------------------------- merging, reversibly

def merge(
    db: Session,
    winner_person_id: int,
    loser_person_id: int,
    *,
    merged_by: str,
    evidence: dict | None = None,
) -> PersonMerge:
    """Apply a merge a human decided on.

    The losing record is kept and flagged, never deleted, so the merge is
    reversible from the first day (§8.2) with both histories intact.
    Everything in MERGE_FOLLOWS moves to the winner: contacts because a number
    is an attribute, sessions because they are the clinical history the merge
    exists to join, **consent records because a worker's decision about his
    own data must not be lost when a clerk joins two records**, and exposure
    profiles because a work history accumulates across sectors.

    Where both records hold a decision on the same permission, the more recent
    one stands -- `consent._standing()` takes the latest, which is the right
    answer: it is the same person's later decision.
    """
    if winner_person_id == loser_person_id:
        raise IdentityError("a person cannot be merged into themselves")

    winner = effective_person(db, winner_person_id)
    loser = db.get(Person, loser_person_id)
    if loser is None:
        raise IdentityError(f"no person {loser_person_id}")
    if loser.merged_into_id is not None:
        raise IdentityError(
            f"person {loser_person_id} is already merged into "
            f"{loser.merged_into_id}. Unmerge that first; chaining merges "
            "makes the reversal ambiguous."
        )
    if winner.id == loser.id:
        raise IdentityError(
            "those two records already resolve to the same person"
        )

    for model, column in MERGE_FOLLOWS:
        for row in db.scalars(
            select(model).where(getattr(model, column) == loser.id)
        ).all():
            setattr(row, column, winner.id)

    # The winner inherits anything it was missing, and overwrites nothing: a
    # merge must not be able to change a value somebody already recorded.
    for attribute in ("national_id_hash", "name_hmac", "name_encrypted", "age_band", "sex"):
        if getattr(winner, attribute, None) in (None, "") and getattr(loser, attribute, None):
            setattr(winner, attribute, getattr(loser, attribute))
    if winner.provisional and not loser.provisional:
        winner.provisional, winner.provisional_reason = 0, None

    loser.merged_into_id = winner.id

    record = PersonMerge(
        winner_person_id=winner.id,
        loser_person_id=loser.id,
        evidence=json.dumps(evidence or {}, sort_keys=True),
        merged_by=merged_by,
    )
    db.add(record)

    for row in db.scalars(
        select(PersonMatchQueue).where(
            PersonMatchQueue.status == "pending",
            PersonMatchQueue.incoming_person_id.in_([winner.id, loser.id]),
            PersonMatchQueue.candidate_person_id.in_([winner.id, loser.id]),
        )
    ).all():
        row.status = "merged"
        row.resolved_by = merged_by
        row.resolved_at = _utcnow()

    db.flush()
    return record


def unmerge(db: Session, merge_id: int, *, reversed_by: str) -> PersonMerge:
    """Undo a merge, keeping the audit of both the merge and the reversal.

    Contacts and sessions are **not** moved back. Which rows belonged to which
    record before the merge is not recoverable from the surviving data, and
    inventing an answer would be worse than the honest one: the reversal
    restores the two identities and a health worker reassigns the encounters.
    Recorded here rather than discovered by whoever first needs it.
    """
    record = db.get(PersonMerge, merge_id)
    if record is None:
        raise IdentityError(f"no merge {merge_id}")
    if record.reversed_at is not None:
        raise IdentityError(f"merge {merge_id} was already reversed")

    loser = db.get(Person, record.loser_person_id)
    if loser is None:
        raise IdentityError(f"merge {merge_id} names a person that no longer exists")

    loser.merged_into_id = None
    record.reversed_by = reversed_by
    record.reversed_at = _utcnow()
    db.flush()
    return record


# --------------------------------------------------------------- the queue API

def pending_matches(db: Session, limit: int = 50) -> list[PersonMatchQueue]:
    return list(
        db.scalars(
            select(PersonMatchQueue)
            .where(PersonMatchQueue.status == "pending")
            .order_by(PersonMatchQueue.score.desc(), PersonMatchQueue.id)
            .limit(limit)
        ).all()
    )


def decide_match(
    db: Session, match_id: int, *, decision: str, decided_by: str
) -> PersonMatchQueue:
    """Apply or reject one queued pair.

    `merge` performs the merge with the queue row's own evidence attached, so
    the reason a reviewer was shown a pair is the reason recorded against the
    merge. `reject` keeps the row: "this pair was reviewed and they are
    different people" has to survive, or the same pair is queued again at the
    next screening.
    """
    row = db.get(PersonMatchQueue, match_id)
    if row is None:
        raise IdentityError(f"no queued match {match_id}")
    if row.status != "pending":
        raise IdentityError(f"queued match {match_id} is already {row.status}")

    if decision == "merge":
        evidence = json.loads(row.evidence) if row.evidence else {}
        evidence["queued_match_id"] = match_id
        evidence["score"] = row.score
        merge(
            db,
            winner_person_id=row.candidate_person_id,
            loser_person_id=row.incoming_person_id,
            merged_by=decided_by,
            evidence=evidence,
        )
        # merge() already resolved this row.
        db.refresh(row)
        return row

    if decision != "reject":
        raise IdentityError(f"decision must be 'merge' or 'reject', not {decision!r}")

    row.status = "rejected"
    row.resolved_by = decided_by
    row.resolved_at = _utcnow()
    db.flush()
    return row
