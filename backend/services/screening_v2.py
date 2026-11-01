"""The screening pipeline.

Master Reference v1.0 §10.3, and Figure 2. **The order is deliberate and each
step exists because of a specific failure the previous design allowed.**

    1.  resolve identity          participant code, bundle match, provisional
    2.  check consent             versioned text, timestamp
    3.  load instrument version   questions, options, rules
    4.  PERSIST RAW ANSWERS       before any scoring happens
    5.  score per condition       deterministic rules
    6.  deterioration             against the previous session
    7.  safety overrides          raise only, never lower. LAST.
    8.  write result rows         one per condition, with provenance
    9.  select patient-facing text reviewed strings, person's language
    10. tier 3/4 -> referral      facility, window, code
    11. return                    identical output online or offline

Three points carry most of the safety weight, in §10.3's own words:

  **Answers are persisted before any scoring occurs**, so that a downstream
  failure can never lose what the worker actually reported. This module
  therefore commits twice: once after step 4 and once at the end. If scoring
  raises -- an incomplete instrument, a malformed rule -- the session and its
  answers stand with no result rows, and the caller is told exactly that.
  That is the opposite of `routers/screening.py`, which **deletes** the
  screening when the model call fails.

  **Safety overrides run last**, after scoring and after deterioration
  escalation, so that no earlier step and no model can be the final word on a
  red flag. The engine enforces this; this module does not reorder it.

  **The result is the same whether the device was online or offline**, because
  the same deterministic engine produced it in both cases.

And one that carries the rest: **a duplicate submission does not create a
second session.** `client_session_uuid` is checked before anything else runs,
so a mobile retry or a gateway redelivery returns the first session's result
with `replayed=True` and writes nothing. That is the structural fix for the 23
August incident, where a Gemini flakiness window produced eighteen duplicate
rows for one miner.

What is NOT here, and why:

  **Sending.** Step 11's messages are not sent. Two prerequisites are absent:
  no patient-facing string has been approved yet (item 1.6b, the Clinical
  Lead's), and `notifications.worker_id` is NOT NULL against the v1 `miners`
  table, so a message to a `Person` cannot even be logged until that table is
  rebuilt (§12 item 15, the `drop_v1` migration). The outcome therefore reports which
  message codes *would* be sent and records that nothing was, with the reason.
  §10.3 requires a messaging failure to be recorded rather than lost, and "no
  approved text exists" is a recorded reason rather than a silent skip.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from db_models import (
    Instrument,
    OutreachVisit,
    Person,
    Referral,
    ScreeningAnswer,
    ScreeningResult,
    ScreeningSession,
)
from services import consent, content_store, identity, instrument_store, referrals_v2
from services.rules_engine import (
    ConditionResult,
    IncompleteScreeningError,
    Screening,
    classify,
    primary_tier,
)

#: Message code per tier, for the result the worker is told. The codes are
#: fixed here; the words are the Clinical Lead's and live in the content
#: store, so this is a selector and not a source of text (§8.4).
TIER_MESSAGE_CODES = {
    "GREEN": "result.green.sms",
    "YELLOW": "result.yellow.sms",
    "ORANGE": "result.orange.sms",
    "RED": "result.red.sms",
}


class ScreeningError(ValueError):
    """The screening cannot run: no such person, no approved instrument, or a
    missing idempotency key. Raised before anything is written."""


class IncompleteScreening(ScreeningError):
    """An applicable question was unanswered, so no tier may be produced
    (§13.1). **The answers are already persisted and stay persisted** -- rule
    7, a completed screening is never discarded.

    Carries the session id because that is what the caller needs: finish THAT
    session. Resubmitting under the same idempotency key would only replay a
    session that has no results.
    """

    def __init__(self, session_id: int, missing: list[str]):
        self.session_id = session_id
        self.missing = list(missing)
        super().__init__(
            f"session {session_id} is incomplete and produced no tier. The "
            f"answers given are saved. Unanswered applicable questions: "
            f"{', '.join(self.missing)}."
        )


@dataclass(frozen=True)
class ScreeningRequest:
    """One screening, as submitted by a channel.

    `client_session_uuid` is generated on the device when the session starts
    and replayed on retry. It is required, not optional: it is the only thing
    that makes a retry safe, and a channel that cannot produce one is a
    channel that will create duplicates.
    """

    person_id: int
    client_session_uuid: str
    #: question code -> recorded answer value. An explicit unknown or refused
    #: option belongs here too; the engine derives `unknown` from the
    #: instrument rather than from absence (§12.2 item 10).
    answers: dict[str, str]
    channel: str = "APP"
    screened_by: str | None = None
    site_id: int | None = None
    site_text: str | None = None
    programme_id: int | None = None
    outreach_visit_id: int | None = None
    instrument_code: str | None = None
    started_at: datetime | None = None
    #: The device ran the rules engine locally and had no connectivity. Not a
    #: different result -- the same engine produced it -- but worth recording.
    offline: bool = False


@dataclass(frozen=True)
class MessagePlan:
    """What would be sent, and whether the words exist yet."""

    code: str
    available: bool
    language: str | None = None
    text: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class ReferralPlan:
    referral_code: str
    condition: str
    tier: str
    facility: str | None
    deadline: str | None


@dataclass(frozen=True)
class Outcome:
    session_id: int
    person_id: int
    participant_code: str | None
    primary_tier: str
    results: tuple[ConditionResult, ...]
    instrument_code: str
    instrument_version: int
    #: True when this submission matched an existing `client_session_uuid`.
    #: Nothing was written.
    replayed: bool = False
    #: False when longitudinal consent was absent, so no previous session was
    #: linked and no deterioration comparison was possible (§14.2).
    longitudinal_linked: bool = False
    referrals: tuple[ReferralPlan, ...] = ()
    messages: tuple[MessagePlan, ...] = ()
    #: Why nothing was sent. Empty once item 1.6b and `drop_v1` land.
    not_sent_reason: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") if value else None


# ----------------------------------------------------------- idempotency

def find_replay(db: Session, client_session_uuid: str) -> ScreeningSession | None:
    """The session a repeat submission already created, if any."""
    if not client_session_uuid:
        return None
    return db.scalar(
        select(ScreeningSession).where(
            ScreeningSession.client_session_uuid == client_session_uuid
        )
    )


def _results_for(db: Session, session_id: int) -> list[ScreeningResult]:
    return list(
        db.scalars(
            select(ScreeningResult)
            .where(ScreeningResult.session_id == session_id)
            .order_by(ScreeningResult.condition_code)
        ).all()
    )


def _stored_outcome(db: Session, session: ScreeningSession) -> Outcome:
    """Rebuild the outcome of a session already on disk, for a replay.

    Reads the stored rows rather than re-running the engine. Re-running would
    be the subtler bug: the instrument could have been superseded between the
    first submission and the retry, and a retry must return what the worker
    was actually told, not what the current rules would say.
    """
    rows = _results_for(db, session.id)
    if not rows:
        raise ScreeningError(
            f"session {session.id} was persisted but produced no results, so "
            "there is nothing to replay. The answers are kept (rule 7); the "
            "screening needs to be completed, not resubmitted under the same "
            "idempotency key."
        )
    person = db.get(Person, session.person_id)
    results = tuple(
        ConditionResult(
            condition=r.condition_code,
            tier=r.tier,
            score=r.score or 0,
            method=r.method,
            instrument_code=r.instrument_code or "",
            instrument_version=r.instrument_version or 0,
            scored_tier=r.scored_tier or r.tier,
            override_fired=bool(r.override_fired),
            override_rule_codes=tuple(
                c for c in (r.override_rule_codes or "").split(",") if c
            ),
        )
        for r in rows
    )
    referrals = tuple(
        ReferralPlan(
            referral_code=ref.referral_code,
            condition=ref.condition_code or "",
            tier=next((r.tier for r in rows if r.id == ref.result_id), ""),
            facility=ref.hospital,
            deadline=_iso(ref.deadline),
        )
        for ref in db.scalars(
            select(Referral).where(Referral.result_id.in_([r.id for r in rows]))
        ).all()
    )
    return Outcome(
        session_id=session.id,
        person_id=session.person_id,
        participant_code=person.participant_code if person else None,
        primary_tier=primary_tier(list(results)),
        results=results,
        instrument_code=session.instrument_code or "",
        instrument_version=session.instrument_version or 0,
        replayed=True,
        longitudinal_linked=session.previous_session_id is not None,
        referrals=referrals,
        started_at=_iso(session.started_at),
        completed_at=_iso(session.completed_at),
    )


# ------------------------------------------------------------------ text

def _plan_messages(db: Session, tier: str, language: str) -> tuple[list[MessagePlan], str | None]:
    """Which strings this result would send, and whether they exist.

    Deliberately does not fall back to a hardcoded sentence. The whole of
    §8.4 is that a worker reads reviewed words or nothing; a placeholder
    shipped "for now" is how unreviewed text reaches people.
    """
    code = TIER_MESSAGE_CODES.get(tier)
    if code is None:
        return [], f"no message code is mapped for tier {tier}"

    try:
        rendered = content_store.render(db, code, language)
    except content_store.ContentNotFound:
        return (
            [MessagePlan(code=code, available=False,
                         reason="not in the content store yet")],
            "the content store holds no message for this tier yet (item 1.6b)",
        )
    except content_store.ContentNotApproved:
        return (
            [MessagePlan(code=code, available=False,
                         reason="exists but is not approved")],
            "the message for this tier is not approved by the Clinical Lead yet",
        )
    except content_store.PlaceholderError as exc:
        return (
            [MessagePlan(code=code, available=False, reason=str(exc))],
            "the message for this tier needs values this pipeline does not supply yet",
        )

    return (
        [MessagePlan(code=code, available=True,
                     language=rendered["language"], text=rendered["text"])],
        None,
    )


# -------------------------------------------------------------- the pipeline

def screen(db: Session, request: ScreeningRequest) -> Outcome:
    """Run one screening. See this module's docstring for the order and why.

    Commits twice, deliberately: once after the answers are persisted and once
    when the results are written. A caller must not wrap this in its own
    transaction expecting a single rollback point -- the whole design is that
    the answers survive a later failure.
    """
    if not request.client_session_uuid:
        raise ScreeningError(
            "client_session_uuid is required. It is generated on the device "
            "when the session starts and replayed on retry, and it is the only "
            "thing that makes a duplicate submission safe (§10.3)."
        )

    # ---- 0. idempotency, before anything is read or written --------------
    existing = find_replay(db, request.client_session_uuid)
    if existing is not None:
        return _stored_outcome(db, existing)

    # ---- 1. identity -----------------------------------------------------
    person = identity.effective_person(db, request.person_id)

    # ---- 2. consent ------------------------------------------------------
    # Raises ConsentMissing. The one hard gate in the pipeline: §14.2's core
    # permission is "required to proceed. Without it there is no service."
    consent.may_screen(db, person.id)
    keep_history = consent.may_keep_longitudinal_record(db, person.id)

    # ---- 3. instrument ---------------------------------------------------
    code = request.instrument_code
    if code is None:
        codes = {
            row for row in db.scalars(select(Instrument.code)).all()
        }
        if len(codes) != 1:
            raise ScreeningError(
                "instrument_code must be given: the database holds "
                f"{len(codes)} instruments and there is no default. An "
                "instrument is chosen deliberately, never guessed."
            )
        code = codes.pop()
    try:
        instrument = instrument_store.read_active(db, code)
    except instrument_store.InstrumentLoadError as exc:
        raise ScreeningError(str(exc)) from exc

    # The previous session, for deterioration -- only where the worker
    # consented to a longitudinal record (§14.2). Without that consent the
    # screening still happens; it simply has no history attached.
    previous: ScreeningSession | None = None
    if keep_history:
        previous = db.scalar(
            select(ScreeningSession)
            .where(ScreeningSession.person_id == person.id)
            .order_by(ScreeningSession.created_at.desc(), ScreeningSession.id.desc())
            .limit(1)
        )

    # ---- 4. PERSIST RAW ANSWERS FIRST ------------------------------------
    session = ScreeningSession(
        person_id=person.id,
        channel=request.channel,
        screened_by=request.screened_by,
        site_id=request.site_id,
        site_text=request.site_text,
        programme_id=request.programme_id,
        instrument_code=instrument["code"],
        instrument_version=instrument["version"],
        ruleset_version=f"{instrument['code']}-v{instrument['version']}",
        previous_session_id=previous.id if previous else None,
        client_session_uuid=request.client_session_uuid,
        outreach_visit_id=request.outreach_visit_id,
        started_at=request.started_at or _utcnow(),
    )
    db.add(session)
    db.flush()

    for question_code, value in request.answers.items():
        db.add(
            ScreeningAnswer(
                session_id=session.id,
                question_code=question_code,
                answer_value=value,
            )
        )

    if request.outreach_visit_id is not None:
        visit = db.get(OutreachVisit, request.outreach_visit_id)
        if visit is not None:
            visit.screened_count = (visit.screened_count or 0) + 1

    # The commit §10.3 requires. Everything after this point can fail without
    # losing what the worker reported.
    db.commit()

    # ---- 5-7. score, deterioration, overrides ----------------------------
    previous_answers = (
        {
            a.question_code: a.answer_value
            for a in db.scalars(
                select(ScreeningAnswer).where(ScreeningAnswer.session_id == previous.id)
            ).all()
        }
        if previous
        else None
    )
    try:
        results = classify(
            instrument,
            Screening(
                answers=dict(request.answers),
                channel=request.channel.lower(),
                previous_answers=previous_answers,
            ),
        )
    except IncompleteScreeningError as exc:
        # §13.1: a partially answered instrument must never produce a tier.
        # The answers are already committed and stay committed -- rule 7, a
        # completed screening is never discarded -- so the error names the
        # session, because the caller must finish THAT session rather than
        # resubmit under the same idempotency key, which would only replay a
        # resultless session.
        raise IncompleteScreening(session.id, exc.missing) from exc

    # ---- 8. result rows, one per condition -------------------------------
    stored_results: list[ScreeningResult] = []
    for result in results:
        row = ScreeningResult(
            session_id=session.id,
            condition_code=result.condition,
            tier=result.tier,
            score=result.score,
            confidence=1.0,
            method=result.method,
            instrument_code=result.instrument_code,
            instrument_version=result.instrument_version,
            ruleset_version=session.ruleset_version,
            scored_tier=result.scored_tier,
            override_fired=1 if result.override_fired else 0,
            override_rule_codes=",".join(result.override_rule_codes) or None,
            deterioration_changed=1
            if (result.deterioration and result.deterioration.changed)
            else 0,
        )
        db.add(row)
        stored_results.append(row)
    db.flush()

    session.completed_at = _utcnow()

    # ---- 9. patient-facing text ------------------------------------------
    tier = primary_tier(results)
    messages, not_sent = _plan_messages(db, tier, person.language or "en")

    # ---- 10. referral for a tier that refers -----------------------------
    plans: list[ReferralPlan] = []
    for row, result in zip(stored_results, results):
        referral = referrals_v2.create_for_result(
            db, row, instrument, site_text=request.site_text
        )
        if referral is not None:
            plans.append(
                ReferralPlan(
                    referral_code=referral.referral_code,
                    condition=result.condition,
                    tier=result.tier,
                    facility=referral.hospital,
                    deadline=_iso(referral.deadline),
                )
            )

    db.commit()

    # ---- 11. return ------------------------------------------------------
    return Outcome(
        session_id=session.id,
        person_id=person.id,
        participant_code=person.participant_code,
        primary_tier=tier,
        results=tuple(results),
        instrument_code=instrument["code"],
        instrument_version=instrument["version"],
        replayed=False,
        longitudinal_linked=previous is not None,
        referrals=tuple(plans),
        messages=tuple(messages),
        not_sent_reason=not_sent
        or "no message was sent: the v2 pipeline does not send yet (item 1.6b "
        "for the words, the drop_v1 migration for a notifications row that can name "
        "a person)",
        started_at=_iso(session.started_at),
        completed_at=_iso(session.completed_at),
    )
