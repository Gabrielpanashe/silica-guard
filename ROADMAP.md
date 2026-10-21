# Roadmap

> Derived from `docs/master/MASTER_REFERENCE.md` §21.4 and §22 (Master Reference v1.0, September 2026). The master document wins on any conflict. Dates are changed there first and reflected here in the same week. Updated at each phase close.

**Current phase: Phase Zero — Foundation.** Week one begins Monday 21 September 2026. Every deadline is the Friday of the week named.

## Method

The project runs in phases with entry and exit criteria rather than on fixed calendar dates, because the three hardest dependencies — ethics approval, shortcode allocation and Ministry clearance — move at institutional pace and are not within the team's control. Within a phase, work runs in two-week iterations with a written review at the end of each.

Three items start immediately regardless of phase, because their lead times are longest: the **shortcode process**, the **ethics submission preparation**, and the **founders agreement with company registration**.

The organising principle is that the team is standing at the last moment when the expensive decisions are still cheap: the database holds only demonstration data, no consent has been taken, nothing is under a data-protection obligation. **Do the irreversible things first and defer everything reversible** (`ARCHITECTURE.md`, the five irreversible decisions).

## Phases

### Phase Zero — Foundation (~4 weeks, almost entirely non-technical)

| Workstream | Tasks | Owner |
|---|---|---|
| Legal and structural | Founders agreement drafted and reviewed. Company registration started. Data-protection obligations confirmed with a lawyer. | Panashe leads, all three agree |
| Identity and presence | Domain purchased. Dedicated email created and secured. Password manager established. Website built and deployed. Social accounts created with consistent handles. Team photograph taken. | Takudzwa builds, Panashe owns accounts |
| Clinical | Instrument version two specification drafted with citations, patient-facing wording in three languages, the ten corrections in `docs/CLINICAL.md` resolved, the asymptomatic-exposure decision taken. | Gabriel |
| Technical design | Version two schema designed on paper and reviewed before any code. Instrument and rules table design. Identity resolution design. | Panashe |
| External dependencies started | Regulator contacted on shortcode and data-controller registration. Operators contacted on provisioning and reverse billing. Ethics submission requirements obtained. | Panashe |
| Engagement | Letter wave one sent. Stakeholder tracker established. Scope contradiction resolved with the mentor. | Panashe |

**Exit criteria**: founders agreement signed, website live, instrument specification at a reviewable draft, schema design agreed, wave one letters sent, shortcode process opened.

### Phase One — Core rebuild (~3 months, overlapping the end of Phase Zero)

Where the five irreversible decisions become code, while the database still holds nothing but demonstration data.

- Version two schema: people, contacts, exposure profiles, sites, sessions, per-condition results, programmes, consent records.
- Instrument, questions, options, scoring rules, thresholds and safety rules as versioned data, with instrument version one loaded from the Clinical Lead's specification.
- Deterministic classification engine as the single tier of record across both channels, safety overrides enforced in code outside and after any model call.
- Language architecture: all patient-facing strings as versioned content keyed by message code and language; character-set validator in the build pipeline; no runtime machine translation, enforced by a test.
- Identity resolution: participant codes, bundle match, human review queue, reversible merges.
- Consent capture on both channels with versioned consent text.
- Interface versioned so the mobile application and dashboard migrate in step.
- Demonstration data reseeded to a realistic distribution.
- Mobile application rebuilt to render an instrument received as data rather than hardcoded questions.

**Exit criteria**: a worker can be screened end to end on both channels against a versioned instrument, with a deterministic tier, a recorded consent, a resolved identity and a stored instrument version, with no language model anywhere on the clinical path.

### Phase Two — Channel hardening (~2 months, overlapping Phase One)

- USSD session state moved to the database, with resumption, idempotent webhooks and a graceful unavailable response.
- Delivery-receipt capture per message: accepted, delivered, failed, expired.
- Alphanumeric sender identifier registered and in use.
- Education broadcast separated from transactional messaging, with its own consent, opt-out, frequency cap and quiet hours.
- Offline behaviour verified on the floor-specification devices: airplane mode, roster pre-synchronisation, encrypted local storage.
- Standalone installer, replacing the developer-tooling dependency.
- Error monitoring and an in-application diagnostics screen.
- Screening-duration and USSD drop-off instrumentation (pilot findings that cannot be added retrospectively).

**Exit criteria**: a full screening completes on a floor-specification handset with no network, synchronises cleanly, and produces a message whose delivery is confirmed by receipt on a real handset on a real network.

### Phase Three — Pre-pilot readiness (~2–3 months, gated by external approvals)

- Ethics submission lodged and questions answered.
- Ministry clearance and District Medical Officer agreement.
- Medicines Control Authority determination on device classification.
- Data-controller registration completed; hosting sovereignty decision implemented.
- Shortcode allocated, provisioned, reverse billing agreed.
- Research partnership agreed; validation protocol written with the partner.
- Facilities onboarded, hospital staff trained on the referral-code lookup.
- Village health workers recruited and trained; written manual and user guide.
- Linguistic validation: back translation and comprehension testing with miners.
- A full dry run at a single site with consenting volunteers.

**Exit criteria**: every approval in hand, facilities trained, workers trained, dry run completed and defects resolved. The pre-pilot security checklist in `docs/SECURITY.md` signed and dated.

### Phase Four — Pilot

Six months of field operation in Kwekwe District (master document §19), monthly internal reporting, a mid-point review at three months at which the instrument may be revised as version two with a clean break in the analysis.

### Phase Five — Evaluation and validation (~3 months)

Data cleaning, analysis against the pilot indicators, validation analysis with the research partner, health-economics analysis, written pilot report, publication preparation. Resourced as seriously as the build phases — this is what converts the project from a prototype into evidence.

### Phase Six and beyond

Geographic expansion on the existing instrument; tuberculosis as the second condition on the multi-result architecture; formal-sector service launch (master document §23); wider pneumoconioses and other dust-exposed sectors; cumulative exposure modelling once multi-year data exists; national register governance agreed with the Ministry.

## Critical path

Three chains, three owners:

- **Clinical chain** (Gabriel): instrument specification → ethics submission → approval. The longest chain the team controls the start of. **The Clinical Lead is currently on the critical path for the whole project.**
- **Regulatory and telecommunications chain** (Panashe): shortcode application → operator provisioning → reverse billing. The longest chain the team does not control. Opens in week one even though the channel is not needed for months.
- **Technical chain** (Panashe, Takudzwa): schema design → core rebuild → channel hardening. The only chain that can be compressed by working harder.

## Individual deadlines

Where a date slips, it is renegotiated openly in the weekly written status, never allowed to drift silently.

### Panashe — team leader, backend and artificial intelligence

| Deliverable | Deadline | Blocks |
|---|---|---|
| Domain purchased, dedicated email created and secured, password manager and two-factor set up | Week 1, 25 Sep | Every account, the website, all correspondence |
| Letter wave one sent: ethics council, Ministry directorate | Week 1, 25 Sep | Ethics approval, which gates the pilot |
| Stakeholder tracker established and back-filled | Week 1, 25 Sep | Prevents further loss of thread status |
| Letter wave two sent: district officer, regulator on shortcode, regulator on data protection | Week 2, 2 Oct | Shortcode allocation, the longest lead item |
| Version two schema designed on paper and reviewed with Takudzwa before any code | Week 2, 2 Oct | The entire Phase One rebuild |
| Operator letters, Cimas follow-up, research development centre follow-up | Week 3, 9 Oct | Reverse billing, which determines whether the USSD channel is viable |
| Founders agreement drafted for legal review | Week 3, 9 Oct | Company registration, all institutional agreements |
| University and device authority letters | Week 4, 16 Oct | Validation study, classification determination |
| Schema and instrument tables implemented, demonstration data reseeded | Week 8, 13 Nov | Mobile rebuild, all clinical implementation |
| Deterministic engine live as the tier of record on both channels | Week 10, 27 Nov | Channel equivalence testing, offline safety |
| Language architecture, identity resolution and consent capture implemented | Week 12, 11 Dec | Ethics submission accuracy, pilot readiness |
| USSD session persistence, resumption and idempotency | Week 16, 8 Jan 2027 | Real-world USSD reliability |
| Delivery receipts, sender identifier registered, education and transactional messaging separated | Week 16, 8 Jan 2027 | Interpretation of the headline metric |
| Error monitoring, backups automated and a restore tested | Week 18, 22 Jan 2027 | Pre-pilot security checklist |
| Ethics submission lodged with the Clinical Lead | Week 20, 5 Feb 2027 | Pilot start |
| Pre-pilot security checklist signed off | Week 24, 5 Mar 2027 | Pilot start |

### Takudzwa — mobile, web, interface and design

| Deliverable | Deadline | Blocks |
|---|---|---|
| Website built and deployed on the new domain | Week 1, 25 Sep | The professional network page and the credibility of every letter |
| Real team photograph organised and taken | Week 1, 25 Sep | Website, social accounts, any application |
| Brand assets exported per platform, light and dark variants | Week 2, 2 Oct | Social launch |
| Company registration process started | Week 2, 2 Oct | Institutional agreements, research partnership |
| Two floor-specification handsets sourced and set as reference devices | Week 3, 9 Oct | All device testing and every performance claim |
| Schema and interface contract reviewed with Panashe and agreed | Week 3, 9 Oct | Mobile rebuild |
| Mobile application rebuilt to render an instrument received as data | Week 12, 11 Dec | Any instrument change without a new release |
| Offline path verified on floor devices in airplane mode, with roster pre-synchronisation | Week 14, 25 Dec | Field viability |
| Encrypted local storage, access code on open, lost-device behaviour | Week 16, 8 Jan 2027 | Pre-pilot security checklist |
| Standalone installer produced and installed on a real device from scratch | Week 16, 8 Jan 2027 | Field deployment |
| Screening-duration and drop-off instrumentation in the interface | Week 16, 8 Jan 2027 | Pilot measurement |
| In-application diagnostics screen | Week 18, 22 Jan 2027 | Remote support during the pilot |
| Sunlight and accessibility pass: contrast, touch targets, tier labels and icons not colour alone | Week 18, 22 Jan 2027 | Field usability |
| Health-worker training materials and user guide, with the Clinical Lead | Week 22, 19 Feb 2027 | Worker training |
| Dashboard updated for per-condition results and role-scoped access | Week 22, 19 Feb 2027 | Facility and coordinator use during the pilot |

### Gabriel — clinical lead

| Deliverable | Deadline | Blocks |
|---|---|---|
| Decision on the ten corrections in `docs/CLINICAL.md`, in writing, including which safety overrides stand | Week 2, 2 Oct | Instrument implementation and the whole clinical chain |
| Decision on the asymptomatic long-exposure pathway | Week 2, 2 Oct | Instrument sensitivity and the imaging cost model |
| Read the Victorian stone-industry exposure tool and the validated instruments named in `docs/CLINICAL.md` | Week 3, 9 Oct | Quality and defensibility of the exposure block |
| Instrument version one draft: all questions, blocks, response options, scores, with a citation for every question and threshold | Week 6, 30 Oct | Ethics submission, schema loading, mobile rebuild |
| Tier cascade, override list, re-screen interval per tier and referral window per tier, stated unambiguously | Week 6, 30 Oct | Rules implementation |
| Patient-facing wording in English, within the channel character budget | Week 8, 13 Nov | Content store, translation |
| Shona and Ndebele wording authored with a first-language health communicator, not translated | Week 12, 11 Dec | Language architecture, comprehension testing |
| Statement of what the instrument does not detect, including the asymptomatic early-disease limitation | Week 12, 11 Dec | Ethics submission, honest positioning |
| Clinical sections of the ethics protocol, with Panashe | Week 18, 22 Jan 2027 | Ethics submission |
| Instrument version one signed and dated, loaded as an approved immutable version | Week 18, 22 Jan 2027 | Pilot start |
| Review and sign-off of every patient-facing string in the content store | Week 20, 5 Feb 2027 | Pilot start |
| Comprehension testing with miners, back-translation check completed | Week 22, 19 Feb 2027 | Linguistic validation |
| Clinical content of health-worker training, with Takudzwa | Week 22, 19 Feb 2027 | Worker training |
| Validation protocol clinical sections with the research partner | Week 24, 5 Mar 2027 | Validation study |

## Immediate actions — the first two weeks

Master document Appendix E, in order. Everything here is either a long-lead external process or a blocker for other work.

| Action | Owner |
|---|---|
| Purchase the domain | Panashe |
| Create and secure the dedicated email | Panashe |
| Set up the password manager and two-factor authentication | Panashe |
| Build and deploy the website | Takudzwa |
| Take the real team photograph | All three |
| Create social accounts with consistent handles | Panashe |
| Draft the founders agreement | All three |
| Begin company registration | Takudzwa |
| Contact the regulator on shortcode and data-controller registration | Panashe |
| Contact operators on provisioning and reverse billing | Panashe |
| Obtain ethics submission requirements | Panashe |
| Resolve the instrument corrections (`docs/CLINICAL.md`) | Gabriel |
| Decide the asymptomatic exposure question | Gabriel |
| Design the version two schema on paper | Panashe |
| Send letter wave one | Panashe |
| Resolve the scope contradiction with the mentor | Panashe |
| Buy two floor-specification handsets | Takudzwa |
| Establish the stakeholder tracker | Panashe |

## Phase history

| Phase | Status | Closed |
|---|---|---|
| Healthathon prototype (July–August 2026) | Complete. Cimas Healthathon 3.0 won, August 2026. Dated build history in `docs/PROGRESS_LOG.md`. | 28 August 2026 |
| Phase Zero — Foundation | **In progress** | — |
