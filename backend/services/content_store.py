"""Load reviewed patient-facing content into the database, read it back, and
render a message for a person.

Master Reference v1.0 §8.4. **No runtime machine translation of anything a
worker reads or hears, and no model-generated free text on any patient-facing
surface.** Every string is human-authored, clinically reviewed, versioned, and
stored against a message code with one row per language. The reviewable source
is `content/messages/*.yaml`, validated by `content/schema.json` and
`scripts/validate_content.py`, approved on a pull request by the Clinical Lead
(§11.4); a data migration calls `load()` here to write the rows.

The round trip is the point, as it was for the instrument tables: `read()`
returns the dict shape of the file it came from, and a test asserts that both
forms agree. A column missing from these tables shows up as a failing test
rather than as a message a worker cannot read.

Three guarantees, each enforced here rather than left to review:

  **Only approved words reach a person.** `render()` serves `approved`
  messages only. The filler in `content/messages/example.yaml` is `draft`, so
  it is structurally unsendable in every environment -- the equivalent, for
  content, of the instrument loader refusing `status: example`. There is no
  `example` status in the content format, and approval gating is a better
  guard than one would be: it catches any unreviewed string, not just the
  ones that happen to live in an example file.

  **An approved version is immutable.** A change is a new version, because a
  consent text or a result message must be reproducible for any session that
  referenced it.

  **The character-set and budget checks run at load, not only in CI.** The CI
  gate only fires on a pull request that touches `content/`; this one fires on
  anything that tries to enter the database. A single character outside the
  GSM 03.38 seven-bit alphabet drops a segment from 160 characters to 70 and
  permanently multiplies the cost of every send containing it, invisibly. The
  arithmetic lives in `services/content_format.py`, which both this module and
  the CI gate import, so the two cannot disagree.

What this module does NOT do: translate, generate, truncate, or choose which
message to send. A string that does not fit its channel is rewritten by its
author, never truncated at runtime (§13.1).
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from db_models import Message, MessageText
from services.content_format import (
    CHANNEL_BUDGET,
    LANGUAGE_NAMES,
    LANGUAGES,
    LOOKALIKES,
    non_gsm7,
    placeholders_in,
    septets,
)

#: Statuses that, once stored, may not be overwritten.
FROZEN_STATUSES = {"approved", "retired"}
#: The only status whose text may be sent to, or displayed to, a person.
SENDABLE_STATUS = "approved"
#: Language of last resort. §8.4 forbids machine translation, so there is no
#: generated fallback: an absent language falls back to the authored English
#: and `render()` reports which language was actually used, so the fallback is
#: visible in the data rather than silent.
FALLBACK_LANGUAGE = "en"


class ContentLoadError(ValueError):
    """The content cannot be stored: an attempt to overwrite a frozen version,
    a string outside GSM-7, a string over its channel budget, a placeholder
    mismatch, or an approved message missing a language."""


class ContentNotFound(KeyError):
    """No such message code, or no such version."""


class ContentNotApproved(RuntimeError):
    """The message exists but has not been approved by the Clinical Lead, so
    it may not be sent to or displayed to a person. Raised rather than
    returning the draft: a worker reading unreviewed text is the failure this
    store exists to prevent."""


class PlaceholderError(ValueError):
    """The values supplied to `render()` do not match the message's declared
    substitution contract. Raised rather than sending a message containing a
    literal `{name}` to the people least able to query it."""


def _as_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    return datetime.fromisoformat(str(value))


def _budget(message: dict) -> int:
    override = message.get("max_len_override")
    if override:
        return int(override)
    return CHANNEL_BUDGET[message["channel"]]


def _check_text(message: dict, language: str, value: str, budget: int) -> int:
    """GSM-7 encodability and channel budget, in septets. Returns the cost."""
    code = message.get("code")
    offenders = non_gsm7(value)
    if offenders:
        detail = ", ".join(
            f"position {i} {ch!r}"
            + (f" (use {LOOKALIKES[ch]!r})" if ch in LOOKALIKES else "")
            for i, ch in offenders[:5]
        )
        raise ContentLoadError(
            f"{code} [{LANGUAGE_NAMES.get(language, language)}] contains "
            f"characters outside the GSM 03.38 seven-bit alphabet: {detail}. "
            "One such character drops a segment from 160 characters to 70 and "
            "multiplies the cost of every send containing it."
        )
    cost = septets(value)
    if cost > budget:
        raise ContentLoadError(
            f"{code} [{LANGUAGE_NAMES.get(language, language)}] is {cost} "
            f"septets against a {message['channel']} budget of {budget}. A "
            "string that does not fit is rewritten by its author, never "
            "truncated at runtime (§13.1)."
        )
    return cost


def load(db: Session, doc: dict, area: str | None = None) -> list[Message]:
    """Write a validated content file's messages into the tables.

    `doc` is the parsed YAML, already checked against `content/schema.json` by
    `scripts/validate_content.py`. This function enforces what a JSON Schema
    cannot: a frozen version is never overwritten, the character set and
    budget hold for every language, the placeholder contract is identical
    across languages, and an approved message has all three.
    """
    file_area = doc.get("area") or area
    stored: list[Message] = []

    for entry in doc.get("messages") or []:
        code = entry.get("code")
        version = int(entry.get("version", 1))
        status = entry.get("status")
        texts = entry.get("text") or {}
        declared = set(entry.get("placeholders") or [])
        budget = _budget(entry)

        if status == SENDABLE_STATUS:
            missing = [lang for lang in LANGUAGES if not texts.get(lang)]
            if missing:
                names = ", ".join(LANGUAGE_NAMES[lang] for lang in missing)
                raise ContentLoadError(
                    f"{code} v{version} is approved but has no {names} text. A "
                    "message is not usable until all three languages exist "
                    "(§8.4); Ndebele is not optional in this geography."
                )
            if not entry.get("approved_by") or not entry.get("approved_at"):
                raise ContentLoadError(
                    f"{code} v{version} is approved with no approver or date. "
                    "Every patient-facing string carries the Clinical Lead's "
                    "recorded approval (§11.4)."
                )

        existing = db.scalar(
            select(Message).where(Message.code == code, Message.version == version)
        )
        if existing is not None:
            if existing.status in FROZEN_STATUSES:
                raise ContentLoadError(
                    f"{code} v{version} is {existing.status} and immutable. A "
                    "change is a new version, never an edit: a consent text or "
                    "a result message must be reproducible for any session "
                    "that referenced it."
                )
            # A draft under review may be reloaded in place.
            for row in db.scalars(
                select(MessageText).where(MessageText.message_id == existing.id)
            ).all():
                db.delete(row)
            db.delete(existing)
            db.flush()

        comprehension = entry.get("comprehension_tested") or {}
        message = Message(
            code=code,
            version=version,
            channel=entry.get("channel"),
            status=status,
            purpose=entry.get("purpose"),
            placeholders=",".join(sorted(declared)) or None,
            max_len_override=entry.get("max_len_override"),
            approved_by=entry.get("approved_by"),
            approved_at=_as_date(entry.get("approved_at")),
            comprehension_tested_at=_as_date(comprehension.get("date")),
            comprehension_participants=comprehension.get("participants"),
            comprehension_outcome=comprehension.get("outcome"),
            area=file_area,
            notes=entry.get("notes"),
        )
        db.add(message)
        db.flush()

        for language in LANGUAGES:
            value = texts.get(language)
            if value is None:
                continue
            # Parity is checked from `review` onward, matching
            # scripts/validate_content.py exactly: a message is authored one
            # language at a time over weeks (English Week 8, Shona and
            # Ndebele Week 12), so a draft whose local-language entry is
            # still a "to be authored" marker must load. It must never reach
            # review or approval with a placeholder present in one language
            # and missing in another. The loader and the CI gate enforcing
            # different rules would be worse than either rule alone.
            used = placeholders_in(value)
            if status in ("review", SENDABLE_STATUS) and used != declared:
                raise ContentLoadError(
                    f"{code} [{LANGUAGE_NAMES[language]}] uses placeholders "
                    f"{sorted(used) or '[]'} against a declared contract of "
                    f"{sorted(declared) or '[]'}. A placeholder present in one "
                    "language and missing in another sends a broken message to "
                    "the people least able to query it."
                )
            cost = _check_text(entry, language, value, budget)
            db.add(
                MessageText(
                    message_id=message.id,
                    language=language,
                    text_value=value,
                    septets=cost,
                )
            )

        stored.append(message)

    db.flush()
    return stored


def _to_dict(db: Session, message: Message) -> dict:
    texts = {
        row.language: row.text_value
        for row in db.scalars(
            select(MessageText).where(MessageText.message_id == message.id)
        ).all()
    }
    out: dict = {
        "code": message.code,
        "version": message.version,
        "channel": message.channel,
        "status": message.status,
        "text": texts,
    }
    if message.purpose:
        out["purpose"] = message.purpose
    if message.placeholders:
        out["placeholders"] = sorted(message.placeholders.split(","))
    if message.max_len_override:
        out["max_len_override"] = message.max_len_override
    if message.approved_by:
        out["approved_by"] = message.approved_by
    if message.approved_at:
        out["approved_at"] = message.approved_at.date().isoformat()
    if message.comprehension_tested_at or message.comprehension_participants:
        tested: dict = {}
        if message.comprehension_tested_at:
            tested["date"] = message.comprehension_tested_at.date().isoformat()
        if message.comprehension_participants:
            tested["participants"] = message.comprehension_participants
        if message.comprehension_outcome:
            tested["outcome"] = message.comprehension_outcome
        out["comprehension_tested"] = tested
    if message.notes:
        out["notes"] = message.notes
    return out


def read(db: Session, code: str, version: int) -> dict:
    """One stored version, in the shape of the file it came from. The inverse
    of `load()`, and tested as a round trip."""
    message = db.scalar(
        select(Message).where(Message.code == code, Message.version == version)
    )
    if message is None:
        raise ContentNotFound(f"no message {code!r} version {version}")
    return _to_dict(db, message)


def read_active(db: Session, code: str) -> dict:
    """The highest approved version of a message -- the only version that may
    be sent."""
    message = db.scalar(
        select(Message)
        .where(Message.code == code, Message.status == SENDABLE_STATUS)
        .order_by(Message.version.desc())
        .limit(1)
    )
    if message is None:
        if db.scalar(select(Message).where(Message.code == code)) is None:
            raise ContentNotFound(f"no message {code!r}")
        raise ContentNotApproved(
            f"{code} exists but no version is approved. Every patient-facing "
            "string requires the Clinical Lead's recorded approval before it "
            "ships (§11.4)."
        )
    return _to_dict(db, message)


def catalogue(
    db: Session,
    language: str = FALLBACK_LANGUAGE,
    channel: str | None = None,
    since: datetime | None = None,
) -> list[dict]:
    """Every approved message in one language -- the snapshot a client caches
    so that the strings it shows offline are the reviewed ones.

    Offline is the normal case (§10.1): a handset with no connectivity must
    still show authored text, so the client holds a copy rather than fetching
    per screening. Approved versions are immutable, so `since` against the row
    creation time is a sound watermark: a change is a new row.
    """
    stmt = select(Message).where(Message.status == SENDABLE_STATUS)
    if channel is not None:
        stmt = stmt.where(Message.channel == channel)
    if since is not None:
        stmt = stmt.where(Message.created_at > since)

    #: Highest approved version per code.
    by_code: dict[str, Message] = {}
    for message in db.scalars(stmt.order_by(Message.code, Message.version)).all():
        by_code[message.code] = message

    out: list[dict] = []
    for code in sorted(by_code):
        message = by_code[code]
        row = db.scalar(
            select(MessageText).where(
                MessageText.message_id == message.id, MessageText.language == language
            )
        )
        used_language = language
        if row is None:
            row = db.scalar(
                select(MessageText).where(
                    MessageText.message_id == message.id,
                    MessageText.language == FALLBACK_LANGUAGE,
                )
            )
            used_language = FALLBACK_LANGUAGE
        if row is None:
            continue
        out.append(
            {
                "code": message.code,
                "version": message.version,
                "channel": message.channel,
                "language": used_language,
                "text": row.text_value,
                "placeholders": sorted(message.placeholders.split(","))
                if message.placeholders
                else [],
            }
        )
    return out


def render(
    db: Session,
    code: str,
    language: str = FALLBACK_LANGUAGE,
    values: dict[str, str] | None = None,
) -> dict:
    """The text to send, with placeholders substituted.

    Returns the string together with the version and language it actually
    came from, so a sender can record what a person was told and a fallback to
    English is visible in the data rather than silent.

    Raises ContentNotApproved for anything the Clinical Lead has not approved,
    and PlaceholderError when the supplied values do not match the declared
    contract exactly. Both refuse to send rather than sending something
    wrong -- a worker reading unreviewed or half-substituted text is the
    failure this store exists to prevent.
    """
    message = db.scalar(
        select(Message)
        .where(Message.code == code, Message.status == SENDABLE_STATUS)
        .order_by(Message.version.desc())
        .limit(1)
    )
    if message is None:
        if db.scalar(select(Message).where(Message.code == code)) is None:
            raise ContentNotFound(f"no message {code!r}")
        raise ContentNotApproved(
            f"{code} exists but no version is approved, so it may not be sent."
        )

    declared = set(message.placeholders.split(",")) if message.placeholders else set()
    supplied = set(values or {})
    if supplied != declared:
        raise PlaceholderError(
            f"{code} declares placeholders {sorted(declared) or '[]'} but was "
            f"given {sorted(supplied) or '[]'}. Refusing to send: an "
            "unsubstituted placeholder reaches a worker as literal braces."
        )

    row = db.scalar(
        select(MessageText).where(
            MessageText.message_id == message.id, MessageText.language == language
        )
    )
    used_language = language
    if row is None:
        row = db.scalar(
            select(MessageText).where(
                MessageText.message_id == message.id,
                MessageText.language == FALLBACK_LANGUAGE,
            )
        )
        used_language = FALLBACK_LANGUAGE
    if row is None:
        raise ContentNotFound(
            f"{code} v{message.version} has no text in {language!r} or "
            f"{FALLBACK_LANGUAGE!r}"
        )

    text_value = row.text_value
    for name, value in (values or {}).items():
        text_value = text_value.replace("{" + name + "}", str(value))

    leftover = placeholders_in(text_value)
    if leftover:
        raise PlaceholderError(
            f"{code} still contains {sorted(leftover)} after substitution."
        )

    # Cost and encodability of the FINAL string, reported rather than
    # enforced. A substituted value is the one part of a message its author
    # could not check: a worker named with a curly apostrophe, or a facility
    # name carrying an en-dash, drops the whole message from 160 characters
    # per segment to 70, and a long name can push an SMS past one segment.
    # Neither is a reason to send nothing -- rule 7, fail toward recording
    # and never toward silence -- so the sender gets the numbers and logs
    # them, and `content/EXCEPTIONS.md` records why this is the one place the
    # budget is observed instead of imposed.
    cost = septets(text_value)
    return {
        "code": message.code,
        "version": message.version,
        "language": used_language,
        "channel": message.channel,
        "text": text_value,
        "septets": cost if cost >= 0 else None,
        "gsm7": cost >= 0,
        "over_budget": cost < 0 or cost > _budget(
            {"channel": message.channel, "max_len_override": message.max_len_override}
        ),
    }
