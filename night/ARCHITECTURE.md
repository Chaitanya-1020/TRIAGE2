# Production Hybrid Clinical Decision Support System
## Architecture & Design Documentation

---

## SYSTEM ARCHITECTURE DIAGRAM

```
═══════════════════════════════════════════════════════════════════════════════
                    HYBRID CDSS — FULL SYSTEM OVERVIEW
═══════════════════════════════════════════════════════════════════════════════

 ┌──────────────────────────────────────────────────────────────────────────┐
 │                        CLIENTS (Low-Bandwidth Optimized)                 │
 │   ┌─────────────────────┐              ┌───────────────────────────┐    │
 │   │  PHW Mobile/Tablet  │              │  Specialist Doctor Portal │    │
 │   │  (Next.js 15 PWA)   │              │  (Next.js 15 App Router)  │    │
 │   └──────────┬──────────┘              └─────────────┬─────────────┘    │
 └──────────────┼───────────────────────────────────────┼──────────────────┘
                │ HTTPS + WSS                            │ Magic Link + JWT
                ▼                                        ▼
 ┌──────────────────────────────────────────────────────────────────────────┐
 │                          NGINX REVERSE PROXY                             │
 │           TLS Termination │ Rate Limiting │ Load Balancing               │
 └──────────────────────────┬───────────────────────────────────────────────┘
                            │
 ┌──────────────────────────▼───────────────────────────────────────────────┐
 │                       FASTAPI APPLICATION LAYER                          │
 │                                                                          │
 │  ┌─────────────────────────────────────────────────────────────────┐    │
 │  │                    API ROUTER  (/api/v1/*)                      │    │
 │  │  /worker/login     /intake     /analyze     /escalate           │    │
 │  │  /specialist/*     /cases/*    /ws/case/*                       │    │
 │  └──────────────────────────────┬──────────────────────────────────┘    │
 │                                 │                                        │
 │  ┌──────────────────────────────▼──────────────────────────────────┐    │
 │  │                   MIDDLEWARE CHAIN                               │    │
 │  │  JWT Auth → Request Logging → PHI Audit → CORS → Rate Limit     │    │
 │  └──────────────────────────────┬──────────────────────────────────┘    │
 └──────────────────────────────────┼──────────────────────────────────────┘
                                    │
          ┌─────────────────────────┼────────────────────────────┐
          ▼                         ▼                             ▼
 ┌─────────────────┐    ┌───────────────────────┐    ┌──────────────────────┐
 │  RULE ENGINE    │    │   ML INFERENCE LAYER  │    │  MED-SYMPTOM ENGINE  │
 │  (NEWS2-style)  │    │                       │    │                      │
 │                 │    │  ┌─────────────────┐  │    │  Drug-Drug pairs     │
 │  SpO2 < 90 →    │    │  │  XGBoost Model  │  │    │  Drug-Condition      │
 │  CRITICAL       │    │  │  predict_proba  │  │    │  Drug-Symptom        │
 │                 │    │  └────────┬────────┘  │    │  danger patterns     │
 │  BP < 90 →      │    │          │            │    │                      │
 │  CRITICAL       │    │  ┌────────▼────────┐  │    │  Anticoag+HeadInj → │
 │                 │    │  │  SHAP Values    │  │    │  Auto-escalate       │
 │  RR > 30 →      │    │  │  Top 5 drivers  │  │    │                      │
 │  CRITICAL       │    │  └─────────────────┘  │    └──────────────────────┘
 │                 │    │                       │
 │  Rule OVERRIDES │    │  Output: risk_prob    │
 │  ML output      │    │  + shap_values        │
 └────────┬────────┘    └──────────┬────────────┘
          │                        │
          └────────────┬───────────┘
                       ▼
         ┌─────────────────────────────┐
         │    DECISION AGGREGATOR      │
         │                             │
         │  Priority cascade:          │
         │  1. Rule CRITICAL → Final   │
         │  2. Med Override → Flag     │
         │  3. ML score → Risk tier    │
         │  4. Combined recommendation │
         └─────────────┬───────────────┘
                       │
         ┌─────────────▼───────────────┐
         │   AI SBAR GENERATOR         │
         │   (Gemini 1.5 Flash API)    │
         │   On escalation only        │
         └─────────────┬───────────────┘
                       │
 ┌─────────────────────▼──────────────────────────────────────────────────┐
 │                    WEBSOCKET SERVER                                      │
 │    Patient-case channels │ JWT-validated │ Role-bound rooms             │
 │    PHW ←→ Specialist real-time sync                                     │
 └─────────────────────────────────────────────────────────────────────────┘
                       │
 ┌─────────────────────▼──────────────────────────────────────────────────┐
 │                    DATA LAYER                                            │
 │  ┌──────────────────┐   ┌───────────────┐   ┌────────────────────┐     │
 │  │   PostgreSQL     │   │     Redis     │   │   Object Storage   │     │
 │  │  (Primary DB)    │   │  (WS state,   │   │  (ML model files,  │     │
 │  │  JSONB / FHIR    │   │   sessions,   │   │   audit exports)   │     │
 │  │  Audit logs      │   │   cache)      │   │                    │     │
 │  │  Row-level sec.  │   └───────────────┘   └────────────────────┘     │
 │  └──────────────────┘                                                   │
 └─────────────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════
                        DECISION PIPELINE (Step-by-Step)
═══════════════════════════════════════════════════════════════════════════════

  PHW submits patient data
          │
          ▼
  [1] Pydantic v2 validates all fields (ranges, types, cross-field rules)
          │
          ▼
  [2] Run in PARALLEL:
      ├── Rule Engine → check critical thresholds
      ├── XGBoost → predict risk probability (0–1)
      └── Med Engine → check drug interactions + danger patterns
          │
          ▼
  [3] AGGREGATE:
      ├── If ANY rule CRITICAL → risk = CRITICAL, skip ML tier
      ├── If Med override → inject warning, may force escalation
      └── Else → use ML risk tier (Low/Moderate/High)
          │
          ▼
  [4] Generate SHAP top-5 feature drivers (always, for transparency)
          │
          ▼
  [5] Return RiskAssessment to PHW dashboard
          │
    PHW decides to escalate?
          │ YES
          ▼
  [6] Generate magic link → notify specialist
  [7] Gemini generates SBAR summary
  [8] WebSocket broadcasts case status update
          │
          ▼
  [9] Specialist reviews → Acknowledges → Advises
  [10] Advice pushed via WebSocket to PHW in real time
  [11] Full audit trail written to PostgreSQL
```

---

## FOLDER STRUCTURE

```
cdss/
├── backend/
│   ├── app/
│   │   ├── main.py                     # FastAPI app + middleware
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── router.py           # Aggregate all routers
│   │   │       └── endpoints/
│   │   │           ├── auth.py         # /worker/login, /refresh
│   │   │           ├── intake.py       # Patient intake
│   │   │           ├── analyze.py      # Hybrid decision engine
│   │   │           ├── escalate.py     # Escalation + SBAR
│   │   │           ├── specialist.py   # Specialist portal
│   │   │           └── cases.py        # Case CRUD
│   │   ├── core/
│   │   │   ├── config.py               # Settings (pydantic-settings)
│   │   │   ├── security.py             # JWT, password hashing
│   │   │   ├── logging.py              # Structured audit logging
│   │   │   └── dependencies.py        # FastAPI Depends()
│   │   ├── db/
│   │   │   ├── session.py              # Async SQLAlchemy engine
│   │   │   └── base.py                 # Base model
│   │   ├── models/                     # SQLAlchemy ORM models
│   │   │   ├── user.py
│   │   │   ├── patient.py
│   │   │   ├── case.py
│   │   │   ├── vitals.py
│   │   │   ├── risk_assessment.py
│   │   │   └── specialist_advice.py
│   │   ├── schemas/                    # Pydantic v2 schemas
│   │   │   ├── auth.py
│   │   │   ├── intake.py
│   │   │   ├── decision.py
│   │   │   └── specialist.py
│   │   ├── services/
│   │   │   ├── auth_service.py
│   │   │   ├── case_service.py
│   │   │   ├── sbar_service.py         # Gemini API
│   │   │   └── notification_service.py
│   │   ├── ml/
│   │   │   ├── model_loader.py         # Model init + caching
│   │   │   ├── risk_predictor.py       # XGBoost inference
│   │   │   ├── shap_explainer.py       # SHAP values
│   │   │   └── train_model.py          # Training script
│   │   ├── rules/
│   │   │   ├── news2_guardrail.py      # Critical vital rules
│   │   │   └── medication_engine.py    # DDI + danger patterns
│   │   └── websocket/
│   │       ├── manager.py              # Connection manager
│   │       └── handlers.py             # WS event handlers
│   ├── alembic/                        # DB migrations
│   ├── tests/
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
│
├── frontend/
│   ├── app/
│   │   ├── layout.tsx                  # Root layout
│   │   ├── auth/login/page.tsx
│   │   ├── dashboard/
│   │   │   ├── page.tsx                # PHW dashboard
│   │   │   └── intake/page.tsx         # Multi-step form
│   │   └── specialist/
│   │       └── portal/page.tsx
│   ├── components/
│   │   ├── forms/                      # Intake steps
│   │   ├── charts/                     # SHAP chart (Recharts)
│   │   └── layout/
│   ├── hooks/
│   │   └── useWebSocket.ts
│   ├── lib/
│   │   └── api.ts                      # API client
│   └── types/index.ts
│
└── infrastructure/
    ├── docker/
    │   ├── docker-compose.yml
    │   └── docker-compose.prod.yml
    └── nginx/
        └── nginx.conf
```
