# Mobile → v2 contract: gap list

Written 14 November 2026 by Takudzwa's session, read from `mobile/src/` and `docs/API_CONTRACT.md` (v2 section, as on `main` at `fcc6ec9`). **Nothing here is built.** Every row says what the app does today, what v2 offers, and what is missing. Where a question is for Panashe it is numbered Q1–Q8 at the end.

## What production holds today (checked 14 November, read-only GETs)

| Route | Result |
|---|---|
| `GET /api/health` | `database: up`, `schema: ok` |
| `GET /api/v2/instrument/active` | **404** — no instrument loaded (Clinical Lead's deliverable, §12.5) |
| `GET /api/v2/instrument/versions` | `[]` |
| `GET /api/v2/content?language=en&channel=app` | `count: 0` |
| `GET /api/v2/consents/texts/CORE` | **404** — no approved consent text |
| `GET /api/v2/consents/permissions` | live, six permissions |

So the app **cannot be moved to v2 and tested end to end against production yet**: there is no instrument to screen against, no consent text to show, and no words to display. The contract says this is correct sequencing. It also means mobile work now is limited to what can be built and tested against fixtures.

## The gaps, screen by screen

| # | Where | Today (v1) | v2 target | Gap |
|---|---|---|---|---|
| 1 | `IntakeScreen` | Collects name, phone, mine site. Phone is the identity key (`POST /api/workers`, 409 → look up by phone). | `POST /api/v2/persons/resolve` | Phone must stop being a key. Intake has no field for the participant code on the worker's card, age band, sex or language. No place to show the participant code after resolve. |
| 2 | (none) | **No consent screen exists anywhere in the app.** | `GET /consents/permissions`, `GET /consents/texts/{code}`, `POST /consents`; screening returns `403` without consent | A consent screen rendered from the server definition. Blocked on approved consent text (404 today). Also needs queueing when offline (Q1, Q6). |
| 3 | `QuestionScreen` | Nine questions hard-coded with English and Shona text and numeric scores, "synced 2026-08-05". | `GET /api/v2/instrument/active` + `GET /api/v2/content` | Questions and words must come from the instrument and the content store, not the app. This is also a rule: no patient-facing string lives in app code. App has no Ndebele. Blocked on instrument version one and content. |
| 4 | `offlineScore()` in `QuestionScreen.js:128` | Summed scores, bands ≤8/≤16/≤24, two overrides. **Verified from the code**: a miner answering "getting dressed / resting" for breathlessness (score 5) and the lowest option elsewhere totals under 9 and reads **GREEN**; nothing overrides it. | Device runs the same rules as the server | Port `services/predicates.py` to JavaScript (item 1.14a), with the server's own test cases as fixtures, and delete `offlineScore`. Evaluate over the **whole** instrument, render only `channel_questions` (contract: otherwise an unanswered red-flag rule stops firing). |
| 5 | `submitScreening` | Array of `{question_code, answer_value, answer_score}`; `POST /api/screen`; gets `tier`, `confidence`, `explanation_english/_shona`, `advice_line`, `contributing_factors`, `referral_code`, `facility_name`, `deadline` | `POST /api/v2/screenings`: map `code → value`, **no scores**, `client_session_uuid` required | The app does not generate a session UUID. v2 returns `results[]`, `primary_tier`, `referrals[]` and **no explanation text, advice line or confidence**: `ResultScreen` has no source for its copy until the content store is populated and message codes are agreed (Q7). |
| 6 | `offlineQueue.js` | Retries every failure; entry holds miner, answers, screened_by | Idempotent replay by `client_session_uuid`; per-status rules | Entry must carry the UUID, the person bundle, consent decisions and the instrument version used. Retry rules: `400` incomplete → **do not retry**, answers already saved; `403` → back to the worker; `422` → no; `503` → retry. `offline_fallback_used` becomes `offline: true`. The encryption and quarantine from 1.0.1 carry over unchanged. |
| 7 | `ReferralScreen` | `notifyReferralEmail(phone)` triggers the hospital alert email | not in the contract | v2 screening **sends nothing** (`not_sent_reason`: no messaging until 1.6b and `drop_v1`). Moving over now would stop the miner SMS and the hospital pre-alert. **Cutover must wait for messaging** (Q4). |
| 8 | `WorklistScreen` | "Refer now" list from v1 `dashboard/today`; attend via `POST /referrals/lookup/{code}/confirm-attendance` | `POST /api/v2/referrals/{code}/close` with a closed-vocabulary outcome | Close needs an outcome picker (five values from `/referrals/outcomes/vocabulary`). **No v2 route lists open referrals** for a worker or site, so the list has no replacement (Q3). |
| 9 | `HomeScreen`, `OutreachStatsScreen`, notifications feed | v1 `GET /dashboard/today`, no auth: counts **plus** today's log, watch list, refer-now items, outreach visits | `GET /api/v2/dashboard/today`: **Bearer**, counts per condition and tier only | No list data in v2, and it needs a token the app does not have. |
| 10 | `ResultScreen` history | `GET /api/workers/{phone}` (phone lookup) | `GET /api/v2/persons/{code}/sessions`: Bearer, `screening.read` | Needs a token; phone lookup should go. |
| 11 | Auth | App never logs in | identity read, sessions and dashboard all need Bearer | A **device credential** (item 1.13) is a prerequisite for rows 9 and 10. Design is open (Q2). `expo-secure-store` is now in the app, so storage is available. |
| 12 | Outreach planner, mines, facilities | `POST /api/outreach`, `GET /api/mines`, `GET /api/facilities` | **no v2 equivalent** (contract: `/api/v2/outreach/*` not built; v1 planner still serves) | Stays on v1. The v2 screening takes `site_id` and `outreach_visit_id`: confirm these are the same ids (Q5). |
| 13 | Language | English + Shona only; some strings in code | `GET /content?language=en|sn|nd&channel=app&since=` | A cache with `since` watermark; a language setting; Ndebele. Reports a row's served language, so an authoring gap is visible rather than filled. |

## What can be built now, safely, without waiting

In this order; each step is independent and reversible, and none changes what production sees until a flag is switched.

1. **`client_session_uuid`** generated when a screening starts and stored in the queue entry. Harmless on v1, required on v2, and it is what makes a retry safe.
2. **JavaScript port of the predicate interpreter**, tested against fixture instruments and the server's own expected tiers. No backend dependency, and it retires the known GREEN flaw in row 4.
3. **Content cache** with the `since` watermark. Returns empty today, which is the correct state.
4. **Consent screen**, rendered from `/consents/permissions`, behind a flag, testable against fixtures.
5. **Intake rework** for participant code, age band, sex and language.
6. **Cutover behind a flag**, not before: an approved instrument, approved consent text, content, messaging (row 7) and a device credential (row 11) all exist, and staging has rehearsed it.

## Questions for Panashe

- **Q1 — Offline first contact.** `persons/resolve` is an online call that returns `person_id`, and `consents` and `screenings` both take `person_id`. A first-time worker screened with no signal has none. Is the intended design a queued bundle (resolve, consent, screening) replayed in order, or something else? This decides the queue's shape.
- **Q2 — Device credential (1.13).** What is it, who issues it, and what happens when a phone is lost? Rows 9–11 wait on it.
- **Q3 — Worklist.** Will there be a v2 route listing open referrals and today's sessions for a worker or site? Without one, Home and Refer Now lose their lists.
- **Q4 — Messaging.** When does v2 send the miner SMS and the hospital pre-alert? The app should not be cut over before it does.
- **Q5 — Ids.** Are v2 `site_id` and `outreach_visit_id` the v1 `mines.id` and outreach ids?
- **Q6 — Consent replay.** `POST /consents` has no client UUID. If an offline consent is replayed after a lost response, does it write a duplicate record?
- **Q7 — Result copy.** Which message codes does the app render for each tier and for the referral card? The `result.*.sms` codes in the contract are SMS, not app.
- **Q8 — Device tier.** The v2 request carries no tier, so the server is the authority and the device tier is a provisional display only. Confirm that is intended, and that a device/server mismatch needs no handling.
