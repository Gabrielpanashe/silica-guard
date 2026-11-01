"""Load a reviewed instrument specification into the database, and read it
back out in the shape the rules engine consumes.

Master Reference v1.0 §8.3. The instrument is versioned data, not code: the
reviewable source is `clinical/instruments/<CODE>-v<N>.yaml`, validated by
`clinical/instrument.schema.json` and approved on a pull request by the
Clinical Lead; a generated data migration calls `load()` here to write the
rows (§11.3, "the migration that loads each version").

The round trip is the point. `read()` returns exactly the dict shape
`services/rules_engine.py` already takes, so the engine neither knows nor
cares whether an instrument came from a file or from the database -- and a
test asserts that both paths classify a set of answer profiles identically.
That is what proves these tables model the format faithfully rather than
approximately.

Two guarantees, both from §8.3:

  **An approved version is immutable.** `load()` refuses to touch an
  instrument whose stored status is `approved` or `retired`. A change is a
  new version, because every screening result stores the version that
  produced it and a result whose rules were edited afterwards is
  uninterpretable.

  **A format illustration can never become an instrument.** `status:
  example` is refused outright, so the synthetic file in
  `clinical/examples/` cannot reach a database in any environment.
"""

from __future__ import annotations

import json
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from db_models import (
    AnswerBand,
    AnswerOption,
    Instrument,
    InstrumentBlock,
    InstrumentChannel,
    InstrumentCondition,
    InstrumentInterval,
    InstrumentQuestion,
    SafetyRule,
    ScoringRule,
    TierRule,
)

#: Statuses that may never be written to the database at all.
REFUSED_STATUSES = {"example"}
#: Statuses that, once stored, may not be overwritten.
FROZEN_STATUSES = {"approved", "retired"}


class InstrumentLoadError(ValueError):
    """The file cannot be loaded: refused status, or an attempt to overwrite
    a frozen version."""


def _as_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    return datetime.fromisoformat(str(value))


def _dumps(value):
    return None if value is None else json.dumps(value, sort_keys=True)


def _loads(value):
    return None if value in (None, "") else json.loads(value)


def load(db: Session, doc: dict) -> Instrument:
    """Write a validated instrument document into the tables.

    `doc` is the parsed YAML, already checked against
    `clinical/instrument.schema.json` by `scripts/validate_instrument.py`.
    This function enforces the two rules a schema cannot: a refused status
    never lands, and a frozen version is never overwritten.
    """
    code = doc.get("code")
    version = int(doc.get("version", 0))
    status = doc.get("status")

    if status in REFUSED_STATUSES:
        raise InstrumentLoadError(
            f"{code} v{version} has status {status!r} and may never be loaded. "
            "A format illustration is not an instrument -- see clinical/README.md."
        )

    existing = db.scalar(
        select(Instrument).where(Instrument.code == code, Instrument.version == version)
    )
    if existing is not None:
        if existing.status in FROZEN_STATUSES:
            raise InstrumentLoadError(
                f"{code} v{version} is {existing.status} and immutable. A clinical "
                "change is a new version, never an edit: every screening result "
                "stores the version that produced it, and a result whose rules "
                "were edited afterwards cannot be interpreted."
            )
        # A draft under review may be reloaded in place.
        _delete_children(db, existing)
        db.delete(existing)
        db.flush()

    instrument = Instrument(
        code=code,
        version=version,
        status=status,
        approved_by=doc.get("approved_by"),
        approved_at=_as_date(doc.get("approved_at")),
        supersedes=doc.get("supersedes"),
        unknown_score=int((doc.get("unknown_handling") or {}).get("unknown_score", 0)),
        refused_score=int((doc.get("unknown_handling") or {}).get("refused_score", 0)),
        partial_session_may_produce_tier=int(
            bool((doc.get("unknown_handling") or {}).get("partial_session_may_produce_tier", False))
        ),
        limitations=_dumps(doc.get("limitations") or []),
        notes=doc.get("notes"),
    )
    db.add(instrument)
    db.flush()

    for i, condition in enumerate(doc.get("conditions") or []):
        db.add(InstrumentCondition(instrument_id=instrument.id, condition_code=condition, ordinal=i))

    for i, block in enumerate(doc.get("blocks") or []):
        db.add(InstrumentBlock(
            instrument_id=instrument.id, code=block["code"],
            title_message_code=block["title_message_code"],
            ordinal=i, notes=block.get("notes"),
        ))

    for i, question in enumerate(doc.get("questions") or []):
        row = InstrumentQuestion(
            instrument_id=instrument.id,
            code=question["code"],
            block_code=question["block"],
            clinical_label=question["clinical_label"],
            response_type=question["response_type"],
            label_message_code=question["label_message_code"],
            ordinal=i,
            tracked_for_trajectory=int(bool(question.get("tracked_for_trajectory", False))),
            branching=_dumps(question.get("branching")),
            citation=question["citation"],
            notes=question.get("notes"),
        )
        db.add(row)
        db.flush()

        for j, option in enumerate(question.get("options") or []):
            db.add(AnswerOption(
                question_id=row.id, value=option["value"],
                label_message_code=option["label_message_code"], ordinal=j,
                is_unknown=int(bool(option.get("is_unknown", False))),
            ))
        for j, band in enumerate(question.get("bands") or []):
            db.add(AnswerBand(
                question_id=row.id, from_value=int(band["from"]), value=band["value"],
                label_message_code=band["label_message_code"], ordinal=j,
            ))
        for channel in question.get("channels") or []:
            db.add(InstrumentChannel(question_id=row.id, channel=channel))
        for score in question.get("scores") or []:
            db.add(ScoringRule(
                instrument_id=instrument.id, question_id=row.id,
                condition_code=score["condition"], answer_value=score["value"],
                score=int(score["score"]),
            ))

    for rule in doc.get("tier_rules") or []:
        db.add(TierRule(
            instrument_id=instrument.id, condition_code=rule["condition"],
            tier=rule["tier"], priority=int(rule.get("priority", 0)),
            predicate=_dumps(rule["predicate"]), label=rule.get("label"),
            citation=rule["citation"],
        ))

    for rule in doc.get("safety_rules") or []:
        db.add(SafetyRule(
            instrument_id=instrument.id, code=rule["code"],
            condition_code=rule.get("condition"), forces_tier=rule["forces_tier"],
            predicate=_dumps(rule["predicate"]), label=rule.get("label"),
            citation=rule["citation"],
        ))

    for interval in doc.get("intervals") or []:
        db.add(InstrumentInterval(
            instrument_id=instrument.id, condition_code=interval["condition"],
            tier=interval["tier"], rescreen_days=interval.get("rescreen_days"),
            referral_window_hours=interval.get("referral_window_hours"),
            citation=interval.get("citation"),
        ))

    db.flush()
    return instrument


def _delete_children(db: Session, instrument: Instrument) -> None:
    question_ids = [
        q.id for q in db.scalars(
            select(InstrumentQuestion).where(InstrumentQuestion.instrument_id == instrument.id)
        )
    ]
    for model in (AnswerOption, AnswerBand, InstrumentChannel):
        for row in db.scalars(select(model).where(model.question_id.in_(question_ids or [-1]))):
            db.delete(row)
    for model in (ScoringRule, TierRule, SafetyRule, InstrumentInterval,
                  InstrumentCondition, InstrumentBlock, InstrumentQuestion):
        for row in db.scalars(select(model).where(model.instrument_id == instrument.id)):
            db.delete(row)
    db.flush()


def read(db: Session, code: str, version: int) -> dict:
    """Read a stored instrument back into the dict shape the rules engine
    takes. The inverse of `load()`, and tested as a round trip."""
    instrument = db.scalar(
        select(Instrument).where(Instrument.code == code, Instrument.version == version)
    )
    if instrument is None:
        raise InstrumentLoadError(f"no instrument {code} v{version}")
    return _to_dict(db, instrument)


def read_active(db: Session, code: str) -> dict:
    """The highest approved version of an instrument -- what a screening
    session is stamped with."""
    instrument = db.scalar(
        select(Instrument)
        .where(Instrument.code == code, Instrument.status == "approved")
        .order_by(Instrument.version.desc())
        .limit(1)
    )
    if instrument is None:
        raise InstrumentLoadError(
            f"no approved version of {code}. An instrument must be approved by the "
            "Clinical Lead before it can classify anybody."
        )
    return _to_dict(db, instrument)


def _to_dict(db: Session, instrument: Instrument) -> dict:
    conditions = [
        r.condition_code for r in db.scalars(
            select(InstrumentCondition)
            .where(InstrumentCondition.instrument_id == instrument.id)
            .order_by(InstrumentCondition.ordinal)
        )
    ]
    blocks = [
        {"code": b.code, "title_message_code": b.title_message_code,
         **({"notes": b.notes} if b.notes else {})}
        for b in db.scalars(
            select(InstrumentBlock)
            .where(InstrumentBlock.instrument_id == instrument.id)
            .order_by(InstrumentBlock.ordinal)
        )
    ]

    questions = []
    for q in db.scalars(
        select(InstrumentQuestion)
        .where(InstrumentQuestion.instrument_id == instrument.id)
        .order_by(InstrumentQuestion.ordinal)
    ):
        entry: dict = {
            "code": q.code,
            "block": q.block_code,
            "clinical_label": q.clinical_label,
            "response_type": q.response_type,
            "label_message_code": q.label_message_code,
            "citation": q.citation,
        }
        options = [
            {"value": o.value, "label_message_code": o.label_message_code,
             **({"is_unknown": True} if o.is_unknown else {})}
            for o in db.scalars(
                select(AnswerOption).where(AnswerOption.question_id == q.id)
                .order_by(AnswerOption.ordinal)
            )
        ]
        if options:
            entry["options"] = options
        bands = [
            {"from": b.from_value, "value": b.value, "label_message_code": b.label_message_code}
            for b in db.scalars(
                select(AnswerBand).where(AnswerBand.question_id == q.id)
                .order_by(AnswerBand.ordinal)
            )
        ]
        if bands:
            entry["bands"] = bands
        channels = [
            c.channel for c in db.scalars(
                select(InstrumentChannel).where(InstrumentChannel.question_id == q.id)
                .order_by(InstrumentChannel.id)
            )
        ]
        if channels:
            entry["channels"] = channels
        scores = [
            {"condition": s.condition_code, "value": s.answer_value, "score": s.score}
            for s in db.scalars(
                select(ScoringRule).where(ScoringRule.question_id == q.id)
                .order_by(ScoringRule.id)
            )
        ]
        if scores:
            entry["scores"] = scores
        if q.tracked_for_trajectory:
            entry["tracked_for_trajectory"] = True
        if q.branching:
            entry["branching"] = _loads(q.branching)
        if q.notes:
            entry["notes"] = q.notes
        questions.append(entry)

    tier_rules = [
        {"condition": r.condition_code, "tier": r.tier, "priority": r.priority,
         "predicate": _loads(r.predicate), "citation": r.citation,
         **({"label": r.label} if r.label else {})}
        for r in db.scalars(
            select(TierRule).where(TierRule.instrument_id == instrument.id)
            .order_by(TierRule.id)
        )
    ]
    safety_rules = [
        {"code": r.code, "forces_tier": r.forces_tier, "predicate": _loads(r.predicate),
         "citation": r.citation,
         **({"condition": r.condition_code} if r.condition_code else {}),
         **({"label": r.label} if r.label else {})}
        for r in db.scalars(
            select(SafetyRule).where(SafetyRule.instrument_id == instrument.id)
            .order_by(SafetyRule.id)
        )
    ]
    intervals = [
        {"condition": i.condition_code, "tier": i.tier,
         "rescreen_days": i.rescreen_days,
         "referral_window_hours": i.referral_window_hours,
         **({"citation": i.citation} if i.citation else {})}
        for i in db.scalars(
            select(InstrumentInterval).where(InstrumentInterval.instrument_id == instrument.id)
            .order_by(InstrumentInterval.id)
        )
    ]

    doc: dict = {
        "code": instrument.code,
        "version": instrument.version,
        "status": instrument.status,
        "conditions": conditions,
        "blocks": blocks,
        "questions": questions,
        "tier_rules": tier_rules,
        "safety_rules": safety_rules,
        "intervals": intervals,
        "unknown_handling": {
            "unknown_score": instrument.unknown_score,
            "refused_score": instrument.refused_score,
            "partial_session_may_produce_tier": bool(instrument.partial_session_may_produce_tier),
        },
        "limitations": _loads(instrument.limitations) or [],
    }
    if instrument.approved_by:
        doc["approved_by"] = instrument.approved_by
    if instrument.approved_at:
        doc["approved_at"] = instrument.approved_at.date().isoformat()
    if instrument.supersedes:
        doc["supersedes"] = instrument.supersedes
    if instrument.notes:
        doc["notes"] = instrument.notes
    return doc
