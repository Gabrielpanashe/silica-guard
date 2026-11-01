"""Keyed hashing and reversible encryption for direct identifiers.

Master Reference v1.0 §16.2 (storage at rest: "direct identifiers separated
from clinical content into distinct tables with distinct access paths.
National identity numbers, if collected, stored only as a salted hash") and
`docs/IMPLEMENTATION_PLAN.md` §12 item 11.

**Two columns for one value, deliberately.** A telephone number has to be
found by equality -- the USSD webhook arrives with a caller number and must
locate the person -- and it also has to be sent to, which needs the number
back. An encrypted column cannot be indexed for equality and a hash cannot be
reversed, so one alone cannot do both jobs. Every identifier here therefore
gets a keyed hash for lookup beside an encrypted value for use.

**A keyed hash, not a per-row salt.** The textbook answer for storing an
identifier is a random salt per row, and it is the wrong answer here: a
per-row salt makes two records holding the same national identity number
hash differently, which destroys the one deterministic match §8.2 relies on.
The key is the salt, it is the same for every row, and it lives in the
platform secret store rather than in the database -- so a dump of the
database alone does not let anyone test a guess. This is a real trade-off and
is written down rather than assumed: it protects against database disclosure,
not against disclosure of the database and the key together.

**Domain separation.** Every digest is computed over `purpose + ":" + value`,
so the same string hashed as a phone number and as a national identity number
produces different digests. Without it, a number entered in the wrong field
would silently match across columns and merge two people -- the exact failure
§8.2 calls a clinical safety event.

**A missing key is a hard failure, not a default.** `routers/auth.py:29` falls
back to `"dev-secret"` when `SECRET_KEY` is unset; that pattern is not copied
here. A production instance that quietly hashed national identity numbers
under a guessable default would produce a column that looks protected, is
not, and cannot be migrated afterwards because the plaintext is gone. Failing
loudly on the first call is the better outcome. `.env.example` names both
variables and deliberately carries no values -- a working key committed there
is indistinguishable from a real one, both to the secret scanner and to a
reader, so a developer generates their own.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import unicodedata

from cryptography.fernet import Fernet, InvalidToken

#: Environment variable names. Both are set on the Render service and in
#: `.env` locally; neither has a default.
HMAC_KEY_VAR = "IDENTITY_HMAC_KEY"
ENCRYPTION_KEY_VAR = "CONTACT_ENCRYPTION_KEY"

#: Allowed `purpose` values. A closed set rather than a free string, so a
#: typo becomes an error instead of a silently separate namespace whose rows
#: can never be matched again.
PURPOSES = ("phone", "national_id", "name")


class KeyMissingError(RuntimeError):
    """A key the operation needs is not configured. Raised rather than
    falling back to a default -- see this module's docstring."""


class DecryptionError(ValueError):
    """The stored value could not be decrypted: a wrong or rotated key, or a
    corrupted column. Raised rather than returning an empty string, because
    an empty name on a referral letter is worse than a failure."""


def _require(variable: str) -> str:
    value = os.getenv(variable)
    if not value:
        raise KeyMissingError(
            f"{variable} is not set. Identifiers are stored as a keyed hash "
            "beside an encrypted value, and both need a key from the platform "
            "secret store. There is deliberately no default: hashing a "
            "national identity number under a guessable key produces a column "
            "that looks protected, is not, and cannot be fixed afterwards. "
            "See .env.example and docs/SECURITY.md."
        )
    return value


def _fernet() -> Fernet:
    key = _require(ENCRYPTION_KEY_VAR)
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise KeyMissingError(
            f"{ENCRYPTION_KEY_VAR} is not a valid Fernet key. Generate one "
            "with: python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        ) from exc


# --------------------------------------------------------------- normalising

def normalise_phone(value: str) -> str:
    """To `+263...` where the number is recognisably Zimbabwean, otherwise to
    digits with a leading `+` preserved.

    Normalising before hashing is not cosmetic: `0771234567`, `263771234567`
    and `+263 77 123 4567` are one handset, and three digests for one handset
    means three people in the register. Africa's Talking delivers the caller
    number in international form; a health worker types whatever the worker
    recites.
    """
    if value is None:
        raise ValueError("phone number is required")
    digits = re.sub(r"[^\d+]", "", str(value))
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if digits.startswith("0") and len(digits) >= 9:
        # Local form. Zimbabwe mobile numbers are 0 then nine digits.
        return "+263" + digits[1:]
    if digits.startswith("263"):
        return "+" + digits
    if digits.startswith("+"):
        return digits
    return "+" + digits


def normalise_national_id(value: str) -> str:
    """Upper case, punctuation removed. A Zimbabwean identity number is
    written with dashes and spaces inconsistently, and the deterministic match
    in §8.2 is only deterministic if both sides normalise the same way."""
    if value is None:
        raise ValueError("national identity number is required")
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


def normalise_name(value: str) -> str:
    """Case-folded, accent-stripped, whitespace-collapsed.

    Used for the *exact*-name digest only. Fuzzy comparison happens on
    decrypted plaintext in memory (see `services/identity.py`), because edit
    distance cannot be computed on a hash -- which is the cost of encrypting
    the name at rest and is recorded in `docs/IMPLEMENTATION_PLAN.md` §12.
    """
    if value is None:
        raise ValueError("name is required")
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.casefold().split())


NORMALISERS = {
    "phone": normalise_phone,
    "national_id": normalise_national_id,
    "name": normalise_name,
}


# -------------------------------------------------------------------- hashing

def keyed_hash(value: str, purpose: str) -> str:
    """Domain-separated HMAC-SHA256 of the normalised value, as hex.

    `purpose` must be one of PURPOSES and is part of the hashed input, so the
    same string under two purposes cannot collide across columns.
    """
    if purpose not in PURPOSES:
        raise ValueError(
            f"unknown hash purpose {purpose!r}; expected one of {PURPOSES}. "
            "The set is closed so that a typo is an error rather than a "
            "silently separate namespace whose rows can never be matched."
        )
    normalised = NORMALISERS[purpose](value)
    if not normalised:
        raise ValueError(f"{purpose} normalised to an empty string")
    key = _require(HMAC_KEY_VAR).encode("utf-8")
    message = f"{purpose}:{normalised}".encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def hashes_match(stored: str | None, value: str, purpose: str) -> bool:
    """Constant-time comparison. The timing channel is theoretical here, but
    `compare_digest` costs nothing and the habit is worth keeping."""
    if not stored:
        return False
    return hmac.compare_digest(stored, keyed_hash(value, purpose))


# ----------------------------------------------------------------- encrypting

def encrypt(value: str) -> str:
    """Fernet: AES-128 in CBC mode with an HMAC-SHA256 authentication tag and
    a timestamp. Authenticated encryption, so a tampered column fails to
    decrypt rather than returning different plaintext -- which matters for a
    telephone number that a result message is about to be sent to."""
    if value is None:
        raise ValueError("value is required")
    return _fernet().encrypt(str(value).encode("utf-8")).decode("ascii")


def decrypt(token: str | None) -> str | None:
    """None in, None out. A present-but-undecryptable value raises."""
    if token in (None, ""):
        return None
    try:
        return _fernet().decrypt(str(token).encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise DecryptionError(
            "stored value could not be decrypted: a wrong or rotated "
            f"{ENCRYPTION_KEY_VAR}, or a corrupted column. See the key "
            "rotation procedure in docs/SECURITY.md."
        ) from exc


def generate_encryption_key() -> str:
    """For `.env.example` documentation and for operators rotating a key.
    Never called at runtime."""
    return Fernet.generate_key().decode("ascii")


def generate_hmac_key() -> str:
    """256 bits, url-safe base64. Never called at runtime."""
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")


def keys_configured() -> bool:
    """Whether both keys are present. For `/api/health` and for a startup
    warning -- never as a reason to proceed without them."""
    return bool(os.getenv(HMAC_KEY_VAR)) and bool(os.getenv(ENCRYPTION_KEY_VAR))
