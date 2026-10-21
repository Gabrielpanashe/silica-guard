# Approved figures and sources

> Derived from `docs/master/MASTER_REFERENCE.md`, Appendix B (Master Reference v1.0, September 2026). The master document wins on any conflict.

**This is the only permitted source of figures for any SilicaGuard material** — decks, letters, applications, social posts, exhibition material, repository documentation, prompts, and UI copy. No number appears anywhere unless it appears here. Anything marked UNVERIFIED is never stated as fact, in any context, and never appears in public material at all. Adding a figure means adding it here first, with its source, before it is used.

Whether a figure may be used publicly is decided by Panashe as document owner, against this table, with Gabriel consulted on anything clinical (master document §21.4, decision rights).

| Figure | Source | Status |
|---|---|---|
| More than 500,000 artisanal and small scale miners in Zimbabwe | Sector estimates | Approved |
| Ratio of approximately 28 to 1 against roughly 18,000 formal gold sector workers | Sector estimates | Approved |
| Approximately 75 percent of 2025 gold output, being 34.9 of 46.7 tonnes | Fidelity Gold Refinery | Approved |
| Approximately 19 percent silicosis prevalence, sample of 3,821 miners | Moyo and colleagues, International Journal of Environmental Research and Public Health, 2022 | Approved |
| Tuberculosis rate 39 times the national average | International Journal of Environmental Research and Public Health, 2024 | Approved |
| Mean age 35 | Same prevalence study | Approved |
| Two dedicated occupational health clinics nationally, at Gweru and Gwanda | National facility record | Approved |
| 10,668 miners screened over three years, approximately 3,556 per year | Kunda Nqob'iTB published report | Approved |
| Approximately 141 years to screen the population once at that rate | Team calculation from the above | Approved, described as a calculation |
| 73 percent of miners needing follow up completed it | Kunda Nqob'iTB published report | Approved. **This is the headline baseline.** |
| Programme folded when funding ended in 2024 | Public record | Approved |
| Approximately 53 million dollar grant to Zimbabwe Health Interventions terminated in 2025 | Public record | Approved |
| Zimbabwe has never implemented the Basic Occupational Health Services model | Confirmed in the Kunda Nqob'iTB published report | Approved |
| SilicaGuard delivers 6 of the 8 Basic Occupational Health Services components | Team assessment against the model | Approved, described as an assessment |
| CAPTURE sensitivity 48.2 percent, specificity 88.6 percent, 4,325 patients | Martinez and colleagues, Journal of the American Medical Association | Approved, external comparator |
| qXR deployed in more than 3,100 sites across more than 90 countries | Vendor published material | Approved, described as vendor reported |
| Approximately one death per week at Kwekwe General Hospital | Newsletter citing Dr Gunda. Not confirmed by Dr Gunda despite direct contact. | **UNVERIFIED. Never stated as fact. Never used in public material.** |
| 50 to 60 silicosis deaths per year in Kwekwe District | Same unconfirmed source | **UNVERIFIED. Never used.** |

## Figures found in the repository that are not in this table

Audit of 18 September 2026. Each is either removed, or flagged to its owner because it lives in code rather than documentation.

| Where | Figure | Action |
|---|---|---|
| `SILICAGUARD.md` (retired) | "one silicosis death a week — 50 to 60 a year"; "500,000–1.5 million"; "6.8% TB"; "18% HIV" | Removed 18 September 2026 (commit `950e40c`) |
| `backend/prompts/risk_engine_prompt.txt` lines 6–7 | "TB prevalence is 6.8%, HIV prevalence is 18% — silicosis raises TB risk 3-5x" | **Open.** Prompt text, so it ships with the system. Owner: Panashe (code) with Gabriel (clinical). Either source and add here, or remove from the prompt. Becomes moot when the classification moves off the model (master document §9). |
| `backend/scripts/throughput_model.py` docstring; `docs/PROGRESS_LOG.md` | "20 screenings per worker per day", "36/day", "4.9x", "5.4x", "2.5x", "2.7x" | **Open.** Derived from master document v6.0's planning table, absent from v1.0's Appendix B. Not for public use until added here with a source. |
| `docs/API_CONTRACT.md` | "142 miners were screened across three sites, with 9 at elevated risk" | Illustrative example payload of the narrative endpoint, not a claim. Labelled as such. |
| `docs/VALIDATION.md` (from master document §7) | Dutch COPD app study: 76.4% excluded, 48.9% of those for digital access; LUDESC: 120 patients, 98% reported accuracy; Lung DT: 96.8% reported accuracy | **Cited in the master document's §7 but absent from its Appendix B.** Internal comparator context only. To be added to Appendix B with sources (master document change) before any public use — the Dutch figure in particular is the strongest argument for the USSD channel and will be wanted in letters. |
