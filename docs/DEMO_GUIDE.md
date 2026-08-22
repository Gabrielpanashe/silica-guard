# SilicaGuard — Demo & System Guide

Written 22–23 August 2026, ahead of the 24 August submission video, to answer one question precisely for every module: **what is this, is it really AI, is it actually working right now, and how do I show it live on camera in under a minute.** Ground-truth, verified against the real code and (where noted) the live production backend — not the master doc's aspirational description. Where the two disagree, that's called out explicitly rather than smoothed over.

Production backend: `https://silicaguard-backend.onrender.com` (Postgres/Supabase). USSD web simulator: `https://silicaguard-backend.onrender.com/ussd-simulator`. Dashboard: `https://silicaguard-dashboard.onrender.com`. Hospital referral lookup: `https://silicaguard-dashboard.onrender.com/lookup.html`.

**Warm the server before recording.** Render's free tier sleeps after inactivity — the first request after a sleep can take 30–60 seconds. Hit `/api/health` a few minutes before you start filming.

---

## 1. Which of "the four AI modules" are actually AI

This matters because CLAUDE.md's own module list slightly overclaims it, and overclaiming on camera is worse than being precise. Ground truth:

| Module | Real AI call? | What it actually is |
|---|---|---|
| **Risk Stratification Engine** | **Yes** — real Gemini (`gemini-flash-latest`) call, `prompts/risk_engine_prompt.txt` | The LLM reads the 10 raw answers and reasons about tier/confidence/contributing factors/explanation as a combination, not a formula |
| **Longitudinal Deterioration Detection** | **No** | Pure Python: compares specific answer scores to the previous screening, escalates tier one level on any worsening (`services/deterioration.py`) |
| **"Smart" Referral Router** | **No** | 100% deterministic rules: facility name-matching, fixed urgency windows (RED 48h / ORANGE 14d), fixed reminder/escalation timedeltas (`services/facility_matching.py`, `services/referral_cascade.py`). "Smart" describes the composition of rules + real side effects (SMS, referral codes), not a model |
| **Population Health Intelligence** | **Yes, partially** — the narrative paragraph is a real Gemini call | The underlying "clustering" is a plain SQL `GROUP BY site` count; the LLM's genuine contribution is judging in prose whether one site's ORANGE/RED share looks disproportionate, not a clustering algorithm |

**On camera**: say plainly that 2 of the 4 modules make a real AI call and the other 2 are deterministic engineering that make the AI-driven tier trustworthy (safety overrides can't be second-guessed by a model; the router acts consistently on whatever tier the AI assigned). That's a more credible claim than saying "four AI modules" without qualification.

**Safety overrides** (`services/safety_overrides.py`) are also not AI — four hard-coded red-flag rules (severe breathlessness, severe chest pain, current TB treatment, any prior lung diagnosis) that force RED regardless of what the model said, applied strictly after the AI call. This is the non-negotiable rule in code, worth showing: the model literally cannot downgrade a RED.

**Math/statistics, honestly**: nothing in the live API is more sophisticated than counts, percentages, a max-pick, and (as of this push) a day-gap average. The one genuine piece of applied math — a Little's-Law queueing simulation projecting screening throughput — lives only in `scripts/throughput_model.py`, a standalone script for the deck, never imported by the running API. Don't claim statistical modelling is happening inside the app; it isn't, by design, and the deck's throughput number should be sourced to that script, not to the API.

---

## 2. Risk Stratification Engine — live demo

1. Register a worker: `POST /api/workers` or through the mobile app's Intake screen.
2. Screen them with answers that land RED (e.g. `PRIOR_LUNG_DIAGNOSIS: yes` or `BREATHLESSNESS: severe`) or ORANGE (heavy exposure, mild symptoms, no red flags).
3. Show the response: `tier`, `confidence`, `explanation_english`, `explanation_shona`, `contributing_factors`, and `advice_line` — every screening carries a personalised advice line by non-negotiable rule; point out it's template-selected from the miner's own weakest answer, not free AI text (the explanation text is the free AI text; the advice line deliberately isn't, for consistency).
4. Every AI call's input/output is persisted for audit: the input via the `screening_answers` table (joined to the screening), the output as parsed fields (`tier`, `risk_confidence`, `ai_explanation_english`, `ai_contributing_factors`) on the `screenings` row — not the raw model response text verbatim, which is a small precision worth having if asked.

---

## 3. Longitudinal Deterioration Detection — live demo

1. Screen the same miner twice (use `GET /api/workers/{phone}` or the mobile app's re-screen flow — phone number is the identity, see Section 8).
2. Second time, answer one symptom/exposure question worse than before.
3. The response's `deterioration` object shows `changed: true` and a plain-English summary; the returned `tier` is bumped one level even if the raw answers alone wouldn't have warranted it — this is the whole point of the module, and it's a single before/after comparison, not a multi-point trend (see Section 9 for the new trend feature that now exists alongside it).
4. Say on camera: this is deliberately not AI — tier escalation is a safety decision, made in Python against stored scores, not asked of the model.

---

## 4. Smart Referral Router + referral tracking — live demo (no scheduler wait needed)

The full loop works end-to-end live, no need to wait for the 10-minute APScheduler tick:

1. Screen a miner to RED (or ORANGE). The response already carries `referral_code` (e.g. `SG-2HBC`), `facility_name`, and `deadline` — created synchronously inside `POST /api/screen`.
2. On mobile, tapping "Generate Referral Card" shows this real code/facility/deadline (fixed 22 August — previously the card fabricated its own fake code client-side).
3. Open `https://silicaguard-dashboard.onrender.com/lookup.html`, type the code, click **Confirm Attendance** — this is the unauthenticated hospital-facing page a real nurse would use, no login needed.
4. Switch to the main dashboard's Referral Queue (or the mobile Worklist's "Refer Now" list) — the same referral now shows `attended`, confirming both views read the same record.
5. **What's "smart" here, precisely**: facility matching (RED → nearest hospital-level facility; ORANGE → a clinic name-matched to the mine site, falling back to the hospital), a fixed urgency window per tier, and a fixed reminder/escalation cascade (RED reminds at 24h/escalates at 48h; ORANGE reminds at day 3 and day 7/escalates at day 14) — all deterministic Python, all real side effects (SMS, referral codes, hospital pre-alerts).

---

## 5. USSD self-screening — live demo

1. Visit `https://silicaguard-backend.onrender.com/ussd-simulator` — a phone-shaped keypad UI that sends the exact fields a real Africa's Talking webhook would.
2. Enter a phone number, **CALL** to dial `*384*1#`, then answer the same 10 questions one at a time, **SEND** after each.
3. At the end it creates a **real** screening/referral through the identical code path as the app — no mock data. ORANGE/RED triggers the same referral-code SMS flow as Section 4.
4. No LLM call anywhere in this path (`services/ussd_handler.py` is a pure decision tree, sums scores, checks the same red-flag triggers) — required by the 10-second Africa's Talking response limit, and worth stating on camera as a deliberate engineering choice, not a missing AI feature.
5. A CLI version (`backend/scripts/ussd_simulator.py`) also still works if a terminal demo reads better than the browser one.

---

## 6. Outreach Planner + bulk SMS — live demo

1. Schedule a visit: `POST /api/outreach` (site, date, expected headcount) — from the dashboard's Outreach Planner panel or the mobile Home screen.
2. **On-demand bulk-send (new, 22 August)**: `POST /api/outreach/{id}/send-now`, authenticated — sends the 3-day/1-day announcement SMS to every registered worker at that site immediately, through the exact same send function the scheduler uses. This exists specifically because the scheduled version only fires from a background job up to 10 minutes later, and only once truly inside its window — not something you can wait out on camera.
3. Once the visit date passes, `GET /api/outreach` and the unauthenticated `GET /api/dashboard/today` both compute the same post-visit report (screened/attended/pending/high-risk, tier distribution, referral list) live from the linked screenings — never a stale cached blob.

---

## 7. Teach Mode — what it actually is right now, said plainly

The master doc's Teach Mode is **six illustrated full-screen cards in the mobile app**, held up during a 15-minute pre-screening group session. **This in-app UI is genuinely not built** — no stub, no placeholder screen, confirmed by a repo-wide search. There was no safe way to design and verify six new illustrated screens blind, this close to submission, without design assets or a way to test a new mobile build in this environment.

**What exists instead (22 August, new)**: the same six topics — dust danger, why it's silent, the mask that works, water suppression, the red-flag signs, NSSA rights — as short EN+Shona SMS templates (`services/education_messages.py`), broadcastable on demand to every miner at a site via `POST /api/education/broadcast` (authenticated, dashboard-triggered), reusing the exact bulk-send mechanism built for Outreach.

**Live demo**: pick a site with registered miners, `POST /api/education/broadcast {"site": "...", "topic": "mask_that_works"}`, show the sent count and the real SMS log entry in the `notifications` table (`template = "teach_mode_tip_mask_that_works"`).

**Say this outright on camera**: this is a pragmatic SMS-channel demonstration of the health-education concept, not the in-app illustrated cards — those remain future work. Stating the substitution explicitly is more credible than letting it look like the full feature.

---

## 8. Unique identity, repeat screenings, and viewing all screened miners

- **Unique ID**: `miners.phone` — unique, plaintext (not hashed; see the tension flagged in CLAUDE.md's "Phone-number hashing rule" note — a genuine, acknowledged, unresolved item, not part of this push). Everything else hangs off `miner_id`.
- **How a repeat visit gets detected**: the mobile app calls `POST /api/workers` first; a `409` (already registered) triggers `GET /api/workers/{phone}` instead, pulling the real miner ID and full history. This is what turns a second visit into a re-screen rather than a duplicate registration.
- **Viewing every screened miner — already built, not a gap**: `GET /api/miners` (authenticated) returns the full roster with `screening_count`, `last_screened_at`, `latest_tier`; `GET /api/screenings` returns every screening across every miner/channel. Both are already live on the dashboard (Miners directory table with an expandable per-miner history row, plus a separate Activity Log panel) — this existed since 10 August, it just was never mentioned in CLAUDE.md's own log until this pass.

---

## 9. Repeat-screening stats — the gap that's now closed (22 August)

Before this push, there was genuinely no graph or stat anywhere for "how long between this miner's screenings" — only a flat chronological list. Now:

- `GET /api/workers/{phone}` includes `days_since_previous` per screening (null for a miner's first/oldest screening).
- `GET /api/dashboard/week` includes `avg_rescreen_interval_days` — the mean gap across every miner screened more than once, population-wide.
- Both are pure Python `datetime` arithmetic over existing timestamps — no schema change, no new library.

**Live demo**: pull up a real repeat-screened miner in the dashboard's Miners directory (expand their row) or hit `GET /api/workers/{phone}` directly — show the day-gap number, then point at the headline `avg_rescreen_interval_days` stat.

---

## 10. Offline mobile module — live demo, and it's genuinely fast

- **Trigger**: any fetch failure inside `ResultScreen.js`'s screening submission — no explicit timeout, no airplane-mode-specific check, just a plain rejected promise. In true airplane mode this rejects almost immediately.
- **Recovery**: purely focus-driven — `HomeScreen`'s `useFocusEffect` retries the whole pending queue every time Home regains focus, plus a manual **"Retry now"** button. There is **no fixed interval or sleep timer anywhere in this path** — nothing to wait out.
- **Demo script**: turn on airplane mode → complete a screening (queues instantly, offline tier shown from the client-side mirror of the same scoring thresholds) → navigate to Home → banner shows "N screening(s) waiting to sync" and the header pill now honestly reads OFFLINE (fixed 22 August — it used to hardcode LIVE even here) → turn airplane mode off → tap **Retry now** (or just navigate away and back) → banner clears, pill reads LIVE again.
- **Known, accepted limitation**: no true network-connectivity check exists (no NetInfo dependency, deliberately not added this close to submission) — the LIVE/OFFLINE pill is derived from "is anything currently queued," so a phone that's offline with nothing queued yet still shows LIVE. Worth knowing if a judge asks a pointed question, not worth fixing under this deadline.

---

## 11. The dashboard

Two live pages, `dashboard/index.html` (coordinator/hospital login) and `dashboard/lookup.html` (unauthenticated hospital referral-code entry). As of this push: real Chart.js visualisations (tier distribution, site breakdown, per-miner trend) and a Leaflet map of every hospital/clinic facility replace the previous plain CSS-bar "charts" — see the dashboard section of CLAUDE.md's sprint log for what shipped. Framework note for anyone asked about it on stage: the documented target stack is React+Vite+Recharts+Leaflet; a full rewrite was deliberately not attempted 1–2 days before submission (no way to build-and-verify a new toolchain blind in this environment), so this upgrade keeps the zero-build-step architecture and uses Leaflet for real while treating Chart.js as the pragmatic charting choice instead of Recharts specifically. Documented as intentional technical debt, not hidden.

---

## 12. Non-negotiable rules — quick verification checklist

| Rule | Verified how |
|---|---|
| Hard red-flag overrides live in Python, outside the model call | `services/safety_overrides.py`, applied after the AI call and after deterioration escalation — the model can never downgrade a RED |
| USSD responds within 10s, no LLM call in-session | `services/ussd_handler.py` is a pure decision tree — confirmed no network/model call anywhere in the file |
| Every screening stores AI input+output for audit | Input via `screening_answers`, output via parsed fields on `screenings` — see Section 2's precision note |
| Full offline screening + clean sync | Section 10 — code-complete, demo script above |
| Phone numbers hashed at rest, never in an exportable table | **Not currently true** — `miners.phone` is plaintext, operationally necessary (SMS/USSD/lookup all need it); flagged as an open, acknowledged tension in CLAUDE.md, not resolved by this push |
| Every result carries a personalised advice line | `advice_line`, always populated, template-selected from the miner's weakest answer — verified in Section 2's live response |
