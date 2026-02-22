"""
NEWS2-Style Rule-Based Safety Guardrail — Weighted Scoring
==========================================================
Replaces binary override logic with weighted severity scoring.
Only genuinely life-threatening findings (GCS ≤ 8, cardiac arrest,
severe hypothermia) trigger hard CRITICAL overrides.

All other rules contribute weighted severity scores that are
aggregated into a final rule-engine risk level.

Reference: Royal College of Physicians NEWS2 (2017) + WHO ETAT guidelines.
"""

from typing import List
from dataclasses import dataclass, field
from app.schemas.intake import VitalsInput, VulnerabilityFlags, SymptomInput, RiskLevel
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


@dataclass
class RuleResult:
    triggered: bool = False
    risk_level: RiskLevel = RiskLevel.low
    reasons: List[str] = field(default_factory=list)
    override_ml: bool = False
    confidence: float = 0.0
    severity_score: float = 0.0
    triggered_rules: List[str] = field(default_factory=list)

    @property
    def is_critical(self) -> bool:
        return self.risk_level == RiskLevel.critical


class NEWS2Guardrail:
    """
    Weighted clinical safety guardrail.
    Hard overrides for life-threatening findings only.
    Everything else uses weighted scoring → aggregated risk level.
    """

    # ─── HARD OVERRIDE — life-threatening (always CRITICAL) ───────────────
    # These are genuinely life-threatening and must always override ML.

    HARD_CRITICAL_RULES = [
        {
            "check": lambda v: v.gcs_score is not None and v.gcs_score <= settings.GCS_CRITICAL,
            "reason": lambda v: f"Severely altered consciousness: GCS = {v.gcs_score}",
            "flag": "GCS_CRITICAL",
            "weight": 1.0,
        },
        {
            "check": lambda v: v.temperature < settings.TEMP_HYPOTHERMIA,
            "reason": lambda v: f"Hypothermia: Temp = {v.temperature}°C",
            "flag": "TEMP_HYPOTHERMIA",
            "weight": 1.0,
        },
        {
            "check": lambda v: v.systolic_bp >= settings.SBP_HYPERTENSIVE_CRISIS,
            "reason": lambda v: f"Hypertensive crisis: BP = {v.systolic_bp}/{v.diastolic_bp} mmHg",
            "flag": "HTN_CRISIS",
            "weight": 1.0,
        },
    ]

    # ─── WEIGHTED CRITICAL — serious but scored, not auto-override ────────

    WEIGHTED_CRITICAL_RULES = [
        {
            "check": lambda v: v.spo2 < settings.SPO2_CRITICAL,
            "reason": lambda v: f"Severe oxygen desaturation: SpO₂ = {v.spo2}% (threshold < {settings.SPO2_CRITICAL}%)",
            "flag": "SPO2_CRITICAL",
            "weight": 0.35,
        },
        {
            "check": lambda v: v.systolic_bp < settings.SBP_CRITICAL,
            "reason": lambda v: f"Severe hypotension/shock risk: SBP = {v.systolic_bp} mmHg (threshold < {settings.SBP_CRITICAL} mmHg)",
            "flag": "SBP_CRITICAL",
            "weight": 0.30,
        },
        {
            "check": lambda v: v.respiratory_rate > settings.RR_CRITICAL,
            "reason": lambda v: f"Severe respiratory distress: RR = {v.respiratory_rate}/min (threshold > {settings.RR_CRITICAL}/min)",
            "flag": "RR_CRITICAL",
            "weight": 0.25,
        },
        {
            "check": lambda v: v.temperature > settings.TEMP_CRITICAL,
            "reason": lambda v: f"Hyperpyrexia: Temp = {v.temperature}°C (threshold > {settings.TEMP_CRITICAL}°C)",
            "flag": "TEMP_CRITICAL",
            "weight": 0.20,
        },
        {
            "check": lambda v: v.blood_glucose_mgdl is not None and v.blood_glucose_mgdl < settings.BG_SEVERE_HYPO,
            "reason": lambda v: f"Severe hypoglycaemia: BG = {v.blood_glucose_mgdl} mg/dL",
            "flag": "HYPOGLYCEMIA_SEVERE",
            "weight": 0.25,
        },
    ]

    # ─── HIGH Warning Thresholds (weighted scoring) ──────────────────────

    HIGH_RULES = [
        {
            "check": lambda v: settings.SPO2_CRITICAL <= v.spo2 < settings.SPO2_HIGH,
            "reason": lambda v: f"Low oxygen saturation: SpO₂ = {v.spo2}%",
            "flag": "SPO2_HIGH",
            "weight": 0.15,
        },
        {
            "check": lambda v: settings.SBP_CRITICAL <= v.systolic_bp < settings.SBP_HIGH,
            "reason": lambda v: f"Low systolic BP: {v.systolic_bp} mmHg",
            "flag": "SBP_HIGH",
            "weight": 0.12,
        },
        {
            "check": lambda v: v.heart_rate > settings.HR_HIGH_TACHY,
            "reason": lambda v: f"Significant tachycardia: HR = {v.heart_rate} bpm",
            "flag": "HR_TACHY",
            "weight": 0.12,
        },
        {
            "check": lambda v: v.heart_rate < settings.HR_HIGH_BRADY,
            "reason": lambda v: f"Significant bradycardia: HR = {v.heart_rate} bpm",
            "flag": "HR_BRADY",
            "weight": 0.10,
        },
        {
            "check": lambda v: v.respiratory_rate > settings.RR_HIGH,
            "reason": lambda v: f"Tachypnoea: RR = {v.respiratory_rate}/min",
            "flag": "RR_HIGH",
            "weight": 0.10,
        },
        {
            "check": lambda v: v.temperature >= settings.TEMP_HIGH_FEVER,
            "reason": lambda v: f"High fever: Temp = {v.temperature}°C",
            "flag": "TEMP_FEVER",
            "weight": 0.08,
        },
        {
            "check": lambda v: v.blood_glucose_mgdl is not None and v.blood_glucose_mgdl > settings.BG_SEVERE_HYPER,
            "reason": lambda v: f"Severe hyperglycaemia: BG = {v.blood_glucose_mgdl} mg/dL",
            "flag": "HYPERGLYCEMIA",
            "weight": 0.10,
        },
        {
            "check": lambda v: v.shock_index > 1.0,
            "reason": lambda v: f"Elevated shock index: {v.shock_index:.2f} (HR/SBP)",
            "flag": "SHOCK_INDEX",
            "weight": 0.15,
        },
    ]

    # ─── Symptom-based Critical Keywords ──────────────────────────────────

    CRITICAL_SYMPTOM_KEYWORDS = {
        "cardiac arrest":    0.50,
        "stopped breathing": 0.50,
        "unconscious":       0.30,
        "seizure":           0.25,
        "convulsion":        0.25,
        "stroke":            0.30,
        "paralysis":         0.25,
        "sudden vision loss":0.20,
        "coughing blood":    0.20,
        "vomiting blood":    0.20,
        "chest pain":        0.18,
        "severe abdominal pain": 0.15,
        "stiff neck":        0.15,
    }

    # ─── Pregnancy Danger Signs ───────────────────────────────────────────

    OBSTETRIC_CRITICAL_KEYWORDS = [
        "bleeding", "vaginal bleeding", "antepartum hemorrhage",
        "severe headache", "visual disturbance", "blurred vision",
        "epigastric pain", "fits", "convulsion", "eclampsia",
        "reduced fetal movement", "leaking", "cord prolapse"
    ]

    def evaluate(
        self,
        vitals: VitalsInput,
        flags: VulnerabilityFlags,
        symptoms: List[SymptomInput],
    ) -> RuleResult:
        result = RuleResult()
        total_weight = 0.0

        # ── 1. Hard override — life-threatening ──────────────────────────
        for rule in self.HARD_CRITICAL_RULES:
            try:
                if rule["check"](vitals):
                    result.triggered = True
                    result.override_ml = True
                    result.risk_level = RiskLevel.critical
                    result.reasons.append(rule["reason"](vitals))
                    result.triggered_rules.append(rule["flag"])
                    total_weight += rule["weight"]
                    logger.warning(
                        f"NEWS2 HARD CRITICAL: {rule['flag']}",
                        extra={"rule_flag": rule["flag"], "override": True}
                    )
            except Exception as e:
                logger.error(f"Rule evaluation error ({rule['flag']}): {e}")

        # If hard critical triggered, set max confidence and return
        if result.override_ml:
            result.severity_score = min(total_weight, 1.0)
            result.confidence = 0.98
            return result

        # ── 2. Weighted critical rules ───────────────────────────────────
        for rule in self.WEIGHTED_CRITICAL_RULES:
            try:
                if rule["check"](vitals):
                    result.triggered = True
                    result.reasons.append(rule["reason"](vitals))
                    result.triggered_rules.append(rule["flag"])
                    total_weight += rule["weight"]
                    logger.info(
                        f"NEWS2 weighted critical: {rule['flag']} (+{rule['weight']})",
                        extra={"rule_flag": rule["flag"], "weight": rule["weight"]}
                    )
            except Exception as e:
                logger.error(f"Rule evaluation error ({rule['flag']}): {e}")

        # ── 3. HIGH thresholds ───────────────────────────────────────────
        for rule in self.HIGH_RULES:
            try:
                if rule["check"](vitals):
                    result.triggered = True
                    result.reasons.append(rule["reason"](vitals))
                    result.triggered_rules.append(rule["flag"])
                    total_weight += rule["weight"]
                    logger.info(
                        f"NEWS2 HIGH rule: {rule['flag']} (+{rule['weight']})",
                        extra={"rule_flag": rule["flag"], "weight": rule["weight"]}
                    )
            except Exception as e:
                logger.error(f"Rule evaluation error ({rule['flag']}): {e}")

        # ── 4. Symptom red flags (weighted) ──────────────────────────────
        sym_names = [s.symptom_name.lower() for s in symptoms]
        for keyword, weight in self.CRITICAL_SYMPTOM_KEYWORDS.items():
            if any(keyword in s for s in sym_names):
                result.triggered = True
                result.reasons.append(f"Critical symptom reported: '{keyword}'")
                result.triggered_rules.append(f"SYMPTOM_{keyword.upper().replace(' ', '_')}")
                total_weight += weight
                logger.info(f"Symptom trigger: '{keyword}' (+{weight})")

        # ── 5. Obstetric danger signs (hard override — clinically justified)
        if flags.pregnant:
            for keyword in self.OBSTETRIC_CRITICAL_KEYWORDS:
                if any(keyword in s for s in sym_names):
                    result.triggered = True
                    result.override_ml = True
                    result.risk_level = RiskLevel.critical
                    result.reasons.append(f"Obstetric danger sign: '{keyword}'")
                    result.triggered_rules.append(f"OBSTETRIC_{keyword.upper().replace(' ', '_')}")
                    total_weight += 0.40
                    logger.warning(f"Obstetric CRITICAL: '{keyword}'")

            # Pregnancy + hypertension (preeclampsia) — hard override
            if vitals.systolic_bp >= 140 or vitals.diastolic_bp >= 90:
                result.triggered = True
                result.risk_level = RiskLevel.critical
                result.override_ml = True
                result.reasons.append(
                    f"Pregnancy hypertension (possible preeclampsia): "
                    f"BP {vitals.systolic_bp}/{vitals.diastolic_bp} mmHg"
                )
                result.triggered_rules.append("OBSTETRIC_PREECLAMPSIA")
                total_weight += 0.40

        # If obstetric override was triggered, return early
        if result.override_ml:
            result.severity_score = min(total_weight, 1.0)
            result.confidence = 0.95
            return result

        # ── 6. Immunocompromised + fever ──────────────────────────────────
        if flags.immunocompromised and vitals.temperature >= 38.0:
            result.triggered = True
            result.reasons.append(
                f"Immunocompromised patient with fever: {vitals.temperature}°C — "
                "sepsis must be excluded"
            )
            result.triggered_rules.append("IMMUNOCOMP_FEVER")
            total_weight += 0.20

        # ── 7. Aggregate weighted score → risk level ─────────────────────
        result.severity_score = min(total_weight, 1.0)

        if result.triggered:
            if result.severity_score >= settings.CRITICAL_OVERRIDE_THRESHOLD:
                result.risk_level = RiskLevel.critical
                result.override_ml = True
                result.confidence = 0.90
            elif result.severity_score >= settings.HIGH_OVERRIDE_THRESHOLD:
                result.risk_level = RiskLevel.high
                result.confidence = 0.82
            elif result.severity_score >= 0.25:
                result.risk_level = RiskLevel.moderate
                result.confidence = 0.70
            else:
                result.risk_level = RiskLevel.low
                result.confidence = 0.60
        else:
            result.confidence = 0.50  # No rules triggered — neutral

        logger.info(
            f"NEWS2 result: score={result.severity_score:.2f} "
            f"level={result.risk_level} rules={len(result.triggered_rules)} "
            f"confidence={result.confidence:.2f}"
        )

        return result


# Singleton
news2_guardrail = NEWS2Guardrail()
