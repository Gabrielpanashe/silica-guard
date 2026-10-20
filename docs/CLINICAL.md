# The clinical screening instrument

> Derived from `docs/master/MASTER_REFERENCE.md` §12 and Appendix A (Master Reference v1.0, September 2026). The master document wins on any conflict. **Owner: Gabriel, Clinical Lead.** Nothing in this document is final until it carries the Clinical Lead's name and a date. Every pull request touching clinical content requires his recorded approval (`CONTRIBUTING.md`).

The instrument is the clinical heart of the system. It is currently **on the critical path for the entire project**: ethics approval gates the pilot, the ethics submission needs the instrument at a reviewable version, and the instrument is the Clinical Lead's deliverable. No amount of engineering shortens that chain.

## Sign-off record

| Version | Status | Approver | Date | Notes |
|---|---|---|---|---|
| Deployed draft (10 questions, `backend/questions.py`) | Draft, never signed off | — | — | Built July 2026 for the Healthathon. No citations. See *Corrections required*. |
| Instrument version one | Not yet drafted | Gabriel | Due Week 6, 30 Oct 2026 (draft); Week 18, 22 Jan 2027 (signed and loaded as immutable) | See `ROADMAP.md` |

## Construction methodology

- **Build from published validated instruments** wherever one exists; write original questions only for the exposure block. Use the Modified Medical Research Council dyspnoea scale for breathlessness. Use the standard four-symptom tuberculosis screen (cough, fever, night sweats, weight loss). Consider the chronic airways assessment instruments for symptom burden. Read the Victorian stone-benchtop industry exposure tool before finalising the exposure block (`docs/VALIDATION.md`).
- **Every question and every threshold carries a citation.** The current draft contains no references at all. An ethics committee will require them; Professor Mushiri explicitly requested them; it is the difference between an instrument and an opinion.
- **Graded responses rather than yes/no** wherever the underlying variable is graded. Binary answers discard most of the signal.
- **Blocks**: identity and demographics, exposure, lifestyle, symptom core, history. The symptom core is shared across conditions. The exposure block is what changes for a new sector.
- **Patient-facing wording written separately from clinical labels**, in all three languages, authored rather than translated, against a hard character budget (`docs/CHANNELS.md`).
- **State explicitly what the instrument does not detect.**

## Corrections required to the current draft

In order of severity. To be resolved in writing by Week 2, 2 October 2026.

| # | Issue | Detail | Resolution |
|---|---|---|---|
| 1 | **Safety overrides contradict the tier rules** | The deployed overrides (`backend/services/safety_overrides.py`) force the top tier for severe chest pain and for any prior lung diagnosis. The draft places chest pain and past pulmonary history in tier three. If both ship, the override silently promotes a large share of intended tier-three cases to tier four and floods the 48-hour queue. | Clinical Lead decides which stands. The overrides list must be owned by the Clinical Lead, not inherited from code. **Highest severity.** |
| 2 | Question numbering does not match the question list | Tier two cites occasional cough as question three, but question three is sputum production. Tier one requires negative answers to question one, which is exposure duration and has no negative. Sputum production appears and then plays no part in any rule. | Renumber and reconcile. |
| 3 | One question drives two tiers | Functional decline routes to tier two as minor fatigue and to tier four as severe progressive decline, from the same binary question. | Split, or use graded options with a defined cut point. |
| 4 | Two exposure questions were dropped | Job role and wet drilling are deployed and absent from the draft. Wet drilling is the primary modifiable dust control and the basis of the tier-one advice. Job role determines exposure intensity and generalises the instrument to other sectors. | Restore both. |
| 5 | A shortcode is printed in the draft | No shortcode has been allocated; the printed code is likely already in use. | Remove. No shortcode appears anywhere until allocated. |
| 6 | A facility is hardcoded in a clinical rule | Tier three names a specific hospital. Facility routing is a separate deterministic function. The same defect exists in code: `backend/services/tier_messages.py:27-28` names Kwekwe District Hospital inside the ORANGE message. | Remove from the rule and from the message text. Confirm whether spirometry is available at the receiving facility and whether it belongs in the instruction at all — silicosis is a radiological diagnosis and lung function can be normal in early disease. |
| 7 | Tier-three referral window unstated | Tier four specifies 24–48 hours; tier three says only "priority". The system uses 14 days. | Confirm or change explicitly. |
| 8 | Re-screen intervals conflict between drafts | Current draft: tier two at three months. Earlier draft: six. The deployed prompt says three. | Decide, sign off with name and date. |
| 9 | Top-tier pathway assumes a health worker who may not exist | Immediate clinical escort and manual tracking cannot happen for a miner self-screening from his own handset at night. | Design the unattended top-tier pathway explicitly. Operational and funding question as well as clinical. |
| 10 | Unknown and refused answers are not handled | An unanswered red-flag question must never default to a negative. | Define explicit unknown and refused values and their scoring. |

## The clinical question that matters most

Silicosis is characteristically asymptomatic in its early stages. Under the current rules, a worker with fifteen years of exposure who wears a respirator consistently and reports no symptoms lands in the lowest tier with an annual re-screen — and may be exactly the person with early radiological silicosis and nothing to report.

**Decision required (Week 2, 2 October)**: whether cumulative exposure alone should raise the tier independently of symptoms, and whether a long-exposure pathway to a baseline chest X-ray should exist regardless of symptom status. This single decision probably does more for sensitivity than anything else in the instrument. It also pushes more people toward imaging, with a real cost consequence — a genuine trade-off, to be decided explicitly and recorded.

## Instrument version two — question set

Agreed structure. Response options, scores and citations are completed by the Clinical Lead using the template below. Questions that are not scored are still recorded and still form part of the instrument version. Every question carries patient-facing wording in three languages and a character-budget check.

### Block A — identity and demographics

| Code | Clinical label | Response type | Why included |
|---|---|---|---|
| `AGE` | Age in years | Integer, banded for analysis | Stratified analysis; reference values if peak flow is ever added; interpreting exposure duration. **New.** |
| `SEX` | Sex | Male, female, prefer not to say | Reference values, stratified analysis, participation. **New.** |

### Block B — exposure

| Code | Clinical label | Response type | Notes |
|---|---|---|---|
| `YEARS_EXPOSED` | Duration of active dust exposure | Banded years | Underground mining, rock-face drilling, surface crushing or hammer milling. Banding improves recall. *(Replaces deployed `YEARS_UNDERGROUND`.)* |
| `JOB_ROLE` | Primary task performed | Single select: driller, crusher/mill operator, panner, loader, other | Exposure intensity; the field that generalises to other sectors. **Restored.** |
| `WET_DRILLING` | Water suppression during drilling or crushing | Always, sometimes, never, not applicable | Primary modifiable dust control. **Restored.** |
| `PPE_USE` | Respirator use during high-dust activity | Always, sometimes, never | Graded. Specify respirator type in the wording. |

### Block C — lifestyle

| Code | Clinical label | Response type | Notes |
|---|---|---|---|
| `SMOKING_STATUS` | Tobacco smoking status | Never, former, current | Confounds every symptom; required by any validation analysis. **New.** Pack-years or a quantity band at the Clinical Lead's discretion. |

### Block D — symptom core, shared across conditions

| Code | Clinical label | Response type | Notes |
|---|---|---|---|
| `COUGH_DURATION` | Persistent cough | None, under three weeks, three weeks or more | Three weeks is the standard tuberculosis threshold. |
| `SPUTUM` | Productive cough | None, clear, discoloured | Currently unused in any rule. Give it a scoring role or remove it. |
| `BREATHLESSNESS` | Exertional dyspnoea | Modified Medical Research Council grade 0–4 | The published scale — validated, translated, interpretable to any clinician. |
| `CHEST_PAIN` | Chest pain or tightness | None, mild, moderate, severe | Graded, because the override conflict (#1) turns on severity. |
| `CONSTITUTIONAL_TB` | Constitutional symptoms | Multi-select: weight loss, night sweats, fever | Standard tuberculosis screen. Multi-select preserves which are present. *(Replaces deployed `WEIGHT_LOSS`.)* |
| `HAEMOPTYSIS` | Coughing blood | Never, past, current | Red flag. Distinguish current from historical. **New.** |
| `FUNCTIONAL_DECLINE` | Decline in work capacity over six months | None, mild, marked | Graded, to resolve #3. **New.** |

### Block E — history

| Code | Clinical label | Response type | Notes |
|---|---|---|---|
| `TB_HISTORY` | Tuberculosis history | Never, treated and completed, currently on treatment | Kept separate from other lung history — override treatment differs. |
| `PRIOR_LUNG_DIAGNOSIS` | Other diagnosed chronic lung condition | No, yes, unsure | Kept separate for the same reason. |
| `PRIOR_SCREENING` | Previously screened for lung disease | No, yes, unsure | Optional. Interpreting the first screening; measuring prior programme reach. **New.** |

## The deployed draft, for reference

What `backend/questions.py` and its three duplicated rule sets do today, so the corrections above can be checked against code. Draft copy throughout; none of it signed off.

- Ten questions: `YEARS_UNDERGROUND`, `JOB_ROLE`, `WET_DRILLING`, `PPE_USE`, `COUGH_DURATION`, `BREATHLESSNESS`, `TB_HISTORY`, `WEIGHT_LOSS`, `CHEST_PAIN`, `PRIOR_LUNG_DIAGNOSIS`, each with Shona and English wording and scored options.
- Overrides forcing RED, in code: `BREATHLESSNESS = severe`, `CHEST_PAIN = severe`, `TB_HISTORY = current`, `PRIOR_LUNG_DIAGNOSIS = yes`.
- USSD thresholds: total score ≥ 12 → ORANGE, ≥ 6 → YELLOW. Mobile offline thresholds: ≤ 8 GREEN, ≤ 16 YELLOW, ≤ 24 ORANGE, else RED, with weaker overrides. The mobile-online path asks a language model. Three different instruments in effect — `ARCHITECTURE.md` explains why this ends in Phase One.
- Re-screen intervals as shown to the miner/clinician (`backend/prompts/risk_engine_prompt.txt`): GREEN 12 months, YELLOW 3 months. Nothing enforces an interval as a scheduled recall.
- Referral windows: RED 48 hours, ORANGE 14 days.

## Pending clinical decisions carried over from the prototype

Flagged 15 August 2026 (formerly `backend/prompts/PENDING_CLINICAL_REVIEW.md`), still unresolved; both are subsumed by corrections #6 and #8 above and by the language rule in `ARCHITECTURE.md`.

1. **YELLOW re-screen interval** — code says 3 months, the previous master draft said 6. Decide.
2. **Tier wording at the message boundary** — code sends colour-free but unnumbered text ("Your risk appears low…"); the master document requires **Level 1 to Level 4** in all messages and USSD screens, because colour does not carry meaning in plain text (§2.6). The previous draft stems were: *Level 1 — Wakanaka. Ramba uchishandisa mask yako. / Level 2 — Ngwarira. Dzokera kunotariswa mumwedzi mitanhatu. / Level 3 — Enda kuchipatara mumazuva gumi nemana. / Level 4 — Enda kuchipatara nhasi.* Whether to adopt that brevity or keep the current text's specificity (hospital name, X-ray mention) is Gabriel's call — but note that `docs/SECURITY.md` requires minimal clinical detail in message text, which argues for the shorter stems, and #6 removes the hospital name regardless.

## Deliverable required from the Clinical Lead

One document, versioned and dated, carrying the Clinical Lead's name, containing:

1. For each question: internal code, clinical label, patient-facing wording in English, Shona and Ndebele, response options with values and scores, and a citation.
2. The tier rule cascade in unambiguous logic.
3. The red-flag override list as an explicit set owned by the Clinical Lead.
4. The re-screen interval per tier.
5. The referral window per tier.
6. The handling of unknown and refused answers.
7. A short section stating honestly what the instrument does not detect, including the asymptomatic early-disease limitation.

That document becomes instrument version one in the database, forms part of the ethics submission, and is quoted in the validation study. It is the single highest-value artefact any member of the team can produce at this stage.

## Appendix A — instrument specification template

Each question occupies one block. The completed document is versioned, dated, signed by name, and loaded into the instrument tables by migration.

| Field | Content required |
|---|---|
| Question code | Stable uppercase identifier. Never changed once an approved version uses it. |
| Block | Identity, exposure, lifestyle, symptom core or history. |
| Clinical label | Internal clinical name. May use clinical terminology. |
| Patient-facing wording, English | Plain language as actually asked. Within the character budget. |
| Patient-facing wording, Shona | Authored by a first-language health communicator, not translated. Within the budget. |
| Patient-facing wording, Ndebele | Authored, not translated. Within the budget. |
| Response options | Value, label in three languages, score. Explicit unknown and refused options where appropriate. |
| Conditions scored | Which conditions this question contributes to, with what weight for each. |
| Branching | Conditions under which the question is shown or skipped. |
| Citation | Source for the question and for its scoring. **Mandatory.** |
| Notes | Anything a reviewer or a future clinical lead needs to know. |

## The risk tiers

| Tier | Internal name | Message name | Meaning | Action |
|---|---|---|---|---|
| 1 | Green | Level 1 | No current symptomatic indicators. | Reinforce dust control and protective equipment. Routine re-screen. |
| 2 | Yellow | Level 2 | Cumulative unprotected exposure or mild isolated symptoms. | Targeted education. Shortened re-screen interval. |
| 3 | Orange | Level 3 | Core chronic symptoms present. Imaging indicated. | Referral with a defined window. Reminder cascade. |
| 4 | Red | Level 4 | Red-flag indicators. Possible complicated disease or active tuberculosis. | Urgent referral within 48 hours with active tracking. |

Colour is never used alone: every tier also carries a written label and an icon. Re-screen intervals and referral windows per tier remain subject to final clinical sign-off.
