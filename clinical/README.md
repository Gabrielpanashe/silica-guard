# Clinical instrument specifications

> Implements Master Reference v1.0 §8.3 (the instrument and rules as versioned data) and Appendix A (the specification template). Reasoning lives in the master document; this file is the working format. See `docs/CLINICAL.md` for the instrument's clinical content and sign-off record, and `docs/IMPLEMENTATION_PLAN.md` §6 for how these files become database rows.

**Owner: Gabriel, Clinical Lead.** Every pull request touching this directory requires his recorded approval (§11.4).

## What this directory is for

An instrument version is **data, not code**. The questions, options, scores, tier rules and safety rules live in versioned database tables; this directory holds the reviewable source those tables are loaded from, so that a clinical change is a reviewed file diff rather than a code deployment.

```
clinical/
  instrument.schema.json          JSON Schema for an instrument file. Validated in CI.
  fixtures.schema.json            JSON Schema for a fixtures file. Validated in CI.
  instruments/<CODE>-v<N>.yaml    One approved instrument version. Immutable once status: approved.
  instruments/<CODE>-v<N>.fixtures.yaml   Answer profiles with expected tiers. The regression suite.
  examples/TEST-INSTRUMENT.yaml           A synthetic example, for reading the format.
  examples/TEST-INSTRUMENT.fixtures.yaml  The same, for the fixtures format.
```

`instruments/` is **empty**, and that is the correct state until instrument version one is approved. Everything that loads it exists: the two schemas, two validators, the database tables, the loader, the migration generator and the regression harness. What is missing is the clinical content, which is the one part nobody but the Clinical Lead can supply.

**`instruments/` is empty.** Instrument version one is the Clinical Lead's deliverable (§12.5) and does not exist yet. The example under `examples/` uses deliberately meaningless question codes (`T1`, `T2`, `T3`) and must never be loaded into any environment — see "The example is not an instrument" below.

## How a version reaches the database

1. Gabriel delivers the specification in the Appendix A format: for each question, the code, clinical label, patient-facing wording in English, Shona and Ndebele, response options with values and scores, and **a citation for every question and every threshold**. Plus the tier cascade, the red-flag override list, the re-screen interval and referral window per tier, the handling of unknown and refused answers, and a statement of what the instrument does not detect.
2. It is transcribed into `instruments/<CODE>-v<N>.yaml` and validated against `instrument.schema.json`. CI rejects a file that does not validate.
3. Gabriel approves the pull request. His name and the date go in the file's `approved_by` and `approved_at`.
4. **Regression fixtures** go in `instruments/<CODE>-v<N>.fixtures.yaml` on the same pull request, and Gabriel approves them too — an expected tier is a clinical assertion, not a test detail. Format: `fixtures.schema.json`; worked example: `examples/TEST-INSTRUMENT.fixtures.yaml`.
5. `backend/scripts/gen_instrument_migration.py <file>` writes the data migration. It refuses an unapproved file, refuses one that does not validate, and refuses one with no fixtures beside it. The generated migration **reads the YAML at upgrade time rather than copying the cascade into Python**, so the reviewed source and the loaded rows cannot diverge.
6. The migration inserts the rows with `status: approved`. From that moment the version is **immutable** — a change is a new version, never an edit, because every screening result stores the instrument version that produced it and a result whose rules were edited afterwards is uninterpretable. The generated downgrade refuses while any result references the version, for the same reason.

**The regression suite switches over on its own.** `backend/tests/test_instrument_regression.py` discovers files rather than naming them: while `instruments/` is empty it runs against the synthetic example, and the moment a real instrument and its fixtures land it uses those and stops using the example. A real instrument with **no** fixtures fails the build rather than skipping — an approved instrument whose behaviour nobody has pinned is exactly what that gate exists to prevent, and a skip is how that becomes permanent.

## Patient-facing wording is not stored here

Each question and option carries a `label_message_code` pointing at `content/`, not the words themselves. One store, one translation pipeline, one GSM-7 validator, one approval trail for everything a worker reads (§8.4). A new language is rows in the content store, not a change to any instrument file.

The `clinical_label` field **is** held here: it is the internal clinical name, may use clinical terminology, and is never shown to a worker.

## The predicate grammar

Tier rules and safety rules are boolean predicates over answers, not score bands. §9.2 states the cascade is "expressible entirely as boolean logic over answer values", and §12.2's corrections contain rules of the form *(years > 10 AND any symptoms) OR (past TB AND any breathlessness)* — a `(min_score, max_score)` table cannot express that, and flattening a boolean cascade into additive scores would change the instrument.

The grammar is **closed**: a fixed set of node types, interpreted by `backend/services/rules_engine.py` (Phase One) and by a matching JavaScript interpreter on the device. There is no expression language and nothing is ever `eval`'d.

```
predicate := {"all":   [predicate, ...]}                 every child must hold
           | {"any":   [predicate, ...]}                 at least one child must hold
           | {"not":    predicate}                        the child must not hold
           | {"answer": CODE, "in": [VALUE, ...]}         this answer is one of these values
           | {"score":  CONDITION, "gte": N}              condition score at or above N
           | {"score":  CONDITION, "lte": N}              condition score at or below N
           | {"count":  {"codes": [CODE, ...],
                         "in":    [VALUE, ...]},
              "gte":    N}                                at least N of these answered this way
           | {"unknown": CODE}                            answered unknown, refused, or not asked
```

Notes that matter clinically:

- **A score band is just one predicate.** `{"score": "silicosis", "gte": 12}` is the whole of a threshold rule; nothing is lost by using the richer form.
- **`unknown` is explicit** (§12.2 item 10). An unanswered red-flag question must never default to a negative, so "not answered" is a value the rules can test rather than a silent absence.
- **`all` and `any` do not short-circuit.** Every child is evaluated even once the outcome is known. If they short-circuited, a malformed sibling node would go unevaluated for some workers and raise for others depending on their answers, so a broken rule would be detected intermittently — the one property this engine exists to remove. The JavaScript interpreter on the device must match this, or the channels can disagree on a broken instrument.
- **`count` exists for symptom clusters** — "at least two of cough, fever, night sweats" — without writing out every combination.
- **Evaluation order per condition**, and it is not negotiable: score the answers; take the first matching tier rule in descending `priority`; apply deterioration, which may raise the tier one level; then apply safety rules **last**. §10.3 step 7 puts overrides after every other step precisely so that no earlier step, and no model, can be the final word on a red flag.
- **Safety rules raise a tier and never lower one.** The engine takes the higher of the scored tier and the rule's `forces_tier`, so a rule whose `forces_tier` sits below the scored tier records that it fired without changing the outcome. The rule code is recorded on the result either way, so a classification can be audited afterwards.

## The example is not an instrument

`examples/TEST-INSTRUMENT.yaml` exists so that the format can be read and so the rules engine has something to test against before a real instrument exists. Its question codes are `T1`, `T2`, `T3` and its labels say what they are. It carries `status: example`, which the loader refuses, so it cannot reach a database.

This is deliberate. A plausible-looking invented question set is the single most dangerous artefact this directory could contain, because it would be indistinguishable from a reviewed one a month later and might quietly become the instrument. Nothing in this repository invents clinical content. The question set in `docs/CLINICAL.md` §"Instrument version two question set" is the master document's own draft, quoted as the Clinical Lead's draft, and is not a loadable file.

## Validating locally

```
cd backend
./venv/Scripts/python.exe scripts/validate_instrument.py            # all files under clinical/
./venv/Scripts/python.exe scripts/validate_instrument.py ../clinical/examples/TEST-INSTRUMENT.yaml
./venv/Scripts/python.exe scripts/validate_fixtures.py              # the regression fixtures
./venv/Scripts/python.exe -m pytest tests/test_instrument_regression.py
```

CI runs all of these on every pull request: the shape checks as the `clinical` job, and the fixtures plus the regression suite as the `regression` job — §11.8's seventh and last gate.

An unquoted `approved_at: 2026-11-01` is fine. YAML parses it as a date and the validators normalise it before the schema sees it, because the YAML date type is a feature and the schema's spelling of it is an implementation detail you should not have to know about.
