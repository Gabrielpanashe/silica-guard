"""Layered consent, recorded as data.

Master Reference v1.0 §8.5 and §14.2. The fifth and last irreversible
decision. **Consent cannot be applied retrospectively**, which is why it is a
schema decision rather than a feature: a record created before consent existed
can never be brought inside it, and an ethics committee will ask what the
person was shown and when.

Six permissions, never bundled into one agreement (§14.2). The separation is
the point: a worker may accept screening and decline retention, or accept
everything except unsolicited education messages, and each of those is a
different row rather than a different interpretation of one tick box.

Three rules hold the whole module together:

  **Absence is never consent.** `granted()` returns False for a permission
  nobody recorded. There is no default, no implied grant from a related
  permission, and no inheritance from a programme -- an employer-funded
  cohort does not consent on a worker's behalf (§14.4).

  **A consent record must say what the person was shown.** `consent_text_id`
  is required. A row saying "agreed" with no wording attached is not
  evidence, and the wording is versioned content in the store like every
  other patient-facing string (§8.4), so one review and translation pipeline
  covers it. The practical consequence is that consent capture does not work
  until the Clinical Lead has approved a consent text -- which is correct
  sequencing, not a gap.

  **A withdrawal is recorded, never a deletion.** The original row is kept and
  stamped, because §14.3 requires the retention and withdrawal mechanism to be
  demonstrable. "Granted, then withdrawn on this date" is a different story
  from "never granted", and only one of them can be shown to a committee.

What this module does NOT do: decide what a worker is told, send anything, or
infer a permission from behaviour. It records decisions and answers questions
about them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from db_models import ConsentRecord, ConsentText, Message, Person


@dataclass(frozen=True)
class Permission:
    code: str
    scope: str
    #: Without this one there is no service at all.
    required_to_screen: bool = False
    #: Not available in phase one. §14.4's boundary, built before any
    #: commercial pressure exists to blur it.
    future_phase: bool = False


#: §14.2, in the master document's own order. A seventh permission is a row
#: here plus a migration, never a reinterpretation of an existing one.
PERMISSIONS: tuple[Permission, ...] = (
    Permission(
        "screening_and_referral",
        "Screening, tier assignment, referral to a facility, and the messages "
        "required to deliver that.",
        required_to_screen=True,
    ),
    Permission(
        "longitudinal_record",
        "Retention of the record for comparison at future screenings. "
        "Separable: a worker may accept screening and decline retention.",
    ),
    Permission(
        "contact_by_message",
        "Result messages, reminders and escalation. Required for referral "
        "follow-through, and distinct from education broadcast.",
    ),
    Permission(
        "education_broadcast",
        "Unsolicited health education messaging. Separate, with a working and "
        "permanent opt-out.",
    ),
    Permission(
        "research_and_statistics",
        "De-identified data for validation, research and aggregate national "
        "reporting. Refusable without losing the service.",
    ),
    Permission(
        "employer_disclosure",
        "Any disclosure of individual results to an employer or programme "
        "sponsor. Separate, specific and refusable. Never bundled.",
        future_phase=True,
    ),
)

BY_CODE = {p.code: p for p in PERMISSIONS}
#: The one permission without which there is no service (§14.2).
REQUIRED_TO_SCREEN = tuple(p.code for p in PERMISSIONS if p.required_to_screen)
#: Not grantable in phase one, through any path.
FUTURE_PHASE = tuple(p.code for p in PERMISSIONS if p.future_phase)

#: Channels a decision can be recorded through. USSD consent is a short
#: statement in spoken register followed by an explicit keypress (§14.2).
CHANNELS = ("APP", "USSD", "PAPER")


class ConsentError(ValueError):
    """The decision cannot be recorded: an unknown permission, a missing
    consent text, a future-phase permission, or an unknown person."""


class ConsentMissing(PermissionError):
    """An operation needs a permission the person has not granted. Raised
    rather than proceeding: proceeding is the thing consent exists to
    prevent."""

    def __init__(self, person_id: int, permission: str):
        self.person_id = person_id
        self.permission = permission
        super().__init__(
            f"person {person_id} has not granted {permission!r}. "
            f"{BY_CODE[permission].scope if permission in BY_CODE else ''}"
        )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ------------------------------------------------------------ consent texts

def register_text(
    db: Session,
    code: str,
    message_code: str,
    *,
    version: int = 1,
    status: str = "draft",
    approved_by: str | None = None,
    approved_at: datetime | None = None,
) -> ConsentText:
    """Bind a consent text version to a message code in the content store.

    The wording itself is never stored here. It lives in `messages` /
    `message_texts`, so consent text goes through the same review, the same
    three languages, the same GSM-7 and budget checks and the same approval
    trail as every other patient-facing string (§8.4). This table records
    *which* version of *which* message was the consent text, because §14.2
    requires a consent record to name the version displayed.
    """
    if not db.scalar(select(Message.id).where(Message.code == message_code)):
        raise ConsentError(
            f"consent text {code!r} points at message {message_code!r}, which "
            "is not in the content store. The wording is authored and approved "
            "there first (§8.4) -- a consent text that is not reviewable "
            "content is not a consent text."
        )
    existing = db.scalar(
        select(ConsentText).where(ConsentText.code == code, ConsentText.version == version)
    )
    if existing is not None:
        if existing.status in ("approved", "retired"):
            raise ConsentError(
                f"consent text {code!r} v{version} is {existing.status} and "
                "immutable. Consent records reference it, so a change is a new "
                "version -- otherwise a record cannot say what was shown."
            )
        db.delete(existing)
        db.flush()

    text = ConsentText(
        code=code,
        version=version,
        message_code=message_code,
        status=status,
        approved_by=approved_by,
        approved_at=approved_at,
    )
    db.add(text)
    db.flush()
    return text


def active_text(db: Session, code: str) -> ConsentText:
    """The highest approved version of a consent text -- the only version that
    may be shown to anybody."""
    text = db.scalar(
        select(ConsentText)
        .where(ConsentText.code == code, ConsentText.status == "approved")
        .order_by(ConsentText.version.desc())
        .limit(1)
    )
    if text is None:
        if db.scalar(select(ConsentText.id).where(ConsentText.code == code)) is None:
            raise ConsentError(f"no consent text {code!r}")
        raise ConsentError(
            f"consent text {code!r} exists but no version is approved. The "
            "Clinical Lead approves the wording before anybody is asked to "
            "agree to it (§11.4)."
        )
    return text


# -------------------------------------------------------------- recording

def record(
    db: Session,
    person_id: int,
    permission: str,
    granted_value: bool,
    *,
    consent_text_id: int,
    channel: str = "APP",
    session_id: int | None = None,
    recorded_by: str | None = None,
) -> ConsentRecord:
    """Record one decision.

    A refusal is recorded as deliberately as a grant: "asked and declined" is
    the answer an ethics committee wants, and it also stops the same question
    being asked at every visit.
    """
    if permission not in BY_CODE:
        raise ConsentError(
            f"unknown permission {permission!r}; expected one of "
            f"{tuple(BY_CODE)}. The set is closed because a seventh permission "
            "is a schema change and a governance decision, not a new string."
        )
    if permission in FUTURE_PHASE and granted_value:
        raise ConsentError(
            f"{permission!r} is future-phase and cannot be granted in phase "
            "one (§14.4). An employer or programme sponsor never receives "
            "individual results, and the path to change that does not exist "
            "yet -- so a grant recorded now would be a promise nothing honours."
        )
    if channel not in CHANNELS:
        raise ConsentError(f"channel must be one of {CHANNELS}, not {channel!r}")
    if db.get(Person, person_id) is None:
        raise ConsentError(f"no person {person_id}")

    text = db.get(ConsentText, consent_text_id)
    if text is None:
        raise ConsentError(
            f"no consent text {consent_text_id}. A consent record must name "
            "the version of the wording the person was shown (§14.2); a row "
            "saying 'agreed' with nothing attached is not evidence."
        )
    if text.status != "approved":
        raise ConsentError(
            f"consent text {text.code!r} v{text.version} is {text.status!r}, "
            "not approved. Nobody is asked to agree to unapproved wording."
        )

    row = ConsentRecord(
        person_id=person_id,
        permission=permission,
        granted=1 if granted_value else 0,
        consent_text_id=consent_text_id,
        channel=channel,
        session_id=session_id,
        recorded_by=recorded_by,
    )
    db.add(row)
    db.flush()
    return row


def record_many(
    db: Session,
    person_id: int,
    decisions: dict[str, bool],
    *,
    consent_text_id: int,
    channel: str = "APP",
    session_id: int | None = None,
    recorded_by: str | None = None,
) -> list[ConsentRecord]:
    """A whole consent screen in one call, validated before anything is
    written.

    All-or-nothing on purpose: a half-recorded consent screen is worse than a
    failed one, because the missing permissions are indistinguishable from
    refusals afterwards.
    """
    for permission, value in decisions.items():
        if permission not in BY_CODE:
            raise ConsentError(f"unknown permission {permission!r}")
        if permission in FUTURE_PHASE and value:
            raise ConsentError(f"{permission!r} is future-phase and cannot be granted")

    return [
        record(
            db,
            person_id,
            permission,
            value,
            consent_text_id=consent_text_id,
            channel=channel,
            session_id=session_id,
            recorded_by=recorded_by,
        )
        for permission, value in decisions.items()
    ]


def withdraw(
    db: Session, person_id: int, permission: str, *, withdrawn_by: str | None = None
) -> ConsentRecord | None:
    """Withdraw a standing grant.

    The original row is kept and stamped rather than deleted or edited: §14.3
    requires the withdrawal mechanism to be demonstrable, and "granted, then
    withdrawn on this date" is a different story from "never granted".

    Returns None when there was nothing standing to withdraw, which is not an
    error -- a worker opting out of something they never opted into should not
    get a failure.
    """
    if permission not in BY_CODE:
        raise ConsentError(f"unknown permission {permission!r}")

    row = _standing(db, person_id, permission)
    if row is None:
        return None
    row.withdrawn_at = _utcnow()
    if withdrawn_by:
        row.recorded_by = f"{row.recorded_by or ''} (withdrawn by {withdrawn_by})".strip()
    db.flush()
    return row


# --------------------------------------------------------------- answering

def _standing(db: Session, person_id: int, permission: str) -> ConsentRecord | None:
    """The most recent record for a permission that has not been withdrawn."""
    return db.scalar(
        select(ConsentRecord)
        .where(
            ConsentRecord.person_id == person_id,
            ConsentRecord.permission == permission,
            ConsentRecord.withdrawn_at.is_(None),
        )
        .order_by(ConsentRecord.recorded_at.desc(), ConsentRecord.id.desc())
        .limit(1)
    )


def granted(db: Session, person_id: int, permission: str) -> bool:
    """Whether a permission is standing. **False for anything nobody
    recorded**: absence is never consent, and there is no inheritance from a
    related permission or from a programme."""
    if permission not in BY_CODE:
        raise ConsentError(f"unknown permission {permission!r}")
    row = _standing(db, person_id, permission)
    return bool(row and row.granted)


def require(db: Session, person_id: int, permission: str) -> None:
    """Raise ConsentMissing unless the permission is standing."""
    if not granted(db, person_id, permission):
        raise ConsentMissing(person_id, permission)


def may_screen(db: Session, person_id: int) -> None:
    """§14.2: without the core permission there is no service."""
    for permission in REQUIRED_TO_SCREEN:
        require(db, person_id, permission)


def may_keep_longitudinal_record(db: Session, person_id: int) -> bool:
    """Whether this person's sessions may be linked to each other.

    The one place the §14.2 separation bites in code: a worker may accept
    screening and decline retention, and a declined retention means a session
    is recorded with **no `previous_session_id`** and no deterioration
    comparison. The screening still happens and the result is still real; it
    simply has no history attached.
    """
    return granted(db, person_id, "longitudinal_record")


def may_contact(db: Session, person_id: int) -> bool:
    """Result messages, reminders, escalation."""
    return granted(db, person_id, "contact_by_message")


def may_broadcast(db: Session, person_id: int) -> bool:
    """Unsolicited health education. Separate from `may_contact` precisely so
    that a worker who wants his results can refuse the newsletter."""
    return granted(db, person_id, "education_broadcast")


def may_use_for_research(db: Session, person_id: int) -> bool:
    return granted(db, person_id, "research_and_statistics")


def may_disclose_to_employer(db: Session, person_id: int) -> bool:
    """§14.4, the most consequential governance rule in the document.

    Always False in phase one, because `record()` refuses to grant the
    permission at all. Written as a real lookup rather than a hardcoded
    `False` so that the day the formal-sector module exists, the boundary is
    already a per-person permission check in the code path rather than a
    policy somebody has to remember to implement.
    """
    return granted(db, person_id, "employer_disclosure")


def history(db: Session, person_id: int) -> list[ConsentRecord]:
    """Every decision ever recorded for a person, oldest first -- what a
    worker, an auditor or an ethics committee is entitled to see."""
    return list(
        db.scalars(
            select(ConsentRecord)
            .where(ConsentRecord.person_id == person_id)
            .order_by(ConsentRecord.recorded_at, ConsentRecord.id)
        ).all()
    )


def summary(db: Session, person_id: int) -> dict[str, bool]:
    """The standing position on all six permissions, including the ones never
    asked about -- which read as False, because absence is never consent."""
    return {p.code: granted(db, person_id, p.code) for p in PERMISSIONS}
