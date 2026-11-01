"""Pydantic request and response shapes for the `/api/v2` surface.

Kept apart from `models.py` rather than grown into it. The v1 shapes serve the
mobile application and dashboard until those clients move (`docs/
IMPLEMENTATION_PLAN.md` §5), and two files make it obvious which contract a
change affects -- `docs/API_CONTRACT.md` is versioned the same way.

The v1 file is deleted with the adapter, not merged into this one.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class MessageOut(BaseModel):
    """One approved string in one language — what a client caches so that the
    text it shows offline is the reviewed text (§8.4, §10.1).

    `language` is what was actually served, which may be the English fallback
    rather than the language asked for. It is reported rather than silently
    substituted: there is no machine translation anywhere in this system, so a
    missing language is a gap in authoring and the client should be able to see
    that it has one.
    """

    code: str
    version: int
    channel: str
    language: str
    text: str
    placeholders: List[str] = Field(default_factory=list)


class ContentCatalogueOut(BaseModel):
    """The snapshot. `language` echoes the request; a message served in English
    instead carries its own `language` on the row."""

    language: str
    count: int
    messages: List[MessageOut]
    #: Null when the store holds no approved content yet, which is the correct
    #: state until the Clinical Lead approves version one rather than an error.
    generated_at: Optional[str] = None


# ───────────────────────────────────────────────────────────── identity (§8.2)


class IdentityBundleIn(BaseModel):
    """What is known about the person being screened.

    Every field is optional, but a bundle with no participant code, no
    national identity number, no name and no contact number identifies nobody
    and is rejected. `site_id`/`site_text` are the session's site, carried
    here because site is one of §8.2's matching-bundle fields even though it
    lives on the session rather than on the person.

    **The national identity number is voluntary and is never stored in a
    recoverable form** — only a keyed hash (§16.2). It is the one field §8.2
    permits a deterministic, directly-applied match on.
    """

    participant_code: Optional[str] = None
    national_id: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    age_band: Optional[str] = None
    sex: Optional[str] = None
    site_id: Optional[int] = None
    site_text: Optional[str] = None
    language: str = "en"
    channel: str = "APP"


class MatchCandidateOut(BaseModel):
    """A person who might be the same person, with the evidence.

    The reasons travel with the score because a reviewer deciding a merge
    needs the evidence rather than a number. No name or number appears here:
    the reviewer looks the candidate up by participant code, which keeps the
    scoring response free of direct identifiers.
    """

    person_id: int
    participant_code: Optional[str] = None
    score: float
    reasons: List[str] = Field(default_factory=list)


class ResolutionOut(BaseModel):
    """`person_id` is always usable. An uncertain match produces a new person
    plus a queue entry, never a blocked screening — rule 7, a completed
    screening is never discarded, and §8.2, a duplicate is preferable to a
    false merge."""

    person_id: int
    participant_code: Optional[str] = None
    #: One of identity.OUTCOMES.
    outcome: str
    provisional: bool = False
    provisional_reason: Optional[str] = None
    #: Scored above the queue threshold and **queued, never applied**.
    candidates: List[MatchCandidateOut] = Field(default_factory=list)
    queued_match_ids: List[int] = Field(default_factory=list)


class PersonOut(BaseModel):
    """A person, as a health worker sees them.

    `name` and `phone` are decrypted for this response and for nothing else.
    They are here because a health worker confirming "is this the right
    person?" at the next outreach has no other way to do it, and because a
    referral letter needs a name.
    """

    person_id: int
    participant_code: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    age_band: Optional[str] = None
    sex: Optional[str] = None
    language: str = "en"
    provisional: bool = False
    provisional_reason: Optional[str] = None
    has_national_id: bool = False
    session_count: int = 0
    #: Set when this record lost a merge, so a stale client holding the old id
    #: can follow the pointer rather than reading a dead record.
    merged_into_person_id: Optional[int] = None


class QueuedMatchOut(BaseModel):
    person_id: int
    participant_code: Optional[str] = None
    candidate_person_id: int
    candidate_participant_code: Optional[str] = None
    match_id: int
    score: Optional[float] = None
    reasons: List[str] = Field(default_factory=list)
    status: str
    created_at: Optional[str] = None


class MatchDecisionIn(BaseModel):
    """`merge` or `reject`. Rejection is recorded, not discarded: "reviewed,
    and they are different people" has to survive, or the same pair is queued
    again at the next screening."""

    decision: str
    decided_by: str


class MergeIn(BaseModel):
    winner_person_id: int
    loser_person_id: int
    merged_by: str
    reason: Optional[str] = None


class MergeOut(BaseModel):
    merge_id: int
    winner_person_id: int
    loser_person_id: int
    merged_by: Optional[str] = None
    merged_at: Optional[str] = None
    reversed_by: Optional[str] = None
    reversed_at: Optional[str] = None
