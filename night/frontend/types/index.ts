// ── Enums ─────────────────────────────────────────────────────────────────────

export type RiskLevel = "low" | "moderate" | "high" | "critical";
export type SexEnum = "male" | "female" | "other";
export type AdviceType =
    | "urgent_referral"
    | "observe_2h"
    | "manage_locally"
    | "start_iv_fluids"
    | "admit"
    | "custom";

// ── Auth ──────────────────────────────────────────────────────────────────────

export interface LoginRequest {
    username: string;
    password: string;
}

export interface TokenResponse {
    access_token: string;
    token_type: string;
    role: "phw" | "specialist";
    full_name: string;
}

export interface User {
    id: string;
    email: string;
    full_name: string;
    role: "phw" | "specialist";
    facility?: string;
}

// ── Vitals ────────────────────────────────────────────────────────────────────

export interface VitalsInput {
    systolic_bp: number;
    diastolic_bp: number;
    heart_rate: number;
    respiratory_rate: number;
    spo2: number;
    temperature: number;
    blood_glucose_mgdl?: number;
    weight_kg?: number;
    gcs_score?: number;
}

// ── Patient Intake ────────────────────────────────────────────────────────────

export interface VulnerabilityFlags {
    pregnant: boolean;
    diabetic: boolean;
    elderly: boolean;
    heart_disease: boolean;
    immunocompromised: boolean;
}

export interface MedicationInput {
    rxnorm_code?: string;
    drug_name: string;
    dose?: string;
    frequency?: string;
    route?: string;
}

export interface SymptomInput {
    symptom_name: string;
    is_red_flag: boolean;
    severity?: "mild" | "moderate" | "severe";
    duration_hours?: number;
}

export interface PatientIntakeRequest {
    patient_name: string;
    age: number;
    sex: SexEnum;
    village?: string;
    district?: string;
    vulnerability_flags: VulnerabilityFlags;
    vitals: VitalsInput;
    medications: MedicationInput[];
    symptoms: SymptomInput[];
    chief_complaint: string;
}

// ── Decision Engine Response ──────────────────────────────────────────────────

export interface SHAPFeature {
    feature: string;
    value: unknown;
    shap_value: number;
    label: string;
}

export interface MedWarning {
    drug1: string;
    drug2?: string;
    warning_type: "ddi" | "drug_condition" | "drug_symptom";
    severity: "mild" | "moderate" | "severe" | "contraindicated";
    message: string;
    action_required: boolean;
    override_triggered: boolean;
}

export interface RuleEngineResult {
    triggered: boolean;
    risk_level?: RiskLevel;
    reasons: string[];
    override_ml: boolean;
}

export interface MLResult {
    risk_probability: number;
    risk_level: RiskLevel;
    shap_features: SHAPFeature[];
    shap_text: string;
}

export interface RiskAssessmentResponse {
    assessment_id: string;
    case_id: string;
    final_risk_level: RiskLevel;
    final_risk_score: number;
    rule_engine: RuleEngineResult;
    ml_result?: MLResult;
    med_warnings: MedWarning[];
    recommendation: string;
    escalation_suggested: boolean;
    assessed_at: string;
}

// ── Escalation ────────────────────────────────────────────────────────────────

export interface EscalationResponse {
    case_id: string;
    specialist_magic_link: string;
    sbar: {
        situation: string;
        background: string;
        assessment: string;
        recommendation: string;
    };
    escalated_at: string;
}

// ── Case ──────────────────────────────────────────────────────────────────────

export interface Case {
    id: string;
    patient_name: string;
    age: number;
    sex: SexEnum;
    chief_complaint: string;
    risk_level: RiskLevel;
    risk_score: number;
    status: "active" | "escalated" | "advised" | "closed";
    created_at: string;
    escalated_at?: string;
    phw_name?: string;
}

// ── Specialist ────────────────────────────────────────────────────────────────

export interface SpecialistAdviceRequest {
    case_id: string;
    advice_type: AdviceType;
    custom_notes?: string;
    medications_advised: string[];
    investigations: string[];
    follow_up_hours?: number;
}

export interface SpecialistPortalData {
    case_id: string;
    patient_summary: {
        age: number;
        sex: SexEnum;
        vulnerability_flags: VulnerabilityFlags;
    };
    vitals: VitalsInput;
    symptoms: SymptomInput[];
    medications: MedicationInput[];
    risk_assessment: RiskAssessmentResponse;
    sbar: EscalationResponse["sbar"];
    phw_name: string;
    facility: string;
    escalated_at: string;
}

// ── WebSocket ─────────────────────────────────────────────────────────────────

export interface WSMessage {
    type: "STATUS_UPDATE" | "ADVICE_PUSH" | "PING";
    case_id?: string;
    status?: string;
    advice?: SpecialistAdviceRequest;
    timestamp?: string;
}

// ── UI ────────────────────────────────────────────────────────────────────────

export interface AppState {
    user: User | null;
    token: string | null;
    currentView: "login" | "dashboard" | "intake" | "results" | "specialist";
}

export interface IntakeFormState {
    step: number;
    patient_name: string;
    age: string;
    sex: SexEnum | "";
    village: string;
    district: string;
    pregnant: boolean;
    diabetic: boolean;
    elderly: boolean;
    heart_disease: boolean;
    immunocompromised: boolean;
    systolic_bp: string;
    diastolic_bp: string;
    heart_rate: string;
    respiratory_rate: string;
    spo2: string;
    temperature: string;
    blood_glucose_mgdl: string;
    weight_kg: string;
    gcs_score: string;
    medications: MedicationInput[];
    symptoms: SymptomInput[];
    chief_complaint: string;
}
