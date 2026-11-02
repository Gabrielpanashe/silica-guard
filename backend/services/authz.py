"""The eight roles, what each may see, and the scope that makes that
enforceable.

Master Reference v1.0 §16.3. Every role in that table has a "cannot see"
column, and the "cannot see" half is the half that needs code: a role defined
only by what it may do is a role nobody can test negatively.

**A role plus a scope, never a role alone.** "Facility user: can see referrals
directed to their facility" is not a role, it is a role *and* a facility. A
village health worker covers a handful of workings, not one and not all. A
district coordinator is defined by their district. Without the second half the
first half is a label, so every scoped role carries its scope on the `users`
row and this module refuses to grant a scoped capability to a user whose scope
is empty.

**Deny by default.** `allows()` answers False for any capability a role does
not list. A new capability is therefore invisible to every role until somebody
adds it deliberately, which is the safe direction for the mistake to run in.

**Password hashing uses `hashlib.scrypt`** from the standard library, with a
per-user salt. Chosen over bcrypt/passlib to avoid a dependency whose version
handling has broken more builds than it has protected passwords; scrypt is
memory-hard, which is the property that matters.

What this module does NOT do: decide what a *worker* may see of their own
record (§16.3's last row, "the person screened", which has no login and reaches
their data through USSD and the card in their pocket), or write the audit
trail. `services/audit.py` does that, and the dependency in
`routers/auth.py` wires the two together.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass

from sqlalchemy import false, select
from sqlalchemy.orm import Session

from db_models import User

#: scrypt parameters. n=2**14 with r=8, p=1 is roughly 16 MiB and tens of
#: milliseconds per hash -- enough to make a stolen table expensive to attack
#: and cheap enough for a login. Stored in the hash string so that raising
#: them later does not invalidate existing passwords.
_SCRYPT_N = 2 ** 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_BYTES = 16


# ─────────────────────────────────────────────────────────── capabilities

#: Capability names are verbs on objects, matching `audit.ACTIONS` where an
#: action exists. Closed so that a typo is a denial rather than a silent
#: grant -- `allows()` answers False for anything unknown.
CAPABILITIES = (
    #: Read an identified person: name, contact number, participant code.
    "person.read",
    #: Resolve an identity, which may create a person.
    "person.resolve",
    #: Work the identity review queue, and merge or unmerge records. A merge
    #: mixes two clinical histories if it is wrong, so it is the narrowest
    #: capability here.
    "person.merge",
    #: Record or withdraw a consent decision.
    "consent.write",
    "consent.read",
    #: Submit a screening.
    "screening.write",
    #: Read identified clinical detail.
    "screening.read",
    #: Read referrals, and confirm attendance or close one with an outcome.
    "referral.read",
    "referral.close",
    #: Aggregate views only, with small-cell suppression.
    "aggregate.read",
    #: Pseudonymised extract under an approved protocol.
    "export.pseudonymised",
    #: Create and deactivate users, load instrument versions and content.
    "admin.manage",
)


@dataclass(frozen=True)
class Role:
    code: str
    label: str
    capabilities: frozenset[str]
    #: The scope column on `users` this role is meaningless without.
    scope_field: str | None = None
    #: §16.3's "cannot see" column, kept in code rather than only in the
    #: document, because this is the sentence a negative test is written
    #: from.
    cannot: str = ""


ROLES: tuple[Role, ...] = (
    Role(
        "village_health_worker",
        "Village health worker",
        frozenset({
            "person.resolve", "person.read", "consent.write", "consent.read",
            "screening.write", "screening.read", "referral.read",
        }),
        scope_field="site_ids",
        cannot="Other sites, other workers' encounters, national data.",
    ),
    Role(
        "facility_user",
        "Facility user",
        frozenset({"referral.read", "referral.close", "person.read"}),
        scope_field="facility_id",
        cannot=(
            "Screenings with no referral to them, other facilities' "
            "referrals, aggregate national data."
        ),
    ),
    Role(
        "district_coordinator",
        "District coordinator",
        frozenset({"aggregate.read", "referral.read"}),
        scope_field="district",
        cannot=(
            "Identified records outside their district; clinical detail "
            "beyond what coordination requires."
        ),
    ),
    Role(
        "national_stakeholder",
        "National stakeholder",
        frozenset({"aggregate.read"}),
        cannot="Any identified record.",
    ),
    Role(
        "researcher",
        "Researcher",
        frozenset({"aggregate.read", "export.pseudonymised"}),
        cannot="Direct identifiers and the re-identification key.",
    ),
    Role(
        "programme_sponsor",
        "Programme sponsor",
        frozenset({"aggregate.read"}),
        scope_field="programme_id",
        cannot=(
            "Individual results; anything outside their cohort. §14.4: an "
            "employer or sponsor never receives individual results without "
            "separate, specific, refusable consent."
        ),
    ),
    Role(
        "administrator",
        "Administrator",
        frozenset({"admin.manage", "person.merge", "aggregate.read"}),
        cannot=(
            "Routine clinical browsing. Administrative access is not a "
            "licence to read records; every read is audited."
        ),
    ),
    #: The two prototype accounts, kept only so the existing dashboard keeps
    #: working through the transition. Deleted with the v1 adapter (item
    #: 1.11); `routers/auth.py` refuses them the moment a real user exists.
    Role(
        "hospital",
        "Hospital (prototype account)",
        frozenset({"referral.read", "referral.close", "screening.read", "person.read"}),
        cannot="Nothing, which is the problem. Replaced by facility_user.",
    ),
    Role(
        "cimas",
        "Cimas (prototype account)",
        frozenset({"aggregate.read", "referral.read", "screening.read", "person.read"}),
        cannot="Nothing, which is the problem. Replaced by programme_sponsor.",
    ),
)

BY_CODE = {r.code: r for r in ROLES}
#: §16.3's table has eight rows and there are seven roles here, which is not
#: a miscount: the eighth is **the person screened**, who has no login. A
#: worker reaches their own record through USSD and the card in their pocket,
#: so their access is bounded by the participant code rather than by a role,
#: and there is no `users` row to give them. Modelling them as a role would
#: mean issuing credentials to half a million people to express a permission
#: the channel already enforces.
SPECIFIED_ROLES = tuple(r.code for r in ROLES if r.code not in ("hospital", "cimas"))
#: Kept only so the existing dashboard keeps working through the transition,
#: and refused to any new user. Deleted with the v1 adapter (item 1.11).
LEGACY_ROLES = ("hospital", "cimas")


class AuthzError(ValueError):
    """The user or role cannot be used: unknown role, or a scoped role with
    no scope."""


@dataclass(frozen=True)
class Principal:
    """Who is acting, resolved from the token and the `users` row.

    `scope` holds whatever the role needs: a facility id, a set of site ids,
    a district, a programme id. Empty for the unscoped roles.
    """

    user_id: int | None
    email: str
    role: str
    scope: dict
    active: bool = True
    #: True for a prototype env-var account, which has no `users` row.
    legacy: bool = False

    @property
    def capabilities(self) -> frozenset[str]:
        role = BY_CODE.get(self.role)
        return role.capabilities if role else frozenset()

    def allows(self, capability: str) -> bool:
        """Deny by default: False for any capability this role does not
        list, including one that does not exist."""
        return self.active and capability in self.capabilities


# ────────────────────────────────────────────────────────────── passwords

def hash_password(password: str) -> str:
    """`scrypt$n$r$p$salt$hash`, all base64. The parameters travel with the
    hash so that raising them later does not invalidate existing passwords."""
    if not password or len(password) < 8:
        raise AuthzError("a password must be at least 8 characters")
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P
    )
    def b64(raw: bytes) -> str:
        return base64.b64encode(raw).decode("ascii")

    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${b64(salt)}${b64(digest)}"


def verify_password(password: str, stored: str | None) -> bool:
    """Constant-time comparison. False for a malformed or absent hash rather
    than raising: a corrupted row must not be a way in."""
    if not stored or not password:
        return False
    try:
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=base64.b64decode(salt_b64),
            n=int(n), r=int(r), p=int(p),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, base64.b64decode(hash_b64))


# ───────────────────────────────────────────────────────── users and scope

def _scope_for(user: User) -> dict:
    role = BY_CODE.get(user.role)
    if role is None or role.scope_field is None:
        return {}
    if role.scope_field == "site_ids":
        ids = [int(s) for s in (user.site_ids or "").split(",") if s.strip()]
        return {"site_ids": ids}
    return {role.scope_field: getattr(user, role.scope_field)}


def principal_for(user: User) -> Principal:
    return Principal(
        user_id=user.id,
        email=user.email,
        role=user.role,
        scope=_scope_for(user),
        active=bool(user.active),
    )


def create_user(
    db: Session,
    email: str,
    password: str,
    role: str,
    *,
    name: str | None = None,
    facility_id: int | None = None,
    site_ids: list[int] | None = None,
    district: str | None = None,
    programme_id: int | None = None,
) -> User:
    """Create a user, refusing a scoped role with no scope.

    That refusal is the point of this function. A facility user with no
    facility, or a district coordinator with no district, passes every
    capability check and is scoped to nothing — which in practice means
    scoped to everything, since a filter on an empty scope is a filter that
    matches no rows or every row depending on how it is written. Refusing at
    creation makes the question unanswerable rather than answered wrongly.
    """
    role_def = BY_CODE.get(role)
    if role_def is None:
        raise AuthzError(f"unknown role {role!r}; expected one of {tuple(BY_CODE)}")
    if role in LEGACY_ROLES:
        raise AuthzError(
            f"{role!r} is a prototype account kept only for the transition and "
            "may not be given to a new user. Use its replacement: "
            "facility_user for hospital, programme_sponsor for cimas."
        )

    scope_value = {
        "facility_id": facility_id,
        "site_ids": site_ids,
        "district": district,
        "programme_id": programme_id,
    }.get(role_def.scope_field) if role_def.scope_field else None

    if role_def.scope_field and not scope_value:
        raise AuthzError(
            f"role {role!r} needs {role_def.scope_field}. A scoped role with "
            "no scope passes every capability check and is bounded by "
            "nothing, which is worse than no account at all."
        )

    if db.scalar(select(User).where(User.email == email.lower())) is not None:
        raise AuthzError(f"a user with email {email!r} already exists")

    user = User(
        email=email.lower(),
        password_hash=hash_password(password),
        role=role,
        name=name,
        facility_id=facility_id,
        site_ids=",".join(str(i) for i in site_ids) if site_ids else None,
        district=district,
        programme_id=programme_id,
    )
    db.add(user)
    db.flush()
    return user


def authenticate(db: Session, email: str, password: str) -> User | None:
    """The `users` row for these credentials, or None. Inactive users do not
    authenticate."""
    user = db.scalar(select(User).where(User.email == (email or "").lower()))
    if user is None or not user.active:
        return None
    return user if verify_password(password, user.password_hash) else None


def any_user_exists(db: Session) -> bool:
    """Whether the prototype environment accounts are still permitted.

    They work **only while this returns False**. The moment a real user is
    created they stop working, which makes the fallback self-disarming rather
    than a flag somebody has to remember to turn off — and a flag nobody
    turns off is how a prototype credential reaches production.
    """
    return db.scalar(select(User.id).limit(1)) is not None


def legacy_principal(email: str, role: str) -> Principal:
    return Principal(user_id=None, email=email, role=role, scope={}, legacy=True)


# ──────────────────────────────────────────────────────── scoped queries

def for_facility(statement, column, principal: Principal):
    """Narrow a query to the principal's facility.

    Returns a statement that matches **nothing** when the role is scoped to a
    facility and has none, rather than everything. That is the whole reason
    these helpers exist instead of an inline `if`: the failure mode of a
    missing scope must be an empty result, never an unfiltered one.
    """
    if "facility_id" not in principal.scope:
        return statement if principal.allows("aggregate.read") else statement.where(false())
    return statement.where(column == principal.scope["facility_id"])


def for_sites(statement, column, principal: Principal):
    ids = principal.scope.get("site_ids")
    if not ids:
        return statement.where(false())
    return statement.where(column.in_(ids))


def for_district(statement, column, principal: Principal):
    district = principal.scope.get("district")
    if not district:
        return statement.where(false())
    return statement.where(column == district)


def for_programme(statement, column, principal: Principal):
    programme = principal.scope.get("programme_id")
    if not programme:
        return statement.where(false())
    return statement.where(column == programme)


def scoped_to_a_cohort(principal: Principal) -> bool:
    """True for a role whose own "cannot" sentence limits it to one cohort.

    Only `programme_sponsor` today. §16.3 gives that role "anything outside
    their cohort" as a refusal, which is stronger than every other scope line
    in the table: a district coordinator is refused *identified* records
    outside their district and may see national aggregates, while a sponsor
    is refused the aggregate too. §14.4 is why -- an employer or insurer
    paying for screening must not be handed a picture of anybody else's
    workforce along with their own.
    """
    role = BY_CODE.get(principal.role)
    return role is not None and role.scope_field == "programme_id"


def for_aggregate_sessions(statement, column, principal: Principal):
    """Narrow an aggregate over screening sessions to this principal's cohort.

    `column` is `ScreeningSession.programme_id`, passed in so this module
    stays free of a dependency on the session model.

    Unscoped for every other `aggregate.read` role, deliberately: a national
    stakeholder's whole purpose is the national picture, a researcher's is the
    population, and an administrator holds `aggregate.read` for operational
    reasons. The one role the master document limits to a cohort is the one
    narrowed here.

    Narrows to **nothing** for a sponsor with no programme, like every other
    helper in this file: the failure mode of a missing scope must be an empty
    result, never an unfiltered one.
    """
    if not scoped_to_a_cohort(principal):
        return statement
    programme = principal.scope.get("programme_id")
    if not programme:
        return statement.where(false())
    return statement.where(column == programme)


def may_read_identified(principal: Principal) -> bool:
    """§16.3: a national stakeholder, a researcher and a programme sponsor
    must never reach an identified record, whatever else they can do."""
    return principal.allows("person.read")
