# The National Artisanal Miners Health Register

> Derived from `docs/master/MASTER_REFERENCE.md` §15 (Master Reference v1.0, September 2026). The master document wins on any conflict. Everything in this document is **Planned** — the register does not exist yet; today's database holds demonstration data only.

SilicaGuard's most valuable long-term output is not the application. It is the register. No national database of artisanal miners' occupational health exists in Zimbabwe, and its absence is why nobody can say how many miners have silicosis, where the worst-affected sites are, whether the situation is improving, or what an intervention would cost.

That is precisely why it must be built carefully. A register of identifiable health data about half a million informal workers is also, handled badly, a surveillance instrument and a serious liability.

## What the register is and is not

| It is | It is not |
|---|---|
| A longitudinal occupational health record that follows the worker across sites, employers and sectors. | A registry of who is mining where, and never a tool for identifying, policing or taxing informal miners. |
| A source of aggregate epidemiological intelligence on prevalence, exposure and geography. | A source of individual data for any employer, insurer or authority without that individual's separate consent. |
| A referral and follow-through record that proves whether care actually reached the person. | A diagnostic record. It records screening tiers and referral outcomes, not diagnoses made by SilicaGuard. |
| A national asset whose stewardship belongs with the Ministry of Health and Child Care. | A commercial dataset owned by a startup and available for sale. |

The second row is the difference between a register that miners participate in and one they avoid. If there is any credible suspicion that the register feeds enforcement, taxation or employer screening, participation collapses and the register becomes both useless and harmful. Every design decision below follows from that.

## Ownership and stewardship

SilicaGuard is the operator and technical custodian. Stewardship belongs with the Ministry. The architecture must make an eventual handover possible rather than assuming perpetual control.

- A governance structure is **proposed** to the Ministry: a small oversight group including the Ministry, the occupational health function, a research partner, and representation for the mining communities, meeting on a defined cycle to approve access requests and review use.
- Data ownership is documented in writing before the first real record: **the data subjects own their data, the Ministry stewards the collection, SilicaGuard operates it under a defined mandate.**
- A handover path is designed from the start: documented schemas, open export formats, no proprietary lock-in, a migration procedure that could be executed if the mandate ended.
- A continuity plan exists for the failure of SilicaGuard as an organisation, because a register that dies with a startup is worse than no register.

## Data classification and who sees what

Every consumer receives the least identifying form of data that answers their question — the single most important control in the design, enforced technically rather than by policy.

| Class | Contains | Who may access | Control |
|---|---|---|---|
| Identified | Name, contact, participant code, linked to clinical results. | The screening health worker for their own encounters. The receiving facility for their own referral. The person themselves. | Role-based, scoped to the specific encounter or referral. Every read audited. |
| Pseudonymised | Clinical and exposure data keyed to an internal identifier, direct identifiers removed and held separately. | Research partners under an approved protocol. Internal analysis. | Separate access path. Re-identification key held apart, released only under the governance process. |
| Aggregate | Counts, rates and distributions by site, district, sector, age band and tier, with small-cell suppression. | Ministry, provincial and district health, research partners, programme sponsors, public reporting. | Computed from a de-identified view. Small cells suppressed so an individual cannot be inferred. |
| Programme-scoped | Aggregate data for one employer- or insurer-funded cohort only. | That programme's sponsor. | Aggregate only, never individual, unless the worker has given separate and specific consent. |

An aggregate report saying that one worker at a named small mine has a red tier is not aggregate data — it identifies a person to everyone who knows the site. Suppression thresholds are set before the first report is produced.

## How stakeholders use it

| Stakeholder | What they get | What it enables |
|---|---|---|
| Ministry of Health and Child Care | District and national aggregate prevalence, tier distribution, referral completion, hot spots, trends. | The first evidence base for occupational lung disease in the informal sector; a measurable national indicator. |
| District health teams and hospitals | Their own incoming referrals, attendance confirmation, their district's aggregate picture. | Workload and radiology planning; closing the loop on referrals that currently disappear. |
| National tuberculosis programme | Aggregate co-morbidity intelligence; later, direct referral into tuberculosis services. | Case finding in a population with tuberculosis rates many times the national average. |
| National Social Security Authority | Aggregate evidence on disease burden in workers outside the compensation system. | The evidence any policy discussion about extending cover would require. |
| Research institutions | Pseudonymised datasets under approved protocols. | Validation, prevalence, exposure-response, health economics. |
| Ministry of Mines and mining associations | Aggregate site-level exposure and risk intelligence, never individual results. | Targeted dust-control interventions. |
| Insurers and employers, later phases | Programme-scoped aggregate risk intelligence. | Underwriting, prevention investment, duty-of-care evidence, funding the free channel. |
| **The worker** | Their own record, tier history and referral status. | The person screened is a data subject with rights, not only a data source. |

## Interoperability

A register that cannot exchange data with the national health system will eventually be replaced by one that can.

- Standard clinical coding for conditions and outcomes rather than private codes.
- A record structure expressible in a standard health-data exchange format when required, without redesigning the schema.
- A national patient identifier supported as an additional identity attribute if one becomes available, without depending on it.
- Open, documented export formats.
- A structured referral payload that can hand off into a radiology workflow, including an AI-assisted one (`docs/VALIDATION.md`, the Qure.ai finding).

## Data quality

| Risk | Control |
|---|---|
| Identity duplication and false merges, corrupting longitudinal analysis. | The identity design in `ARCHITECTURE.md`: merges never automatic, always reversible; telephone number never used as identity. |
| Self-reported exposure and symptom recall. | Banded rather than free-text responses; validated instrument wording; honest documentation of the limitation. |
| Channel bias — USSD self-screening produces different data quality from health-worker screening. | Channel recorded on every session and analysed separately, as Professor Mushiri asked. |
| Site naming inconsistency — informal workings are free text. | A curated site list with free text as a fallback, and periodic reconciliation. |
