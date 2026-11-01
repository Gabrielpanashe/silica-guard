"""Keyed hashing and reversible encryption for direct identifiers.

Master Reference v1.0 §16.2 and `docs/IMPLEMENTATION_PLAN.md` §12 item 11.

Three properties carry the weight here, and each has a specific failure it
prevents:

  **Normalisation before hashing.** `0771234567` and `+263771234567` are one
  handset. Two digests for one handset means two people in a register whose
  headline metric depends on matching a worker to his own earlier record.

  **Domain separation.** A number typed into the national-identity field must
  not produce the same digest as the same number typed into the phone field,
  or the system merges two people — the clinical safety event §8.2 names.

  **A missing key fails loudly.** The alternative is a column that looks
  protected, is not, and cannot be fixed afterwards because the plaintext is
  gone.
"""

import pytest

from services import crypto
from services.crypto import DecryptionError, KeyMissingError


# ----------------------------------------------------------- normalising

@pytest.mark.parametrize(
    "written",
    [
        "0771234567",
        "+263771234567",
        "263771234567",
        "+263 77 123 4567",
        "077 123 4567",
        "(077) 123-4567",
        "00263771234567",
    ],
)
def test_one_handset_normalises_to_one_number(written):
    """Every form a health worker or a gateway might supply is the same
    handset, so every form must hash the same."""
    assert crypto.normalise_phone(written) == "+263771234567"
    assert crypto.keyed_hash(written, "phone") == crypto.keyed_hash(
        "+263771234567", "phone"
    )


def test_a_different_number_hashes_differently():
    assert crypto.keyed_hash("0771234567", "phone") != crypto.keyed_hash(
        "0771234568", "phone"
    )


@pytest.mark.parametrize(
    "written", ["63-123456-A-00", "63 123456 A 00", "63123456a00", "  63123456A00 "]
)
def test_an_identity_number_normalises_past_its_punctuation(written):
    """A Zimbabwean identity number is written with dashes and spaces
    inconsistently, and §8.2's deterministic match is only deterministic if
    both sides normalise the same way."""
    assert crypto.normalise_national_id(written) == "63123456A00"


@pytest.mark.parametrize(
    "written", ["Tendai Moyo", "  tendai   moyo ", "TENDAI MOYO", "Tendai\tMoyo"]
)
def test_a_name_normalises_for_the_exact_match_digest(written):
    assert crypto.normalise_name(written) == "tendai moyo"


def test_accents_are_stripped_before_hashing():
    """A name typed with and without a diacritic is one person."""
    assert crypto.normalise_name("Chiprê") == crypto.normalise_name("Chipre")


# ------------------------------------------------------ domain separation

def test_the_same_string_hashes_differently_per_purpose():
    """Without this, a number entered in the wrong field matches across
    columns and merges two people."""
    value = "63123456A00"
    digests = {
        crypto.keyed_hash(value, "national_id"),
        crypto.keyed_hash("+263771234567", "phone"),
        crypto.keyed_hash(value, "name"),
    }
    assert len(digests) == 3


def test_an_unknown_purpose_is_refused():
    """The set is closed so a typo is an error rather than a silently separate
    namespace whose rows can never be matched again."""
    with pytest.raises(ValueError, match="unknown hash purpose"):
        crypto.keyed_hash("x", "nationalid")


def test_a_digest_is_stable_across_calls():
    """Equality lookup depends on it: a per-row salt would break the one
    deterministic match §8.2 relies on, which is why the key is the salt."""
    first = crypto.keyed_hash("0771234567", "phone")
    assert first == crypto.keyed_hash("0771234567", "phone")
    assert len(first) == 64  # SHA-256, hex


def test_hashes_match_compares_safely():
    stored = crypto.keyed_hash("0771234567", "phone")
    assert crypto.hashes_match(stored, "+263 77 123 4567", "phone")
    assert not crypto.hashes_match(stored, "0771234568", "phone")
    assert not crypto.hashes_match(None, "0771234567", "phone")


def test_an_empty_value_is_refused():
    with pytest.raises(ValueError):
        crypto.keyed_hash("   ", "name")


# ---------------------------------------------------------- encryption

def test_a_value_round_trips():
    token = crypto.encrypt("+263771234567")
    assert token != "+263771234567"
    assert crypto.decrypt(token) == "+263771234567"


def test_encryption_is_not_deterministic():
    """Fernet includes an initialisation vector and a timestamp, so the same
    number encrypted twice gives different ciphertext — which is why this
    column cannot be the one used for lookup."""
    assert crypto.encrypt("+263771234567") != crypto.encrypt("+263771234567")


def test_a_tampered_value_fails_rather_than_returning_different_plaintext():
    """Authenticated encryption. This matters for a telephone number a result
    message is about to be sent to: silently delivering a worker's result to a
    different handset is a disclosure, not a glitch."""
    token = crypto.encrypt("+263771234567")
    tampered = token[:-6] + ("AAAAAA" if not token.endswith("AAAAAA") else "BBBBBB")
    with pytest.raises(DecryptionError):
        crypto.decrypt(tampered)


def test_none_decrypts_to_none():
    assert crypto.decrypt(None) is None
    assert crypto.decrypt("") is None


def test_a_name_with_accents_round_trips():
    assert crypto.decrypt(crypto.encrypt("Chiprê Ncübe")) == "Chiprê Ncübe"


# ------------------------------------------------------- the missing key

def test_hashing_without_a_key_raises_rather_than_defaulting(monkeypatch):
    """`routers/auth.py:29` falls back to "dev-secret" when SECRET_KEY is
    unset. That pattern is deliberately not copied: hashing a national
    identity number under a guessable default produces a column that looks
    protected, is not, and cannot be fixed afterwards."""
    monkeypatch.delenv(crypto.HMAC_KEY_VAR, raising=False)
    with pytest.raises(KeyMissingError, match=crypto.HMAC_KEY_VAR):
        crypto.keyed_hash("0771234567", "phone")


def test_encrypting_without_a_key_raises(monkeypatch):
    monkeypatch.delenv(crypto.ENCRYPTION_KEY_VAR, raising=False)
    with pytest.raises(KeyMissingError, match=crypto.ENCRYPTION_KEY_VAR):
        crypto.encrypt("+263771234567")


def test_a_malformed_encryption_key_raises_with_the_fix(monkeypatch):
    monkeypatch.setenv(crypto.ENCRYPTION_KEY_VAR, "not-a-fernet-key")
    with pytest.raises(KeyMissingError, match="Fernet.generate_key"):
        crypto.encrypt("x")


def test_keys_configured_reports_both(monkeypatch):
    assert crypto.keys_configured()
    monkeypatch.delenv(crypto.HMAC_KEY_VAR, raising=False)
    assert not crypto.keys_configured()


def test_a_different_key_produces_a_different_digest(monkeypatch):
    """Which is also the warning: rotating the key orphans every stored hash,
    so rotation is a re-encryption pass rather than an edit."""
    first = crypto.keyed_hash("0771234567", "phone")
    monkeypatch.setenv(crypto.HMAC_KEY_VAR, "a-completely-different-key")
    assert crypto.keyed_hash("0771234567", "phone") != first


def test_a_value_encrypted_under_another_key_will_not_decrypt(monkeypatch):
    token = crypto.encrypt("+263771234567")
    monkeypatch.setenv(crypto.ENCRYPTION_KEY_VAR, crypto.generate_encryption_key())
    with pytest.raises(DecryptionError, match="rotated"):
        crypto.decrypt(token)


# --------------------------------------------------------- key generation

def test_generated_keys_are_usable(monkeypatch):
    monkeypatch.setenv(crypto.ENCRYPTION_KEY_VAR, crypto.generate_encryption_key())
    monkeypatch.setenv(crypto.HMAC_KEY_VAR, crypto.generate_hmac_key())
    assert crypto.decrypt(crypto.encrypt("value")) == "value"
    assert len(crypto.keyed_hash("0771234567", "phone")) == 64


def test_the_env_example_keys_are_valid(monkeypatch):
    """A fresh checkout copies `.env.example` and must run. A placeholder that
    is not a real Fernet key would fail at the first screening instead."""
    import re
    from pathlib import Path

    text = (Path(__file__).resolve().parent.parent / ".env.example").read_text(
        encoding="utf-8"
    )
    for variable in (crypto.HMAC_KEY_VAR, crypto.ENCRYPTION_KEY_VAR):
        match = re.search(rf"^{variable}=(.+)$", text, re.MULTILINE)
        assert match, f"{variable} is not in .env.example"
        monkeypatch.setenv(variable, match.group(1).strip())
    assert crypto.decrypt(crypto.encrypt("value")) == "value"
    assert len(crypto.keyed_hash("0771234567", "phone")) == 64
