# Validation and the research agenda

> Derived from `docs/master/MASTER_REFERENCE.md` §7 and §17 (Master Reference v1.0, September 2026). The master document wins on any conflict. The comparator figures below come from §7; the CAPTURE and qXR figures are in `docs/FIGURES.md` (Appendix B). **The Dutch exclusion study, LUDESC and Lung DT figures are cited in §7 but not listed in Appendix B** — they are internal context here and are not used in public material until Appendix B carries them.

**Current validation status: none.** No sensitivity, no specificity, no comparison against radiological confirmation, no linguistic validation, no measured screening duration. No real patient has ever been screened. This document is the plan for changing that honestly.

## Realistic performance expectations

### CAPTURE and the performance ceiling

CAPTURE (COPD Assessment in Primary Care To Identify Undiagnosed Respiratory Disease and Exacerbation Risk) is the closest analogue that exists: five symptom and exposure questions, peak expiratory flow for a subset, scored to a threshold that triages toward further testing. Developed over roughly a decade by a consortium including Weill Cornell, Michigan, National Jewish Health and Minnesota; validated prospectively in 4,325 primary-care patients and published in the Journal of the American Medical Association. **Sensitivity 48.2 percent, specificity 88.6 percent.**

Three conclusions, the most important external findings in the master document:

1. **SilicaGuard's realistic ceiling is lower than the team has assumed.** A ten-question instrument administered by a village health worker or self-administered on a keypad will not outperform a decade of consortium work in a well-resourced setting. The roadmap plans for this rather than discovering it in the field.
2. **It is still transformative, and this is the argument to make.** CAPTURE's comparator is a health system with spirometry and regular doctors. SilicaGuard's comparator is nothing at all. A tool that finds half of a population currently receiving zero screening changes outcomes.
3. **Repeat screening is the compensating mechanism.** The same worker screened every six or twelve months, compared against himself, catches a meaningful share of what the first pass missed. The longitudinal module is a core part of the clinical rationale, not a feature.

### The peak-flow question

CAPTURE pairs its questionnaire with peak expiratory flow. A mechanical meter is inexpensive, needs no power, and adds the only objective measurement to an otherwise self-reported instrument — with real complications: technique coaching, disposable mouthpieces, population-appropriate reference values. And early silicosis is a restrictive, radiological process that may not show on it; its value here may lie more in co-detecting obstructive disease. **A formal pilot evaluation question for the Clinical Lead, not a committed design change.**

### Check@ir — build from validated blocks

Check@ir's value is its construction: built on published validated instruments such as the Modified Medical Research Council dyspnoea scale, not invented questions. Every question taken from a validated instrument is a question that does not have to be defended, is already translated and studied, and makes results comparable with the literature. This is a direct instruction to the Clinical Lead (`docs/CLINICAL.md`).

### Qure.ai — the X-ray argument reframed

qXR reads a chest X-ray in under sixty seconds, is FDA-cleared and CE-marked, evaluated by the WHO for tuberculosis screening, and deployed across more than 3,100 sites in over 90 countries. SilicaGuard does not compete with this. **Qure reads the X-ray. SilicaGuard decides who should get one and makes sure the person turns up.** Two actions: the X-ray argument is reframed — SilicaGuard is the front end to radiology, increasing the yield of every image taken; and referral payloads are structured so they could one day hand off into an imaging workflow.

### LUDESC and Lung DT — the defensive answer

Both report accuracies above 96 percent — on retrospective, curated public datasets, one of 120 patients. Neither appears deployed at scale. When asked why SilicaGuard does not use deep learning, the answer is: those figures come from retrospective datasets; the closest prospectively validated real-world analogue achieved 48.2 percent sensitivity; SilicaGuard would rather report a real number honestly than a benchmark that will not survive the field.

One idea retained for the long term: a "digital twin" stripped of terminology is a persistent per-person model updated by repeated measurement — which is what a longitudinal screening record is. Cumulative exposure and trajectory modelling becomes possible once several years of repeat screenings exist. A destination, not a current activity.

### The Australian silica screening tool

Victoria's regulator commissioned a REDCap-based screening tool for the stone-benchtop industry after a silicosis outbreak — a regulator-backed, published, silicosis-specific occupational exposure instrument with a usability study attached. **The Clinical Lead reads it before finalising the exposure block.** Its usability methodology is the template for testing the SilicaGuard form with miners.

### The finding that validates the USSD channel

In a Dutch study of a mobile COPD self-management application, 76.4 percent of patients had to be excluded, 48.9 percent of those for lack of digital skills, device or internet — in one of the wealthiest countries in the world. Every smartphone-only lung-health tool in the literature quietly excludes precisely the population SilicaGuard is built for. **The USSD channel is not a convenience feature. It is the reason this system reaches anybody at all.**

## The validation questions

| Question | Why it matters | Who is needed |
|---|---|---|
| Tier-specific sensitivity and specificity against radiological confirmation | The core validation claim. Requested explicitly by Professor Mushiri. Without it no performance claim can be made. | University partner, statistician, radiologist reads, ethics-approved protocol |
| USSD-specific validation, separate from app-administered screening | The channels are administered differently and must be validated separately. Also requested explicitly. | The same prospective university partnership; pilot designed so the channels are separable |
| Calibration by site, age and exposure | A single threshold may be wrong for subgroups. | Statistician; sufficient sample |
| Linguistic validation | Back translation and comprehension testing in Shona and Ndebele. | A university language or public-health department |
| Health economics: cost per case found, cost per referral completed | Converts a technology result into a policy argument — the number a ministry acts on. | Health economist |
| Whether cumulative exposure should trigger imaging independently of symptoms | The asymptomatic early-disease problem; probably the largest determinant of sensitivity. | Clinical Lead with occupational-health input |
| Whether peak expiratory flow adds value | The only available objective measurement. | Clinical Lead; pilot sub-study |

## Institutions to approach

1. **University of Zimbabwe**, faculty of medicine and community medicine — occupational health and epidemiology. First approach.
2. **National University of Science and Technology**, Bulawayo — Midlands and Matabeleland geography, the Gwanda clinic.
3. **Chinhoyi University of Technology** — the team leader's alma mater; an existing relationship.
4. **Matsuo Iwasawa Laboratory programme, University of Tokyo** — data-science and validation methodology.
5. **Scientific and Industrial Research and Development Centre**, via the existing conversation with Professor Mushiri — national AI-strategy alignment and possible regulatory sandbox access. **An early conversation, never described as a partnership.**

### How to approach them

Do not ask for money or endorsement. Offer a dataset and a publishable study in a field where Zimbabwean data barely exists: co-authorship on the validation study, SilicaGuard providing platform, field access and data collection, the institution providing methodology, statistical rigour and academic credibility. A peer-reviewed validation paper changes what SilicaGuard is — from a competition-winning startup to evidence, and a ministry adopting evidence is a far easier decision.

**Precondition**: the founders agreement and ideally company registration complete before signing any research or data-sharing agreement. A university legal office will ask who owns the intellectual property.

## Partnership status

| Institution | Status (September 2026) |
|---|---|
| All of the above | No research partnership exists. Letter wave three (`ROADMAP.md`) opens these conversations from Week 4. |
| Professor Mushiri, SIRDC | Replied substantively; confirmed architecture alignment with the national strategy's ethical-AI principle; approved a quote; flagged device classification, data sovereignty, and that no partnership exists; requested the validation questions above. |

## What the pilot must be designed to produce

Beyond the referral-completion rate: **the first labelled dataset pairing screening responses and exposure history with radiological outcomes for this population.** That requires the referral loop to capture the radiological outcome at close, not merely confirm attendance — a schema requirement, a hospital-workflow requirement and a Ministry conversation, designed in from the start (`ARCHITECTURE.md`, the four-stage roadmap).
