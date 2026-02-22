-- ═══════════════════════════════════════════════════════════════════
-- CDSS Production Database Schema
-- PostgreSQL 15+ with JSONB, Row-Level Security, Audit Logging
-- ═══════════════════════════════════════════════════════════════════

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- fuzzy drug name search

-- ─── ENUMS ────────────────────────────────────────────────────────────────

CREATE TYPE user_role AS ENUM ('phw', 'specialist', 'admin');
CREATE TYPE case_status AS ENUM (
    'intake', 'analyzed', 'escalated',
    'specialist_reviewing', 'advised', 'closed', 'cancelled'
);
CREATE TYPE risk_level AS ENUM ('low', 'moderate', 'high', 'critical');
CREATE TYPE advice_type AS ENUM (
    'urgent_referral', 'observe_2h', 'manage_locally',
    'start_iv_fluids', 'admit', 'custom'
);

-- ─── USERS ────────────────────────────────────────────────────────────────

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    full_name       VARCHAR(255) NOT NULL,
    role            user_role NOT NULL DEFAULT 'phw',
    facility_id     VARCHAR(100),                   -- PHC/CHC code
    facility_name   VARCHAR(255),
    is_active       BOOLEAN NOT NULL DEFAULT true,
    is_verified     BOOLEAN NOT NULL DEFAULT false,
    last_login_at   TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}',             -- extra attributes
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ                     -- soft delete
);

CREATE INDEX idx_users_email ON users(email) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_role ON users(role) WHERE deleted_at IS NULL;

-- ─── PATIENTS ─────────────────────────────────────────────────────────────

CREATE TABLE patients (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- Encrypted PII (AES-256 at application layer)
    name_encrypted      TEXT NOT NULL,
    dob_encrypted       TEXT,
    phone_encrypted     TEXT,

    -- De-identified searchable fields
    age                 SMALLINT NOT NULL CHECK (age BETWEEN 0 AND 150),
    sex                 VARCHAR(10) NOT NULL CHECK (sex IN ('male', 'female', 'other')),
    village             VARCHAR(255),
    district            VARCHAR(255),
    state               VARCHAR(100),

    -- Vulnerability flags
    vulnerability_flags JSONB NOT NULL DEFAULT '{
        "pregnant": false,
        "diabetic": false,
        "elderly": false,
        "heart_disease": false,
        "immunocompromised": false
    }',

    -- FHIR-compatible full patient record
    fhir_resource       JSONB,

    created_by          UUID NOT NULL REFERENCES users(id),
    facility_id         VARCHAR(100),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at          TIMESTAMPTZ
);

CREATE INDEX idx_patients_created_by ON patients(created_by);
CREATE INDEX idx_patients_flags ON patients USING GIN(vulnerability_flags);

-- ─── CASES ────────────────────────────────────────────────────────────────

CREATE TABLE cases (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id              UUID NOT NULL REFERENCES patients(id),
    phw_id                  UUID NOT NULL REFERENCES users(id),
    specialist_id           UUID REFERENCES users(id),
    status                  case_status NOT NULL DEFAULT 'intake',
    chief_complaint         TEXT,
    escalation_reason       TEXT,
    specialist_magic_token  TEXT UNIQUE,            -- secure escalation link
    magic_token_expires_at  TIMESTAMPTZ,
    closed_at               TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at              TIMESTAMPTZ
);

CREATE INDEX idx_cases_patient ON cases(patient_id);
CREATE INDEX idx_cases_phw ON cases(phw_id);
CREATE INDEX idx_cases_specialist ON cases(specialist_id);
CREATE INDEX idx_cases_status ON cases(status) WHERE deleted_at IS NULL;
CREATE INDEX idx_cases_magic_token ON cases(specialist_magic_token) WHERE specialist_magic_token IS NOT NULL;

-- ─── VITALS ───────────────────────────────────────────────────────────────

CREATE TABLE vitals (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_id             UUID NOT NULL REFERENCES cases(id),
    recorded_by         UUID NOT NULL REFERENCES users(id),

    systolic_bp         SMALLINT CHECK (systolic_bp BETWEEN 40 AND 350),
    diastolic_bp        SMALLINT CHECK (diastolic_bp BETWEEN 20 AND 250),
    heart_rate          SMALLINT CHECK (heart_rate BETWEEN 20 AND 350),
    respiratory_rate    SMALLINT CHECK (respiratory_rate BETWEEN 4 AND 80),
    spo2                NUMERIC(4,1) CHECK (spo2 BETWEEN 50 AND 100),
    temperature         NUMERIC(4,1) CHECK (temperature BETWEEN 30 AND 45),
    blood_glucose_mgdl  SMALLINT CHECK (blood_glucose_mgdl BETWEEN 20 AND 1000),
    weight_kg           NUMERIC(5,1),
    gcs_score           SMALLINT CHECK (gcs_score BETWEEN 3 AND 15),

    -- Raw JSON for extensibility
    raw_readings        JSONB DEFAULT '{}',

    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_vitals_case ON vitals(case_id);
CREATE INDEX idx_vitals_recorded_at ON vitals(recorded_at DESC);

-- ─── MEDICATIONS ──────────────────────────────────────────────────────────

CREATE TABLE case_medications (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_id         UUID NOT NULL REFERENCES cases(id),
    rxnorm_code     VARCHAR(20),
    drug_name       VARCHAR(255) NOT NULL,
    dose            VARCHAR(100),
    frequency       VARCHAR(100),
    route           VARCHAR(50),
    is_current      BOOLEAN DEFAULT true,
    added_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_medications_case ON case_medications(case_id);
CREATE INDEX idx_medications_rxnorm ON case_medications(rxnorm_code);
-- Trigram index for fuzzy drug search
CREATE INDEX idx_medications_name_trgm ON case_medications USING GIN(drug_name gin_trgm_ops);

-- ─── SYMPTOMS ─────────────────────────────────────────────────────────────

CREATE TABLE case_symptoms (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_id         UUID NOT NULL REFERENCES cases(id),
    symptom_code    VARCHAR(50),                -- SNOMED/ICD code if available
    symptom_name    VARCHAR(255) NOT NULL,
    is_red_flag     BOOLEAN NOT NULL DEFAULT false,
    severity        VARCHAR(20) CHECK (severity IN ('mild', 'moderate', 'severe')),
    duration_hours  INTEGER,
    notes           TEXT,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_symptoms_case ON case_symptoms(case_id);
CREATE INDEX idx_symptoms_red_flags ON case_symptoms(case_id) WHERE is_red_flag = true;

-- ─── RISK ASSESSMENTS ─────────────────────────────────────────────────────

CREATE TABLE risk_assessments (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_id                 UUID NOT NULL REFERENCES cases(id),
    vitals_id               UUID REFERENCES vitals(id),

    -- Rule engine output
    rule_triggered          BOOLEAN NOT NULL DEFAULT false,
    rule_level              risk_level,
    rule_reasons            JSONB DEFAULT '[]',     -- ["SpO2 < 90%", ...]

    -- ML output
    ml_risk_probability     NUMERIC(4,3) CHECK (ml_risk_probability BETWEEN 0 AND 1),
    ml_risk_level           risk_level,
    shap_values             JSONB DEFAULT '{}',     -- feature: shap_value pairs
    shap_top_features       JSONB DEFAULT '[]',     -- [{feature, value, shap, label}]
    shap_text_interpretation TEXT,

    -- Medication engine output
    med_warnings            JSONB DEFAULT '[]',
    med_override_triggered  BOOLEAN DEFAULT false,

    -- Final aggregated
    final_risk_level        risk_level NOT NULL,
    final_risk_score        NUMERIC(4,3),
    recommendation          TEXT,
    escalation_suggested    BOOLEAN DEFAULT false,

    -- AI SBAR (generated on escalation)
    sbar_situation          TEXT,
    sbar_background         TEXT,
    sbar_assessment         TEXT,
    sbar_recommendation     TEXT,
    sbar_generated_at       TIMESTAMPTZ,

    model_version           VARCHAR(50),
    assessed_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_risk_case ON risk_assessments(case_id);
CREATE INDEX idx_risk_level ON risk_assessments(final_risk_level);

-- ─── SPECIALIST ADVICE ────────────────────────────────────────────────────

CREATE TABLE specialist_advice (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_id             UUID NOT NULL REFERENCES cases(id),
    risk_assessment_id  UUID NOT NULL REFERENCES risk_assessments(id),
    specialist_id       UUID NOT NULL REFERENCES users(id),

    acknowledged_at     TIMESTAMPTZ,
    advice_type         advice_type NOT NULL,
    custom_notes        TEXT,
    medications_advised JSONB DEFAULT '[]',
    investigations      JSONB DEFAULT '[]',     -- lab tests, imaging
    follow_up_hours     INTEGER,

    submitted_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_advice_case ON specialist_advice(case_id);
CREATE INDEX idx_advice_specialist ON specialist_advice(specialist_id);

-- ─── AUDIT LOG ────────────────────────────────────────────────────────────

CREATE TABLE audit_logs (
    id              BIGSERIAL PRIMARY KEY,
    user_id         UUID REFERENCES users(id),
    action          VARCHAR(100) NOT NULL,      -- "case.create", "risk.assess", etc.
    resource_type   VARCHAR(50),
    resource_id     UUID,
    ip_address      INET,
    user_agent      TEXT,
    request_id      UUID,
    old_value       JSONB,
    new_value       JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_user ON audit_logs(user_id);
CREATE INDEX idx_audit_resource ON audit_logs(resource_type, resource_id);
CREATE INDEX idx_audit_created ON audit_logs(created_at DESC);

-- ─── ROW LEVEL SECURITY ───────────────────────────────────────────────────

ALTER TABLE patients ENABLE ROW LEVEL SECURITY;
ALTER TABLE cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE vitals ENABLE ROW LEVEL SECURITY;

-- PHWs only see their own patients/cases
CREATE POLICY phw_own_cases ON cases
    USING (phw_id = current_setting('app.current_user_id')::UUID
           OR current_setting('app.current_user_role') IN ('specialist', 'admin'));

-- ─── UPDATED_AT TRIGGER ───────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_patients_updated BEFORE UPDATE ON patients
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_cases_updated BEFORE UPDATE ON cases
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ─── DRUG REFERENCE TABLE ─────────────────────────────────────────────────

CREATE TABLE drug_reference (
    id              SERIAL PRIMARY KEY,
    rxnorm_code     VARCHAR(20) UNIQUE,
    generic_name    VARCHAR(255) NOT NULL,
    brand_names     JSONB DEFAULT '[]',
    drug_class      VARCHAR(100),
    contraindications JSONB DEFAULT '[]',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_drug_rxnorm ON drug_reference(rxnorm_code);
CREATE INDEX idx_drug_name_trgm ON drug_reference USING GIN(generic_name gin_trgm_ops);

-- ─── DDI INTERACTION TABLE ────────────────────────────────────────────────

CREATE TABLE drug_interactions (
    id              SERIAL PRIMARY KEY,
    drug1_rxnorm    VARCHAR(20),
    drug2_rxnorm    VARCHAR(20),
    drug1_name      VARCHAR(255) NOT NULL,
    drug2_name      VARCHAR(255) NOT NULL,
    severity        VARCHAR(20) NOT NULL CHECK (severity IN ('mild', 'moderate', 'severe', 'contraindicated')),
    mechanism       TEXT,
    clinical_effect TEXT NOT NULL,
    recommendation  TEXT NOT NULL,
    source          VARCHAR(100),
    UNIQUE(drug1_rxnorm, drug2_rxnorm)
);
