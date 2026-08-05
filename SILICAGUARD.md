# SilicaGuard — Product & Technical Reference

Version 4.0 shape. This document mirrors the master reference document (`SilicaGuardcompletedocumentation_final.docx`, v4.0, FINAL) — if the two ever disagree, the `.docx` wins and this file needs updating. **As of 5 August 2026 this file reflects the artisanal-only scope pivot (see Section 13); the `.docx` has not been manually updated to match yet — see Section 13 for what still needs transferring.** For day-to-day working rules see `CLAUDE.md` and `SKILL.md`; for exact request/response shapes see `docs/API_CONTRACT.md`.

## 1. Project Identity

| | |
|---|---|
| Product | SilicaGuard — Occupational Lung Health Platform, Module 1: Silicosis |
| Deployment channels | Android practitioner app (React Native / Expo) · USSD · SMS · Web browser |
| Team | Panashe M. Chandiwana — AI & Backend Engineer · Mobile & UX/UI Engineer · Mr Gabriel — Clinical Lead |
| Pilot location | Kwekwe District, Midlands Province, Zimbabwe |
| Sprint window | 1–11 August 2026, feature freeze end of Day 8 |
| Prototype presentation | 11 August 2026 |

## 2. The Problem in One Paragraph

Kwekwe District Hospital records roughly one silicosis death a week — 50 to 60 a year in one district. Silicosis is incurable; early detection and removal from dust exposure are the only effective interventions. Zimbabwe has 500,000–1.5 million artisanal and small-scale gold miners with 19% silicosis prevalence, 6.8% TB, 18% HIV, and zero digital occupational screening infrastructure. The USAID-funded programme that used to screen this population (Kunda Nqob'iTB, 10,668 miners screened 2020–2023) lost its funding in 2024 and nothing replaced it. Formal/enterprise mining employers already run their own occupational health programmes for this reason SilicaGuard is scoped entirely to artisanal and small-scale miners — see Section 13.

## 3. Solution Overview — Three Pillars

1. **Early Detection** — every screening creates a record; a re-screen is compared against the previous one, so deterioration is caught even when the absolute risk tier hasn't crossed into referral territory.
2. **Risk Stratification** — four tiers (GREEN/YELLOW/ORANGE/RED), each with a defined clinical action, re-screen interval and communication package.
3. **Smart Referral** — a referral is a tracked workflow (route → packet → pre-alert → remind → close → escalate), not a verbal instruction that disappears.

## 4. What We're Building, and What We're Deliberately Not

| Building for 11 August | Deliberately not building | Why not |
|---|---|---|
| Practitioner Android app, offline, Teach Mode + screening | Consumer app for artisanal miners | They can't pay; everything they need already works through the health worker, USSD and SMS |
| Four-tier AI risk stratification | Chest X-ray AI | Needs imaging hardware, labelled local data and regulatory clearance we can't obtain by August |
| Longitudinal deterioration detection | Voice line / IVR | Africa's Talking Voice doesn't list Zimbabwe — unbounded external risk |
| Smart referral routing with tracked closure | WhatsApp channel | Needs a smartphone, paid data, Meta business verification, and can't reach a user outside a 24-hour window |
| USSD self-screening | Recorded audio modules | A live health worker in Shona is better, and costs a day less to build |
| SMS results, reminders, outreach announcements | Four-week message sequence | Education belongs at the moment of screening, not scattered across weeks |
| Outreach Planner with auto-generated reports | Peer champion programme | Described in the pilot plan, not built as software |
| Clinical web dashboard | Enterprise/employer module (bulk workforce upload, campaigns, employer dashboard) | Descoped 5 August 2026 per Dr Bopoto's feedback — formal mining companies already have robust pneumoconiosis programmes; see Section 13 |

## 5. Technology Stack — locked, do not introduce alternatives

| Layer | Technology | Notes |
|---|---|---|
| Backend | Python FastAPI | All API routes, business logic, AI orchestration |
| Database | SQLite (MVP) | Migrates to PostgreSQL at pilot scale |
| Mobile | React Native (Expo) | Offline-first, `expo-sqlite` local storage. **No Flutter.** |
| Mobile QR | react-native-qrcode-svg | Referral card QR generation on-device |
| Dashboard | React + Vite + Recharts + Leaflet | Clinical dashboard, role-based views (hospital staff, district health) |
| AI | Google Gemini 2.5 Flash | All four AI modules. Claude API is the documented drop-in alternative if Anthropic billing becomes available. |
| USSD + SMS | Africa's Talking, called via `httpx` directly | **Not** the official SDK — it fails with an SSL error on Windows in this environment |
| Backend hosting | Render (free tier) | Sleeps after inactivity; warm it before any demo |
| Dashboard hosting | Vercel | Static hosting, auto-deploy from repo |

**Permanently removed, do not reintroduce**: Flutter/Dart, chest X-ray AI, WhatsApp as a channel, voice/IVR, the four-week education message sequence, the enterprise/employer module. See Section 12 and Section 13 for why.

## 6. Project Structure

```
backend/
├── main.py                      # FastAPI app, router registration
├── database.py                  # Raw SQL schema + sqlite3 connection helper
├── models.py                    # Pydantic request/response schemas
├── questions.py                 # The screening question bank (shared codes with mobile)
├── prompts/
│   └── risk_engine_prompt.txt   # Gemini system prompt — never inline in Python
├── routers/                     # Thin HTTP layer — parses request, calls services/
│   ├── auth.py
│   ├── dashboard.py
│   ├── screening.py
│   └── ussd.py
├── services/                    # Business logic
│   ├── ai_risk_engine.py        # Gemini call + strict JSON parsing
│   ├── notifications.py         # SMS via Africa's Talking REST API (httpx)
│   ├── referrals.py             # Referral creation + notification trigger
│   └── ussd_handler.py          # Pure decision tree, no AI call
├── scripts/
│   ├── seed_demo_data.py        # One-command reproducible demo dataset
│   └── ussd_simulator.py        # Interactive local USSD testing
└── tests/

mobile/        # React Native (Expo) — not yet scaffolded, collaborator's ownership
dashboard/     # React + Vite — not yet scaffolded, collaborator's ownership
docs/
└── API_CONTRACT.md              # The interface contract between backend and both frontends
```

## 7. Database Schema

Raw SQL lives in `backend/database.py`. **The tables below are the v4.0 target shape** — check `CLAUDE.md`'s "Current sprint status" and `docs/API_CONTRACT.md` for what's actually live today versus still pending migration.

| Table | Key fields | Purpose |
|---|---|---|
| `workers` (currently `miners`) | `id, phone (unique, persistent identity), name, site, job_role, created_at` | The worker register. Phone number is the identity across all screenings. |
| `screenings` | `id, worker_id, previous_screening_id, tier, confidence, advice_line, channel, provisional, created_at` | One row per screening. `previous_screening_id` enables deterioration detection. |
| `screening_answers` | `id, screening_id, question_code, answer_value, answer_score` | Individual answers, retained for audit and re-evaluation. |
| `referrals` | `id, screening_id, worker_id, facility_id, urgency, deadline, status, pre_alert_sent, attended_at, closed_at` | Full referral lifecycle with timestamps on every transition. |
| `facilities` | `id, name, level, address, phone, latitude, longitude` | Facility register used by the Smart Referral Router. |
| `notifications` | `id, worker_id, channel, template, payload, sent_at, delivery_status` | Every SMS sent, for audit and delivery reporting. |
| `outreach_visits` | `id, site, scheduled_date, expected_headcount, screened_count, health_workers, report_generated` | Outreach planner. |

**Explicitly removed, not part of this schema**: `xray_results` table, `whatsapp_messages` table, `referrals.xray_completed` column, any `XRAY_UPLOADED` referral status, the `employers` table, the `campaigns` table (both removed 5 August 2026 — see Section 13).

## 8. API Routes

See `docs/API_CONTRACT.md` for the full contract with request/response examples and a LIVE vs TARGET marker per route. Summary:

| Route | Method | Purpose |
|---|---|---|
| `/api/workers` | POST, GET | Register a worker; look up by phone with full screening history |
| `/api/screen` | POST | Submit a screening; returns tier, confidence, factors, explanation, advice line, deterioration result |
| `/api/ussd` | POST | Africa's Talking USSD webhook. Deterministic tree, no model call inside the session. |
| `/api/referrals` | GET, PATCH | Referral queue; update status and record outcome |
| `/api/outreach` | POST, GET | Schedule a visit, trigger bulk SMS, retrieve post-visit report |
| `/api/dashboard/week` | GET | Weekly Population Intelligence narrative and headline metrics |
| `/api/auth/login` | POST | JWT authentication with role claim: `practitioner`, `clinical` |

## 9. The 10 Screening Questions

Defined verbatim in `backend/questions.py` (`SCREENING_QUESTIONS`), bilingual Shona/English, each with scored options: `YEARS_UNDERGROUND`, `JOB_ROLE`, `WET_DRILLING`, `PPE_USE`, `COUGH_DURATION`, `BREATHLESSNESS`, `TB_HISTORY`, `WEIGHT_LOSS`, `CHEST_PAIN`, `PRIOR_LUNG_DIAGNOSIS`. Question codes are shared between mobile and backend — see the gotcha in `SKILL.md`.

## 10. AI Services — Exactly Four Modules, Nothing Else Is AI

1. **Risk Stratification Engine** — screening answers → Gemini call with a clinical system prompt (`backend/prompts/risk_engine_prompt.txt`, authored with the Clinical Lead) → strict JSON: tier, confidence, contributing factors, plain-language explanation, and the personalised advice line drawn from the weakest answer. **Hard red-flag safety overrides are enforced in Python code, outside the model call — the model can never downgrade a RED.**
2. **Longitudinal Deterioration Detection** — on every re-screen, compares current answers against the worker's most recent previous screening. Any adverse movement in symptom or exposure trajectory raises the tier one level even where absolute values wouldn't warrant it. Says so explicitly when there's insufficient prior data rather than inferring.
3. **Smart Referral Router** — sets the urgency window (48h RED / 14 days ORANGE), matches the appropriate facility level, composes the referral packet, schedules the reminder cascade (day 3, day 7) and the day-14 escalation task.
4. **Population Health Intelligence** — a scheduled weekly job reads the preceding period's screening/referral/attendance data, identifies site-level risk clustering, and produces a short plain-language narrative for the dashboard.

**Not AI**: the mobile app UI, the dashboards, SMS dispatch, Teach Mode cards, the USSD decision tree, and the outreach planner. Never describe these as AI.

**AI governance**: the system errs upward when uncertain. No tier is a diagnosis — every output is a screening result requiring clinical confirmation. Every AI output is stored with its input for audit. The Clinical Lead validates the engine against a written 20-profile test set. No AI output reaches a patient as free-form text — patient-facing content is template-bound and clinician-approved.

## 11. Health Education & Outreach

**Teach Mode** — six illustrated full-screen cards in the mobile app, held up by the health worker during a 15-minute pre-screening group session, with a script underneath so any trained VHW can deliver it: (1) what the dust does, (2) why it's silent, (3) the mask that works, (4) water changes everything, (5) the signs that mean go now, (6) your rights (NSSA compensation). No audio, no recordings — a live person beats a recording.

**Personalised advice** — the AI risk engine's output includes a single sentence, drawn from the miner's own weakest answer, telling him the one thing that will most change his outcome (e.g. never wears a respirator → told specifically to get an N95). This line appears on the result card, the referral card, and in the result SMS. Every screening result must carry one — a result without it is incomplete.

**Outreach Planner** — a coordinator schedules a visit (site, date, expected headcount); the system bulk-SMSes registered workers at that site 3 days and 1 day before; on the day the app tracks screened count live against expected headcount; on sync, a post-visit report (attendance, tier distribution, referral list) generates automatically for the hospital dashboard.

**SMS is the only notification channel**, used narrowly for short, time-critical, actionable messages: screening result, referral reminders (day 3/7), re-screen due, outreach announcement. Never for education — a paragraph of written Shona is the wrong instrument for this audience.

## 12. Key Decisions and Constraints — what was removed, and why

| Area | Status | Why |
|---|---|---|
| Chest X-ray AI | Removed, stays removed | Needs imaging hardware we don't control, labelled local radiologist data we don't have, and regulatory clearance unobtainable by August |
| Voice line / IVR | Removed, stays removed | Africa's Talking Voice doesn't list Zimbabwe; an unbounded external risk on an 11-day sprint |
| Recorded audio education modules | Removed, replaced by Teach Mode script cards | Saves a day of recording/editing/re-takes; a live health worker in Shona is better than a recording |
| Four-week message sequence | Removed, replaced by personalised advice at the moment of screening | Education at the moment of attention beats messages scattered across weeks nobody reads |
| WhatsApp | Stays out of the MVP | Needs a smartphone, paid data, Meta business verification, and can't reach a user outside a 24-hour window |
| Flutter | Replaced by React Native (Expo) | Team decision made in v2.0; stays |
| Three-tier risk model | Replaced by four tiers (GREEN/YELLOW/ORANGE/RED) | YELLOW captures workers on a trajectory toward disease who aren't yet sick enough to refer — precisely the group nobody currently tracks |
| Enterprise Occupational Health pillar | Removed, stays removed | Formal mining companies already run their own pneumoconiosis programmes — not innovative to target them; see Section 13 |

## 13. Mentor Feedback & Scope Pivot (5 August 2026)

**Feedback received**, from Dr Bopoto (Clinical Lead / mentor): established/formal mining companies already run robust pneumoconiosis (silicosis) programmes, so building for them is not innovative. Focus entirely on artisanal and small-scale miners — the population covered by neither NSSA nor any existing occupational health programme.

**What this means**: the formal/enterprise mining sector is removed as a target user *and* as a revenue source. SilicaGuard now exists for one population only: artisanal and small-scale miners.

**What did not change**: four-tier risk stratification, deterioration detection, Smart Referral Router, USSD self-screening, Teach Mode, personalised advice, the Outreach Planner, and the platform roadmap (TB as Module 2 on the same infrastructure). All of it already served artisanal miners.

**What was removed** (see also Section 4, 5, 7, 8, 12):
- The "Pillar 4 — Enterprise Occupational Health" pillar and all its features: bulk CSV workforce upload, scheduled campaigns, the employer aggregate dashboard, statutory/NSSA compliance export.
- The `employer` role and the employer/worker privacy boundary that existed to protect it (the boundary only existed because the employer role did — it goes with it).
- The `employers` and `campaigns` database tables, dropped from the schema (not left as dead tables — see `backend/database.py`).
- The employer/insurer revenue model description.

**Who gets what, and who pays** (replaces the four-stakeholder enterprise model):
- **Artisanal miners** — the beneficiaries. Never pay.
- **Health workers (VHWs, nurses)** — the delivery mechanism. Never pay.
- **Kwekwe District Hospital / district health** — free access; sees every referral and whether it was completed.

**Sustainability — not yet resolved.** With the formal sector removed from scope, the funding model needs rework. Candidate directions under evaluation, none committed yet:
1. NSSA or MoHCC as a public health data/surveillance commissioner — they currently have no visibility into artisanal miner respiratory health.
2. Insurer or corporate social responsibility funding, positioned as population health investment rather than member risk pricing.
3. Donor/programme funding structured across multiple funders so it doesn't collapse if one exits — unlike Kunda Nqob'iTB, which depended on a single funder.

This is an open question put back to Dr Bopoto directly. Update this section once his input lands. Do not invent a confident new revenue model in the meantime.

**Mentor feedback log**

| Date | Channel | Feedback received | Action taken |
|---|---|---|---|
| 5 August 2026 | PDF response | Formal mining companies already have robust pneumoconiosis programmes — not innovative to target them. Focus only on artisanal miners, uncovered by NSSA or any existing programme. | Removed the entire Enterprise/formal-sector pillar, the employer role, and the employer revenue model. Repositioned product as artisanal-miner-only. Follow-up question sent to Dr Bopoto on realistic funding sources now that employers are out of scope. |

**Still to do**: the `.docx` master reference document has not been manually updated to match — it still contains the full "Pillar 4 — Enterprise Occupational Health" section, the employer/insurer revenue model, the Day 7 "Enterprise module" sprint-plan entry, the Day 8 employer stakeholder interview, and the enterprise API routes/schema. See the handoff checklist provided alongside this pivot for the exact sections to edit.

## 14. Demo Day Scenarios

1. **Teach Mode** (mobile) — six cards on the phone, the moment that answers Dr Gunda's request for education and outreach.
2. **Screening → tier → personalised advice** (mobile) — screen a returning miner, four-tier result, the change since last screening, then the advice line — different for every miner, drawn from his own answers.
3. **Smart referral** (mobile + dashboard) — QR referral card, SMS arrives, facility pre-alerted, dashboard status changes live.
4. **USSD reach** (any phone) — dial the shortcode, self-screen, result message arrives — reaches the miner with no smartphone and no data.
5. **Dashboards + Outreach Planner** (web) — referral queue with one-tap close, outreach planner scheduling a visit.

Use one worker throughout, screened at month zero and again later, so the deterioration detection has something real to show.

## 15. Sprint Status & Environment

Current sprint day, what's live vs. pending, and ownership are tracked in `CLAUDE.md` — update that file, not this one, as work lands. Environment variables are documented in `backend/.env.example`, one line per var, never committed with real values.
