# CLAUDE.md

Read this at the start of every session. It is the shared reference for both developers on SilicaGuard. If anything here conflicts with the master reference document (`SilicaGuardcompletedocumentation_final.docx`, v4.0, FINAL), the reference document wins — flag the conflict and update this file.

## Project identity

SilicaGuard is an occupational lung health screening system for Zimbabwe's artisanal and small-scale mining workforce — miners covered by neither NSSA nor any existing occupational health programme (formal/enterprise mining employers already run their own; see "Current sprint status" for the 5 August scope pivot). A health worker takes an Android app to a mine site, delivers a fifteen-minute group education session using illustrated cards on the phone, then screens each miner in about ten minutes with no doctor present. The system classifies each worker into one of four risk tiers, compares the result against their previous screening to detect deterioration early, and tells each miner the single most important thing he personally should change — drawn from his own answers. Where a referral is needed it routes it to the right facility with a deadline, pre-alerts that facility, and chases the worker until attendance is confirmed. Miners who miss the outreach day self-screen by dialling a USSD code from any phone, with no internet and no cost. Everyone receives their result and reminders by SMS. Hospitals see every referral and whether it was completed. Silicosis is the first module; tuberculosis is next, on the same infrastructure.

- **Prototype presentation**: 11 August 2026 (online demonstration preferred).
- **Feature freeze**: end of Day 8 of the sprint. Days 9–11 are testing, rehearsal and evidence only — no new functionality.
- **Sprint window**: 1–11 August 2026. Note: the sprint plan's "Day 1" is dated 1 August; if today's date is later than that, count forward from 1 August to find the actual current day rather than assuming Day 1.

## Ownership boundaries

Two developers share this repo. Respect these boundaries — **never edit a file in the other person's directory without saying so first.**

| Area | Owner |
|---|---|
| `backend/` (schema, AI services, all API routes, deployment, seed scripts) | Panashe — AI & Backend Engineer |
| `mobile/` (React Native / Expo app) | Collaborator — Mobile & UX/UI Engineer |
| `dashboard/` (React web dashboard) | Collaborator — Mobile & UX/UI Engineer |
| `docs/`, `CLAUDE.md`, the API contract, `.env.example`, database schema | **Shared — requires agreement before changing** |

Any change to the database schema or an API response shape must be announced in the shared progress log before merging — it breaks the other developer's work if it lands silently.

## Tech stack — do not suggest alternatives

- **Backend**: Python FastAPI, SQLite (MVP; migrates to PostgreSQL at pilot scale), deployed on Render free tier.
- **Mobile**: React Native (Expo), `expo-sqlite`, offline-first. No Flutter.
- **Dashboard**: React + Vite + Recharts + Leaflet, deployed on Vercel.
- **AI**: Google Gemini 2.5 Flash via the Gemini API. Claude API is the documented drop-in alternative if Anthropic billing becomes available — that's why `ANTHROPIC_API_KEY` exists in `.env.example` even though it's currently unused.
- **USSD and SMS**: Africa's Talking, called directly over `httpx` — **not** the official SDK, which fails with an SSL error on Windows in this environment.
- **No WhatsApp. No voice/IVR. No Flutter. No chest X-ray model.** These were built or considered in earlier versions (v1.0–v3.0) and were deliberately removed. Do not reintroduce them.

## The four AI modules — and nothing else is AI

1. **Risk Stratification Engine** — screening answers → four-tier classification, reasoning like an occupational health physician, output includes the personalised advice line.
2. **Longitudinal Deterioration Detection** — compares a re-screen against the worker's previous screening; any adverse trajectory escalates the tier one level even if absolute values wouldn't warrant it.
3. **Smart Referral Router** — sets urgency window, matches facility, composes the referral packet, schedules reminders/escalation.
4. **Population Health Intelligence** — weekly job producing site-clustering analysis and a plain-language narrative for the hospital dashboard.

The mobile app UI, the dashboards, SMS dispatch, Teach Mode cards, the USSD decision tree, the outreach planner and the compliance export are **not AI**. They are good software engineering. Never describe them as AI — overclaiming weakens the four real claims.

## Non-negotiable rules

Copied verbatim from the reference document's implementation map. These are not up for reinterpretation in the course of normal feature work — if one seems wrong, say so and raise it rather than quietly deviating.

- Hard red-flag overrides live in Python code, outside the model call. The model can never downgrade a RED.
- USSD handlers must respond within 10 seconds and complete a session within 180 seconds. No LLM call inside a USSD session.
- Every screening stores the AI input and output together, so any classification can be audited afterwards.
- The mobile app must complete a full screening with no connectivity and sync cleanly afterwards. Test in airplane mode before declaring done.
- Phone numbers are hashed at rest. Never store a raw phone number in an exportable table.
- Every patient-facing string requires the Clinical Lead's written sign-off before it ships.
- Every screening result must carry a personalised advice line. A result without one is incomplete.

## Coding conventions

- API responses use `snake_case` JSON keys.
- All timestamps stored in UTC, ISO 8601.
- Never hardcode secrets — always read from environment variables.
- Any change to the database schema or an API response shape must be announced in the shared log before merging.

## Git workflow

- `main` is protected and always deployable.
- Branch naming: `be/<short-description>` for backend, `fe/<short-description>` for frontend.
- Small commits, clear messages, pull request into `main`.
- Pull from `main` before starting work every day.

## Current sprint status

Last updated: 5 August 2026 (sprint Day 5). **Note on this section's own history**: PR #2 (scope pivot) and PR #3 (risk-engine hardening) were developed in parallel branches that both edited this section independently; when both merged to `main`, PR #2's version of this section won and PR #3's updates (safety overrides/deterioration/advice-line landing) were silently lost from this file — the code itself was never lost, only this status writeup. Rewritten below to reflect everything that's actually true as of now, all in one place.

**All of the following is merged to `main`:**

- **Phase A schema migration** (PR #1, 2 August): four-tier `tier` column (`GREEN`/`YELLOW`/`ORANGE`/`RED`, CHECK-constrained), `previous_screening_id`, `advice_line`, `provisional` columns added; `xray_results`/`whatsapp_messages` tables dropped; `referrals` status lifecycle now `open → pre_alerted → reminded → attended → closed → escalated` with `deadline` set on creation (RED = 48h, ORANGE = 14 days).
- **Artisanal-only scope pivot** (PR #2, 5 August): per Dr Bopoto's feedback, formal/enterprise mining companies already run their own pneumoconiosis programmes, so SilicaGuard targets artisanal miners only now. Removed the Enterprise Occupational Health pillar entirely — `employers`/`campaigns` tables dropped (not left dead), the target `employer` role and its privacy-boundary rule, both `/api/enterprise/*` target routes. Full detail and the "who pays" rewrite are in `SILICAGUARD.md` Section 13. **The `.docx` master reference document still has not been manually updated** — still describes the enterprise pillar; see that session's handoff checklist for exact sections to change.
- **Risk Stratification Engine hardening** (PR #3, 5 August): **hard red-flag safety overrides now live in Python** (`backend/services/safety_overrides.py`), closing the non-negotiable-rule violation — applied after the AI call, so the model can never downgrade a RED. **Longitudinal Deterioration Detection is built** (`backend/services/deterioration.py`) — escalates tier one level on any worsened symptom/exposure answer vs the worker's previous screening. **Personalised advice generation is built** (`backend/services/advice_engine.py`) — `advice_line` is now always populated, template-bound (not model-generated free text), selected from the miner's single weakest answer. **Draft copy, not yet Clinical Lead signed off.**
- **Smart Referral Router + Population Health Intelligence** (branch `be/smart-referral-router-and-population-intel`, 5 August, today):
  - Worker endpoints rebuilt as `POST /api/workers` + new `GET /api/workers/{phone}` (replaces the old `POST /api/miners`, which now 404s). Unauthenticated, same deliberate precedent as `/api/screen`.
  - **Facility matching is live** (`backend/services/facility_matching.py`): RED always matches a `district_hospital`-level facility; ORANGE tries a `clinic` whose name plausibly serves the worker's site, falling back to the hospital. Replaces the old hardcoded `'Kwekwe District Hospital'` literal.
  - **Reminder/escalation cascade is live** (`backend/services/referral_cascade.py`): RED gets one reminder at ~24h, escalates at 48h; ORANGE reminds at day 3 and day 7, escalates at day 14. Fires via an in-process **APScheduler** job wired into `main.py`'s lifespan (`SCHEDULER_INTERVAL_MINUTES`, default 10 min; `SCHEDULER_ENABLED=false` disables it — set automatically under pytest). Only runs while the server process is awake.
  - **Population Health Intelligence is live** (`backend/services/population_intelligence.py`) — `GET /api/dashboard/week`'s `ai_narrative` is now a real Gemini call (generated fresh per request, not cached/scheduled — a fast-follow candidate), with a deterministic fallback string if the call fails. New `tier_distribution` field on the same response.
  - Schema: `referrals.facility_id`, `referrals.reminder_stage` added via `ALTER TABLE` (wrapped for idempotency) — unlike most schema changes in this project, an existing local/deployed DB does **not** need deleting for this one.
  - `docs/API_CONTRACT.md` fully updated to match all of the above.
  - All four AI modules are now substantively built for the first time this sprint.

**Phone-number hashing rule, reviewed not changed**: `CLAUDE.md`'s non-negotiable rule says phone numbers must be hashed at rest and never stored raw in an exportable table. `miners.phone` stays plaintext — it's the operational identity for SMS delivery, USSD caller lookup, and `GET /api/workers/{phone}`; a one-way hash there breaks all three (you cannot text a hash). The rule's actual target, an *exportable* table, doesn't exist post-pivot — the enterprise CSV export that would have been that surface is out of scope. Recommend treating the rule as binding on any future bulk-export surface specifically, not the operational table. Flagging per the rule's own "if one seems wrong, say so" instruction, not deciding unilaterally — raise with the team if this reasoning doesn't hold up.

**Still not started**: Outreach Planner endpoints (`POST`/`GET /api/outreach` — needs a `screenings → outreach_visits` link to be more than a shell, deliberately deferred past today), Teach Mode, Clinical Lead sign-off on all draft copy (advice-line templates, reminder/escalation SMS text, the ORANGE Shona/English copy, the narrative prompt), Shona translations (`explanation_shona`, Shona advice/reminder text), auth role rename (`hospital`/`cimas` → target `practitioner`/`clinical`), phone-number hashing decision above needs the team's sign-off. **Also unresolved**: the mobile app (`feat/mobile-frontend` branch) has zero working integration with the backend — `ResultScreen.js` calls the Anthropic API directly from the client instead of `POST /api/screen`, with a hardcoded placeholder API key, no persistence to the backend, and a divergent question-code set from `backend/questions.py`. Flagged to the collaborator; needs his fix before any end-to-end demo works.

Update this section at the end of each session.
