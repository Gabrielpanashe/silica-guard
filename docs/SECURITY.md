# Data governance, security and ethics

> Derived from `docs/master/MASTER_REFERENCE.md` §14 and §16 (Master Reference v1.0, September 2026). The master document wins on any conflict. The team is not legally qualified; the specifics must be confirmed by a lawyer and directly with the relevant authorities. **Built** = true today (audited 18 September 2026); **Planned** = specified, not yet in place.

The standard applied: the system holds sensitive health data about a vulnerable population, and it is built as though a breach would be both a legal event and a personal catastrophe for the people in it, because it would be.

## Legal obligations — all Planned, several before the first real record

- Zimbabwe's **Cyber and Data Protection Act** treats health data as sensitive personal information, requires data controllers to register with the data protection authority, and requires a data protection officer. Assume this must be complete before the first real record.
- **Research ethics approval** from the Medical Research Council of Zimbabwe before screening real people under a protocol. The submission needs the instrument at a specific version, consent documents in all three languages, data flows, retention period and withdrawal mechanism.
- **Medical device classification** with the Medicines Control Authority of Zimbabwe requires a formal determination. The system is designed to sit outside device classification; obtaining the determination is a pre-pilot checklist item. **It is never described as settled.**
- **Ministry of Health and Child Care clearance** at national and district level before any deployment.

## Consent design — Planned, a schema decision that must exist before the first real record

Consent is layered, recorded as data, and separated into distinct permissions rather than bundled.

| Permission | Scope | Notes |
|---|---|---|
| Screening and referral | The core service: screening, tier, referral, and the messages required to deliver that. | Required to proceed. |
| Longitudinal record | Retention for comparison at future screenings. | Separable — a worker may accept screening and decline retention. |
| Contact by message | Result messages, reminders, escalation. | Required for follow-through. Distinct from education broadcast. |
| Education broadcast | Unsolicited health education messaging. | Separate consent with a working, permanent opt-out. |
| Research and national statistics | De-identified data for validation, research, aggregate reporting. | Separate and refusable without losing the service. |
| Employer disclosure | Any disclosure of individual results to an employer or programme sponsor. | **Future phase only.** Separate, specific, refusable. Never bundled. |

For USSD, consent is a short statement in spoken register followed by an explicit keypress, recorded with a timestamp and the version of the consent text displayed. Consent text is versioned content like every other patient-facing string.

**Today**: no consent table, no consent step on either channel, education broadcast has no consent or opt-out.

## The employer boundary — the most consequential governance rule

If an employer or insurer funds screening, that organisation **never receives individual results** without separate, specific and refusable consent from the worker. It receives aggregate exposure and risk intelligence. Any individual fitness-to-work communication goes through a clinician, never through a data interface.

Built into the programme model now, before any commercial pressure exists, it is defensible to a union, a ministry and an ethics committee. It is also commercially load-bearing: it is the reason workers answer honestly rather than concealing symptoms to protect their jobs, and honest answers are what make the data worth paying for. The technical control is that programme scoping is enforced at the data-access layer, with a test that attempts cross-programme access and confirms it fails (`ARCHITECTURE.md`, the nullable programme reference).

## Data sovereignty — decision due before the pilot

Hosting is currently outside Zimbabwe (Render, Oregon; Supabase, eu-west-1), a gap relative to national policy expectations that Professor Mushiri has already flagged. Three honest options: accept and disclose it for the pilot; move to in-country hosting; or split the architecture so identifiers remain in Zimbabwe while de-identified analytics run elsewhere. Any is defensible if chosen deliberately and explained. What is not defensible is being asked and having no answer.

## Ownership of the register

A national register of workers' occupational health data should not be owned by a startup, and saying so first is what protects the project. SilicaGuard is the **operator and technical custodian**; stewardship belongs with the Ministry of Health and Child Care, with a defined governance structure and handover path. Stated in the first substantive Ministry meeting, unprompted. Detail in `docs/REGISTER.md`.

## Threat model

| Threat | Realistic scenario | Primary control | Today |
|---|---|---|---|
| Lost or stolen field device | A handset lost at a mine site with queued screenings and a pre-synced roster. | Encrypted local storage, access code, minimal retention, server-side revocation, remote wipe. | Unencrypted AsyncStorage, no PIN, no protocol. |
| Credential compromise | A reused or phished password gives access to hosting or the database. | Password manager, unique credentials, two-factor by authenticator, least privilege, no shared logins. | Personal accounts; no vault; Phase Zero. |
| Insider or over-broad access | A dashboard account sees far more than needed; an engineer queries production out of curiosity. | Role-based access scoped to site, facility or programme; read auditing; production access restricted and logged. | Two flat roles; no read audit; production queried directly for diagnosis. |
| Data exposure through a test or demo | A staging demo sends a real message; production data copied to a laptop. | Separate credentials per environment; synthetic data outside production; prohibition on copying production data. | One environment; one credential set. |
| Message misdelivery | A result goes to a recycled number now held by a stranger. | Number verification, delivery-failure handling, reverification of dormant contacts, minimal clinical detail in text. | None; ORANGE text names an X-ray and a hospital. |
| Interception in transit | Data intercepted between device, gateway and backend. | Transport encryption everywhere, certificate validation, webhook signature verification where supported. | HTTPS on Render and Supabase; no webhook verification. |
| Public endpoint abuse | The open referral lookup is enumerated to harvest data. | Non-sequential codes from a restricted alphabet; rate limiting; lockout; minimal data returned; all lookups logged. | Codes non-sequential (built). No rate limiting, no lockout, no lookup log. |
| Dependency compromise | A vulnerable or malicious package enters the build. | Pinned dependencies; vulnerability scanning in CI; high severity blocks merge. | Backend requirements largely unpinned; no CI. |
| Coercion or pressure to disclose | An employer, official or other party pressures the team for individual results. | The employer boundary; a documented refusal position; a governance process; consent records. | No consent records exist to point to. |
| Loss of data | Corruption, deletion, provider failure. | Automated backups, tested restores, recovery objectives, reversible migrations. | No backups configured beyond the provider default; no restore ever tested. The 6 September Supabase pause was recovered by a dashboard restore, not a backup. |

## Controls by layer

| Layer | Control |
|---|---|
| Transport | Encryption in transit on every connection including gateway callbacks. No unencrypted endpoint in any environment. Webhook payloads verified where the provider supports signing. |
| Storage at rest | Encryption at rest. Direct identifiers separated from clinical content into distinct tables with distinct access paths. National identity numbers, if collected, stored only as a salted hash. |
| Key management | Secrets in the hosting platform's secret store and the vault. Never in the repository, a chat message or a log. A secret exposed once is rotated immediately and the exposure recorded. |
| Application | Input validation through request schemas. Parameterised queries only. Rate limiting on public endpoints. Idempotency on webhooks and synchronisation. No personal data in error messages. |
| Authorisation | Role-based least privilege. Every clinical read scoped to the requester's legitimate relationship with that record. |
| Device | Encrypted local storage, access code, minimum pre-synced data, clearing of synced records, lost-device procedure with server-side revocation. |
| Messaging | Minimal clinical detail. A message says a result requires attention and directs to a facility; it does not name a suspected disease on a handset that may be shared. |
| Audit | Append-only audit of clinical reads and writes, consent changes, merges, exports and administrative actions, retained and reviewable. |
| Backup | Automated encrypted offsite backups; restore tested before the pilot and at least once during it. A backup that has never been restored is not a backup. |
| Build and supply chain | Pinned dependencies, vulnerability scanning, secret scanning, protected `main`, review before merge. |

## Roles and permissions — Planned

| Role | Can see | Cannot see |
|---|---|---|
| Village health worker | People they are screening at their assigned site, their own encounters, the pre-synced roster for that outreach. | Other sites, other workers' encounters, national data. |
| Facility user | Referrals directed to their facility; the lookup and confirmation function. | Screenings with no referral to them, other facilities' referrals, aggregate national data. |
| District coordinator | Aggregate and operational data for their district; referral ageing. | Identified records outside their district; clinical detail beyond what coordination requires. |
| National stakeholder | Aggregate views with small-cell suppression. | Any identified record. |
| Researcher | Pseudonymised extracts under an approved protocol. | Direct identifiers and the re-identification key. |
| Programme sponsor | Aggregate data for their own cohort only. | Individual results; anything outside their cohort. |
| Administrator | System configuration, instrument versions, user management. | Routine clinical browsing. Administrative access is not a licence to read records; every read audited. |
| The person screened | Their own record and referral status. | Anyone else's. |

**Today**: two roles, `hospital` and `cimas`, from environment-variable credentials (`backend/routers/auth.py`), gating only whether the dashboard's authenticated routes respond at all.

## De-identification and analysis — Planned

All analysis, dashboards and reporting run against a de-identified view by default. Direct identifiers are removed, not masked, and the re-identification key held separately under the governance process. Small-cell suppression on every aggregate output, thresholds set in advance. Site-level reporting considered carefully: a small workings with few workers is close to identifying and may need grouping upward. **Today**: every dashboard number is computed on the identified tables.

## Incident response — Planned, written before it is needed

1. **Detect and contain.** Revoke the affected credential or device access immediately. Containment before investigation.
2. **Assess.** What data, how many people, identified or not, still exposed?
3. **Record.** A written incident log started at the moment of detection.
4. **Notify.** The data protection authority and affected individuals as the law requires, through district and facility structures where direct contact is not practical.
5. **Remediate.** Fix the cause, verify the fix.
6. **Review.** A blameless written review within two weeks, changes tracked to completion.

Incident owner: the team leader, unless the incident concerns his access, in which case the mobile engineer. Authority and ethics-committee contact details recorded before the pilot.

## Security roadmap

| Phase | Security work |
|---|---|
| Zero | Password manager and two-factor across all accounts. Secret scanning and dependency scanning in CI. Separate credentials per environment. Written lost-device procedure. |
| One | Identifier/clinical separation in the new schema. Encryption at rest. Hashed national identity numbers. Consent records. Role model implemented. Audit logging of clinical reads and writes. |
| Two | Device encryption and access code. Rate limiting and lockout on the public lookup. Message content minimisation. Backup automation and a tested restore. |
| Three | Data-controller registration complete. Sovereignty decision implemented. Independent security review if a partner or budget allows. Incident response rehearsed. Pre-pilot checklist signed. |
| Pilot and beyond | Periodic access review, audit review, restore testing, dependency updates, threat-model review on any material architecture change. |

## Pre-pilot security checklist

No real screening takes place until every item is true and the list has been signed and dated.

- [ ] Data-controller registration complete and a data protection officer named.
- [ ] Ethics approval granted, with the approved consent texts loaded as versioned content.
- [ ] Encryption in transit and at rest verified, not assumed.
- [ ] Identifiers separated from clinical content; identity numbers hashed.
- [ ] Role-based access implemented and tested by attempting access that should fail.
- [ ] Audit logging active for clinical reads, writes, merges, exports and consent changes.
- [ ] Backups automated and a restore successfully tested end to end.
- [ ] Device encryption, access code and lost-device procedure in place; health workers trained on it.
- [ ] Staging and production fully separated; no possibility of a test message reaching a real person.
- [ ] Public lookup rate-limited and monitored.
- [ ] Incident response plan written, owner named, authority contacts recorded.
- [ ] No production data on any personal device or personal account.

Signed: ______________________ Date: ____________

## Phone-number storage — documented tradeoff, expiring

`miners.phone` is stored in plaintext because it is the operational identity for SMS delivery, USSD caller lookup and `GET /api/workers/{phone}`, and a one-way hash breaks all three. This was an acceptable prototype tradeoff and **ceases to be acceptable the moment real patient data exists**. The schema rebuild moves contact numbers to an encrypted `contact` table separated from clinical content (`ARCHITECTURE.md`, decisions 1 and 2), which resolves it.
