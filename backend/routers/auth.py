"""Authentication, and the dependency every protected route uses.

Master Reference v1.0 §16.3, §16.6.

**The two environment-variable accounts are self-disarming.** They work only
while the `users` table is empty; the moment a real user exists they stop
authenticating. That is deliberately not a feature flag: a flag nobody turns
off is exactly how a prototype credential reaches production, and "we will
remove the fallback later" is a sentence no audit accepts. Creating the first
administrator is what retires them.

**Passwords are hashed** with `hashlib.scrypt` and a per-user salt
(`services/authz.py`). The prototype accounts compared plaintext from an
environment variable, in constant-unsafe `!=`, which is the other reason they
need an end date.

**`SECRET_KEY` no longer falls back to `"dev-secret"`.** That default meant a
production instance missing the variable signed tokens with a value published
in this repository's history — anyone could mint an administrator token. It
now raises on first use, loudly, at the point of signing.

Three dependencies, in increasing strictness:

  `get_current_user`   a valid token. What the v1 dashboard routes use today.
  `current_principal`  the token resolved against the `users` row, with scope.
  `require(capability)` the principal, refused unless the role allows it —
                       and the refusal is written to the audit log, because a
                       boundary nobody can show being enforced is a boundary
                       nobody can show exists.
"""

import hmac
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from db_models import User
from models import LoginRequest, LoginResponse
from services import audit, authz

router = APIRouter(prefix="/api", tags=["auth"])

ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 12

_bearer_scheme = HTTPBearer()


def _signing_key() -> str:
    """No default, deliberately.

    This used to be `os.getenv("SECRET_KEY", "dev-secret")`. A production
    instance missing the variable would sign tokens with a value published in
    this repository, which means anyone could mint an administrator token. A
    loud failure at signing time is the only safe behaviour; `.env.example`
    and `tests/conftest.py` both supply a value.
    """
    key = os.getenv("SECRET_KEY")
    if not key:
        raise HTTPException(
            status_code=503,
            detail=(
                "SECRET_KEY is not configured on this server, so no token can "
                "be issued or verified. There is deliberately no default: a "
                "published fallback would let anyone mint a token."
            ),
        )
    return key


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> dict:
    """The token's claims. Used by the v1 dashboard routes, which have no
    scoping of their own yet — they are replaced by the adapter (item 1.11).

    Screening and the hospital lookup stay unauthenticated on purpose: the
    VHW application never logs in and facility staff have no account.
    """
    try:
        payload = jwt.decode(
            credentials.credentials, _signing_key(), algorithms=[ALGORITHM]
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


def current_principal(
    user: dict = Depends(get_current_user), db: Session = Depends(get_db)
) -> authz.Principal:
    """The token resolved against the `users` row, with its scope.

    A token for a user who has since been deactivated is refused here rather
    than at the capability check, because a deactivated account should stop
    working immediately and a twelve-hour token would otherwise outlive it.
    """
    email = (user.get("sub") or "").lower()
    row = db.scalar(select(User).where(User.email == email))
    if row is not None:
        if not row.active:
            raise HTTPException(status_code=401, detail="This account is deactivated")
        return authz.principal_for(row)

    # A prototype account's token. Valid only while no real user exists.
    if authz.any_user_exists(db):
        raise HTTPException(
            status_code=401,
            detail=(
                "This token belongs to a prototype account, which stopped "
                "working when the first real user was created. Sign in again."
            ),
        )
    return authz.legacy_principal(email, user.get("role") or "hospital")


def request_id(request: Request) -> str:
    """One id per HTTP request, so the audit rows it writes correlate.

    Honours an inbound `X-Request-Id` where a client sends one, which is what
    makes a mobile synchronisation traceable from the handset's own log.
    """
    supplied = request.headers.get("X-Request-Id")
    return (supplied or audit.new_request_id())[:64]


def require(capability: str):
    """A dependency that refuses unless the role allows the capability — and
    **writes the refusal to the audit log**.

    The refusal row is the one §16.3 is really about. A role model whose
    boundaries are never observed being enforced is indistinguishable, to an
    auditor, from a role model that does not work.
    """

    def dependency(
        principal: authz.Principal = Depends(current_principal),
        rid: str = Depends(request_id),
    ) -> authz.Principal:
        if not principal.allows(capability):
            audit.record_refusal(
                principal,
                _ACTION_FOR_CAPABILITY.get(capability, "aggregate.read"),
                object_type="capability",
                object_id=capability,
                request_id=rid,
                details={"role": principal.role, "capability": capability},
            )
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Role {principal.role!r} may not {capability}. "
                    + (authz.BY_CODE[principal.role].cannot
                       if principal.role in authz.BY_CODE else "")
                ).strip(),
            )
        return principal

    return dependency


#: Which audit verb records a refusal of each capability. Kept beside the
#: dependency rather than guessed, so a refusal is filed under the action the
#: caller was attempting.
_ACTION_FOR_CAPABILITY = {
    "person.read": "person.read",
    "person.resolve": "person.resolve",
    "person.merge": "person.merge",
    "consent.write": "consent.record",
    "consent.read": "consent.read",
    "screening.write": "screening.submit",
    "screening.read": "screening.read",
    "referral.read": "referral.read",
    "referral.close": "referral.close",
    "aggregate.read": "aggregate.read",
    "export.pseudonymised": "export.pseudonymised",
    "admin.manage": "admin.user_create",
}


def _prototype_accounts() -> dict:
    return {
        os.getenv("HOSPITAL_EMAIL", "hospital@silicaguard.health"): {
            "password": os.getenv("HOSPITAL_PASSWORD", "change-me"),
            "role": "hospital",
        },
        os.getenv("CIMAS_EMAIL", "cimas@silicaguard.health"): {
            "password": os.getenv("CIMAS_PASSWORD", "change-me"),
            "role": "cimas",
        },
    }


@router.post("/auth/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
    rid: str = Depends(request_id),
):
    """Sign in against the `users` table, falling back to the prototype
    accounts **only while no real user exists**.

    A failed attempt is audited too. Credential stuffing against an
    unprotected login is invisible otherwise, and §15.4 already records that
    this surface has no rate limiting or lockout (item 1.13's remaining half).
    """
    user = authz.authenticate(db, payload.email, payload.password)
    if user is not None:
        user.last_login_at = datetime.now(timezone.utc).replace(tzinfo=None)
        principal = authz.principal_for(user)
        audit.record(db, principal, "auth.login", object_type="user",
                     object_id=user.id, request_id=rid)
        db.commit()
        return LoginResponse(access_token=_issue(user.email, user.role), role=user.role)

    if not authz.any_user_exists(db):
        account = _prototype_accounts().get(payload.email)
        if account is not None and _constant_equals(account["password"], payload.password):
            principal = authz.legacy_principal(payload.email, account["role"])
            audit.record(db, principal, "auth.login", object_type="user",
                         request_id=rid, details={"prototype_account": True})
            db.commit()
            return LoginResponse(
                access_token=_issue(payload.email, account["role"]),
                role=account["role"],
            )

    audit.record_refusal(
        None, "auth.login_failed", object_type="email", request_id=rid,
        details={"users_exist": authz.any_user_exists(db)},
    )
    raise HTTPException(status_code=401, detail="Invalid credentials")


def _constant_equals(expected: str, supplied: str) -> bool:
    return hmac.compare_digest((expected or "").encode(), (supplied or "").encode())


def _issue(email: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    return jwt.encode(
        {"sub": email.lower(), "role": role, "exp": expire},
        _signing_key(),
        algorithm=ALGORITHM,
    )


@router.get("/auth/me")
def read_current_user(principal: authz.Principal = Depends(current_principal)):
    """Who the token belongs to, what the role may do, and what it may not.

    The `cannot` line comes from §16.3's own "cannot see" column. Serving it
    means a client renders the boundary from the server's definition rather
    than from a copy, and a reviewer can read what a role is refused without
    reading the code.
    """
    role = authz.BY_CODE.get(principal.role)
    return {
        "email": principal.email,
        "role": principal.role,
        "scope": principal.scope,
        "capabilities": sorted(principal.capabilities),
        "cannot": role.cannot if role else "",
        "prototype_account": principal.legacy,
    }
