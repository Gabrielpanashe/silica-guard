# Diagrams

> Derived from `docs/master/MASTER_REFERENCE.md` §10 (Master Reference v1.0, September 2026). The four figures in that section are authoritative; these are their Graphviz sources so that they are reviewable in a pull request and regenerable, rather than hand-edited images (§11.1). Owner: Panashe.

| Figure | Source | Master document rendering |
|---|---|---|
| 1. High-level architecture (§10.2) | `architecture.dot` | `docs/master/media/a6604243884e2e9b364483500dcfc788603850aa.png` |
| 2. Screening pipeline (§10.3) | `screening_pipeline.dot` | `docs/master/media/d48581a1a776f78d11e01a3aa054b5cce2828c36.png` |
| 3. Referral lifecycle (§10.4) | `referral_lifecycle.dot` | `docs/master/media/adf3f4a29d8429afaaea20db4033f8e01c7be31a.png` |
| 4. Core entities (§10.5) | `data_model.dot` | `docs/master/media/b77c91c2f479a0321bc4f759ac5b972c2e35f877.png` |

All four describe the **target** architecture (Phase One and later), not the current code. `ARCHITECTURE.md` states, per figure, what exists today.

## Rendering

Graphviz is not installed on the development machines yet. Until it is, `ARCHITECTURE.md` links the PNGs rendered from the master document. To render from source:

```
winget install Graphviz.Graphviz          # once
cd diagrams
dot -Tpng architecture.dot        -o architecture.png
dot -Tpng screening_pipeline.dot  -o screening_pipeline.png
dot -Tpng referral_lifecycle.dot  -o referral_lifecycle.png
dot -Tpng data_model.dot          -o data_model.png
```

Rendered PNGs are committed alongside the sources once rendered, and `ARCHITECTURE.md` is repointed at them. A change to a diagram is a change to its `.dot` file, reviewed like code; the PNG is regenerated, never edited.

Palette follows §2.6: primary navy `#102A72`, accent green `#07966F` (the deterministic clinical core and safety overrides), ice `#E8ECF7` for primary surfaces. Colour is never the only carrier of meaning — every node is labelled.

If code and a diagram disagree, one of them is wrong, and the disagreement is resolved before the next release rather than left standing (§10).
