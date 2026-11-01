"""Pydantic request and response shapes for the `/api/v2` surface.

Kept apart from `models.py` rather than grown into it. The v1 shapes serve the
mobile application and dashboard until those clients move (`docs/
IMPLEMENTATION_PLAN.md` §5), and two files make it obvious which contract a
change affects -- `docs/API_CONTRACT.md` is versioned the same way.

The v1 file is deleted with the adapter, not merged into this one.
"""

from typing import Dict, List, Optional

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


# ────────────────────────────────────────────────────────────── consent (§14.2)


class ConsentDecisionsIn(BaseModel):
    """A whole consent screen in one request.

    `decisions` maps permission code to the worker's answer. All six may
    appear; any that do not are simply unrecorded, and an unrecorded
    permission reads as **not granted** — absence is never consent (§14.2).

    `consent_text_id` is required and names the version of the wording the
    person was shown. A record saying "agreed" with nothing attached is not
    evidence, which is what §14.2 means by recording the version displayed.
    """

    person_id: int
    decisions: Dict[str, bool]
    consent_text_id: int
    #: APP, USSD or PAPER. On USSD this is a short statement in spoken
    #: register followed by an explicit keypress.
    channel: str = "APP"
    session_id: Optional[int] = None
    recorded_by: Optional[str] = None


class ConsentRecordOut(BaseModel):
    """One decision, as recorded. Carries the consent text version because
    that is the part an ethics committee asks about."""

    record_id: int
    permission: str
    granted: bool
    consent_text_code: Optional[str] = None
    consent_text_version: Optional[int] = None
    channel: Optional[str] = None
    recorded_at: Optional[str] = None
    recorded_by: Optional[str] = None
    withdrawn_at: Optional[str] = None


class ConsentSummaryOut(BaseModel):
    """The standing position on all six permissions plus the full history.

    `standing` always has six keys, including the ones nobody asked about,
    which read `false`. A client must never have to decide what a missing key
    means.
    """

    person_id: int
    participant_code: Optional[str] = None
    standing: Dict[str, bool]
    may_screen: bool
    may_keep_longitudinal_record: bool
    history: List[ConsentRecordOut] = Field(default_factory=list)


class ConsentWithdrawIn(BaseModel):
    person_id: int
    permission: str
    withdrawn_by: str


class ConsentTextOut(BaseModel):
    """A consent text version. The wording itself is not here — it is
    `message_code` in the content store, so consent text goes through the same
    review, the same three languages and the same GSM-7 checks as every other
    patient-facing string (§8.4)."""

    consent_text_id: int
    code: str
    version: int
    message_code: str
    status: str
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None


class PermissionOut(BaseModel):
    """What a permission is for, so a consent screen can be rendered from the
    server's own definition rather than from a copy in the client."""

    code: str
    scope: str
    required_to_screen: bool
    future_phase: bool


# ────────────────────────────────────────────────────────── screening (§10.3)


class ScreeningSubmitIn(BaseModel):
    """One screening, as a channel submits it.

    `client_session_uuid` is **required**: it is generated on the device when
    the session starts and replayed on retry, and it is the only thing that
    makes a duplicate submission safe (§10.3). A channel that cannot produce
    one is a channel that will create duplicates — which is what the v1 path
    did, eighteen times for one miner during a model-flakiness window.

    `answers` maps question code to the recorded value. An explicit unknown or
    refused option belongs here too; the engine derives `unknown` from the
    instrument rather than from absence (§12.2 item 10), because an unanswered
    red-flag question must never read as a negative.
    """

    person_id: int
    client_session_uuid: str = Field(..., min_length=8)
    answers: Dict[str, str] = Field(..., min_length=1)
    channel: str = "APP"
    screened_by: Optional[str] = None
    site_id: Optional[int] = None
    site_text: Optional[str] = None
    programme_id: Optional[int] = None
    outreach_visit_id: Optional[int] = None
    instrument_code: Optional[str] = None
    started_at: Optional[str] = None
    #: The device ran the rules engine locally with no connectivity. Not a
    #: different result — the same engine produced it — but recorded.
    offline: bool = False


class ConditionResultOut(BaseModel):
    """**One row per condition assessed.** The single most important shape in
    the v2 API: a session produces a list, not a tier, which is what makes
    adding tuberculosis rows rather than a migration of patient records.

    Carries the provenance §10.1 requires — which instrument version, which
    ruleset, by what method, and whether a safety override fired.
    """

    condition: str
    tier: str
    score: int
    method: str
    instrument_code: str
    instrument_version: int
    #: The tier before deterioration escalation and overrides, so the cascade
    #: is auditable step by step rather than only at its end.
    scored_tier: str
    tier_rule_label: Optional[str] = None
    override_fired: bool = False
    override_rule_codes: List[str] = Field(default_factory=list)
    deterioration_compared: bool = False
    deterioration_changed: bool = False
    deterioration_summary: Optional[str] = None


class MessagePlanOut(BaseModel):
    """What would be sent, and whether the reviewed words exist yet.

    There is deliberately no fallback sentence. §8.4: a worker reads reviewed
    words or nothing — a placeholder shipped "for now" is how unreviewed text
    reaches people.
    """

    code: str
    available: bool
    language: Optional[str] = None
    text: Optional[str] = None
    reason: Optional[str] = None


class ReferralPlanOut(BaseModel):
    referral_code: str
    condition: str
    tier: str
    facility: Optional[str] = None
    deadline: Optional[str] = None


class ScreeningOutcomeOut(BaseModel):
    """The result returned to the channel — identical online or offline,
    because the same deterministic engine produced it in both cases."""

    session_id: int
    person_id: int
    participant_code: Optional[str] = None
    #: The highest tier across conditions: what drives the referral. A worker
    #: at RED for one condition is at RED, whatever the others say.
    primary_tier: str
    results: List[ConditionResultOut]
    instrument_code: str
    instrument_version: int
    #: True when this submission matched an existing `client_session_uuid`.
    #: **Nothing was written.** A retry is safe.
    replayed: bool = False
    #: False when longitudinal consent was absent, so no previous session was
    #: linked and no deterioration comparison was possible (§14.2). The
    #: screening still happened and the result is still real.
    longitudinal_linked: bool = False
    referrals: List[ReferralPlanOut] = Field(default_factory=list)
    messages: List[MessagePlanOut] = Field(default_factory=list)
    #: Why nothing was sent. Non-null until item 1.6b and migration `0010`.
    not_sent_reason: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class ReferralCloseIn(BaseModel):
    """§10.4: closing a referral captures the radiological or clinical
    **outcome**, not merely that the person attended.

    Without it the pilot produces an operational result and no labelled
    dataset; with it every completed referral is a training example nobody
    else in the country holds. The vocabulary is closed because free text is
    not a label.
    """

    outcome: str
    recorded_by: str
    notes: Optional[str] = None


class ReferralOut2(BaseModel):
    referral_code: str
    condition_code: Optional[str] = None
    person_id: Optional[int] = None
    result_id: Optional[int] = None
    facility: Optional[str] = None
    deadline: Optional[str] = None
    status: str
    attended_at: Optional[str] = None
    outcome: Optional[str] = None
    outcome_notes: Optional[str] = None
    outcome_recorded_at: Optional[str] = None
    outcome_recorded_by: Optional[str] = None
    contributing_reasons: Optional[Dict[str, object]] = None
