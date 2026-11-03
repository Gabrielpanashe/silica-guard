"""The append-only audit trail.

Master Reference v1.0 §16.3: an "append-only audit of clinical reads and
writes, consent changes, merges, exports and administrative actions, retained
and reviewable", and "administrative access is not a licence to read records;
every read audited".

**Append-only means this module has no update and no delete.** Not "has them
but nobody calls them" -- there is no function here that can change or remove
a row, and a test asserts that by inspecting the module, because a log that
can be edited afterwards answers nothing. Enforced in the service layer rather
than by a database trigger, for the fourth time in this schema: triggers are
PostgreSQL-only and invisible to the SQLite unit suite (§16.2).

**A refusal is recorded as carefully as a success.** `allowed=False` rows are
the ones that matter: a role boundary nobody can show being enforced is a role
boundary nobody can show exists, and "has anyone tried to read outside their
district?" is a question an ethics committee and a data-protection regulator
both ask.

**An audit write must not be able to fail a clinical write.** `record()`
flushes rather than commits, so the audit row joins the caller's transaction
and a screening cannot be lost because a log row would not fit. The one
exception is `record_refusal()`, which commits its own session: a refused
request has no transaction of its own to join, and the whole point is that it
is recorded even though the request failed.

**No personal data in a log line** (`CLAUDE.md`). `details` holds codes,
counts and ids -- never a name, a telephone number or an answer. `person_id`
is an integer key, which is what makes "who has read this worker's record?"
answerable without the log itself becoming a second copy of the register.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from db_models import AuditLog
from services.authz import Principal

logger = logging.getLogger("silicaguard.audit")

#: Closed verb set, so the log can be queried rather than grepped. A new
#: action is added here deliberately; `record()` refuses an unknown one,
#: because an action nobody declared is an action nobody will think to audit.
ACTIONS = (
    "auth.login",
    "auth.login_failed",
    "person.resolve",
    "person.read",
    "person.merge",
    "person.unmerge",
    "person.match_decide",
    "consent.record",
    "consent.withdraw",
    "consent.read",
    "screening.submit",
    "screening.read",
    "referral.read",
    "referral.attend",
    "referral.close",
    "aggregate.read",
    "export.pseudonymised",
    "admin.user_create",
    "admin.user_deactivate",
    "admin.instrument_load",
    "admin.content_load",
)

#: Keys that must never appear in `details`. Checked rather than trusted,
#: because the rule is easy to agree with and easy to break in a hurry.
_FORBIDDEN_DETAIL_KEYS = frozenset({
    "name", "phone", "phone_number", "number", "national_id", "password",
    "answers", "text", "message", "email_address", "address",
})


class AuditError(ValueError):
    """An unknown action, or personal data in a log line."""


#: Longest `object_id` a caller may put in the log. The referral-code routes
#: are unauthenticated and record the code that was *attempted*, which means
#: an arbitrary string from the request path reaches this table. Codes are
#: seven characters; anything longer is truncated rather than stored, because
#: a log is not a place to find out how long a caller's input can be.
MAX_OBJECT_ID = 64


#: The caller of the four referral-code routes, which have no login: hospital
#: staff key a code into a page (§16.6, and `routers/referral_lookup.py`).
#:
#: A sentinel rather than `principal=None`, because the columns would then be
#: NULL and a NULL actor must mean one thing. Left as None it would be
#: indistinguishable from a route that forgot to pass its principal -- and
#: "who read this worker's record?" has to be answerable with "an
#: unauthenticated facility caller", not with silence. There is deliberately
#: no `users` row and no role in `authz.ROLES`: this principal holds no
#: capability and `require()` can never produce it.
#: The caller of `POST /api/v2/persons/resolve` and `POST /api/v2/screenings`:
#: a village health worker's handset, which never logs in, because a screening
#: must work in a gold-panning area with no dashboard session. Same reasoning
#: as `FACILITY_LOOKUP` below -- an unauthenticated clinical write has to be
#: attributable to *something*, and a NULL actor must mean one thing.
#:
#: These rows gain a real account at item 1.13's device credential, at which
#: point this sentinel stops appearing in new ones. The old rows keep it,
#: which is correct: they record what was true when they were written.
UNAUTHENTICATED_DEVICE = Principal(
    user_id=None,
    email="",
    role="device_unauthenticated",
    scope={},
    legacy=False,
)


FACILITY_LOOKUP = Principal(
    user_id=None,
    email="",
    role="facility_lookup_unauthenticated",
    scope={},
    legacy=False,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_request_id() -> str:
    """Correlates every row written by one HTTP request."""
    return uuid.uuid4().hex[:16]


def _check_details(details: dict | None) -> str | None:
    if not details:
        return None
    offending = _FORBIDDEN_DETAIL_KEYS & {str(k).lower() for k in details}
    if offending:
        raise AuditError(
            f"details may not contain {sorted(offending)}: no personal data in "
            "a log line (CLAUDE.md). Record an id, a code or a count instead — "
            "the log must not become a second copy of the register."
        )
    return json.dumps(details, sort_keys=True, default=str)


def record(
    db: Session,
    principal: Principal | None,
    action: str,
    *,
    object_type: str | None = None,
    object_id: str | int | None = None,
    person_id: int | None = None,
    allowed: bool = True,
    request_id: str | None = None,
    details: dict | None = None,
) -> AuditLog:
    """Write one row into the caller's transaction.

    Flushes rather than commits, so a clinical write and its audit row stand
    or fall together and a screening can never be lost because a log row would
    not fit.
    """
    if action not in ACTIONS:
        raise AuditError(
            f"unknown audit action {action!r}; expected one of {ACTIONS}. The "
            "set is closed because an action nobody declared is an action "
            "nobody will think to audit."
        )

    row = AuditLog(
        actor_user_id=principal.user_id if principal else None,
        actor_email=principal.email if principal else None,
        actor_role=principal.role if principal else None,
        action=action,
        object_type=object_type,
        object_id=str(object_id)[:MAX_OBJECT_ID] if object_id is not None else None,
        person_id=person_id,
        at=_utcnow(),
        request_id=request_id or new_request_id(),
        allowed=1 if allowed else 0,
        details=_check_details(details),
    )
    db.add(row)
    db.flush()
    return row


def record_best_effort(db: Session, *args, **kwargs) -> None:
    """Write a row on the caller's session, and swallow a failure.

    For the one case where the clinical record is already committed and the
    audit row is not: `POST /api/v2/screenings` commits the answers and then
    the results, so by the time this is called the screening exists. §10.3 --
    "a completed screening is never discarded" -- then settles the question:
    the worker must get the tier he was screened for, and losing the log line
    is strictly better than losing the screening or telling a handset that a
    stored screening failed.

    The failure is logged at ERROR rather than passed over in silence, because
    a system that stops auditing screenings has to be noticed. This is NOT the
    pattern for a read: there, refusing the request is right, since an
    unaudited read of an identified record is what §16.3 forbids and nothing
    is lost by refusing it.
    """
    try:
        record(db, *args, **kwargs)
        db.commit()
    except Exception:  # noqa: BLE001 - see the docstring
        db.rollback()
        logger.exception(
            "AUDIT WRITE FAILED for an already-committed clinical record. The "
            "record stands; the log line is missing. §16.3 expects every "
            "clinical write to be audited, so this needs investigating rather "
            "than retrying."
        )


def record_refusal(
    principal: Principal | None,
    action: str,
    *,
    object_type: str | None = None,
    object_id: str | int | None = None,
    person_id: int | None = None,
    request_id: str | None = None,
    details: dict | None = None,
) -> None:
    """Record a refused access on its own session.

    A refused request has no transaction of its own to join, and the point is
    that it is recorded *even though* the request failed — so this cannot use
    the request's session, which is about to be rolled back. Never raises: a
    failure to log a refusal must not turn a clean 403 into a 500, so the row
    is best-effort and the refusal itself still reaches the caller.
    """
    from database import get_fresh_session

    session = None
    try:
        session = get_fresh_session()
        record(
            session,
            principal,
            action,
            object_type=object_type,
            object_id=object_id,
            person_id=person_id,
            allowed=False,
            request_id=request_id,
            details=details,
        )
        session.commit()
    except Exception:  # noqa: BLE001 - see the docstring
        if session is not None:
            session.rollback()
    finally:
        if session is not None:
            session.close()


# ───────────────────────────────────────────────────────────── reading it

def for_person(db: Session, person_id: int, limit: int = 200) -> list[AuditLog]:
    """Every access to one person's record, newest first.

    "Who has read my record?" is a question a worker is entitled to an answer
    to, and §16.3's audit exists so that the answer is not "we cannot tell".
    """
    return list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.person_id == person_id)
            .order_by(AuditLog.at.desc(), AuditLog.id.desc())
            .limit(limit)
        ).all()
    )


def refusals(db: Session, limit: int = 200) -> list[AuditLog]:
    """Every refused access, newest first — the rows that show the boundary
    being enforced rather than merely declared."""
    return list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.allowed == 0)
            .order_by(AuditLog.at.desc(), AuditLog.id.desc())
            .limit(limit)
        ).all()
    )


def for_request(db: Session, request_id: str) -> list[AuditLog]:
    return list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.request_id == request_id)
            .order_by(AuditLog.id)
        ).all()
    )
