"""
Pydantic v2 Schemas — Strict clinical validation.
All vitals validated against safe physiological ranges.
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime
import uuid


# ─── Enums ────────────────────────────────────────────────────────────────────

class SexEnum(str, Enum):
    male = "male"
    female = "female"
    other = "other"

class RiskLevel(str, Enum):
    low = "low"
    moderate = "moderate"
    high = "high"
    critical = "critical"

class AdviceType(str, Enum):
    urgent_referral = "urgent_referral"
    observe_2h = "observe_2h"
    manage_locally = "manage_locally"
    start_iv_fluids = "start_iv_fluids"
    admit = "admit"
    custom = "custom"


# ─── Auth ─────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str

class SignupRequest(BaseModel):
    email: str
    password: str
    full_name: str
    role: str = "phw"
    facility_id: Optional[str] = None
    facility_name: Optional[str] = None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    full_name: str


# ─── Vitals ───────────────────────────────────────────────────────────────────

class VitalsInput(BaseModel):
    # Absolute physiological limits for initial validation
    systolic_bp: int = Field(..., ge=40, le=350, description="mmHg")
    diastolic_bp: int = Field(..., ge=20, le=250, description="mmHg")
    heart_rate: int = Field(..., ge=20, le=350, description="bpm")
    respiratory_rate: int = Field(..., ge=4, le=80, description="/min")
    spo2: float = Field(..., ge=50.0, le=100.0, description="%")
    temperature: float = Field(..., ge=30.0, le=45.0, description="°C")
    blood_glucose_mgdl: Optional[int] = Field(None, ge=20, le=1000)
    weight_kg: Optional[float] = Field(None, ge=1, le=300)
    gcs_score: Optional[int] = Field(None, ge=3, le=15)

    @field_validator("diastolic_bp")
    @classmethod
    def dbp_lt_sbp(cls, v: int, info) -> int:
        if "systolic_bp" in info.data and v >= info.data["systolic_bp"]:
            raise ValueError("Diastolic BP must be less than systolic BP")
        return v

    @property
    def shock_index(self) -> float:
        return self.heart_rate / max(self.systolic_bp, 1)

    @property
    def pulse_pressure(self) -> int:
        return self.systolic_bp - self.diastolic_bp


# ─── Patient Intake ───────────────────────────────────────────────────────────

class VulnerabilityFlags(BaseModel):
    pregnant: bool = False
    diabetic: bool = False
    elderly: bool = False
    heart_disease: bool = False
    immunocompromised: bool = False

class MedicationInput(BaseModel):
    rxnorm_code: Optional[str] = None
    drug_name: str = Field(..., min_length=2, max_length=200)
    dose: Optional[str] = None
    frequency: Optional[str] = None
    route: Optional[str] = None

class SymptomInput(BaseModel):
    symptom_name: str = Field(..., min_length=2)
    is_red_flag: bool = False
    severity: Optional[str] = Field(None, pattern="^(mild|moderate|severe)$")
    duration_hours: Optional[int] = Field(None, ge=0)

class PatientIntakeRequest(BaseModel):
    # Demographics (will be encrypted at service layer)
    patient_name: str = Field(..., min_length=2, max_length=200)
    age: int = Field(..., ge=0, le=120)
    sex: SexEnum
    village: Optional[str] = None
    district: Optional[str] = None

    # Clinical
    vulnerability_flags: VulnerabilityFlags = VulnerabilityFlags()
    vitals: VitalsInput
    medications: List[MedicationInput] = Field(default_factory=list, max_length=30)
    symptoms: List[SymptomInput] = Field(default_factory=list, max_length=30)
    chief_complaint: str = Field(..., min_length=5, max_length=1000)

    @model_validator(mode="after")
    def validate_pregnancy_sex(self):
        if self.vulnerability_flags.pregnant and self.sex == SexEnum.male:
            raise ValueError("Pregnancy flag cannot be set for male patients")
        return self


# ─── Decision Engine Response ─────────────────────────────────────────────────

class SHAPFeature(BaseModel):
    feature: str
    value: Any
    shap_value: float
    label: str         # Human-readable: "SpO2 (92%) contributed most to HIGH risk"

class MedWarning(BaseModel):
    drug1: str
    drug2: Optional[str] = None
    warning_type: str  # "ddi", "drug_condition", "drug_symptom"
    severity: str      # "mild", "moderate", "severe", "contraindicated"
    message: str
    action_required: bool = False
    override_triggered: bool = False  # Forces escalation

class RuleEngineResult(BaseModel):
    triggered: bool
    risk_level: Optional[RiskLevel] = None
    reasons: List[str] = []
    override_ml: bool = False
    confidence: float = 0.0
    severity_score: float = 0.0

class MLResult(BaseModel):
    risk_probability: float
    risk_level: RiskLevel
    confidence: float = 0.0
    shap_features: List[SHAPFeature]
    shap_text: str     # "Low BP + elevated HR suggest early shock."
    shap_values: List[float] = []         # Raw SHAP values for all features
    feature_importance: List[dict] = []   # [{name, label, value, importance}]

class RiskAssessmentResponse(BaseModel):
    assessment_id: str
    case_id: str
    final_risk_level: RiskLevel
    final_risk_score: float
    confidence: float = 0.0
    rule_engine: RuleEngineResult
    ml_result: Optional[MLResult]
    med_warnings: List[MedWarning]
    recommendation: str
    escalation_suggested: bool
    assessed_at: datetime


# ─── Escalation ───────────────────────────────────────────────────────────────

class EscalateRequest(BaseModel):
    case_id: str
    escalation_reason: str = Field(..., min_length=10)
    specialist_id: Optional[str] = None   # If targeting specific specialist

class EscalationResponse(BaseModel):
    case_id: str
    specialist_magic_link: str
    sbar: dict                             # {situation, background, assessment, recommendation}
    escalated_at: datetime


# ─── Specialist ───────────────────────────────────────────────────────────────

class SpecialistAdviceRequest(BaseModel):
    case_id: str
    advice_type: AdviceType
    custom_notes: Optional[str] = None
    medications_advised: List[str] = []
    investigations: List[str] = []
    follow_up_hours: Optional[int] = Field(None, ge=1, le=720)

class SpecialistPortalData(BaseModel):
    """Full data package for specialist portal."""
    case_id: str
    patient_summary: dict
    vitals: VitalsInput
    symptoms: List[SymptomInput]
    medications: List[MedicationInput]
    risk_assessment: RiskAssessmentResponse
    sbar: dict
    phw_name: str
    facility: str
    escalated_at: datetime
