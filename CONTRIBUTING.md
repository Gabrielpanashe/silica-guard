# Contributing to SilicaGuard

> Derived from `docs/master/MASTER_REFERENCE.md` §2.5, §11.4, §21.3 and §21.4 (Master Reference v1.0, September 2026). The master document wins on any conflict. Anything that contradicts it is wrong until the document is updated.

These rules govern code review, documentation and communication equally. They were established through the competition and the stakeholder engagement that followed, and they are rules, not aspirations.

## The five operating disciplines

1. **Never state an unconfirmed figure as fact.** Attribute it to its source, flag it explicitly as unverified, or leave it out. `docs/FIGURES.md` is the only permitted source of numbers — in code comments, prompts and UI copy as much as in a deck.
2. **Never claim a partnership that is not formally confirmed.** SIRDC, NSSA, the Ministry of Health and Child Care and Cimas are organisations SilicaGuard is in conversation with or sponsored by. None of them is a partner. Dashboard copy, README text and social biographies are all "public material" for this purpose.
3. **Be explicit and precise about what is genuinely artificial intelligence and what is deterministic engineering.** Two of the four modules make a language-model call today; the classification is moving to deterministic rules (`ARCHITECTURE.md`). Never describe deterioration detection, referral routing, the USSD tree, the dashboard or the outreach planner as AI.
4. **Name gaps and limitations before being asked.** In pull requests, in docs, in demos. Every document in this repository carries a Built / Planned marker for that reason.
5. **Keep the artisanal and small scale mining scope** unless the full team has made and recorded a deliberate decision to expand it. No formal-sector or construction language in anything public.

## Working practices

- **The master document is the reference.** `docs/master/MASTER_REFERENCE.md` is generated from the `.docx`; the `.docx` is edited, then regenerated, then the derived files under `docs/` are updated in the same week (Appendix D mapping).
- **Written weekly status**, every Friday, from each member: what shipped, what slipped, what is blocked, what is needed from the other two. Anything blocked for more than five days is escalated in that status rather than waited on.
- **A fortnightly call of no more than forty-five minutes**, agenda drawn from the blocked items.
- **One shared stakeholder tracker**, updated at the moment of sending (Appendix C template).
- **All clinical content changes are versioned and signed off by name and date.** No exceptions.
- **A phase closes with a written review** against its exit criteria and a version increment on the master document.
- **Documentation is updated in the same pull request** as the change it describes.

## Branching and release

- Short-lived branches named for the change: `be/<change>`, `fe/<change>`, `docs/<change>`, `clinical/<change>`. Long-lived branches accumulate conflicts and hide work — this repository has already lost edits that way twice.
- `main` is protected. Every change reaches it through a reviewed pull request, including changes by the person who owns that area.
- **Any pull request touching clinical content requires Gabriel's explicit approval recorded on the pull request**: the `clinical/` and `content/` directories once they exist, and until then `backend/questions.py`, `backend/services/safety_overrides.py`, `backend/services/deterioration.py`, `backend/services/tier_messages.py`, `backend/services/advice_engine.py`, `backend/services/explanation_shona.py`, `backend/services/education_messages.py`, `backend/prompts/`, and any patient-facing string in `mobile/` or `dashboard/`.
- Merging to `main` deploys to **staging** automatically. Production deploys from a **tagged commit**, deliberately, never automatically. *(Planned — today there is one environment and it auto-deploys from `main`; see `docs/STACK.md`.)*
- Every production release is tagged with a version and a short release note saying what changed clinically, if anything.
- Schema and API-response-shape changes are announced in `docs/PROGRESS_LOG.md` before merging.

## Ownership

| Area | Owner | Decides |
|---|---|---|
| `backend/` — schema, clinical engine, routers, services, migrations, security implementation, deployment | Panashe | Technical architecture, schema, security. Consults Takudzwa on the interface contract. |
| `mobile/`, `dashboard/`, `website/` — interface, device targets, field usability, brand | Takudzwa | Interface, devices, brand. Consults Gabriel on anything a worker reads, Panashe on data implications. |
| `clinical/`, `content/` — instrument, scoring, thresholds, overrides, intervals, every patient-facing string | Gabriel | Clinical content. **Nobody may override a clinical decision.** Consults Panashe and Takudzwa on feasibility and channel constraints. |
| `docs/`, `README.md`, `ROADMAP.md`, `ARCHITECTURE.md`, `CLAUDE.md`, `docs/API_CONTRACT.md`, `.env.example` | Shared | Requires agreement before changing. |
| Scope (conditions, sectors, channels); any agreement binding the company | All three, unanimously, recorded in the master document | Mentor and stakeholders as input, never as instruction. |
| Whether a figure may be used publicly | Panashe, against `docs/FIGURES.md` | Gabriel on anything clinical. |
| Release to production | Panashe, with Gabriel's recorded approval on any change touching clinical content | Takudzwa consulted. |
| Day-to-day delivery within an agreed area | The area owner alone | Raised in weekly status. |

Never edit a file in someone else's area without saying so first.

## Definition of done

The review checklist for every change is in `docs/STACK.md` (§11.6 of the master document). In one line: logic in the service layer, no hardcoded clinical constant or patient-facing string, tests including a failure case, a reversible migration for any schema change, provenance recorded on anything clinical, correct offline or documented as online-only, no screening ever lost, no personal data in a log line, docs updated in the same pull request.
