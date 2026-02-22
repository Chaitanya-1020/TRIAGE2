# CDSS — Best Practices & Recommended Improvements

## ══ CLINICAL SAFETY PRINCIPLES ══════════════════════════════════════════

### 1. Rule Engine Is Absolute
The NEWS2 rule-based guardrail ALWAYS runs before ML.
CRITICAL rule triggers bypass ML output entirely.
This ensures zero false-negative risk from model uncertainty.

### 2. Explainability Is Non-Negotiable
Every ML prediction ships with SHAP feature attribution.
PHW sees: "SpO₂ + shock index driving HIGH risk."
Specialist sees: SBAR + SHAP chart side-by-side.
No black-box outputs are surfaced to clinicians.

### 3. Doctor Authority Is Final
All AI outputs are labeled as "AI-assisted suggestion."
System prompts clinician to confirm before escalating.
Specialist advice submitted by human overwrites all AI recommendations.

---

## ══ PRODUCTION IMPROVEMENTS ═════════════════════════════════════════════

### ML & AI

| Improvement | Why | How |
|-------------|-----|-----|
| Train on real PHC data | Synthetic data limits accuracy | Partner with NHM for deidentified outcome data |
| Add LIME alongside SHAP | Complementary local explanations | pip install lime |
| Calibrate model output | Raw XGBoost probabilities need calibration | CalibratedClassifierCV (already in train_model.py) |
| Add model versioning | Track which model version made each decision | Store model_version field in risk_assessments |
| Drift detection | Clinical patterns shift seasonally | Evidently AI or custom monitoring |
| Lightweight TFLite model | For offline/edge inference | Convert XGBoost → ONNX → CoreML/TFLite |

### Backend

| Improvement | Why | How |
|-------------|-----|-----|
| Async task queue | ML inference shouldn't block API | Celery + Redis or ARQ |
| DB connection pooling | Async SQLAlchemy + asyncpg | Already configured; tune pool_size |
| Response caching | Same vitals → same result (TTL 5min) | Redis cache with vitals hash key |
| GraphQL API | More flexible querying for specialist portal | Strawberry GraphQL |
| FHIR R4 compliance | Interoperability with hospital HIS | fhir.resources Python library |
| HL7 v2 parsing | Receive lab results from existing systems | python-hl7 |
| Audit log streaming | Real-time audit to SIEM | Stream audit_logs to Elasticsearch |

### Infrastructure

| Improvement | Why | How |
|-------------|-----|-----|
| Kubernetes (K8s) | Scale backend pods independently | Helm chart provided separately |
| Service mesh | Secure inter-service communication | Istio or Linkerd |
| CDN for frontend | Fast load in rural areas | Cloudflare or AWS CloudFront |
| Progressive Web App | Works offline, installable on tablet | next-pwa (already in Next.js) |
| Offline-first sync | Rural areas with no connectivity | IndexedDB + background sync API |
| SMS fallback | If internet fails, SMS specialist | Twilio or MSG91 (India) |

### Security

| Improvement | Why | How |
|-------------|-----|-----|
| mTLS between services | Zero-trust service authentication | Nginx client certs |
| KMS for PHI keys | HSM-backed encryption keys | AWS KMS / Azure Key Vault |
| ABAC (Attribute-Based Access Control) | Fine-grained data access | OPA (Open Policy Agent) |
| PHI tokenization | Replace PHI with tokens in logs | Presidio (Microsoft) |
| Penetration testing | OWASP Top 10 for healthcare APIs | Burp Suite, OWASP ZAP |
| DAST in CI/CD | Catch vulns in pipeline | OWASP ZAP GitHub Action |

---

## ══ API SAMPLE PAYLOADS ══════════════════════════════════════════════════

### POST /api/v1/analyze/risk

REQUEST:
```json
{
  "patient_name": "Sunita Devi",
  "age": 45,
  "sex": "female",
  "vulnerability_flags": {
    "diabetic": true,
    "heart_disease": true
  },
  "vitals": {
    "systolic_bp": 85,
    "diastolic_bp": 55,
    "heart_rate": 118,
    "respiratory_rate": 26,
    "spo2": 91.5,
    "temperature": 38.8
  },
  "medications": [
    {"drug_name": "Atenolol", "dose": "50mg", "frequency": "OD"},
    {"drug_name": "Metformin", "dose": "500mg", "frequency": "BD"}
  ],
  "symptoms": [
    {"symptom_name": "chest pain", "is_red_flag": true, "severity": "severe"},
    {"symptom_name": "difficulty breathing", "is_red_flag": true}
  ],
  "chief_complaint": "Severe chest pain + breathing difficulty for 2 hours"
}
```

RESPONSE:
```json
{
  "assessment_id": "a3f1-...",
  "case_id": "b7d2-...",
  "final_risk_level": "critical",
  "final_risk_score": 0.951,
  "rule_engine": {
    "triggered": true,
    "risk_level": "critical",
    "reasons": [
      "Critical oxygen desaturation: SpO₂ = 91.5% (threshold < 90.0%)",
      "Severe hypotension/shock risk: SBP = 85 mmHg",
      "Critical symptom reported: 'chest pain'",
      "Significant tachycardia: HR = 118 bpm"
    ],
    "override_ml": true
  },
  "ml_result": {
    "risk_probability": 0.934,
    "risk_level": "high",
    "shap_features": [
      {"feature": "systolic_bp", "value": 85.0, "shap_value": 0.312, "label": "Systolic Blood Pressure = 85.0 (impact: ↑0.312)"},
      {"feature": "spo2", "value": 91.5, "shap_value": 0.298, "label": "Oxygen Saturation (SpO₂) = 91.5 (impact: ↑0.298)"},
      {"feature": "has_chest_pain", "value": 1.0, "shap_value": 0.245, "label": "Chest Pain Symptom = 1.0 (impact: ↑0.245)"},
      {"feature": "shock_index", "value": 1.39, "shap_value": 0.201, "label": "Shock Index (HR/SBP) = 1.4 (impact: ↑0.201)"},
      {"feature": "has_heart_disease", "value": 1.0, "shap_value": 0.088, "label": "Heart Disease = 1.0 (impact: ↑0.088)"}
    ],
    "shap_text": "Primary driver: low blood pressure combined with oxygen desaturation suggest critical deterioration requiring immediate intervention."
  },
  "med_warnings": [
    {
      "drug1": "Atenolol",
      "warning_type": "drug_symptom",
      "severity": "severe",
      "message": "Beta-blocker + bradycardia symptoms: Monitor heart rate. Consider dose reduction.",
      "action_required": true,
      "override_triggered": false
    }
  ],
  "recommendation": "⚠️ IMMEDIATE ESCALATION REQUIRED. Critical finding: Critical oxygen desaturation: SpO₂ = 91.5%. AI interpretation: Primary driver: low blood pressure combined with oxygen desaturation suggest critical deterioration. ⚠️ Medication alert: Beta-blocker + bradycardia symptoms. Maternal emergency protocol...",
  "escalation_suggested": true,
  "assessed_at": "2025-01-15T10:30:00Z"
}
```

---

## ══ DEPLOYMENT CHECKLIST ═════════════════════════════════════════════════

### Pre-Launch
- [ ] Replace SECRET_KEY with 64-char random string
- [ ] Replace PHI_ENCRYPTION_KEY with proper Fernet key
- [ ] Configure GEMINI_API_KEY
- [ ] Set strong POSTGRES_PASSWORD
- [ ] Configure SSL certificates (Let's Encrypt)
- [ ] Train XGBoost model on real data and save to ml/models/
- [ ] Run DB migrations: `alembic upgrade head`
- [ ] Create initial admin user
- [ ] Test WebSocket connectivity under simulated rural bandwidth (3G)
- [ ] Penetration test API endpoints
- [ ] Verify SHAP explanations are clinically sensible
- [ ] Clinical validation review by qualified medical officer

### Monitoring
- [ ] Set up Prometheus + Grafana for API metrics
- [ ] Alert on: p99 latency > 2s, error rate > 1%, ML model unavailable
- [ ] Log all PHI access to audit_logs table
- [ ] Weekly model performance review
- [ ] Monthly clinical accuracy audit against actual outcomes
