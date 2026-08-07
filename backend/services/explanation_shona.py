"""Shona clinical explanation line for ScreeningResult.explanation_shona.

Mirrors services/advice_engine.py's mechanism exactly, on purpose: same
weakest-answer selection logic, same "always returns something, never None"
guarantee, same DRAFT COPY caveat. Kept as a separate module rather than
folded into advice_engine.py because it answers a different question —
advice_line is "the one thing to change," this is a Shona rendering of *why*
the miner landed in this tier, paired with ScreeningResult.explanation_english
in the API response and mobile app's clinical-explanation section.

Distinct from services/tier_messages.py's short SMS action line: that's a
fixed per-tier message sent by SMS; this is a personalised per-miner
sentence shown in-app.

DRAFT COPY. Per CLAUDE.md: "Every patient-facing string requires the
Clinical Lead's written sign-off before it ships" — none of this text has
that sign-off yet. Do not treat this copy as final.
"""

from typing import List

from models import ScreeningAnswerIn

# question_code -> {answer_value: Shona explanation line}. Same coverage as
# advice_engine.py's ADVICE_TEMPLATES, so every personalised advice_line has
# a matching Shona explanation of the underlying factor.
EXPLANATION_TEMPLATES = {
    "PPE_USE": {
        "never": "Hausati wambopfeka N95 paunenge uchichera kana kupwanya matombo — izvi zvinowedzera guruva rinopinda mumapapu ako.",
        "cloth_mask": "Mask yemucheka haidziviriri guruva reSilica — unoda N95 kana FFP2 chaiyo.",
        "sometimes": "Unopfeka N95 dzimwe nguva chete, kwete nguva dzose paunenge uchichera kana kupwanya.",
    },
    "WET_DRILLING": {
        "never": "Hapana mvura inoshandiswa paunochera — mvura inoderedza guruva zvakanyanya.",
        "sometimes": "Mvura inoshandiswa dzimwe nguva chete paunochera, kwete nguva dzose.",
    },
    "BREATHLESSNESS": {
        "severe": "Unotadza kufema zvakanyanya kunyange uchipfeka kana uchizorora — chiratidzo chinotyisa chinoda kuongororwa nhasi.",
        "moderate": "Unotadza kufema zvishoma paunenge uchishanda — chiratidzo chekutanga chinofanira kucherekedzwa.",
    },
    "COUGH_DURATION": {
        "severe": "Wakosora kwenguva refu — izvi zvinoda kuongororwa nechiremba nekukurumidza.",
        "mild": "Wakosora kwenguva pfupi — cherekedza kana kusingaperi mumavhiki mashoma.",
    },
    "CHEST_PAIN": {
        "severe": "Wava kurwadziwa nechipfuva zvakanyanya — chiratidzo chinoda kuongororwa nechiremba nekukurumidza.",
        "sometimes": "Unorwadziwa nechipfuva dzimwe nguva — taura izvi nechiremba paunoenda kuchipatara.",
    },
    "TB_HISTORY": {
        "current": "Uri kurapwa TB parizvino — izvi pamwe neguruva rewungwaru zvinowedzera njodzi, chinhu chinoda kuongororwa nekukurumidza.",
        "past": "Wakamboita TB kare — chengetedza uchicherekedza zviratidzo zvitsva zvekufema.",
    },
    "WEIGHT_LOSS": {
        "significant": "Waderera zvakanyanya muhuremu hwemuviri usingazivi chikonzero — izvi zvinoda kuongororwa nechiremba.",
        "some": "Waderera zvishoma muhuremu hwemuviri — cherekedza uye uzivise chiremba kana zvichiramba zvichiitika.",
    },
    "PRIOR_LUNG_DIAGNOSIS": {
        "yes": "Wakambozikanwa nechirwere chemapapu kare — zviratidzo zvitsva zvose zvinofanira kutorwa senyore uye kukurumidza kuongororwa.",
    },
    "YEARS_UNDERGROUND": {
        "over_10": "Washanda makore anodarika 10 pasi pevhu — ramba uchiongororwa kunyange uchinzwa uri mutano.",
    },
    "JOB_ROLE": {
        "drilling": "Basa rekuchera ndiro rine guruva rakanyanya pamigodhi — N95 nemvura pakuchera hazvibvumirwe kusiiwa.",
        "crushing": "Basa rekupwanya matombo rine guruva rakanyanya — N95 nemvura pakupwanya hazvibvumirwe kusiiwa.",
    },
}

GREEN_DEFAULT_EXPLANATION = (
    "Mhinduro dzako hadzina kuratidza njodzi huru parizvino. Ramba uchishandisa "
    "N95 uye kumbira mvura ishandiswe paunenge uchichera kana kupwanya."
)


def personalised_explanation_shona(answers: List[ScreeningAnswerIn]) -> str:
    """Every result must carry a Shona explanation, so this always returns
    one — same weakest-answer-first selection as
    advice_engine.personalised_advice_line(), so the English and Shona
    explanations for a given screening are always about the same factor."""
    scored = sorted(
        (a for a in answers if a.answer_score > 0),
        key=lambda a: a.answer_score,
        reverse=True,
    )
    for answer in scored:
        line = EXPLANATION_TEMPLATES.get(answer.question_code, {}).get(answer.answer_value)
        if line:
            return line

    return GREEN_DEFAULT_EXPLANATION
