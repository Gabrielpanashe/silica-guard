# Strings that cannot come from this store, and why

> Promised by `content/README.md` and committed to in `docs/IMPLEMENTATION_PLAN.md` §12 item 5. Master Reference v1.0 §8.4.
>
> **Owner: Gabriel, Clinical Lead.** Every entry needs his recorded approval, exactly like a message in `messages/`. The point of this file is that an exception is *reviewed*, not that it is excused.

The rule is that every string a worker reads or hears is human-authored, clinically reviewed, versioned, and read from the content store at send time. The exceptions below are the complete list of places where that is not achievable, each with the reason and the mitigation. Two of the three are **Planned**, not Built.

A new exception is added here on a pull request Gabriel approves, with the same three columns filled in, or it is not an exception — it is a bug.

---

## 1. The "service unavailable" message when the database is down

**Status: Planned.** Arrives with USSD session persistence (`docs/IMPLEMENTATION_PLAN.md` §8, Phase Two) or sooner if the USSD route is touched first.

**Why it cannot come from the store.** The store *is* the database. A worker dialling the shortcode while Postgres is unreachable cannot be sent a message that has to be read from Postgres. Today this path returns an HTTP 503 from `database.get_db()`, and Africa's Talking shows the handset its own generic gateway error — so the worker currently sees text nobody on this team wrote or reviewed, in English, with no indication of whether to try again. That is strictly worse than a reviewed hardcoded string.

**Mitigation.** One constant, three languages, in `services/ussd_handler.py`, with this file as its review record and a test asserting the constant and this file agree. It must say that the service is temporarily unavailable, that no screening was recorded, and that the worker should dial again later — because rule 7 is *fail toward recording, never toward silence*, and a worker who believes they were screened when they were not is the failure mode that matters.

**Not yet authored.** The English draft is Gabriel's to write; the Shona and Ndebele must be **authored by a first-language health communicator, not translated** (§8.4). Deliberately not drafted here: invented local-language text in this repository is indistinguishable from reviewed local-language text a month later, and this file — the one that records exceptions to review — would be the worst possible place for it.

---

## 2. Values substituted into an approved message at send time

**Status: Built.** `services/content_store.render()`.

**Why it cannot come from the store.** A person's name, a facility name, a referral code and a deadline are data, not content. They are not reviewable in advance because they do not exist in advance.

**Why it is listed anyway.** The *message* is budget-checked and character-set-checked by its author and again by the loader. The *substituted value* cannot be: a worker whose name carries a curly apostrophe drops the whole message from 160 characters per segment to 70, and a long name can push a one-segment SMS to two. The author checked a string the worker will never receive.

**Mitigation.** `render()` returns `septets`, `gsm7` and `over_budget` for the final string and does **not** refuse to send. Refusing would mean a worker gets no result because of the spelling of their name, which trades a cost problem for a clinical one. The sender records the numbers; a pattern in them is a data-entry fix at intake, not a content fix.

---

## 3. Operational and developer-facing text

**Status: Built**, and listed to keep the boundary explicit.

HTTP error details, log lines, the dashboard's own interface copy, the USSD simulator page, and OpenAPI descriptions are not patient-facing and are not in the store. The test of whether something belongs here is **whether a worker reads or hears it**, not whether a worker's data passes through it.

The one case that looks like this but is not: the clinician-facing referral-packet and dashboard result text. A trained member of staff reads it, but it describes a specific person's clinical result, so it is versioned and reviewed like everything else — channel `clinician` in the store, with the same 480-septet budget as in-app text.

---

## What is *not* an exception

- **Anything a language model writes.** There is no exception for model-generated text on a patient-facing surface, and there will not be one. `routers/screening.py` currently returns Gemini's `explanation_english` to the mobile application's result screen; that is a **defect pending item 1.9**, recorded in `docs/IMPLEMENTATION_PLAN.md` §7 and asserted by `backend/tests/test_content_runtime_rule.py`, not a licensed exception.
- **A string that does not fit its channel.** It is rewritten by its author. Runtime truncation is never the answer (§13.1).
- **A language that has not been authored yet.** The store falls back to the authored English and reports that it did so, so the gap is visible. It never translates.
