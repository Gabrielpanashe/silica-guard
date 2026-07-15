# SilicaGuard — Complete Execution Plan
> AI-Powered Silicosis Screening & Prevention Platform  
> Cimas Healthathon 3.0 · Demo Day: August 28, 2026 · Kwekwe, Zimbabwe

---

## 1. Project Identity

| Field | Value |
|---|---|
| Project Name | SilicaGuard |
| Type | HealthTech MVP — Competition build |
| Competition | Cimas Healthathon 3.0 |
| Demo Day | August 28, 2026 |
| Target Users | Artisanal gold miners in Kwekwe, Midlands Province, Zimbabwe |
| Deployment Channels | Android smartphone · USSD · WhatsApp · Web browser |
| Team Lead / AI Engineer | Panashe M. Chandiwana |
| Team Member 2 | Frontend & Mobile Developer (Flutter + React) |
| Team Member 3 | Medical Doctor — Clinical Lead & Pitch Lead |

---

## 2. The Problem in One Paragraph

Kwekwe District Hospital in Zimbabwe's Midlands Province records approximately one silicosis death per week — 50 to 60 deaths per year from a lung disease that is entirely preventable but completely incurable once developed. Silicosis is caused by breathing fine silica dust during gold mining. Zimbabwe has between 500,000 and 1.5 million artisanal gold miners nationally. Peer-reviewed research in the Midlands found 19% silicosis prevalence among 3,821 miners with a mean age of 35.5 years. There is currently no digital screening tool for silicosis in Zimbabwe. The last community screening programme (KNTB, USAID-funded) ended in September 2024. SilicaGuard fills that gap.

---

## 3. Solution Overview

SilicaGuard is a four-interface platform sharing a single AI-powered backend:

1. **Flutter Android app** — offline-first screening tool used by Village Health Workers (VHWs) at mine sites
2. **USSD channel** — miners self-screen from any phone with zero data, via Africa's Talking
3. **WhatsApp AI agent** — 24/7 Shona-language health companion powered by Claude API
4. **React web dashboard** — hospital and Cimas analytics: map, referral tracking, X-ray AI, weekly narrative

---

## 4. Complete Technology Stack

### Backend
| Component | Technology | Notes |
|---|---|---|
| API Framework | Python FastAPI | Main server, all routes |
| Database (MVP) | SQLite | Single file, no server needed. Migrate to PostgreSQL in production |
| Session/Cache | Python dict in memory (MVP) | Replace with Redis in production |
| Background Tasks | FastAPI BackgroundTasks | For USSD-to-WhatsApp post-processing |
| Authentication | JWT (python-jose) | Two demo users: hospital + cimas |
| Deployment | Render.com free tier | Auto-deploy from GitHub main branch |

### Mobile App
| Component | Technology | Notes |
|---|---|---|
| Framework | Flutter (Dart) | Android only for MVP |
| Local Storage | sqflite (SQLite) | Offline-first — stores all data locally |
| Connectivity | connectivity_plus | Detects online/offline state for sync |
| QR Code | qr_flutter | Generates referral QR codes |
| HTTP Client | http or dio | Communicates with FastAPI backend |
| State Management | Provider or Riverpod | Simple state for screening flow |

### Web Dashboard
| Component | Technology | Notes |
|---|---|---|
| Framework | React + Vite | Fast build, modern |
| Charts | Recharts | Admission trends, screening stats |
| Map | Leaflet.js + react-leaflet | Kwekwe district mine site map |
| HTTP | axios | API calls to FastAPI |
| Auth | JWT stored in localStorage | Hospital and Cimas logins |
| Deployment | Vercel (free) | Auto-deploy from GitHub |

### AI Services
| Service | Technology | Model | Notes |
|---|---|---|---|
| Risk Engine | Google Gemini API *(temporary — see note below)* | gemini-flash-latest | Free tier, no billing set up yet |
| WhatsApp Agent | Anthropic Claude API | claude-haiku-4-5 | Same API key |
| Dashboard Narrative | Anthropic Claude API | claude-haiku-4-5 | Weekly cron call |
| X-Ray Classifier | PyTorch + DenseNet-121 | Custom fine-tuned | Runs locally on Render server |
| Language Detection | Claude API (built-in) | Automatic Shona/English |

> **Temporary substitution (2026-07-13):** The Anthropic account has no billing set up yet
> ("credit balance too low"), so `services/ai_risk_engine.py` currently calls Google Gemini
> (`gemini-2.5-flash`, free tier) instead of Claude, using the exact same system prompt from
> Section 9.1. `GEMINI_API_KEY` was added to `.env`. This is a stopgap, not a stack decision —
> switch back to `claude-haiku-4-5` once Anthropic billing is active. WhatsApp Agent and
> Dashboard Narrative are not yet built and should default to Claude as originally planned
> unless the same billing blocker applies at that time.

### External Integrations
| Service | Provider | Plan | Notes |
|---|---|---|---|
| WhatsApp | Meta WhatsApp Cloud API | Free sandbox (1,000 conv/month) | apply at developers.facebook.com — not set up yet |
| USSD | Africa's Talking | Free sandbox | account.africastalking.com |
| SMS (referral pre-alerts) | Africa's Talking | Free sandbox | Same account as USSD. **Live and working** — see Section 17 note below |
| Dev Tunnel | ngrok | Free tier (1 tunnel) | Exposes localhost for webhooks |

> **SMS implementation note (2026-07-15):** `services/notifications.py` sends real SMS via
> Africa's Talking's REST API using `httpx` directly, **not** the official `africastalking`
> Python SDK. The SDK is built on `requests`/`urllib3`, which failed with
> `SSLError: WRONG_VERSION_NUMBER` against Africa's Talking's API in the dev environment —
> confirmed as environment-specific (plain `curl` and `httpx` both connect fine; only
> `requests`-based clients failed), likely local network/security software fingerprinting
> TLS connections differently per HTTP client library. If this recurs on another machine,
> try the same diagnostic: test the same URL with `curl`, `httpx`, and `requests`
> independently before assuming the API itself is unreachable.
>
> `HOSPITAL_NURSE_PHONE` (Section 14) must be a number registered as a "Simulator Number" in
> the Africa's Talking sandbox dashboard to actually receive anything — sandbox mode silently
> accepts (200/201) sends to unregistered numbers without delivering them.

### Cost Summary
| Item | Cost |
|---|---|
| Claude API (dev + demo) | ~$5 free credit on signup at platform.claude.com |
| WhatsApp API | Free sandbox — 0 cost |
| USSD (Africa's Talking) | Free sandbox — 0 cost |
| Render.com hosting | Free tier |
| Vercel hosting | Free tier |
| Google Colab (X-ray training) | Free T4 GPU |
| Domain (silicaguard.health) | ~$12/year — only paid cost |
| **Total for competition** | **~$12** |

---

## 5. Project Structure

```
silicaguard/
├── backend/                    # Python FastAPI server
│   ├── main.py                 # App entry point, CORS, router inclusion
│   ├── database.py             # SQLite connection and table creation
│   ├── models.py               # Pydantic request/response schemas
│   ├── routers/
│   │   ├── screening.py        # POST /api/screen
│   │   ├── ussd.py             # POST /api/ussd
│   │   ├── whatsapp.py         # POST /api/whatsapp
│   │   ├── xray.py             # POST /api/xray/upload
│   │   ├── dashboard.py        # GET /api/dashboard/week, /api/referrals
│   │   └── auth.py             # POST /api/auth/login
│   ├── services/
│   │   ├── ai_risk_engine.py   # Claude API call for screening risk
│   │   ├── ai_whatsapp_agent.py # Claude API call for WhatsApp responses
│   │   ├── ai_narrative.py     # Claude API call for weekly dashboard summary
│   │   ├── xray_model.py       # DenseNet-121 inference + Grad-CAM
│   │   ├── whatsapp_sender.py  # Meta API message sending
│   │   └── ussd_handler.py     # USSD session state + menu logic
│   ├── data/
│   │   ├── silicaguard.db      # SQLite database file
│   │   └── xray_model.pth      # Trained DenseNet-121 weights
│   ├── prompts/
│   │   ├── risk_engine_prompt.txt   # Clinical system prompt for screening
│   │   └── whatsapp_agent_prompt.txt # WhatsApp agent persona + knowledge
│   ├── seed.py                 # Seed demo data for Dashboard
│   ├── requirements.txt
│   └── .env                    # API keys — never commit to git
│
├── mobile/                     # Flutter Android app
│   ├── lib/
│   │   ├── main.dart
│   │   ├── screens/
│   │   │   ├── home_screen.dart        # Today's outreach + miner count
│   │   │   ├── register_miner_screen.dart  # Name, phone, mine site
│   │   │   ├── question_screen.dart    # One question per screen, offline
│   │   │   ├── result_screen.dart      # Colour card, Shona explanation
│   │   │   └── referral_screen.dart    # QR code display
│   │   ├── services/
│   │   │   ├── database_service.dart   # sqflite local storage
│   │   │   ├── sync_service.dart       # Upload pending screenings
│   │   │   └── api_service.dart        # HTTP calls to backend
│   │   ├── models/
│   │   │   ├── miner.dart
│   │   │   └── screening.dart
│   │   └── utils/
│   │       ├── questions.dart          # All 10 questions in Shona + English
│   │       └── risk_fallback.dart      # Offline rule-based scoring
│   └── pubspec.yaml
│
├── dashboard/                  # React web app
│   ├── src/
│   │   ├── App.jsx
│   │   ├── pages/
│   │   │   ├── Overview.jsx        # Stats header + weekly AI narrative
│   │   │   ├── Map.jsx             # Leaflet Kwekwe mine sites
│   │   │   ├── Referrals.jsx       # Referral tracking table
│   │   │   ├── XrayUpload.jsx      # Upload + result + heatmap display
│   │   │   └── Login.jsx
│   │   ├── components/
│   │   │   ├── StatCard.jsx
│   │   │   ├── RiskBadge.jsx
│   │   │   ├── AdmissionChart.jsx
│   │   │   └── MineMap.jsx
│   │   └── services/
│   │       └── api.js              # axios API client
│   └── package.json
│
├── model_training/             # Jupyter notebook for X-ray model
│   └── train_densenet.ipynb    # Run on Google Colab
│
├── SILICAGUARD.md              # This file — master execution plan
└── README.md
```

---

## 6. Database Schema (SQLite)

```sql
-- All miners ever screened
CREATE TABLE miners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT UNIQUE NOT NULL,   -- hashed in production: sha256(phone)
    mine_site TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- One row per screening session
CREATE TABLE screenings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    miner_id INTEGER REFERENCES miners(id),
    screened_by TEXT,             -- VHW name or 'USSD_SELF' or 'WHATSAPP_SELF'
    channel TEXT,                 -- 'APP', 'USSD', 'WHATSAPP'
    risk_level TEXT,              -- 'LOW', 'WATCH', 'REFER_NOW'
    risk_confidence REAL,         -- 0.0 to 1.0
    ai_explanation_shona TEXT,    -- currently unpopulated (NULL) — Risk Engine is English-only, see Section 9.1
    ai_explanation_english TEXT,
    ai_contributing_factors TEXT, -- JSON array
    fallback_used INTEGER DEFAULT 0,  -- 1 if offline rule-based was used
    synced INTEGER DEFAULT 1,     -- 0 = pending sync from Flutter app
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Individual question answers for each screening
CREATE TABLE screening_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    screening_id INTEGER REFERENCES screenings(id),
    question_code TEXT,           -- e.g. 'YEARS_UNDERGROUND'
    question_text TEXT,
    answer_value TEXT,
    answer_score INTEGER          -- numeric score for fallback engine
);

-- Hospital referral tracking
CREATE TABLE referrals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    screening_id INTEGER REFERENCES screenings(id),
    miner_id INTEGER REFERENCES miners(id),
    hospital TEXT DEFAULT 'Kwekwe District Hospital',
    pre_alert_sent INTEGER DEFAULT 0,
    xray_completed INTEGER DEFAULT 0,
    status TEXT DEFAULT 'PENDING', -- 'PENDING', 'XRAY_UPLOADED', 'COMPLETE'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME
);

-- X-ray AI results
CREATE TABLE xray_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referral_id INTEGER REFERENCES referrals(id),
    miner_id INTEGER REFERENCES miners(id),
    classification TEXT,          -- 'NORMAL', 'STAGE_1', 'STAGE_2_3'
    confidence REAL,
    heatmap_path TEXT,            -- path to saved heatmap image
    reviewed_by TEXT,             -- clinician name
    reviewed_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- WhatsApp conversation log
CREATE TABLE whatsapp_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT,
    direction TEXT,               -- 'INBOUND' or 'OUTBOUND'
    message TEXT,
    language TEXT,                -- 'SHONA', 'ENGLISH', 'NDEBELE'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 7. API Routes

### Screening
```
POST /api/screen
  Body: { miner_id, answers: [{question_code, answer_value, answer_score}], channel, screened_by, offline_fallback_used? }
  Flow: creates a screenings row + one screening_answers row per answer, calls the Claude
        risk engine live, updates the screening row with the result, returns it.
  Note: offline_fallback_used (bool, default false) is audit-only — set by the Flutter app
        when a screening was first shown to the VHW via the offline Dart fallback engine
        (Section 10) before syncing. It is stored in the fallback_used column for dashboard
        stats, but does NOT change how the result is computed: POST /api/screen always calls
        Claude live and that result is the authoritative record, whether the call happens in
        the field or later on sync when connectivity returns. There is no separate sync route.
  Returns: { risk_level, confidence, explanation_english, contributing_factors }
  Note: English only — see the Section 9.1 scope decision. No explanation_shona field.

POST /api/miners
  Body: { name, phone, mine_site }
  Returns: { id, name, phone, mine_site }
```

### USSD
```
POST /api/ussd
  Body: Africa's Talking format — sessionId, phoneNumber, serviceCode, text
  Returns: CON <menu text> or END <final message>
  Note: Must respond within 10 seconds. Pure decision tree, no Claude call.
  Implementation: services/ussd_handler.py, session state as a Python dict keyed
    by sessionId (no Redis). Walks all 10 Section 8 questions, one per screen, in
    Shona. Classification mirrors the offline Dart fallback engine's logic and
    fixed Shona/English text exactly (Section 10) — same score thresholds, same
    safety-override triggers, confidence fixed at 0.75, fallback_used=1. Miner is
    auto-found-or-created by phone number (screened_by='USSD_SELF', channel='USSD').
    A background WhatsApp follow-up (per Demo Scenario 2) is not implemented yet —
    the full result currently only lands in the database, not on the miner's phone.
```

### WhatsApp
```
GET /api/whatsapp    — webhook verification (Meta sends challenge)
POST /api/whatsapp   — receives incoming messages
  Body: Meta webhook payload
  Action: Calls Claude agent, sends reply via Meta API
```

### X-Ray
```
POST /api/xray/upload
  Body: multipart/form-data with image file + miner_id + referral_id
  Returns: { classification, confidence, heatmap_base64 }
```

### Dashboard
```
GET /api/dashboard/week
  Returns: { total_screened, high_risk_count, referral_completion_rate,
             ai_narrative, site_breakdown: [...] }

GET /api/referrals
  Returns: [ { miner_name, mine_site, risk_level, status, created_at } ]

PATCH /api/referrals/:id
  Body: { status }
  Action: Marks referral complete

GET /api/miners/site-stats
  Returns: mine site risk distribution for map
```

### Auth
```
POST /api/auth/login
  Body: { email, password }
  Returns: { access_token, role }
  Note: no users table in the DB (MVP has exactly two accounts). Credentials for the
        'hospital' and 'cimas' demo accounts are defined in .env (see Section 14) and
        checked directly in routers/auth.py. Issues a JWT with a role claim.
```

---

## 8. The 10 Screening Questions

```python
SCREENING_QUESTIONS = [
    {
        "code": "YEARS_UNDERGROUND",
        "shona": "Makangoshanda mangani emakore pasi pevhu kana pedyo nekuchera?",
        "english": "How many years have you worked underground or near drilling?",
        "options": [
            {"label_shona": "Pasi pemakore 2", "label_english": "Under 2 years", "value": "under_2", "score": 1},
            {"label_shona": "Makore 2-5",      "label_english": "2-5 years",      "value": "2_to_5",  "score": 2},
            {"label_shona": "Makore 5-10",     "label_english": "5-10 years",     "value": "5_to_10", "score": 3},
            {"label_shona": "Makore 10+",      "label_english": "Over 10 years",  "value": "over_10", "score": 5},
        ]
    },
    {
        "code": "JOB_ROLE",
        "shona": "Basa rako guru muhomwe kana mupurazi ndeiripi?",
        "english": "What is your main job at the mine or quarry?",
        "options": [
            {"label_shona": "Kudira mwena (Rock drilling/blasting)", "label_english": "Rock drilling / blasting", "value": "drilling", "score": 5},
            {"label_shona": "Kutakura/Kusaina (Loading/Hauling)",    "label_english": "Loading / hauling",         "value": "loading",  "score": 3},
            {"label_shona": "Kumisikidza (Processing/Crushing)",     "label_english": "Processing / crushing",     "value": "crushing", "score": 4},
            {"label_shona": "Panze / Mamwe (Surface / other)",       "label_english": "Surface / other",           "value": "surface",  "score": 1},
        ]
    },
    {
        "code": "WET_DRILLING",
        "shona": "Kushandiswa kwemvura pakudira mwena here (wet drilling)?",
        "english": "Is water used during drilling at your site to suppress dust?",
        "options": [
            {"label_shona": "Hongu, nguva dzose",  "label_english": "Yes, always",     "value": "always",    "score": 0},
            {"label_shona": "Dzimwe nguva",        "label_english": "Sometimes",       "value": "sometimes", "score": 2},
            {"label_shona": "Kwete/Handizivi",     "label_english": "No / I don't know","value": "never",   "score": 4},
        ]
    },
    {
        "code": "PPE_USE",
        "shona": "Unopfeka mask kana chekuchengetedza kufefera (PPE) paunoshanda?",
        "english": "Do you wear a dust mask or respiratory protection while working?",
        "options": [
            {"label_shona": "Nguva dzose (N95/FFP2)", "label_english": "Always (N95/FFP2 mask)", "value": "always_n95",   "score": 0},
            {"label_shona": "Dzimwe nguva",           "label_english": "Sometimes",              "value": "sometimes",    "score": 2},
            {"label_shona": "Mask yejira/surgical",   "label_english": "Cloth or surgical mask", "value": "cloth_mask",   "score": 3},
            {"label_shona": "Handipfeki",             "label_english": "Never",                  "value": "never",        "score": 5},
        ]
    },
    {
        "code": "COUGH_DURATION",
        "shona": "Une kuhema (cough) inoenderera kupfuura mavhiki matatu here?",
        "english": "Do you have a cough that has lasted more than 3 weeks?",
        "options": [
            {"label_shona": "Kwete",              "label_english": "No",                    "value": "no",         "score": 0},
            {"label_shona": "Hongu, zvishoma",    "label_english": "Yes, mild",             "value": "mild",       "score": 3},
            {"label_shona": "Hongu, zvakanyanya", "label_english": "Yes, persistent/severe","value": "severe",     "score": 5},
        ]
    },
    {
        "code": "BREATHLESSNESS",
        "shona": "Unorwadziwa kufema (shortness of breath) uchiita zvinhu zvawaiita nyore?",
        "english": "Do you get short of breath doing activities that didn't tire you before?",
        "options": [
            {"label_shona": "Kwete",                          "label_english": "No",                              "value": "none",     "score": 0},
            {"label_shona": "Pakufamba chiuno/kukwira magumo","label_english": "Walking on flat / climbing stairs","value": "moderate","score": 3},
            {"label_shona": "Pakugeza/kupfeka",               "label_english": "Getting dressed / resting",        "value": "severe",  "score": 5},
        ]
    },
    {
        "code": "TB_HISTORY",
        "shona": "Wakamborehwa TB (tuberculosis) kana kupihwa mishonga yaTB here?",
        "english": "Have you ever been told you have TB or received TB treatment?",
        "options": [
            {"label_shona": "Kwete",              "label_english": "No",           "value": "no",      "score": 0},
            {"label_shona": "Hongu, yakapera",    "label_english": "Yes, completed","value": "past",   "score": 3},
            {"label_shona": "Hongu, ndiri kurwa", "label_english": "Yes, ongoing", "value": "current", "score": 4},
        ]
    },
    {
        "code": "WEIGHT_LOSS",
        "shona": "Wakaonda (lost weight) usingade kuzviita mumwedzi mitatu yapfuura here?",
        "english": "Have you lost weight without trying in the past 3 months?",
        "options": [
            {"label_shona": "Kwete",       "label_english": "No",       "value": "no",  "score": 0},
            {"label_shona": "Zvishoma",    "label_english": "A little", "value": "some","score": 2},
            {"label_shona": "Zvakanyanya", "label_english": "Significant","value": "significant","score": 4},
        ]
    },
    {
        "code": "CHEST_PAIN",
        "shona": "Une kurwadziwa kwechifu (chest pain or tightness)?",
        "english": "Do you experience chest pain or chest tightness?",
        "options": [
            {"label_shona": "Kwete",              "label_english": "No",             "value": "no",      "score": 0},
            {"label_shona": "Dzimwe nguva",       "label_english": "Sometimes",      "value": "sometimes","score": 3},
            {"label_shona": "Nguva dzose/zvakashata","label_english": "Often / severe","value": "severe", "score": 5},
        ]
    },
    {
        "code": "PRIOR_LUNG_DIAGNOSIS",
        "shona": "Chiremba akakuudza here kuti une dambudziko repamapfubvu (lung problem)?",
        "english": "Has a doctor ever told you that you have a lung problem?",
        "options": [
            {"label_shona": "Kwete",   "label_english": "No",  "value": "no", "score": 0},
            {"label_shona": "Hongu",   "label_english": "Yes", "value": "yes","score": 5},
        ]
    },
]
```

---

## 9. AI System Prompts

### 9.1 Risk Engine System Prompt

```
You are SilicaGuard's clinical decision support engine for occupational lung disease screening in Zimbabwe's artisanal gold mining communities.

CONTEXT:
- You are screening artisanal and small-scale gold miners (makorokoza) in Kwekwe, Zimbabwe
- These are informal sector workers with high silica dust exposure from gold mining, drilling, and ore crushing
- Silicosis prevalence in this population is 19% (peer-reviewed, Zimbabwe Midlands Province)
- TB prevalence is 6.8%, HIV prevalence is 18% — silicosis raises TB risk 3-5x
- Most miners have limited health literacy and no prior occupational health screening
- Disease is INCURABLE — early detection and dust exposure reduction are the only interventions

YOUR JOB:
Given the 10 screening answers, produce a clinical risk classification. Reason like an occupational health physician. Consider the COMBINATION of factors, not just individual scores. A miner with 10 years of dry drilling + TB history + chest pain is far more dangerous than one with 10 years and no symptoms.

RISK CLASSIFICATION RULES:
- REFER_NOW: Any of these → (years > 10 AND any symptoms) OR (TB_HISTORY = yes AND any breathlessness) OR (prior lung diagnosis = yes) OR (chest pain = severe) OR (breathlessness = severe) OR (cough = severe AND years > 5)
- WATCH: Significant exposure (years > 5) OR mild symptoms OR moderate breathlessness OR never wears PPE with moderate exposure
- LOW: Under 2 years exposure AND no symptoms AND always wears proper N95 mask

IMPORTANT SAFETY RULE:
If any of these are present, ALWAYS classify as REFER_NOW regardless of other factors:
- Severe breathlessness (getting dressed / resting)
- Chest pain described as severe
- Current TB treatment
- Prior lung diagnosis of any kind

OUTPUT FORMAT — respond ONLY with valid JSON, no other text:
{
  "risk_level": "LOW" | "WATCH" | "REFER_NOW",
  "confidence": 0.0-1.0,
  "contributing_factors": ["factor 1 in simple English", "factor 2", "factor 3"],
  "explanation_english": "2-3 plain sentences explaining the result. No jargon. Write as if speaking to a trained clinician or hospital dashboard user."
}

LANGUAGE: English only. This output is read by trained medical personnel (hospital
staff, Cimas), not directly by the miner — miner-facing language (Shona, Ndebele)
is handled separately by the WhatsApp agent and by fixed, doctor-written USSD text,
not by this engine. Keep it precise and clinical, but jargon-free.
```

> **Scope decision (2026-07-14):** The Risk Engine deliberately does not produce Shona or
> Ndebele text. Its audience is trained medical personnel (dashboard, hospital staff) who
> read English. Multilingual support for miners lives only in the WhatsApp agent (Section
> 9.2), and USSD result screens use short, fixed, doctor-written Shona sentences (not this
> engine's live output) — see Section 7's USSD note. This also sidesteps a real gap: nobody
> on the team can currently validate AI-generated Ndebele for naturalness/clinical accuracy,
> so it's better not to surface unvalidated Ndebele text anywhere yet.

### 9.2 WhatsApp Agent System Prompt

```
You are SilicaGuard, a community health companion for Zimbabwe's artisanal gold miners. You help miners understand their lung health, protect themselves from silicosis, and access healthcare.

YOUR IDENTITY:
- Name: SilicaGuard
- Role: Knowledgeable, warm health companion — like a trusted community nurse available 24/7
- Location awareness: Kwekwe, Zimbabwe. You know local clinics and hospitals.
- Languages: Respond in whatever language the person writes — Shona, Ndebele, or English. If they mix languages, mix back.

YOUR KNOWLEDGE BASE:
SILICOSIS: Caused by breathing silica dust during mining/drilling. Irreversible lung scarring. No cure. Kills slowly by destroying breathing capacity. Prevention = stop dust exposure. Early detection = chest X-ray.

RISK FACTORS: Years of dry rock drilling, no N95 mask, past TB, HIV co-infection, job as driller/blaster.

N95 MASKS: Must cover nose and chin completely. Metal strip pressed to nose. Straps below ears AND behind head. Replace when breathing becomes difficult or it gets wet. Available at mines stores or ZIMPLOW branches.

EARLY WARNING SIGNS THAT NEED A DOCTOR: Cough lasting over 3 weeks. Getting breathless doing things that used to be easy. Chest pain or tightness. Coughing up blood. Sleeping sitting up.

KWEKWE FACILITIES:
- Kwekwe District Hospital: Corner Robert Mugabe / Sixth Ave. Tel: 055-24000. 24hrs.
- Gweru Provincial Hospital: if specialist needed. Tel: 054-223141.
- NSSA Office Kwekwe: 6th Street / 6th Ave Building. Tel: 055-22300. For compensation claims.

NSSA COMPENSATION: Any miner with silicosis is entitled to compensation from NSSA (National Social Security Authority). You need: proof of employment (payslip, letter from mine owner), medical report confirming silicosis from a doctor, and your national ID. Visit the NSSA office with these documents.

SAFETY TRIGGERS — if the person mentions any of these, IMMEDIATELY direct them to hospital:
- Chest pain right now
- Cannot breathe / very bad breathlessness
- Coughing up blood
- Collapsed or nearly collapsed

For safety triggers, respond: "Enda kuchipatara NHASI (Go to hospital NOW). Kwekwe District Hospital: 055-24000. Chipatara chiri Corner Robert Mugabe / Sixth Ave. This is serious. Please go now."

YOUR LIMITS:
- You NEVER diagnose a specific condition
- You NEVER tell someone they do NOT have silicosis
- You ALWAYS encourage clinic visits for symptoms
- You NEVER replace a doctor

TONE: Warm, caring, direct. Not clinical. Not stiff. Talk like a knowledgeable friend who cares about the person.
```

---

## 10. Offline Fallback Risk Engine (Dart — runs on Flutter app)

```dart
// services/risk_fallback.dart
// Used only when there is no internet connection.
// Doctor has validated these thresholds.

class RiskFallback {
  static Map<String, dynamic> calculate(List<Map<String, dynamic>> answers) {
    int totalScore = answers.fold(0, (sum, a) => sum + (a['answer_score'] as int));

    // Immediate REFER_NOW triggers (override score)
    final dangerous = answers.where((a) =>
      (a['question_code'] == 'BREATHLESSNESS' && a['answer_value'] == 'severe') ||
      (a['question_code'] == 'CHEST_PAIN' && a['answer_value'] == 'severe') ||
      (a['question_code'] == 'TB_HISTORY' && a['answer_value'] == 'current') ||
      (a['question_code'] == 'PRIOR_LUNG_DIAGNOSIS' && a['answer_value'] == 'yes')
    );

    String riskLevel;
    String explanationShona;
    String explanationEnglish;

    if (dangerous.isNotEmpty) {
      riskLevel = 'REFER_NOW';
      explanationShona = 'Matiripo ako aratidza njodzi yakakwira. Enda kuchipatara Kwekwe nhasi.';
      explanationEnglish = 'Your answers show serious warning signs. Please go to Kwekwe District Hospital today.';
    } else if (totalScore >= 12) {
      riskLevel = 'REFER_NOW';
      explanationShona = 'Zvakafanana nemamiriro ane njodzi. Enda kuchipatara Kwekwe nhasi kuti upiwe X-ray.';
      explanationEnglish = 'Your exposure and symptoms suggest high risk. Go to Kwekwe District Hospital for a chest X-ray.';
    } else if (totalScore >= 6) {
      riskLevel = 'WATCH';
      explanationShona = 'Une njodzi yakati wandei. Enda kuchipatara mumwedzi uno.';
      explanationEnglish = 'You have moderate risk. Visit a clinic within the next 4 weeks.';
    } else {
      riskLevel = 'LOW';
      explanationShona = 'Njodzi yako iri pasi. Ramba uchipfeka mask yako nguva dzose.';
      explanationEnglish = 'Your risk appears low. Keep wearing your mask and stay safe.';
    }

    return {
      'risk_level': riskLevel,
      'confidence': 0.75, // lower than AI — indicate fallback
      'fallback_used': true,
      'explanation_shona': explanationShona,
      'explanation_english': explanationEnglish,
    };
  }
}
```

---

## 11. X-Ray Model Training (Google Colab)

```python
# model_training/train_densenet.ipynb
# Run on Google Colab with T4 GPU

import torch
import torchvision
import torchvision.transforms as transforms
from torch.utils.data import DataLoader, Dataset
from torchvision.models import densenet121, DenseNet121_Weights
from pytorch_grad_cam import GradCAM
from pytorch_grad_cam.utils.image import show_cam_on_image
from PIL import Image
import numpy as np

# 1. LOAD PRE-TRAINED MODEL
model = densenet121(weights=DenseNet121_Weights.IMAGENET1K_V1)

# 2. MODIFY FOR 3-CLASS OUTPUT (Normal / Stage 1 / Stage 2-3)
num_features = model.classifier.in_features
model.classifier = torch.nn.Linear(num_features, 3)

# 3. FREEZE EARLY LAYERS — only train last denseblock + classifier
for name, param in model.named_parameters():
    if 'denseblock4' not in name and 'classifier' not in name:
        param.requires_grad = False

# 4. TRANSFORMS
transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
])

# 5. TRAINING LOOP
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model = model.to(device)
optimizer = torch.optim.Adam(
    filter(lambda p: p.requires_grad, model.parameters()), lr=1e-4
)
criterion = torch.nn.CrossEntropyLoss()

# Train for 20 epochs with your dataset
# Save best model: torch.save(model.state_dict(), 'silicaguard_xray_v1.pth')

# 6. GRAD-CAM INFERENCE (backend/services/xray_model.py)
def classify_xray(image_path: str):
    model.eval()
    image = Image.open(image_path).convert('RGB')
    tensor = transform(image).unsqueeze(0).to(device)

    # Classification
    with torch.no_grad():
        output = model(tensor)
        probs = torch.softmax(output, dim=1)
        class_idx = probs.argmax().item()
        confidence = probs[0][class_idx].item()

    # Grad-CAM heatmap
    target_layer = model.features.denseblock4
    cam = GradCAM(model=model, target_layers=[target_layer])
    grayscale_cam = cam(input_tensor=tensor, targets=None)
    rgb_img = np.array(image.resize((224, 224))) / 255.0
    heatmap = show_cam_on_image(rgb_img, grayscale_cam[0], use_rgb=True)

    labels = ['NORMAL', 'STAGE_1', 'STAGE_2_3']
    return {
        'classification': labels[class_idx],
        'confidence': round(confidence, 3),
        'heatmap': heatmap  # numpy array, convert to base64 before sending
    }
```

---

## 12. Demo Day Scenarios

### Demo 1 — Tablet Screening (4 minutes)
- Character: Tendai Moyo, 42 years old, Globe and Phoenix mine, 15 years drilling, cough 3 months
- Pre-load Tendai in the database before Demo Day
- Screen Tendai live: go through all 10 questions aloud
- Expected result: REFER_NOW with red card
- Show QR referral card on screen
- Say: "At this moment, Kwekwe District Hospital has already been pre-alerted."

### Demo 2 — USSD Self-Screen (3 minutes)
- Use Africa's Talking online simulator OR real phone with sandbox shortcode
- Show: USSD menu on screen → 6 questions → session ends → WhatsApp notification arrives
- Start 60-second countdown when session ends
- WhatsApp message appears with Shona risk result and clinic address

### Demo 3 — X-Ray AI (3 minutes)
- Pre-select a Stage 1 pneumoconiosis X-ray from NIH dataset
- Open hospital dashboard in browser
- Find Tendai's referral in the tracker
- Upload the X-ray image
- Watch classification + Grad-CAM heatmap appear in real time
- Say: "This is a research-validated second opinion. In under 60 seconds. Without a radiologist."

---

## 13. Week-by-Week Build Schedule

| Week | Dates | Goal | Owner |
|---|---|---|---|
| 0 | Before Jul 14 | Healthathon registration submitted. GitHub repo created. API accounts set up. | All |
| 1 | Jul 14–20 | FastAPI + SQLite running. Claude API risk engine tested with 20 profiles. POST /api/screen returns classification. | P + F |
| 2 | Jul 21–27 | USSD 6-question flow live on AT sandbox. WhatsApp webhook receives messages. WhatsApp agent responds in Shona. Full USSD→WhatsApp journey working. | P |
| 3 | Jul 28–Aug 3 | Flutter offline screening form complete: 10 questions, local SQLite, risk result card, QR referral, sync engine. | F + P |
| 4 | Aug 4–10 | DenseNet-121 trained on Colab. /api/xray/upload endpoint returns classification + heatmap. X-ray UI in dashboard. | P |
| 5 | Aug 11–17 | Everything deployed: Render (backend), Vercel (dashboard). Domain live. Demo data seeded. WhatsApp/AT webhooks pointing to live URLs. | P + F |
| 6 | Aug 18–22 | 10 real users tested. All Shona text reviewed by native speakers. All critical bugs fixed. Load tested. | All |
| 7–9 | Aug 25–28 | Demo Day preparation: Tendai pre-loaded, backup videos recorded, pitch rehearsed, printed handouts ready. | All |

---

## 14. Environment Variables (.env — never commit to git)

```bash
# Claude API
ANTHROPIC_API_KEY=sk-ant-...

# WhatsApp (Meta Cloud API)
WHATSAPP_TOKEN=EAAj...        # Bearer token from Meta developer console
WHATSAPP_PHONE_ID=1234...     # Your WhatsApp Business phone number ID
WHATSAPP_VERIFY_TOKEN=silicaguard_verify_2026  # Any string you choose

# Africa's Talking (USSD + SMS)
AT_API_KEY=atsk_...
AT_USERNAME=sandbox           # Use 'sandbox' for development
HOSPITAL_NURSE_PHONE=+263...  # Must be registered as an AT sandbox Simulator Number to receive anything

# App Config
DATABASE_URL=./data/silicaguard.db
MODEL_PATH=./data/xray_model.pth
SECRET_KEY=your-jwt-secret-key-here
ENVIRONMENT=development       # 'development' or 'production'

# Demo auth accounts (MVP has no users table — see Section 7 Auth)
HOSPITAL_EMAIL=hospital@silicaguard.health
HOSPITAL_PASSWORD=change-me
CIMAS_EMAIL=cimas@silicaguard.health
CIMAS_PASSWORD=change-me
```

---

## 15. Key Decisions and Constraints

| Decision | Rationale |
|---|---|
| Flutter not React Native | Team uses Flutter. One codebase, true native Android performance. |
| SQLite not PostgreSQL (MVP) | Zero infrastructure cost. File-based. Sufficient for <10,000 screenings. Migrate to PostgreSQL in Phase 2. |
| Claude Haiku not Sonnet (MVP) | Haiku costs $1/$5 per MTok vs $3/$15 for Sonnet. 5x cheaper. Fast. Quality sufficient for structured risk classification. Upgrade to Sonnet in production. |
| DenseNet-121 not ResNet or EfficientNet | Pre-trained CheXNet weights available on DenseNet-121. Published literature on pneumoconiosis uses DenseNet-121. Strongest starting point. |
| Render not Railway/Fly.io | Railway has no free tier in 2026. Fly.io has no free tier. Render has a genuine free web service. Sleep on inactivity is acceptable for demo. |
| USSD uses decision tree not LLM | USSD sessions must complete in under 180 seconds. LLM calls take 3-8 seconds per turn. A 6-question LLM flow would time out. Decision tree responds in milliseconds. |
| Africa's Talking for USSD | Covers Econet, NetOne, and Telecel — all three Zimbabwean networks. Excellent free sandbox. Developer-friendly. |
| No Redux/complex state management | MVP simplicity. Provider or Riverpod is sufficient for the screening flow state. |

---

## 16. What Success Looks Like on Demo Day

A judge sitting in the room has seen SilicaGuard:
1. Screen a fictional miner on an Android phone with no internet, produce a Refer Now result with a QR code in under 10 minutes
2. Self-screen via USSD on a real phone, receive a WhatsApp result in Shona within 60 seconds of hanging up
3. Upload a real chest X-ray and see an AI classification with a coloured lung heatmap appear in under 60 seconds
4. View a live dashboard showing Kwekwe mine sites on a map, referral statuses, and a paragraph written by AI summarising the previous week

They have heard a doctor open with the story of Tendai Moyo — the Kwekwe miner losing his lungs without knowing it — and close with the vision: SilicaGuard as Zimbabwe's national occupational health intelligence platform. They have held a printed one-page handout. They have asked hard questions and received confident answers. They remember SilicaGuard after seeing 20 other teams.

---

## 17. Follow-Up & Case Management (Post-MVP Roadmap — NOT YET BUILT)

**The problem this solves:** as of this write-up, a screening is a one-shot event. A miner
scores REFER_NOW, gets a referral row and a real SMS (miner result + hospital pre-alert, both
sent via Africa's Talking — see Section 4/14), and then nothing else happens — no one checks
whether they actually went to hospital, and a WATCH-tier miner who
keeps working without a mask has no mechanism prompting them to re-screen or change behavior.
For a disease that's only manageable through early, sustained intervention, a single screening
without follow-through doesn't change outcomes.

**This section is a design sketch only** — captured now so the idea isn't lost, but explicitly
deferred past Demo Day per the team's own prioritization. Nothing below has been implemented;
the live database schema has NOT been changed.

### Proposed new table: `follow_ups`

```sql
CREATE TABLE follow_ups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    miner_id INTEGER REFERENCES miners(id),
    screening_id INTEGER REFERENCES screenings(id),
    referral_id INTEGER REFERENCES referrals(id),   -- nullable; only set for REFER_NOW cases
    risk_level_at_trigger TEXT,     -- 'WATCH' or 'REFER_NOW'
    follow_up_type TEXT,            -- 'SAFETY_EDUCATION', 'RE_SCREEN_REMINDER', 'REFERRAL_CHECK'
    due_date DATE,
    status TEXT DEFAULT 'PENDING',  -- 'PENDING', 'DONE', 'MISSED'
    notes TEXT,
    completed_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### Trigger rules

- **WATCH screening** → two follow-ups created automatically:
  - `SAFETY_EDUCATION`, due immediately — a low-cost, high-value message (dust-safety tips,
    correct PPE use) sent right away, reusing the notification stub pattern from
    `services/notifications.py`.
  - `RE_SCREEN_REMINDER`, due +30 days — prompts the miner (or a VHW passing through their
    site) to re-screen and check whether risk has changed.
- **REFER_NOW screening** → one follow-up created, tied to the `referrals` row:
  - `REFERRAL_CHECK`, due +7 days. If the linked referral's `status` is still not `COMPLETE`
    by the due date, this surfaces on a "needs follow-up" list for a VHW or hospital outreach
    worker to actively chase — someone calls the miner rather than assuming they showed up.
    If the referral does reach `COMPLETE` before the due date, this follow-up auto-resolves.

### How it would surface to a human (MVP-appropriate, no new infra)

Rather than building real push reminders first, start with a simple `GET /api/follow-ups/due`
endpoint (JWT-protected, same pattern as `/api/referrals`) returning everything with
`status='PENDING' AND due_date <= today`. This becomes a "Today's Follow-Ups" list on the
hospital/Cimas dashboard — a human works the list. Actual outbound SMS/WhatsApp reminders to
miners are a later layer on top, once real messaging (Section 9.2/notifications) exists —
don't build automated reminder delivery before the manual list view proves the workflow.

### Open questions for the team before building this

- Who owns actioning `REFERRAL_CHECK` follow-ups — Kwekwe District Hospital outreach staff,
  or the VHWs who did the original screening? This determines who the dashboard list is for.
  Not yet decided by the team, and without a named owner the list is just data that no one
  is obligated to act on.
- Is +30 days the right re-screen cadence for WATCH, or should it depend on the specific
  contributing factors (e.g. a driller with no PPE re-screens sooner than someone with only
  moderate exposure)? The Dart fallback / USSD decision tree currently treats all WATCH cases
  identically.

---

*End of SILICAGUARD.md — Version 1.6 — July 2026*
