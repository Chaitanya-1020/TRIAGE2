"""
XGBoost Risk Prediction + SHAP Explainability
==============================================
Model: XGBoost binary classifier
Target: P(high-risk event within 24 hours)
Output: probability (0–1) + SHAP top-5 feature drivers + confidence

SHAP ensures every prediction is explainable.
"Low BP + elevated HR suggest early shock."
"""

import numpy as np
import asyncio
import logging
from typing import List, Tuple

from app.schemas.intake import (
    VitalsInput, VulnerabilityFlags, SymptomInput,
    MLResult, SHAPFeature, RiskLevel
)
from app.ml.model_loader import model_registry

logger = logging.getLogger(__name__)


# ─── Feature Engineering ──────────────────────────────────────────────────────

FEATURE_NAMES = [
    "spo2", "systolic_bp", "diastolic_bp", "heart_rate", "respiratory_rate",
    "temperature", "blood_glucose", "age_years", "sex_encoded",
    "is_pregnant", "is_diabetic", "has_heart_disease", "is_immunocompromised",
    "bmi_proxy", "shock_index", "pulse_pressure",
    "has_chest_pain", "has_altered_consciousness", "has_breathing_difficulty",
    "has_severe_headache", "has_bleeding", "red_flag_count"
]

FEATURE_LABELS = {
    "spo2": "Oxygen Saturation (SpO₂)",
    "systolic_bp": "Systolic Blood Pressure",
    "diastolic_bp": "Diastolic Blood Pressure",
    "heart_rate": "Heart Rate",
    "respiratory_rate": "Respiratory Rate",
    "temperature": "Temperature",
    "blood_glucose": "Blood Glucose",
    "age_years": "Patient Age",
    "sex_encoded": "Sex",
    "is_pregnant": "Pregnancy",
    "is_diabetic": "Diabetes",
    "has_heart_disease": "Heart Disease",
    "is_immunocompromised": "Immunocompromised",
    "bmi_proxy": "Weight Category",
    "shock_index": "Shock Index (HR/SBP)",
    "pulse_pressure": "Pulse Pressure",
    "has_chest_pain": "Chest Pain Symptom",
    "has_altered_consciousness": "Altered Consciousness",
    "has_breathing_difficulty": "Breathing Difficulty",
    "has_severe_headache": "Severe Headache",
    "has_bleeding": "Bleeding Symptom",
    "red_flag_count": "Number of Red Flag Symptoms",
}


def _extract_features(
    vitals: VitalsInput,
    age: int,
    sex: str,
    flags: VulnerabilityFlags,
    symptoms: List[SymptomInput],
) -> np.ndarray:
    sym_lower = [s.symptom_name.lower() for s in symptoms]

    def has_symptom(*keywords) -> float:
        return 1.0 if any(any(kw in s for kw in keywords) for s in sym_lower) else 0.0

    red_flag_count = sum(1 for s in symptoms if s.is_red_flag)

    features = np.array([
        vitals.spo2,
        vitals.systolic_bp,
        vitals.diastolic_bp,
        vitals.heart_rate,
        vitals.respiratory_rate,
        vitals.temperature,
        vitals.blood_glucose_mgdl or 100.0,
        float(age),
        0.0 if sex == "male" else 1.0,
        1.0 if flags.pregnant else 0.0,
        1.0 if flags.diabetic else 0.0,
        1.0 if flags.heart_disease else 0.0,
        1.0 if flags.immunocompromised else 0.0,
        float(vitals.weight_kg or 60) / 60.0,  # BMI proxy (normalized)
        vitals.shock_index,
        float(vitals.pulse_pressure),
        has_symptom("chest pain", "chest tightness"),
        has_symptom("unconscious", "confused", "confusion", "altered"),
        has_symptom("breathing", "breathless", "dyspnoea"),
        has_symptom("headache", "severe headache"),
        has_symptom("bleeding", "hemorrhage", "blood"),
        float(red_flag_count),
    ], dtype=np.float32)

    return features


# ─── Heuristic Scoring (fallback when model not loaded) ───────────────────────

def _heuristic_predict(features: np.ndarray) -> Tuple[float, np.ndarray]:
    """
    Calibrated heuristic that approximates XGBoost output via logit and sigmoid.
    This guarantees mathematically valid SHAP values matching the final score.
    """
    (spo2, sbp, dbp, hr, rr, temp, bg, age, sex, preg,
     diabetic, heart_dz, immunocomp, bmi, shock_idx, pp,
     chest_pain, confusion, breathing, headache, bleeding, rf_count) = features

    import math

    # Calculate individual feature impacts (SHAP values in log-odds space)
    # The baseline logit controls the default probability when all values are normal.
    base_value = -2.5  # ~7.5% base probability

    # Calculate impacts
    spo2_impact = max((96.0 - spo2) * 0.15, 0.0) if spo2 < 96 else 0.0
    sbp_impact = (90.0 - sbp) * 0.05 if sbp < 90 else max((sbp - 140) * 0.03, 0.0)
    dbp_impact = 0.0
    hr_impact = (hr - 80) * 0.02 if hr > 80 else 0.0
    rr_impact = max((rr - 18) * 0.08, 0.0)
    temp_impact = (temp - 37) * 0.3 if temp > 37 else (36 - temp) * 0.3 if temp < 36 else 0.0
    bg_impact = max((bg - 140) * 0.005, 0.0) if bg > 140 else max((70 - bg) * 0.02, 0.0)
    age_impact = (age - 40) * 0.015
    sex_impact = 0.0
    preg_impact = preg * 0.5
    diabetic_impact = diabetic * 0.4
    heart_dz_impact = heart_dz * 0.6
    immunocomp_impact = immunocomp * 0.8
    bmi_impact = 0.0
    shock_idx_impact = (shock_idx - 0.7) * 2.0 if shock_idx > 0.7 else 0.0
    pp_impact = 0.0
    chest_pain_impact = chest_pain * 1.5
    confusion_impact = confusion * 2.0
    breathing_impact = breathing * 1.2
    headache_impact = headache * 0.5
    bleeding_impact = bleeding * 1.0
    rf_count_impact = rf_count * 0.5

    shap_values = np.array([
        spo2_impact, sbp_impact, dbp_impact, hr_impact, rr_impact, temp_impact,
        bg_impact, age_impact, sex_impact, preg_impact, diabetic_impact, heart_dz_impact,
        immunocomp_impact, bmi_impact, shock_idx_impact, pp_impact, chest_pain_impact,
        confusion_impact, breathing_impact, headache_impact, bleeding_impact, rf_count_impact
    ], dtype=np.float32)

    # Convert logit margin to probability using sigmoid
    logit = base_value + np.sum(shap_values)
    probability = 1.0 / (1.0 + math.exp(-logit))

    return float(probability), shap_values


# ─── Main Predictor ───────────────────────────────────────────────────────────

def _score_to_level(score: float) -> RiskLevel:
    if score >= 0.70:   return RiskLevel.high
    elif score >= 0.30: return RiskLevel.moderate
    return RiskLevel.low


def _build_shap_features(
    shap_values: np.ndarray,
    features: np.ndarray,
    risk_level: RiskLevel,
) -> Tuple[List[SHAPFeature], str]:
    """Build top-5 SHAP features with clinical labels and text summary."""

    # Sort by absolute SHAP value, descending
    indices = np.argsort(np.abs(shap_values))[::-1][:5]

    top_features = []
    for idx in indices:
        name = FEATURE_NAMES[idx]
        label = FEATURE_LABELS.get(name, name)
        shap_val = float(shap_values[idx])
        feat_val = float(features[idx])

        top_features.append(SHAPFeature(
            feature=name,
            value=round(feat_val, 4),
            shap_value=round(shap_val, 4),
            label=f"{label} = {feat_val:.1f} (impact: {'↑' if shap_val > 0 else '↓'}{abs(shap_val):.3f})",
        ))

    # Generate clinical text interpretation
    text = _build_shap_text(top_features, risk_level)
    return top_features, text


def _build_shap_text(features: List[SHAPFeature], risk_level: RiskLevel) -> str:
    """Convert SHAP values into a human-readable clinical sentence."""
    if not features:
        return "Insufficient data to generate clinical interpretation."

    top = features[0]
    second = features[1] if len(features) > 1 else None

    def get_label(feat: SHAPFeature) -> str:
        if feat.feature == "systolic_bp":
            return "low blood pressure" if feat.value < 100 else "elevated blood pressure"
        if feat.feature == "age_years":
            return "younger age" if feat.value < 40 else "older age"
        
        interpretations = {
            "spo2": "oxygen desaturation",
            "shock_index": "shock indicators (elevated HR relative to BP)",
            "respiratory_rate": "rapid breathing",
            "heart_rate": "rapid heart rate",
            "has_altered_consciousness": "altered level of consciousness",
            "has_chest_pain": "chest pain",
            "is_immunocompromised": "immunocompromised state",
            "is_pregnant": "pregnancy-related risk",
            "temperature": "abnormal temperature",
        }
        return interpretations.get(feat.feature, feat.feature.replace("_", " "))

    top_label = get_label(top)
    text = f"Primary driver: {top_label}"

    if second:
        second_label = get_label(second)
        text += f" combined with {second_label}"

    risk_phrase = {
        RiskLevel.critical: "suggest critical deterioration requiring immediate intervention",
        RiskLevel.high: "indicate high risk — escalation strongly recommended",
        RiskLevel.moderate: "suggest moderate risk — close monitoring required",
        RiskLevel.low: "suggest lower risk — standard care appropriate",
    }

    return f"{text} {risk_phrase.get(risk_level, 'require clinical review')}."


async def predict_risk(
    vitals: VitalsInput,
    age: int,
    sex: str,
    flags: VulnerabilityFlags,
    symptoms: List[SymptomInput],
) -> MLResult:
    """
    Main async prediction entry point.
    Uses real XGBoost model if loaded, else heuristic fallback.
    """
    features = _extract_features(vitals, age, sex, flags, symptoms)

    if model_registry.is_ready() and model_registry.model is not None:
        # Production: real XGBoost inference + SHAP
        loop = asyncio.get_event_loop()

        risk_prob = await loop.run_in_executor(
            None,
            lambda: float(model_registry.model.predict_proba([features])[0][1])
        )

        # Handle both TreeExplainer and KernelExplainer output formats
        def _get_shap_values():
            sv = model_registry.explainer.shap_values(features)
            # TreeExplainer may return a list [class_0_vals, class_1_vals]
            if isinstance(sv, list):
                return sv[1] if len(sv) > 1 else sv[0]
            # Or a single array
            if sv.ndim > 1:
                return sv[:, 1] if sv.shape[1] > 1 else sv[:, 0]
            return sv

        shap_vals = await loop.run_in_executor(None, _get_shap_values)
        confidence = 0.90
    else:
        # Fallback heuristic
        risk_prob, shap_vals = _heuristic_predict(features)
        confidence = 0.72

    risk_level = _score_to_level(risk_prob)
    top_features, shap_text = _build_shap_features(shap_vals, features, risk_level)

    # Build raw shap_values list and feature_importance for API response
    shap_values_list = [round(float(v), 4) for v in shap_vals]
    feature_importance = [
        {
            "name": FEATURE_NAMES[i],
            "label": FEATURE_LABELS.get(FEATURE_NAMES[i], FEATURE_NAMES[i]),
            "value": round(float(features[i]), 4),
            "importance": round(abs(float(shap_vals[i])), 4),
        }
        for i in range(len(FEATURE_NAMES))
    ]
    # Sort by importance descending
    feature_importance.sort(key=lambda x: x["importance"], reverse=True)

    logger.info(
        f"ML prediction: prob={risk_prob:.3f} level={risk_level} "
        f"confidence={confidence:.2f} "
        f"mode={'model' if model_registry.is_ready() else 'heuristic'}"
    )

    return MLResult(
        risk_probability=round(risk_prob, 3),
        risk_level=risk_level,
        confidence=confidence,
        shap_features=top_features,
        shap_text=shap_text,
        shap_values=shap_values_list,
        feature_importance=feature_importance,
    )
