# CLAUDE.md

Read this at the start of every session. It is the shared reference for both developers on SilicaGuard. If anything here conflicts with the master reference document (`SilicaGuardcompletedocumentation_final.docx`, v4.0, FINAL), the reference document wins — flag the conflict and update this file.

## Project identity

SilicaGuard is an occupational lung health screening system for Zimbabwe's mining workforce. A health worker takes an Android app to a mine site, delivers a fifteen-minute group education session using illustrated cards on the phone, then screens each miner in about ten minutes with no doctor present. The system classifies each worker into one of four risk tiers, compares the result against their previous screening to detect deterioration early, and tells each miner the single most important thing he personally should change — drawn from his own answers. Where a referral is needed it routes it to the right facility with a deadline, pre-alerts that facility, and chases the worker until attendance is confirmed. Miners who miss the outreach day self-screen by dialling a USSD code from any phone, with no internet and no cost. Everyone receives their result and reminders by SMS. Hospitals see every referral and whether it was completed. Mining companies get the compliance reporting their legal occupational health obligations require, and insurers get early warning on respiratory risk in their insured members. Silicosis is the first module; tuberculosis is next, on the same infrastructure.

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
4. **Population Health Intelligence** — weekly job producing site-clustering analysis and a plain-language narrative for hospital/employer dashboards.

The mobile app UI, the dashboards, SMS dispatch, Teach Mode cards, the USSD decision tree, the outreach planner and the compliance export are **not AI**. They are good software engineering. Never describe them as AI — overclaiming weakens the four real claims.

## Non-negotiable rules

Copied verbatim from the reference document's implementation map. These are not up for reinterpretation in the course of normal feature work — if one seems wrong, say so and raise it rather than quietly deviating.

- Hard red-flag overrides live in Python code, outside the model call. The model can never downgrade a RED.
- USSD handlers must respond within 10 seconds and complete a session within 180 seconds. No LLM call inside a USSD session.
- The employer role must be blocked from individual clinical records at the authorisation layer, with a test proving it.
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

Last updated: 2 August 2026 (sprint Day 2). Branch `be/phase-a-schema-migration`, not yet merged to `main` — awaiting review.

**Phase A (schema migration) complete on its branch:**
- `screenings.risk_level` renamed to `tier`, now four values (`GREEN`/`YELLOW`/`ORANGE`/`RED`, CHECK-constrained) instead of the old three (`LOW`/`WATCH`/`REFER_NOW`). The old REFER_NOW bucket was mechanically split into RED (a hard safety trigger fired — severe breathlessness/chest pain, current TB, prior lung diagnosis) vs ORANGE (score-only, no trigger) — **this split reuses existing logic, not new clinical judgment, and still needs an explicit Clinical Lead pass**, especially the ORANGE Shona/English copy, which is reused verbatim from the old REFER_NOW text and still reads as more urgent ("today") than a 14-day window warrants.
- Added `screenings.previous_screening_id` (populated — every screening links to the worker's most recent prior one), `advice_line` (column exists, always `null` — personalised advice generation isn't built), `provisional` (mirrors `offline_fallback_used`).
- `xray_results` and `whatsapp_messages` tables dropped, along with `referrals.xray_completed`.
- Added `employers`, `campaigns`, `outreach_visits`, `facilities` tables (schema only — no endpoints read/write them yet; seed script populates one row each).
- `referrals` status is now `open → pre_alerted → reminded → attended → closed → escalated` (was `PENDING`/`XRAY_UPLOADED`/`COMPLETE`); `deadline` is set on creation (RED = 48h, ORANGE = 14 days, per the doc's fixed windows); `attended_at`/`closed_at` replace the old single `completed_at`. Status auto-advances to `pre_alerted` when the hospital SMS succeeds. `reminded`/`escalated` exist in the schema but nothing sets them yet — the reminder/escalation scheduler (Smart Referral Router) isn't built.
- All 32 tests pass (was 28); `docs/API_CONTRACT.md` and `backend/scripts/seed_demo_data.py` updated to match.
- No ALTER-based migration — this was a from-empty schema rewrite (`CREATE TABLE IF NOT EXISTS`), per the documented SQLite/MVP-stage approach in `SKILL.md`. Any existing local `backend/data/silicaguard.db` needs deleting and re-seeding.

**Still not started**: hard-coded safety overrides living in Python outside the model call (currently still only in the Gemini prompt text — a non-negotiable-rule violation), Longitudinal Deterioration Detection logic (the link exists, the comparison doesn't), Smart Referral Router (facility matching, reminder cascade, escalation task — only the initial deadline is set), personalised advice generation, Teach Mode, Outreach Planner endpoints, enterprise CSV upload, employer role + the employer-privacy-boundary test.

Update this section at the end of each session.
