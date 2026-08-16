# Pending Clinical Lead review — master doc v6.0 copy discrepancies

**Status: DRAFT. Nothing below has shipped.** Per `CLAUDE.md`'s non-negotiable rule ("every patient-facing string requires the Clinical Lead's written sign-off before it ships"), these two discrepancies between the live code and `SilicaGuard_MasterDocument_Reference_v6.docx` are flagged here for Gabriel to review, not silently applied. Found and written up 15 August 2026.

Both of these are things the master doc itself flags as unconfirmed drafts (its own OPEN/VERIFY markers) — this isn't "the doc says X, the code says Y, fix the code." It's "two different unconfirmed drafts disagree, a clinician needs to pick one."

---

## 1. YELLOW re-screen interval — 3 months (code) vs. 6 months (master doc)

**Live today**, `backend/prompts/risk_engine_prompt.txt` line 17:
> `YELLOW (monitor, re-screen in 3 months): ...`

**Master doc v6.0 Section 13.2** ("Re-screen intervals" table, itself marked `OPEN/VERIFY — drafted for structure, not clinically validated. Gabriel must confirm or correct each interval against occupational health surveillance practice before it is presented or coded as final"):

| Level | Clinical action | Re-screen interval |
|---|---|---|
| Level 1 (GREEN) | Education and advice line only | 12 months |
| Level 2 (YELLOW) | Watch. Education, advice line, added to watch worklist | **6 months** |
| Level 3 (ORANGE) | Referral within 14 days | 3 months after referral outcome |
| Level 4 (RED) | Referral within 48 hours | Per clinical outcome; held open until closed |

GREEN's 12-month interval already matches between code and doc — only YELLOW disagrees (3 vs 6 months). ORANGE/RED aren't simple re-screen-in-N-months intervals in either version (they're referral-outcome-linked), and nothing in the code currently tracks or enforces any interval as a scheduled reminder — this is advice text shown to the miner/clinician, not an automated recall system.

**Proposed change, pending sign-off**: update `risk_engine_prompt.txt` line 17 to `re-screen in 6 months`.

---

## 2. SMS/USSD tier wording — non-numbered phrasing (code) vs. "Level 1–4" (master doc)

**Live today**, `backend/services/tier_messages.py` (shared by the USSD tree and the AI-driven `/api/screen` path) — no "Level N" prefix, different wording throughout:

```
RED:    "Matiripo ako aratidza njodzi yakakwira. Enda kuchipatara Kwekwe nhasi."
        "Your answers show serious warning signs. Please go to Kwekwe District Hospital today."
ORANGE: "Zvakafanana nemamiriro ane njodzi. Enda kuchipatara Kwekwe nhasi kuti upiwe X-ray."
        "Your exposure and symptoms suggest high risk. Go to Kwekwe District Hospital for a chest X-ray."
YELLOW: "Une njodzi yakati wandei. Enda kuchipatara mumwedzi uno."
        "You have moderate risk. Visit a clinic within the next 4 weeks."
GREEN:  "Njodzi yako iri pasi. Ramba uchipfeka mask yako nguva dzose."
        "Your risk appears low. Keep wearing your mask and stay safe."
```

**Master doc v6.0 Section 13.3** ("Levels, not colours, at the SMS boundary" — "colour does not survive plain text"; itself marked `OPEN/VERIFY — all Shona strings are drafts written for structure. Every one needs Clinical Lead sign-off and native-speaker review before it reaches a real miner"):

```
Level 1 — Wakanaka. Ramba uchishandisa mask yako.
          (You are well. Keep using your mask.)
Level 2 — Ngwarira. Dzokera kunotariswa mumwedzi mitanhatu.
          (Take care. Come back for a check in six months.)
Level 3 — Enda kuchipatara mumazuva gumi nemana.
          (Go to the clinic within fourteen days.)
Level 4 — Enda kuchipatara nhasi.
          (Go to the hospital today.)
```

Note Level 2's six-month re-screen phrase lines up with item 1 above — if Gabriel confirms the 6-month YELLOW interval, this wording should carry it too, so the two don't drift independently.

**Also note**: the master doc's Level 3/4 stems are considerably shorter than the current ORANGE/RED text (which names Kwekwe District Hospital explicitly and, for ORANGE, mentions an X-ray). Whether to adopt the doc's brevity as-is or keep the current text's extra specificity (hospital name, X-ray mention) is itself a decision for Gabriel, not something to resolve unilaterally here.

**Proposed change, pending sign-off**: replace `TIER_MESSAGES` in `tier_messages.py` with tier-appropriate wording built from the master doc's stems (bilingual, matching the existing `(shona, english)` tuple shape) — exact final text to be drafted together with Gabriel, not pre-written here, since the specificity question above needs an answer first.

---

## How to apply, once approved

1. Edit `backend/prompts/risk_engine_prompt.txt` and/or `backend/services/tier_messages.py` directly with the agreed text.
2. Delete this file (or move its content to a changelog note) — it exists only to track "known, flagged, not yet resolved," not as permanent documentation.
3. Update `CLAUDE.md`'s "Current sprint status" recording the sign-off and the change.
4. Full pytest suite should stay green — no test currently asserts on the exact wording of these two files' content, only tier logic/behavior, but re-run to confirm.
