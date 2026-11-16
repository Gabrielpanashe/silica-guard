# Channel engineering

> Derived from `docs/master/MASTER_REFERENCE.md` §13 (Master Reference v1.0, September 2026). The master document wins on any conflict. **Built** = true today; **Planned** = specified, not yet in place. First audited 18 September 2026 against the prototype; **re-audited 1 November 2026** after Phase One's backend rebuild, so the markers in this file describe the code as it stands rather than as it stood in September.

Two entry channels feed one backend; the dashboard is a consumer. The USSD channel is not a convenience feature or a fallback — it is the reason this system reaches anybody at all (`docs/VALIDATION.md`, the Dutch exclusion finding).

## USSD

The engineering is the easier part. The difficult parts are three, and only one is within the team's control.

### The shortcode — Planned, longest lead item in the project

Numbering is allocated through the regulator and then provisioned separately by each mobile operator; a code on one network does not work on another. Each operator carries a setup cost and monthly rental. A multi-month regulatory and commercial process that runs in parallel with development and **starts in week one** (`ROADMAP.md`). **No shortcode is printed in any material until one is allocated.**

### Who pays for the session — Planned, the headline commercial ask

By default USSD is billed to the subscriber. If it costs the miner anything, he will not do it, and the channel will look like a design failure when it is a pricing failure. Required: a **reverse-billed or toll-free shortcode**, which needs a commercial agreement with each operator. This ranks above hardware donations in every operator conversation.

### Session persistence — Planned (Phase Two)

Networks terminate a USSD session at around 180 seconds total, each turn well inside 10 seconds. Ten or more questions means ten or more round trips, and the slowest users are precisely the target population.

- Move session state out of process memory into the database. **Today** `backend/services/ussd_handler.py:17` holds sessions in an in-memory dictionary: it fails on restart, fails when the hosting tier spins the instance down, fails with more than one worker process, and cannot support resumption.
- Build explicit resumption: a dropped caller who dials back is offered continue or start again; partial sessions retained for a defined window; **a partially answered instrument never produces a tier**.
- Make the webhook idempotent — operators and aggregators retry, and a retried callback must not create a second session or screening. **Today**: no idempotency.
- Define behaviour when the backend is unreachable: a health-gated graceful message rather than a raw network error. **Today**: none.

### The per-turn budget — Built 10 November 2026, and it was being broken

`CLAUDE.md`: **no language-model call inside a USSD session; under 3 s per turn, hard ceiling well under 10 s.** The first half has been enforced since the content store landed — an import-graph assertion in `backend/tests/test_content_runtime_rule.py` proves neither the handler nor its router can reach a model client by any path. **The second half was enforced by nothing.**

The final turn made **three synchronous outbound calls** on the ORANGE/RED path: the miner's result SMS, the hospital pre-alert SMS and the demonstration email, each with a ten-second timeout. Measured against a merely slow gateway — two seconds a call, well inside every one of those timeouts — one turn cost **six seconds**; the worst case is around thirty. Africa's Talking terminates the session at ten.

**What that costs is the one screen that matters.** The screening survives, because it is committed before any send. What the miner loses is the turn that tells him to go to Kwekwe District Hospital within 48 hours — for a RED self-screen, the entire clinical point of the channel. He answers every question and sees an error.

Two docstrings asserted the opposite while it was happening: the handler's said it "must return in milliseconds" and the router's said "no network calls, so this is effectively instant". Both are corrected.

The sending now runs through FastAPI's `BackgroundTasks`, so it happens after the response has gone back to the gateway. **This is the bounded fix, not the durable one** — a background task lives inside the web process, and the free tier can spin that process down. The durable fix is `docs/IMPLEMENTATION_PLAN.md` §9's queued status on `notifications` plus delivery by the scheduler, with receipts, which is Phase Two. Until then the turn is protected and a send that is lost is logged as failed rather than silently dropped.

### Content constraints — the budget is Built, the strings are Planned

A USSD page holds roughly 182 characters including question, options and navigation hints, in the GSM 7-bit alphabet. Every question in all three languages has a hard character budget; the local-language version is usually the longest. A question that does not fit is rewritten, never truncated at runtime. The Clinical Lead writes against this budget from the first draft; CI checks it.

**Built** (1 November 2026): the 182-septet USSD budget and the GSM 03.38 check are enforced by `backend/scripts/validate_content.py` as a CI gate **and again by `services/content_store.py` at load time**, so a string over budget cannot enter the database even when no pull request touched `content/`. The budget is checked in every language, because the local-language version is usually the longest. **Planned**: the strings themselves (the Clinical Lead's, item 1.6b) and the USSD handler reading them from the store rather than from hardcoded dictionaries (item 1.9).

One exception is written down rather than hidden: the "service unavailable" message when the database is down cannot come from the store, because the store is what is down. `content/EXCEPTIONS.md` records it, with the Shona and Ndebele still to be authored.

### What works today

A ten-question decision tree with deterministic scoring, a result message, referral creation on tier 3/4 and a result SMS — `backend/services/ussd_handler.py`, `routers/ussd.py`. No language-model call inside a session (the rule holds). A browser simulator at `/ussd-simulator` and a terminal simulator (`scripts/ussd_simulator.py`) post the exact fields the gateway sends. No consent step, no participant code, identity attached silently by phone number (`ARCHITECTURE.md`, decision 2), and the tree's thresholds differ from the other channels (decision 3).

## Text messaging

The headline metric depends on messages arriving. Several things about that are not yet true.

| Requirement | Why | Today |
|---|---|---|
| **Delivery receipts** stored per message, distinguishing accepted, delivered, failed, expired | A gateway acceptance proves the aggregator took the message, not that a handset received it. Without receipts, a low referral-completion rate cannot be separated into people who ignored the reminder and people who never got it — which would undermine the entire pilot evaluation. | **Not captured.** `notifications.delivery_status` records send acceptance only; no callback route exists. |
| **Registered alphanumeric sender identifier** | Until approved, messages arrive from an anonymous number — which matters for a message telling someone to attend hospital within two days. | Not registered. |
| **Honest cost model** | One mid-tier referral generates a result message, a facility pre-alert, reminders on day 3 and 7, and an escalation on day 14: five or more messages per screening before any education broadcast, potentially in more than one language. The real number is used because somebody will do the arithmetic. | Modelled nowhere yet. |
| **Education broadcast as a separate legal category** | Referral messages are transactional. Education broadcasts are unsolicited bulk messaging: own consent, a working and permanent opt-out, a frequency cap, quiet hours, and **never on the same day as referral chasing**. | **Still true**: `POST /api/education/broadcast` sends to every miner at a site with no consent, opt-out, cap or quiet hours. **The consent half is built** — `education_broadcast` is one of the six permissions and `consent.may_broadcast()` is the gate — and **cannot be wired until the v1 `miners` rows map to `persons`** (item 1.11), because the broadcast has no person to check. The route is Bearer-protected, so only the team can fire it, which bounds the exposure without excusing it. |
| **Recycled-number handling** | Sending a man's result to whoever now holds his old SIM is a disclosure of health data to a stranger. Verify at screening, stop after repeated delivery failures, reverify dormant contacts. | **The schema is built**: `contacts` carries `verified`, `verified_at`, `valid_from` and `valid_to`, and `identity.attach_contact()` records verification — which is what makes a number an attribute with history rather than a key (§8.2). **Planned**: nothing sets `verified` operationally, there is no stop-after-failures rule, and re-verifying a dormant contact needs the delivery receipts above. |
| **Minimal clinical detail in message text** | A shared handset. A message says a result requires attention and directs to a facility; it does not name a suspected disease. | Current ORANGE text names a chest X-ray and a specific hospital. |
| Two-way reply as a cheap secondary signal | Facility lookup remains the source of truth for attendance; a worker reply is useful for chasing and for detecting attendance at a facility that did not close the referral. | Not built. |

**Built**: seven senders in `backend/services/notifications.py` over Africa's Talking's REST interface (never the SDK), every send logged to the `notifications` table; result SMS for all four tiers; hospital pre-alert by SMS and email. **The endpoint is the sandbox** (`notifications.py:48`), which silently no-ops for any number not registered as a simulator number — no message has ever been confirmed on a physical handset.

## The mobile application and devices

| Requirement | Today |
|---|---|
| **Define the floor device and buy two** — an older Android, two gigabytes of memory, small screen. Nothing ships until it runs acceptably there. | Not defined. Phase Zero, week 3. |
| **Hard installer size budget.** Any dependency adding several megabytes needs justification. | No budget set. Expo Go today; EAS build config added 18 September. |
| **Under five kilobytes per screening.** Batch synchronisation, compress, never poll in the background; sync is explicit and on demand so the health worker controls when data is spent. | Unmeasured. Sync fires on every Home-screen focus. |
| **Pre-synchronise an outreach roster** before a site visit, including each expected person's prior screening summary — deterioration detection cannot compare against a record the device does not hold. The device then holds data about people it has not yet met, and that data must be protected. | Not built. Offline screenings today get no deterioration comparison. |
| **Encrypt local storage, PIN on open, clear synchronised records, written lost-device protocol with server-side revocation.** | AsyncStorage, unencrypted, no PIN, no protocol. |
| **Design for sunlight**: high contrast, no thin grey type, large touch targets for dusty or gloved hands, **never colour alone for a tier** — every tier carries a label and an icon. | Tier pills are colour + label; accessibility pass planned Week 18. |
| **Narrow handset as the design target**, tablet supported. | Built for a phone; untested on a tablet. |
| **Instrument speed as a measured quantity** — elapsed time from intake to result on every session, reported as a distribution; USSD completion and drop-off by question. If the true figure is seventeen minutes rather than ten, the team needs to know in month one. | Not instrumented. Cannot be added retrospectively — Phase Two. |
| Render an instrument received as data, not hardcoded questions. | `QuestionScreen.js` carries its own copy of the ten questions and its own scorer. Rebuild due Week 12. |

**Built**: eight screens, offline queue in AsyncStorage retried on Home focus (code-complete, **never verified in airplane mode**), real referral code/facility/deadline on the referral card, Mark Attended on the worklist, cross-site outreach stats.

## The dashboard

| Requirement | Today |
|---|---|
| Role-based access with least privilege: a facility user sees only their referrals, a site coordinator only their sites. | **Built in the backend** (1 November 2026): seven scoped roles, deny by default, scoped query helpers that narrow to nothing on a missing scope (`docs/SECURITY.md`). **The dashboard still signs in as one of the two prototype accounts** and does not use a capability, so the boundary is enforced by the backend's negative tests rather than exercised by the interface until the Week 22 rebuild. The prototype accounts stop working the moment a real user is created. |
| Read auditing as well as write auditing. | **Built** (1 November 2026): append-only `audit_log`, refusals recorded as well as successes, and reading a person's trail is itself audited. The v2 routes write rows; the **v1 Bearer routes the dashboard actually calls do not yet**, and move across with the adapter (item 1.11). |
| National and aggregate views computed from a de-identified view, never the identified tables. | Computed directly on identified tables. |
| Deterministic fallback for the narrative so a model failure degrades the dashboard rather than breaking it. | **Built** (`population_intelligence.py`). |
| Per-condition results. | **The server half is built**: `GET /api/v2/dashboard/{today|week|month}` counts per condition *and* tier, and `GET /api/v2/persons/{code}/sessions` returns a worker's history. The interface still reads the v1 single-tier routes. Due Week 22. |

**Built**: login, headline stats, tier chart, Gemini narrative, site breakdown, facility map, referral queue with attended/closed actions, outreach planner with scheduling and send-now, education broadcast, miners directory with per-miner history and trend, activity log, watch list. The hospital lookup page (`dashboard/lookup.html`) is unauthenticated by design and needs rate limiting and lockout before real use (`docs/SECURITY.md`).
