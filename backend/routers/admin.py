"""User management and the audit trail, over HTTP.

Master Reference v1.0 §16.3, §16.6.

Everything here needs `admin.manage`, except the per-person audit read, which
needs `person.read` — a village health worker checking who has touched a record
they are responsible for is not an administrative act.

**Creating the first user retires the prototype accounts.** That is the one
side effect worth knowing about: `POST /api/v2/users` is how the two
environment-variable credentials stop working, because `authz.any_user_exists`
gates them. It is not a flag to remember — a flag nobody turns off is how a
prototype credential reaches production.

**Administrative access is not a licence to read records** (§16.3). The
administrator role here has `admin.manage`, `person.merge` and
`aggregate.read` — and deliberately **not** `person.read` or
`screening.read`. An administrator who needs to see a worker's record has to
be given a clinical role as well, which is a decision somebody makes rather
than a capability that arrives with the job.
"""

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import format_datetime, get_db
from db_models import AuditLog, User
from models_v2 import AuditEntryOut, RoleOut, UserCreateIn, UserOut
from routers.auth import request_id, require
from services import audit, authz
from services.authz import AuthzError, Principal

router = APIRouter(prefix="/api/v2", tags=["admin"])


def _user_out(user: User) -> UserOut:
    return UserOut(
        user_id=user.id,
        email=user.email,
        role=user.role,
        name=user.name,
        scope=authz._scope_for(user),
        active=bool(user.active),
        created_at=format_datetime(user.created_at),
        last_login_at=format_datetime(user.last_login_at),
    )


def _entry_out(row: AuditLog) -> AuditEntryOut:
    details = None
    if row.details:
        try:
            details = json.loads(row.details)
        except ValueError:
            details = None
    return AuditEntryOut(
        entry_id=row.id,
        actor_email=row.actor_email,
        actor_role=row.actor_role,
        action=row.action,
        object_type=row.object_type,
        object_id=row.object_id,
        person_id=row.person_id,
        at=format_datetime(row.at),
        request_id=row.request_id,
        allowed=bool(row.allowed),
        details=details,
    )


@router.get("/roles", response_model=list[RoleOut])
def list_roles():
    """The roles, their capabilities, and what each may **not** see.

    Unauthenticated: it describes the model rather than any data, and a
    reviewer or an ethics committee reading what a role is refused should not
    need an account to do it.
    """
    return [
        RoleOut(
            code=r.code,
            label=r.label,
            capabilities=sorted(r.capabilities),
            scope_field=r.scope_field,
            cannot=r.cannot,
            prototype=r.code in authz.LEGACY_ROLES,
        )
        for r in authz.ROLES
    ]


@router.post("/users", response_model=UserOut)
def create_user(
    payload: UserCreateIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("admin.manage")),
    rid: str = Depends(request_id),
):
    """Create a user.

    **The first call retires the two prototype accounts**, because they
    authenticate only while the `users` table is empty.
    """
    try:
        user = authz.create_user(
            db,
            payload.email,
            payload.password,
            payload.role,
            name=payload.name,
            facility_id=payload.facility_id,
            site_ids=payload.site_ids,
            district=payload.district,
            programme_id=payload.programme_id,
        )
    except AuthzError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))

    audit.record(
        db, principal, "admin.user_create", object_type="user",
        object_id=user.id, request_id=rid,
        details={"role": user.role, "scoped": bool(authz._scope_for(user))},
    )
    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.get("/users", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("admin.manage")),
):
    return [
        _user_out(u)
        for u in db.scalars(select(User).order_by(User.email)).all()
    ]


@router.delete("/users/{user_id}", response_model=UserOut)
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("admin.manage")),
    rid: str = Depends(request_id),
):
    """Deactivate, never delete.

    An audit row names a user id, and a deleted user makes every row
    referencing it unreadable — which would let somebody erase their own
    trail by removing their account.
    """
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="No such user")
    if principal.user_id == user_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "You cannot deactivate your own account. With one "
                "administrator that would lock the system out of user "
                "management entirely."
            ),
        )
    user.active = 0
    audit.record(db, principal, "admin.user_deactivate", object_type="user",
                 object_id=user_id, request_id=rid)
    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.get("/audit/persons/{person_id}", response_model=list[AuditEntryOut])
def audit_for_person(
    person_id: int,
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("person.read")),
    rid: str = Depends(request_id),
):
    """Every access to one person's record.

    "Who has read my record?" is a question a worker is entitled to an answer
    to, and §16.3's audit exists so the answer is not "we cannot tell".

    Reading the trail is itself audited. That is not circular pedantry: an
    audit log nobody's reads are recorded in is a log that can be mined
    quietly.
    """
    entries = audit.for_person(db, person_id, limit=limit)
    audit.record(db, principal, "person.read", object_type="audit_log",
                 person_id=person_id, request_id=rid,
                 details={"entries": len(entries)})
    db.commit()
    return [_entry_out(e) for e in entries]


@router.get("/audit/refusals", response_model=list[AuditEntryOut])
def audit_refusals(
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("admin.manage")),
):
    """Every refused access, newest first.

    The rows that show the boundary being enforced rather than merely
    declared — and the first place to look after any suspicion of
    credential sharing.
    """
    return [_entry_out(e) for e in audit.refusals(db, limit=limit)]
