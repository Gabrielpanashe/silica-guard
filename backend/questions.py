# Verbatim from SILICAGUARD.md Section 8 — the doctor-approved 10 screening
# questions. Never edit the Shona/English text here without the doctor's sign-off.

SCREENING_QUESTIONS = [
    {
        "code": "YEARS_UNDERGROUND",
        "shona": "Makangoshanda mangani emakore pasi pevhu kana pedyo nekuchera?",
        "english": "How many years have you worked underground or near drilling?",
        "options": [
            {"label_shona": "Pasi pemakore 2", "label_english": "Under 2 years", "value": "under_2", "score": 1},
            {"label_shona": "Makore 2-5", "label_english": "2-5 years", "value": "2_to_5", "score": 2},
            {"label_shona": "Makore 5-10", "label_english": "5-10 years", "value": "5_to_10", "score": 3},
            {"label_shona": "Makore 10+", "label_english": "Over 10 years", "value": "over_10", "score": 5},
        ],
    },
    {
        "code": "JOB_ROLE",
        "shona": "Basa rako guru muhomwe kana mupurazi ndeiripi?",
        "english": "What is your main job at the mine or quarry?",
        "options": [
            {"label_shona": "Kudira mwena (Rock drilling/blasting)", "label_english": "Rock drilling / blasting", "value": "drilling", "score": 5},
            {"label_shona": "Kutakura/Kusaina (Loading/Hauling)", "label_english": "Loading / hauling", "value": "loading", "score": 3},
            {"label_shona": "Kumisikidza (Processing/Crushing)", "label_english": "Processing / crushing", "value": "crushing", "score": 4},
            {"label_shona": "Panze / Mamwe (Surface / other)", "label_english": "Surface / other", "value": "surface", "score": 1},
        ],
    },
    {
        "code": "WET_DRILLING",
        "shona": "Kushandiswa kwemvura pakudira mwena here (wet drilling)?",
        "english": "Is water used during drilling at your site to suppress dust?",
        "options": [
            {"label_shona": "Hongu, nguva dzose", "label_english": "Yes, always", "value": "always", "score": 0},
            {"label_shona": "Dzimwe nguva", "label_english": "Sometimes", "value": "sometimes", "score": 2},
            {"label_shona": "Kwete/Handizivi", "label_english": "No / I don't know", "value": "never", "score": 4},
        ],
    },
    {
        "code": "PPE_USE",
        "shona": "Unopfeka mask kana chekuchengetedza kufefera (PPE) paunoshanda?",
        "english": "Do you wear a dust mask or respiratory protection while working?",
        "options": [
            {"label_shona": "Nguva dzose (N95/FFP2)", "label_english": "Always (N95/FFP2 mask)", "value": "always_n95", "score": 0},
            {"label_shona": "Dzimwe nguva", "label_english": "Sometimes", "value": "sometimes", "score": 2},
            {"label_shona": "Mask yejira/surgical", "label_english": "Cloth or surgical mask", "value": "cloth_mask", "score": 3},
            {"label_shona": "Handipfeki", "label_english": "Never", "value": "never", "score": 5},
        ],
    },
    {
        "code": "COUGH_DURATION",
        "shona": "Une kuhema (cough) inoenderera kupfuura mavhiki matatu here?",
        "english": "Do you have a cough that has lasted more than 3 weeks?",
        "options": [
            {"label_shona": "Kwete", "label_english": "No", "value": "no", "score": 0},
            {"label_shona": "Hongu, zvishoma", "label_english": "Yes, mild", "value": "mild", "score": 3},
            {"label_shona": "Hongu, zvakanyanya", "label_english": "Yes, persistent/severe", "value": "severe", "score": 5},
        ],
    },
    {
        "code": "BREATHLESSNESS",
        "shona": "Unorwadziwa kufema (shortness of breath) uchiita zvinhu zvawaiita nyore?",
        "english": "Do you get short of breath doing activities that didn't tire you before?",
        "options": [
            {"label_shona": "Kwete", "label_english": "No", "value": "none", "score": 0},
            {"label_shona": "Pakufamba chiuno/kukwira magumo", "label_english": "Walking on flat / climbing stairs", "value": "moderate", "score": 3},
            {"label_shona": "Pakugeza/kupfeka", "label_english": "Getting dressed / resting", "value": "severe", "score": 5},
        ],
    },
    {
        "code": "TB_HISTORY",
        "shona": "Wakamborehwa TB (tuberculosis) kana kupihwa mishonga yaTB here?",
        "english": "Have you ever been told you have TB or received TB treatment?",
        "options": [
            {"label_shona": "Kwete", "label_english": "No", "value": "no", "score": 0},
            {"label_shona": "Hongu, yakapera", "label_english": "Yes, completed", "value": "past", "score": 3},
            {"label_shona": "Hongu, ndiri kurwa", "label_english": "Yes, ongoing", "value": "current", "score": 4},
        ],
    },
    {
        "code": "WEIGHT_LOSS",
        "shona": "Wakaonda (lost weight) usingade kuzviita mumwedzi mitatu yapfuura here?",
        "english": "Have you lost weight without trying in the past 3 months?",
        "options": [
            {"label_shona": "Kwete", "label_english": "No", "value": "no", "score": 0},
            {"label_shona": "Zvishoma", "label_english": "A little", "value": "some", "score": 2},
            {"label_shona": "Zvakanyanya", "label_english": "Significant", "value": "significant", "score": 4},
        ],
    },
    {
        "code": "CHEST_PAIN",
        "shona": "Une kurwadziwa kwechifu (chest pain or tightness)?",
        "english": "Do you experience chest pain or chest tightness?",
        "options": [
            {"label_shona": "Kwete", "label_english": "No", "value": "no", "score": 0},
            {"label_shona": "Dzimwe nguva", "label_english": "Sometimes", "value": "sometimes", "score": 3},
            {"label_shona": "Nguva dzose/zvakashata", "label_english": "Often / severe", "value": "severe", "score": 5},
        ],
    },
    {
        "code": "PRIOR_LUNG_DIAGNOSIS",
        "shona": "Chiremba akakuudza here kuti une dambudziko repamapfubvu (lung problem)?",
        "english": "Has a doctor ever told you that you have a lung problem?",
        "options": [
            {"label_shona": "Kwete", "label_english": "No", "value": "no", "score": 0},
            {"label_shona": "Hongu", "label_english": "Yes", "value": "yes", "score": 5},
        ],
    },
]
