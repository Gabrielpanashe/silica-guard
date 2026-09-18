# Implementation plan — from the prototype to the §8–16 architecture

> Derived from `docs/master/MASTER_REFERENCE.md` §8–16 and §22 (Master Reference v1.0, September 2026), applied to this repository as audited on 18 September 2026. The master document holds the reasoning; this document holds the engineering: which files, tables and migrations change, in what order, at what rough cost, and what each step blocks. Where this plan disagrees with the master document it says so in §12, rather than complying silently.
>
> **This is a plan. Nothing in it is built.** Every item is marked with whether it must exist **before the first real patient record** (Y/N). Effort is in engineer-days for one backend engineer working alone unless a mobile or clinical owner is named; treat it as ±50 percent.
>
> **Assumption**: the Clinical Lead's instrument specification (§12.5, Appendix A format) exists by the time Phase One's instrument work starts — draft by Week 6, signed by Week 18. **This plan designs the instrument and rules tables generically and does not invent a question set.** The only question codes that appear in this document are the master document's own §12.4 draft, quoted as Gabriel's draft, and the synthetic `T1…Tn` codes of a test-only fixture instrument that is never loaded into any environment. A plausible-looking invented instrument is the kind of thing that quietly becomes real; nothing here should be mistaken for one.

## 1. Where the code is and where it has to go

| Concern | Today (`origin/main`, 18 September 2026) | Target (§8–16) |
|---|---|---|
| Tables | 9: `miners`, `screenings`, `screening_answers`, `facilities`, `referrals`, `outreach_visits`, `mines`, `notifications`, `keepalive_pings` | ~25: people, contacts, exposure, sites, programmes, sessions, answers, **results per condition**, referrals keyed to results, consent, instrument/rules, content, USSD sessions, deliveries, audit, users/roles, identity queue and merges |
| Migrations | 3, never executed by any test | Every schema change a reviewed, reversible migration, exercised in CI on PostgreSQL |
| Classifiers | 3 — Gemini (`routers/screening.py`), thresholds (`ussd_handler.py`), thresholds with weaker overrides (`mobile/.../QuestionScreen.js`) | 1 deterministic rules engine, versioned instrument, identical on both channels and offline |
| Clinical constants | Hardcoded in `questions.py`, `safety_overrides.py`, `deterioration.py`, `referrals.py`, `referral_cascade.py`, the prompt, and the mobile copy | Versioned tables, loaded by migration from a reviewed file, immutable once approved |
| Patient-facing text | Hardcoded dicts (`tier_messages.py`, `advice_engine.py`, `explanation_shona.py`, `education_messages.py`, `notifications.py`, mobile) + Gemini free text rendered on `ResultScreen` | Content store, message code × language (EN/SN/ND), reviewed, GSM-7 checked in CI, no model text on any patient surface |
| Identity | `miners.phone UNIQUE`; USSD creates by phone | Person + contacts with history; participant code; bundle match; review queue; reversible merges |
| Consent | None | Six layered permissions as data, both channels |
| USSD session | In-memory dict, one process | Table, resumable, idempotent, graceful when the database is down |
| Messaging | Sandbox endpoint; acceptance logged; no receipts; education unconsented | Production account, sender ID, delivery receipts per message, education separated with consent/opt-out/quiet hours |
| Failure path | Model failure deletes the screening | A completed screening is never discarded |
| Access | Two flat env-var accounts | Eight roles, least privilege, read audit |
| Environments | One Render service = production = demo | Local / staging / production, separate credentials |
| CI | None | Seven gates (§11.8) |

## 2. Phase Zero — Foundation (design only; ~4 weeks; no code)

Nothing in this phase changes `backend/`, `mobile/` or `dashboard/`. It produces the artefacts Phase One consumes.

| Item | Files | Effort | Blocks | Before real data |
|---|---|---|---|---|
| 0.1 Version two schema on paper — the DDL for every table in §4 below, reviewed with Takudzwa (interface contract) before any migration is written | `docs/IMPLEMENTATION_PLAN.md` (this, §4); ERD via `diagrams/data_model.dot` | 3 | All of Phase One | Y |
| 0.2 Instrument file format — JSON Schema for the Appendix A template so the Clinical Lead's deliverable has a machine-checkable target; a worked example using only the synthetic `T1…T3` codes | `clinical/README.md`, `clinical/instrument.schema.json`, `clinical/examples/TEST-INSTRUMENT.yaml` | 2 | 1.3, Gabriel's transcription | Y |
| 0.3 Content file format + the GSM-7 validator as a standalone script (no runtime code) | `content/README.md`, `content/schema.json`, `backend/scripts/validate_content.py` | 2 | 1.6, CI gate | Y |
| 0.4 CI skeleton — GitHub Actions: pytest on SQLite (as today), secret scan, dependency scan; a PostgreSQL service job that runs `alembic upgrade head && alembic downgrade base && alembic upgrade head` against the *current* three migrations | `.github/workflows/ci.yml` | 2 | Every later gate; §16.6 Phase Zero | Y |
| 0.5 Staging environment — second Render web service + second Supabase project (or schema), **separate Africa's Talking and Gemini credentials**, `main` auto-deploys to staging only; production deploys from a tag | Render/Supabase dashboards; `render.yaml` re-synced as a real Blueprint for staging | 1 | §10.6, §11.5; every demonstration from now on | Y |
| 0.6 Predicate grammar specification for tier and safety rules (see §6) so that the rules engine, the mobile interpreter and the Clinical Lead's cascade all target the same closed language | `clinical/README.md` (grammar section) | 1 | 1.2, 1.9 | Y |

Exit: schema DDL agreed, instrument and content formats published, CI green on the current code, staging exists.

## 3. Phase One — Core rebuild (~3 months, overlapping Phase Zero)

Dependency order. Items 1.1–1.3 can proceed before the instrument specification arrives; 1.4 cannot.

| # | Item | Files touched | Effort | Blocks | Before real data |
|---|---|---|---|---|---|
| 1.1 | **Rules engine** — pure module: `(instrument, answers, previous_answers) → results per condition` with scores, tiers, override flags, provenance. Predicate interpreter for the grammar in §6. No database access. | new `backend/services/rules_engine.py`, `backend/services/predicates.py`; tests `tests/test_rules_engine.py` using `TEST-INSTRUMENT` | 5 | 1.5, 1.8, 1.9, channel equivalence | Y |
| 1.2 | **Instrument tables + loader** — migration `0005` (§4); `clinical/instruments/<code>-v<n>.yaml` → data-migration generator; immutability check in the service layer | `backend/db_models.py`, `alembic/versions/0005_v2_instrument.py`, `backend/services/instrument_store.py`, `backend/scripts/gen_instrument_migration.py` | 4 | 1.4, 1.5, 1.9 | Y |
| 1.3 | **Schema v2 core** — migration `0004` (§4): persons, contacts, sites, programmes, exposure profiles, sessions, results, consent, identity queue/merges; `screening_answers.session_id` | `backend/db_models.py`, `alembic/versions/0004_v2_identity_sessions.py` | 4 | 1.5–1.8, 1.10–1.12 | Y |
| 1.4 | **Instrument version one loaded** — Gabriel's Appendix A document transcribed to YAML on a `clinical/` PR he approves; the generated migration inserts it `approved`; regression fixtures beside it | `clinical/instruments/<code>-v1.yaml`, `clinical/instruments/<code>-v1.fixtures.yaml`, `alembic/versions/00xx_load_instrument_<code>_v1.py` | 2 (+ Gabriel) | Anything that screens a real person; ethics submission | Y — **critical path** |
| 1.5 | **v2 screening service + route** — the §10.3 pipeline (identity → consent → instrument → persist answers → score → deterioration → overrides → result rows → text → referral/message → return), `client_session_uuid` idempotency, `started_at`/`completed_at` | new `backend/services/screening_v2.py`, `backend/routers/screenings_v2.py`, `backend/models_v2.py`; `main.py` registration | 6 | Mobile v2, dashboard v2, v1 adapter | Y |
| 1.6 | **Content store** — migration `0006`; `content/*.yaml` → data migration; `GET /api/v2/content`; the runtime rule test; the CI gate wired to `validate_content.py`; **replace every hardcoded string** in `tier_messages.py`, `advice_engine.py`, `explanation_shona.py`, `education_messages.py`, `notifications.py:44` with store lookups (the files become thin selectors keyed by tier/answer → message code) | `backend/db_models.py`, `alembic/versions/0006_v2_content.py`, `backend/services/content_store.py`, `backend/routers/content.py`, `content/`, `.github/workflows/ci.yml`, the five services above | 5 (+ Gabriel for Shona/Ndebele authoring, which is not engineering effort) | 1.5's step 9, mobile strings, USSD strings, consent texts | Y |
| 1.7 | **Identity resolution** — participant code generation (6 characters, §12 item 4), `POST /api/v2/persons/resolve` (deterministic on hashed national ID, then probabilistic bundle → queue), review-queue endpoints, merge/unmerge with `person_merges` history; **USSD provisional persons**; retire `GET /api/workers/{phone}` semantics into the v1 adapter | new `backend/services/identity.py`, `backend/routers/persons.py`; `contacts.number_hmac` + `number_encrypted` (§12 item 11); `services/ussd_handler.py` `_find_or_create_miner` deleted | 6 | Deterioration on real people; the headline metric's integrity | Y |
| 1.8 | **Consent capture** — `consent_texts` loaded from the content store with versions; `POST /api/v2/consents`; six permissions per §14.2; the session refuses to link `previous_session_id` when longitudinal consent is refused; education send refuses without broadcast consent; USSD keypress consent screen | `backend/services/consent.py`, `backend/routers/consents.py`, `services/ussd_handler.py`, `services/education_messages.py` | 4 | Ethics submission accuracy; any real screening | Y |
| 1.9 | **Model off the classification path** — in the order in §7: v2 route never calls `assess_risk`; v1 adapter switched to the rules engine; `_classify`/`_DANGEROUS_TRIGGERS` deleted from USSD; the delete-on-failure block removed; `ai_risk_engine.py` + `prompts/risk_engine_prompt.txt` retired from the request path | `backend/routers/screening.py` (becomes adapter), `backend/services/ussd_handler.py`, `backend/services/ai_risk_engine.py`, `backend/prompts/risk_engine_prompt.txt`, `tests/test_screening.py`, `tests/test_ussd.py`, `tests/test_ai_risk_engine.py` | 3 | Channel equivalence, offline safety, regulatory positioning | Y |
| 1.10 | **Referrals rekeyed to results** — migration `0007`; `create_referral_and_notify` takes a result; contributing reasons; `POST /api/v2/referrals/{code}/close` with a structured outcome (§9.3 stage two depends on this); facility matching unchanged | `backend/services/referrals.py`, `backend/routers/referral_lookup.py`, `alembic/versions/0007_v2_referrals.py` | 3 | The labelled dataset; dashboard v2 | Y (the outcome field is the pilot's asset) |
| 1.11 | **v1 adapter** — `/api/screen`, `/api/workers*`, `/api/mines`, `/api/dashboard/today`, `/api/miners`, `/api/screenings`, `/api/referrals*` served from v2 tables (person → "worker", first result → `tier`), logging `X-SilicaGuard-Client`; **time-boxed** (§5) | `backend/routers/screening.py`, `workers.py`, `mines.py`, `dashboard.py`, `backend/services/v1_compat.py` (new) | 4 | Nothing — it *unblocks* mobile and dashboard landing later | N (deleted before the pilot) |
| 1.12 | **Drop v1 tables** — migration `0008` after 1.14 and 1.15 are on v2 and the adapter is deleted; `seed_demo_data.py` rewritten for v2 with a realistic tier distribution | `alembic/versions/0008_v2_drop_v1.py`, `backend/scripts/seed_demo_data.py`, `backend/db_models.py` | 2 | Clean schema for the ethics submission's data-flow description | Y |
| 1.13 | **Role model + audit log** (§16.6 puts these in Phase One) — `users`, `roles`, scoped query helpers (`for_facility`, `for_site`, `for_district`), append-only `audit_log` written by a dependency on every clinical read and write; replaces the two env-var accounts | migrations `0011_audit_log`, `0012_users_roles`; `backend/routers/auth.py`, `backend/services/authz.py`, every Bearer route in `dashboard.py`/`outreach.py`/`education.py` | 6 | Dashboard role scoping (Takudzwa, Week 22); pre-pilot checklist | Y |
| 1.14 | **Mobile: interpreter first, UI second** (Takudzwa) — (a) `GET /api/v2/instrument/active?channel=app` + a JavaScript port of `predicates.py` running the same fixtures under node; delete `offlineScore()` and the `QUESTIONS` copy; (b) screens rendered from the instrument; consent screen; participant-code entry and card display; v2 submit with `client_session_uuid`; build-time content snapshot | `mobile/src/services/rulesEngine.js` (new), `mobile/src/services/api.js`, `QuestionScreen.js`, `ResultScreen.js`, `IntakeScreen.js`, `ReferralScreen.js`, `offlineQueue.js`; `mobile/__tests__/` (new) | 4 + 10 | Field viability; offline safety | Y |
| 1.15 | **Dashboard on v2** (Takudzwa) — per-condition results, person/participant code, referral outcome capture on the lookup page, role-scoped views | `dashboard/app.js`, `dashboard/lookup.js`, `dashboard/index.html` | 6 | Facility and coordinator use in the pilot | N for the code itself (role scoping is Y — see 1.13) |
| 1.16 | **Tests** (§10) — instrument regression suite, channel equivalence, identity, consent, idempotency, content validator, no-model-string, Postgres migration up/down in CI | `backend/tests/test_instrument_regression.py`, `test_channel_equivalence.py`, `test_identity.py`, `test_consent.py`, `test_content.py`, `.github/workflows/ci.yml` | 5 | Exit criterion of the phase | Y |

Exit: a worker can be screened end to end on both channels against a versioned instrument, with a deterministic tier, a recorded consent, a resolved identity and a stored instrument version, with no language model anywhere on the clinical path. Phase One backend total ≈ **60 engineer-days**; mobile ≈ 14; dashboard ≈ 6.

## 4. Schema migration path

### Principles

- **The Alembic chain is kept**: `0ae36e3a6a65` (initial) → `a97c1fa69c0e` (keepalive) → `f5bebe94f599` (referral code unique). History is never rewritten; the staging database moves through every migration the production database will.
- **Demonstration data is reseeded, not migrated.** The database holds nothing but synthetic rows (§8.1: "cut the version two schema deliberately while the database still contains only demonstration data … and reseed"). No backfill code is written for `miners → persons` or `screenings → sessions/results`; `scripts/seed_demo_data.py` is rewritten against v2. The Alembic chain remains reversible (§11.6) but reversibility of `0008` recreates empty v1 tables, not v1 data.
- **Every migration is exercised in CI on PostgreSQL** (Phase Zero item 0.4) — `upgrade head`, `downgrade base`, `upgrade head`. Today no test runs Alembic at all (`tests/conftest.py` uses `Base.metadata.create_all` on SQLite), so §11.6's "run forward and backward" is currently unverifiable.
- Local development moves to PostgreSQL after `0004` lands (§11.9); SQLite stays for the fast unit suite. `alembic/env.py` does not set `render_as_batch`, which SQLite would need for `ALTER`; it is not needed if migrations only ever run on PostgreSQL.

### Migrations in order

| Migration | Creates / alters | Depends on | Phase |
|---|---|---|---|
| `0004_v2_identity_sessions` | `persons` (id, participant_code UNIQUE, national_id_hash nullable, age_band, sex, language, created_at, merged_into_id nullable); `contacts` (person_id, number_hmac INDEX, number_encrypted, kind, valid_from, valid_to, is_primary, verified, verified_at); `sites` (name, sector, type, district, province, latitude/longitude nullable, curated bool); `programmes` (code, name, kind community/employer/insurer, payer, data_owner, consent_text_code); `exposure_profiles` (person_id, sector, occupation, tasks, years_band, controls, wet_or_dry, recorded_at, session_id nullable); `screening_sessions` (person_id, channel, screened_by, site_id nullable, site_text, programme_id nullable, instrument_id, ruleset_version, previous_session_id, client_session_uuid UNIQUE, outreach_visit_id nullable, started_at, completed_at, created_at); `screening_answers` + `session_id` FK, drop `question_text`; `screening_results` (session_id, condition_code, tier, score, confidence, method, instrument_id, override_fired, override_rule_codes JSON, created_at; UNIQUE(session_id, condition_code)); `consent_texts` (code, version, language, message_code, status); `consent_records` (person_id, permission, granted, consent_text_id, channel, recorded_at, recorded_by, session_id nullable); `person_match_queue` (candidate_person_id, incoming bundle JSON, score, status, resolved_by, resolved_at); `person_merges` (winner_id, loser_id, evidence JSON, merged_by, merged_at, reversed_at nullable) | `f5bebe94f599` | One |
| `0005_v2_instrument` | `instruments` (code, version, condition_codes JSON, status draft/review/approved/retired, approved_by, approved_at, notes; UNIQUE(code, version)); `instrument_questions` (instrument_id, code, block, clinical_label, response_type, ordinal, scored bool, branching_predicate JSON nullable, label_message_code); `instrument_channels` (question_id, channel, included bool — the per-channel subset, §12 item 6); `answer_options` (question_id, value, ordinal, label_message_code); `scoring_rules` (instrument_id, condition_code, question_code, answer_value, score); `tier_rules` (instrument_id, condition_code, tier, priority, predicate JSON, label); `safety_rules` (instrument_id, condition_code nullable, code, predicate JSON, forces_tier, label); `rescreen_intervals` (instrument_id, condition_code, tier, days); `referral_windows` (instrument_id, condition_code, tier, hours) | `0004` | One |
| `0006_v2_content` | `messages` (code, purpose, channel, max_len, description); `message_texts` (message_code, language, version, text, status, approved_by, approved_at; UNIQUE(message_code, language, version)) | — | One |
| `0007_v2_referrals` | `referrals` + `result_id` FK, `contributing_reasons` JSON, `outcome` (enum: attended_imaging_normal / attended_imaging_abnormal / attended_no_imaging / not_attended / other), `outcome_notes`, `outcome_recorded_at`, `outcome_recorded_by`; `notifications` + `recipient_contact_id` nullable, `recipient_facility_id` nullable, `category` (transactional/education), drop NOT NULL on `worker_id` | `0004` | One |
| `00xx_load_instrument_<code>_v1` | Data only: rows into `0005`'s tables from `clinical/instruments/<code>-v1.yaml`; `status=approved` | `0005`, Gabriel's approval | One |
| `00xx_load_content_v1` | Data only: rows into `0006`'s tables from `content/` | `0006`, Gabriel's approval | One |
| `0008_v2_drop_v1` | Drop `miners`, `screenings`, `mines`; drop `referrals.miner_id`, `referrals.screening_id`, `referrals.hospital`; drop `notifications.worker_id` | Adapter deleted; 1.14 and 1.15 on v2 | One (last) |
| `0009_ussd_sessions` | §8 | `0004` | Two |
| `0010_notification_deliveries` | §9 | `0007` | Two |
| `0011_audit_log` | `audit_log` (actor_user_id, actor_role, action, object_type, object_id, person_id nullable, at, request_id, details JSON) append-only | `0004` | One (per §16.6) |
| `0012_users_roles` | `users` (email, password_hash, role, facility_id nullable, site_ids JSON nullable, district nullable, programme_id nullable, active), replacing env-var accounts | `0004` | One |

**Column-name discipline** (§8.1): no table has a `silicosis_*` column. Conditions are values in `screening_results.condition_code`, `scoring_rules.condition_code`, `tier_rules.condition_code`.

## 5. API versioning

Two first-party clients, one team. The goal is that the mobile application and dashboard move in step, not a permanent versioning framework.

- **New routes under `/api/v2/`.** The v2 surface the clients need: `GET /api/v2/instrument/active?channel=app|ussd`, `GET /api/v2/content?language=&since=`, `POST /api/v2/persons/resolve`, `GET /api/v2/persons/{participant_code}`, `POST /api/v2/consents`, `POST /api/v2/screenings` (returns `results[]`, `primary_tier`, `referral{code, facility, deadline}`, `messages{...}`), `GET /api/v2/persons/{code}/sessions`, referral endpoints keyed by code with `close`, `GET /api/v2/dashboard/*` returning per-condition results, `GET /api/v2/outreach/*`.
- **v1 routes become thin adapters over v2 storage** (item 1.11): same paths, same JSON shapes as `docs/API_CONTRACT.md` today, computed from v2 tables (`worker` = person + primary contact; `tier` = the result row for the instrument's primary condition; `explanation_english` = clinician-facing content-store text, not model output). The adapter is what lets the backend land at Week 8–10 while the mobile rebuild lands at Week 12 and the dashboard at Week 22.
- **Time-boxed**: clients send `X-SilicaGuard-Client: mobile/<version>` or `dashboard/<version>`; the server logs it; when staging logs show no v1 traffic for two weeks after 1.15, the adapter and `0008` land in one PR. No v1 route survives to the pilot.
- `docs/API_CONTRACT.md` gains a v2 section as routes land; the v1 section is marked deprecated with the removal PR number.
- **Idempotency**: `POST /api/v2/screenings` requires `client_session_uuid` (generated on the device when the session starts, stored in the offline queue); a repeat returns the existing session's result with `200` and `replayed: true`. The USSD webhook's idempotency is §8.

## 6. Instrument and rules tables, and the loading mechanism

### The tables are generic

Nothing in `0005` knows what a question is about. `instrument_questions.code` is an opaque uppercase identifier; `scoring_rules` and `tier_rules` are keyed by `condition_code` strings; a second condition is more rows, not more columns. The plan does not define codes, options, scores or thresholds — those are the Clinical Lead's deliverable (§12.5) and arrive as data.

### Rules are predicates, not only score bands

§8.3 lists "tier thresholds keyed to instrument version and condition"; §9.2 says the cascade is "expressible entirely as boolean logic over answer values"; §12.2's corrections show rules of the form *(years > 10 AND any symptoms) OR (past TB AND any breathlessness)*. A `(min_score, max_score)` table cannot express those, and asking the Clinical Lead to flatten a boolean cascade into additive scores would change the instrument. So `tier_rules.predicate` holds a **closed predicate grammar** — no `eval`, no expression language:

```
predicate := {"all": [predicate…]} | {"any": [predicate…]} | {"not": predicate}
           | {"answer": CODE, "in": [VALUE…]}
           | {"score": CONDITION, "gte": N} | {"score": CONDITION, "lte": N}
           | {"count": {"codes": [CODE…], "in": [VALUE…]}, "gte": N}
           | {"unknown": CODE}                       # explicit unknown/refused handling (§12.2 item 10)
```

Evaluation: for each condition, safety rules first (any match → `forces_tier`, recorded in `override_rule_codes`); then tier rules by descending priority — first match wins; a pure score band is `{"score": C, "gte": a}` and needs nothing more. Deterioration (§10.3 step 6) runs between scoring and overrides, over the instrument's `deterioration_codes` (a per-question flag `tracked_for_trajectory`, not a hardcoded set as in `deterioration.py:24` today). The same grammar is interpreted in JavaScript on the device; the same fixtures run against both interpreters.

### Patient-facing wording lives in the content store, not the instrument tables

`instrument_questions.label_message_code` and `answer_options.label_message_code` reference `messages.code`. One translation pipeline, one validator, one approval trail for everything a worker reads, and a new language is rows in `message_texts` only.

### Loading mechanism

1. Gabriel delivers the Appendix A document (one block per question; cascade; overrides; intervals; windows; unknown/refused handling; limitations).
2. It is transcribed into `clinical/instruments/<CODE>-v1.yaml`, validated by `clinical/instrument.schema.json`, on a `clinical/` pull request that **requires Gabriel's recorded approval** (§11.4).
3. `backend/scripts/gen_instrument_migration.py` emits `alembic/versions/00xx_load_instrument_<code>_v1.py` — a data migration inserting the rows with `status='approved'`, `approved_by`, `approved_at` from the YAML header. The migration file is committed and reviewed like any other. This is "the migration that loads each version" (§11.3).
4. Regression fixtures `clinical/instruments/<CODE>-v1.fixtures.yaml` (answer profiles → expected per-condition tiers) are approved on the same PR and consumed by `tests/test_instrument_regression.py` and the mobile test runner.
5. Immutability: `instrument_store.py` refuses any write to an instrument whose status is `approved` or `retired`; a change is a new version. Enforced in the service layer with a test, not a database trigger (triggers are PostgreSQL-only and invisible to the SQLite unit suite).
6. The active instrument per channel is the highest approved version; `screening_sessions.instrument_id` and `screening_results.instrument_id` are stamped from it at session start, never resolved later.

## 7. Removing the model from the classification path without losing functionality

1. **Build first, switch second.** `rules_engine.py` (1.1) lands with the synthetic fixture and full unit coverage before any route changes.
2. **v2 route is deterministic from its first commit.** `POST /api/v2/screenings` never calls `assess_risk`.
3. **v1 adapter switches at the same time.** `routers/screening.py` calls the rules engine; Gemini leaves the tier decision for every client at once, so there is no window in which two clients get two classifiers. `explanation_english` and `contributing_factors` keep their field names for the mobile app's existing `ResultScreen` but are populated from clinician-facing content-store text derived from the fired rules — the same words for the same rules every time.
4. **USSD** drops `_classify` and `_DANGEROUS_TRIGGERS` and calls the same engine with the channel's instrument subset.
5. **Mobile** ships the interpreter and instrument fetch before the UI rebuild (1.14a) so the offline path stops disagreeing with the server weeks before the screens change.
6. **The delete-on-failure block** (`routers/screening.py:106-131`) has nothing left to guard: between persisting answers and persisting results there is no external call. It is removed with step 3, and the idempotency key handles the retry case it was compensating for.
7. **The second reader (§9.1)** is not built in Phase One. If it is ever built, it runs as a scheduled batch over completed sessions, writes a `second_reader_flags` row, and never touches `screening_results.tier`. See §12 item 10.
8. **Retire** `services/ai_risk_engine.py`, `tests/test_ai_risk_engine.py` and `prompts/risk_engine_prompt.txt` (which also removes the prompt's non-Appendix-B figures). `population_intelligence.py` stays: downstream, aggregate, with its deterministic fallback.

## 8. USSD session persistence (Phase Two)

`0009_ussd_sessions`: `ussd_sessions` (gateway_session_id PK, contact_hmac INDEX, person_id nullable, instrument_id, pending_index, answers JSON, consent_recorded_at, last_text, last_response, started_at, last_seen_at, status active/completed/abandoned/expired, completed_session_id nullable).

- `services/ussd_handler.py`: `_sessions` dict removed; every turn loads by `gateway_session_id`, appends, saves. The `text` field arrives as the full `*`-joined history, so the handler validates that the history matches what it has stored rather than trusting the last segment alone.
- **Idempotency**: if the incoming `text` equals `last_text`, return `last_response` verbatim without mutating state — this is how a gateway retry is recognised.
- **Resumption**: a new `gateway_session_id` from a `contact_hmac` with an `active` session younger than N minutes (content-store constant, suggested 30) is offered *1 Continue / 2 Start again*; a partial session **never** produces a result row; a scheduler job expires abandoned sessions and records the drop-off question for §13.3's instrumentation.
- **Identity**: with a participant code entered, attach to that person; without, create a provisional `persons` row flagged unverified and a `contacts` row with `verified=false` — never attach to whoever the number was last seen with.
- **Graceful unavailable**: `database.database_reachable()` (already on branch `be/survive-db-outage`) gates a single `END` message. This message is the documented exception to rule 7 (§12 item 5) because the store it would come from is what is down.
- **Consent screen** first (`1.8`), then the channel's instrument subset (`instrument_channels`).
- **Latency**: Render (Oregon) to Supabase (eu-west-1) is roughly 150 ms per round trip; two to three queries per turn fits §10.7's 3 s target with margin, but co-location is recommended (§12 item 9). Tests use injected time; a load test drives the webhook with the exact form fields the gateway sends.

Effort: 5 days. Blocks: real-world USSD reliability, the pilot's passive channel. Before real data: N for the pilot's *start* only if the app channel opens first, Y for any USSD screening of a real person.

## 9. Delivery receipts and the notification schema (Phase Two)

`0010_notification_deliveries`: `notifications` + `provider_message_id` INDEX, `status` (queued/accepted/delivered/failed/expired), `status_updated_at`, `provider_status_raw`, `segments`, `cost_units`; the existing `delivery_status` column is migrated into `status` and dropped.

- `notifications._send_sms` parses the Africa's Talking response (`SMSMessageData.Recipients[].messageId`, `status`, `cost`) and stores `provider_message_id` with `status=accepted`.
- New public `POST /api/webhooks/at/delivery` accepts the gateway's delivery report (`id`, `status`, `phoneNumber`, `networkCode`, `failureReason`), matches on `provider_message_id`, updates `status` and `status_updated_at`, stores the raw payload. The callback URL is configured in the gateway dashboard (manual, per environment — staging must never receive production callbacks). Signature verification where the provider supports it.
- **Education separated from transactional** (`notifications.category`): `send_education_tip` refuses without `education_broadcast` consent, honours opt-out permanently, applies a frequency cap and quiet hours from configuration, and refuses if a transactional message went to the same person that day.
- **Recycled numbers**: after N consecutive `failed`, the contact is marked `verified=false` and sends stop until re-verified at a screening.
- **PII in logs**: `notifications.py:66` logs the recipient number (`logger.info("SMS to %s: …", to)`) — replaced with the contact id. This is a one-line fix that should not wait for Phase Two.
- Sender ID: configuration only, once registered.

Effort: 4 days. Blocks: interpretation of the headline metric (§13.2). Before real data: Y — a referral message whose delivery cannot be known is a pilot evaluation gap from day one.

## 10. Tests each phase requires

| Phase | Test | Mechanism |
|---|---|---|
| One | Rules engine unit | Pure functions, `TEST-INSTRUMENT` fixture (`T1…Tn`), every grammar node, unknown/refused handling, override precedence |
| One | **Instrument regression suite** | `clinical/instruments/<CODE>-v<n>.fixtures.yaml`, Gabriel-approved expected tiers per condition, parametrised pytest; the same file consumed by `mobile/__tests__/rulesEngine.test.js` under node. Any change to a rule that moves an unrelated fixture fails the build. |
| One | **Channel equivalence** | One answer profile submitted via `POST /api/v2/screenings` (channel `APP`) and via a scripted sequence of `POST /api/ussd` webhook calls with the exact gateway form fields; assert identical `screening_results` rows (condition, tier, override flags, instrument id). Automated, because the team claims it publicly (§11.7). |
| One | Identity | Deterministic match on hashed ID; probabilistic candidates land in the queue and are never auto-merged; merge then unmerge restores both records; USSD without a code creates a provisional person |
| One | Consent | Refused longitudinal consent → no `previous_session_id`; refused broadcast → education send returns "not consented" and writes no notification; consent text version stamped |
| One | Idempotency | Same `client_session_uuid` twice → one session, `replayed: true` |
| One | Content | Validator on every `content/*.yaml` (GSM-7, lengths, three languages); runtime test that every patient-facing string in a v2 response equals an approved `message_texts` row byte for byte; a test that greps the response models for any field populated from a model call |
| One | Migrations | CI PostgreSQL job: `upgrade head` → `downgrade base` → `upgrade head` on every PR touching `alembic/` |
| One | Audit and roles | Every clinical read writes an `audit_log` row; negative tests for each role (§16.3) attempting access that must fail |
| Two | USSD | Retry with identical `text` returns identical response; resumption offered inside the window and not outside; expiry job; partial session yields no result; database-down returns the END message |
| Two | Delivery receipts | Webhook state transitions; unknown `provider_message_id` logged and ignored; N failures mark the contact unverified |
| Two | Education rules | Blocked without consent / inside quiet hours / over the cap / same day as a reminder |
| Two | Device (manual, recorded) | Full screening on the floor handset in airplane mode → sync → rows on staging; encrypted storage verified by inspecting the device |
| Three | Public lookup | Rate limit and lockout tests; enumeration attempt logged |
| Three | Restore drill (manual, recorded) | Backup restored to a scratch database and row counts compared |

## 11. Phases Two and Three — remaining engineering

| # | Item | Files | Effort | Blocks | Before real data |
|---|---|---|---|---|---|
| 2.1 | USSD persistence (§8) | as §8 | 5 | Passive channel reliability | Y for USSD screenings |
| 2.2 | Delivery receipts + education separation (§9) | as §9 | 4 | Headline metric interpretation | Y |
| 2.3 | Sender ID, production gateway account, funded balance | configuration; `notifications._AT_SMS_URL` per environment | 1 (+ vendor lead time) | Real delivery | Y |
| 2.4 | Screening-duration and USSD drop-off instrumentation | `screening_sessions.started_at/completed_at` (already in `0004`); USSD per-question timestamps in `ussd_sessions`; `GET /api/v2/dashboard/operations` | 2 | Pilot findings that cannot be added retrospectively | Y |
| 2.5 | Error monitoring (Sentry or equivalent), structured logging with request ids, no PII | `backend/main.py`, `backend/logging.py` (new), mobile SDK | 2 | Pilot support | N (but pre-pilot) |
| 2.6 | Mobile: encrypted local storage + PIN + lost-device revocation; roster pre-sync; standalone installer; diagnostics screen; sunlight/accessibility pass (Takudzwa) | `mobile/src/services/offlineQueue.js` → secure store, new `DiagnosticsScreen.js`, EAS profile | 12 | Field viability; pre-pilot checklist | Y for encryption; N for the rest |
| 2.7 | Backups automated + restore tested | Supabase configuration; `docs/SECURITY.md` drill record | 1 | Pre-pilot checklist | Y |
| 3.1 | Rate limiting + lockout + logging on `/api/referrals/lookup/*` | `backend/main.py` middleware (e.g. `slowapi`), `routers/referral_lookup.py` | 1 | Pre-pilot checklist | Y |
| 3.2 | Hosting sovereignty decision implemented (§14.5) | Render region / Supabase project; possibly split identifiers | 1–5 depending on the option | Data-controller registration | Y |
| 3.3 | Facility onboarding: facility users, outcome capture training | `users` rows; `dashboard/lookup.html` outcome form (Takudzwa) | 2 | Referral completion measurement | Y |
| 3.4 | Dry run at one site with consenting volunteers | Staging | 2 (all three) | Pilot start | Y |

## 12. Disagreements with the master document, and things that would be easier another way

1. **§8.3 "tier thresholds" cannot express the cascade.** §9.2 and §12.2 describe boolean logic over answers; a min/max score table cannot hold *(years > 10 AND any symptoms)*. The plan uses a closed predicate grammar (§6) of which score bands are one case. The master document's table list should say "tier rules" rather than "tier thresholds".
2. **Question wording inside the instrument tables duplicates the content store.** §8.3 puts "patient facing wording in every supported language" on the question; §8.4 puts every patient-facing string in the content store. Holding both means two translation pipelines and two validators. The plan references message codes from the instrument tables and keeps one store.
3. **`answer_options` "with scores" and per-condition `scoring_rules` are two sources for one number.** The plan keeps only `scoring_rules` (per condition), so that adding tuberculosis is rows, not a second score column.
4. **Four-character participant codes are too small.** The referral-code alphabet (32 symbols, 4 characters) gives about a million codes — fine for short-lived referrals, not for a register meant for more than 500,000 people with a low collision tolerance. Participant codes get six characters (about a billion); referral codes stay at four.
5. **Rule 7 has exactly one unavoidable exception.** The USSD "service unavailable" message when the database is down cannot be read from the content store, because the store is what is down. The plan hardcodes that one string in three languages, lists it in `content/EXCEPTIONS.md`, and has Gabriel sign it. Pretending otherwise would hide the exception rather than review it.
6. **A seventeen-question instrument does not fit a 180-second USSD session.** §12.4 has 17 questions across blocks A–E; add a consent screen and participant-code entry, and at a realistic ten seconds per keypad turn the session exceeds the network limit before the last question. Resumption (§13.1) is therefore mandatory rather than a nicety, **and the instrument model needs per-channel inclusion** (`instrument_channels`) so the Clinical Lead can define a shorter USSD subset deliberately, as data, rather than have the channel silently truncate. This is a clinical decision to raise with Gabriel now, because it affects instrument version one.
7. **Migrating demonstration data is wasted work.** No backfills; reseed. The master document says this too, but the "run forward and backward" rule could be read as requiring data-preserving downgrades; for `0008` it does not.
8. **A permanent API versioning framework is over-engineering for two first-party clients.** The v1 adapter is a bridge with a deletion date, not a policy.
9. **The region split hurts USSD and the sovereignty argument.** The backend is in Oregon and the database in Ireland; every USSD turn pays the transatlantic round trip. Co-locate now (Supabase has no African region; Render's Frankfurt region is the nearest to eu-west-1), and revisit both with the §14.5 decision — which may move everything anyway.
10. **The optional second reader keeps a vendor dependency near the clinical path.** §9.1 permits it; the plan defers it out of Phase One and, if it is ever built, runs it as a batch job that writes flags and never touches a tier. Its clinical value is unproven, it costs per screening, and the pilot's real model asset is the labelled dataset (§9.3 stage two), not a second opinion from a general model.
11. **Encrypting identifiers at rest breaks lookup by number.** USSD needs to find a person by caller number; an encrypted column cannot be indexed for equality. The plan stores a keyed hash (HMAC) for lookup beside the encrypted value for sending, with the key in the platform secret store and a documented rotation procedure. §16.2 should say so.
12. **"Migrations run forward and backward" is unverifiable today.** Tests never execute Alembic. The PostgreSQL CI job is a Phase Zero prerequisite, not Phase Three polish.
13. **§16.6 puts the role model in Phase One while the dashboard rebuild is Week 22.** The plan builds backend role scoping in Phase One and accepts that the dashboard exercises only two of the eight roles until Week 22; the negative tests protect the boundary in the meantime.
14. **`deterioration.py`'s tracked-code set is another hardcoded clinical constant** the master document does not list. It becomes a per-question flag in the instrument (`tracked_for_trajectory`), owned by the Clinical Lead.
15. **`notifications.worker_id NOT NULL`** records a hospital pre-alert against the *miner's* row because there is nowhere else to put it. v2 gives notifications a contact or a facility as recipient.

## 13. Effort summary

| Phase | Backend (Panashe) | Mobile / dashboard (Takudzwa) | Clinical dependency | Must precede real data |
|---|---|---|---|---|
| Zero | ~11 days | website, brand (not in this plan) | Instrument corrections, asymptomatic decision | All of it |
| One | ~60 days | ~20 days | Instrument v1 draft (Week 6) and signed (Week 18); Shona/Ndebele authoring | All except the v1 adapter |
| Two | ~17 days | ~12 days | — | USSD persistence, receipts, encryption, backups |
| Three | ~5–10 days | ~2 days | Ethics protocol sections | All of it |

The critical path is unchanged from `ROADMAP.md`: the instrument specification gates 1.4, which gates every real screening; the shortcode gates the passive channel; the technical chain above is the only one that compresses with effort.
