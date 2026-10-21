# Patient-facing content store

> Implements Master Reference v1.0 §8.4 (language) and the channel budgets in §13.1–13.2. Reasoning lives in the master document; this file is the working format. See `docs/IMPLEMENTATION_PLAN.md` §6 for how these files become database rows.

**Owner: Gabriel, Clinical Lead.** Every pull request touching this directory requires his recorded approval (§11.4), because every string here is read or heard by a worker.

## The rule

**No runtime machine translation of anything a worker reads or hears.** Every patient-facing string is human-authored, clinically reviewed, versioned, and stored against a message code with one row per language.

That is not only about quality. Text that does not exist until the moment it is sent **cannot be clinically reviewed before it is used**, cannot be shown to an ethics committee, and cannot be reproduced afterwards to explain what a worker was told. A model drafting a translation at request time fails all three.

Four things follow at once: the Clinical Lead reviews the exact words that will reach a person; the team can demonstrate what was said; a new language is rows rather than a code change; and the register problem disappears, because the text is *authored* by a speaker of the language rather than translated into it by a machine.

## Layout

```
content/
  schema.json          JSON Schema for a content file. Validated in CI.
  messages/*.yaml      Message definitions grouped by area.
  EXCEPTIONS.md        The strings that cannot come from this store, and why.
```

`messages/` holds `example.yaml` only. The real strings are the Clinical Lead's deliverable: English within the channel budget by Week 8, Shona and Ndebele **authored with a first-language health communicator, not translated**, by Week 12 (`ROADMAP.md`).

## Languages

English, Shona and **Ndebele** from the start. Ndebele is not optional in this geography: the Midlands is genuinely mixed and one of the country's only two dedicated occupational health clinics is at Gwanda. Adding a third language to an architecture that assumes two is painful; adding it to one designed for many is data entry.

A message is not usable until all three exist. The validator enforces that for any message whose status is `approved`.

## Quality method (§8.4)

The reason machine-translated local-language health text reads as broken is **register**, not vocabulary — word-by-word translation from English is parseable and alien. So:

1. A first-language health communicator **authors** the message, rather than translating it.
2. An independent back-translation into English is checked against the intent.
3. The message is **read aloud to actual miners**, who are asked to say back what it means.

Step 3 costs a day and is exactly the evidence that strengthens an ethics submission and a validation dossier. Record the outcome in the message's `comprehension_tested` field.

## The character-set trap

A text message in the GSM 03.38 seven-bit alphabet carries **160 characters per segment**. A single character outside that alphabet forces the entire message into sixteen-bit encoding at **70 characters per segment** — so one curly apostrophe pasted out of a word processor permanently doubles or triples the cost of every message that contains it.

Characters in the GSM **extension** set (`^ { } \ [ ] ~ |` and the euro sign) stay inside seven-bit but **count as two**. The validator accounts for that.

This is why the validator runs in CI on every pull request and not as a checklist item. The failure is invisible in review, silent at runtime, and compounds on every send.

## Channel budgets

| Channel | Budget | Why |
|---|---|---|
| `sms` | 160 characters, one segment | Cost is per segment and the marginal cost per screening is already several messages (§13.2) |
| `ussd` | 182 characters **including options and navigation** | A USSD page holds roughly that much, and the question must render with its answers (§13.1) |
| `app` | 480 characters | A screen can scroll; this is a readability ceiling, not a transport limit |
| `clinician` | 480 characters | Dashboard and referral-packet text, read by trained staff |

A string that does not fit is **rewritten, never truncated at runtime** (§13.1). The local-language version is usually the longest, so the budget is checked in every language — which is the point of checking it in all three rather than just English.

## Status lifecycle

`draft` → `review` → `approved` → `retired`. An **approved** message is immutable: a change is a new `version`, because a consent text or a result message must be reproducible for any session that referenced it. The validator requires an approver and a date on anything approved, and requires all three languages.

## Validating locally

```
cd backend
./venv/Scripts/python.exe scripts/validate_content.py              # everything under content/
./venv/Scripts/python.exe scripts/validate_content.py --verbose    # per-message segment counts
```

CI runs the same script on every pull request that touches `content/`.

## Forward hook

Because content is stored as codes with per-language variants, adding an audio file reference per code and language later is a single column. Voice and interactive voice response remain out of scope, but literacy is a real constraint in this population, so the door is left on its hinges even though it stays shut (§8.4).
