"""
Unit tests for Risk Predictor — heuristic mode + SHAP output.
"""

import pytest
import numpy as np
from app.ml.risk_predictor import (
    _extract_features, _heuristic_predict, _score_to_level,
    _build_shap_features, predict_risk, FEATURE_NAMES,
)
from app.schemas.intake import (
    VitalsInput, VulnerabilityFlags, SymptomInput, RiskLevel
)


def make_vitals(**kwargs) -> VitalsInput:
    defaults = {
        "systolic_bp": 120, "diastolic_bp": 80,
        "heart_rate": 75, "respiratory_rate": 16,
        "spo2": 98.0, "temperature": 37.0,
    }
    defaults.update(kwargs)
    return VitalsInput(**defaults)


class TestFeatureExtraction:
    """Feature vector construction."""

    def test_correct_length(self):
        features = _extract_features(
            make_vitals(), 30, "male", VulnerabilityFlags(), []
        )
        assert len(features) == len(FEATURE_NAMES)

    def test_symptom_flags(self):
        symptoms = [
            SymptomInput(symptom_name="chest pain", is_red_flag=True),
            SymptomInput(symptom_name="bleeding"),
        ]
        features = _extract_features(
            make_vitals(), 30, "male", VulnerabilityFlags(), symptoms
        )
        chest_pain_idx = FEATURE_NAMES.index("has_chest_pain")
        bleeding_idx = FEATURE_NAMES.index("has_bleeding")
        red_flag_idx = FEATURE_NAMES.index("red_flag_count")

        assert features[chest_pain_idx] == 1.0
        assert features[bleeding_idx] == 1.0
        assert features[red_flag_idx] == 1.0  # Only chest pain is red flag

    def test_vulnerability_flags(self):
        flags = VulnerabilityFlags(pregnant=True, diabetic=True)
        features = _extract_features(
            make_vitals(), 30, "female", flags, []
        )
        preg_idx = FEATURE_NAMES.index("is_pregnant")
        diab_idx = FEATURE_NAMES.index("is_diabetic")
        assert features[preg_idx] == 1.0
        assert features[diab_idx] == 1.0


class TestHeuristicPredict:
    """Heuristic fallback prediction."""

    def test_normal_vitals_low_score(self):
        features = _extract_features(
            make_vitals(), 30, "male", VulnerabilityFlags(), []
        )
        score, shap_vals = _heuristic_predict(features)
        assert 0.0 <= score <= 1.0
        assert score < 0.30  # Normal vitals → low risk

    def test_critical_vitals_high_score(self):
        features = _extract_features(
            make_vitals(spo2=80.0, systolic_bp=70, diastolic_bp=40, respiratory_rate=40),
            30, "male", VulnerabilityFlags(), []
        )
        score, shap_vals = _heuristic_predict(features)
        assert score >= 0.50  # Should be elevated

    def test_shap_values_correct_length(self):
        features = _extract_features(
            make_vitals(), 30, "male", VulnerabilityFlags(), []
        )
        _, shap_vals = _heuristic_predict(features)
        assert len(shap_vals) == len(FEATURE_NAMES)

    def test_score_capped_at_1(self):
        """Even extreme vitals should not exceed 1.0."""
        features = _extract_features(
            make_vitals(
                spo2=70.0, systolic_bp=60, diastolic_bp=30,
                heart_rate=180, respiratory_rate=50, temperature=42.0,
            ),
            85, "male",
            VulnerabilityFlags(pregnant=False, immunocompromised=True, heart_disease=True, diabetic=True),
            [
                SymptomInput(symptom_name="chest pain", is_red_flag=True),
                SymptomInput(symptom_name="unconscious", is_red_flag=True),
                SymptomInput(symptom_name="bleeding", is_red_flag=True),
            ]
        )
        score, _ = _heuristic_predict(features)
        assert score <= 1.0


class TestScoreToLevel:
    """Risk level classification thresholds."""

    def test_low(self):
        assert _score_to_level(0.15) == RiskLevel.low

    def test_moderate(self):
        assert _score_to_level(0.45) == RiskLevel.moderate

    def test_high(self):
        assert _score_to_level(0.85) == RiskLevel.high

    def test_boundary_moderate(self):
        assert _score_to_level(0.30) == RiskLevel.moderate

    def test_boundary_high(self):
        assert _score_to_level(0.70) == RiskLevel.high


class TestSHAPFeatures:
    """SHAP feature output formatting."""

    def test_top_5_features(self):
        features = np.array([98, 120, 80, 75, 16, 37, 100, 30, 0, 0, 0, 0, 0, 1, 0.6, 40, 0, 0, 0, 0, 0, 0], dtype=np.float32)
        shap_vals = np.random.randn(22).astype(np.float32)
        top_features, text = _build_shap_features(shap_vals, features, RiskLevel.moderate)
        assert len(top_features) == 5
        assert all(hasattr(f, "feature") for f in top_features)
        assert all(hasattr(f, "shap_value") for f in top_features)
        assert isinstance(text, str)
        assert len(text) > 0

    def test_shap_values_sorted_by_abs(self):
        features = np.zeros(22, dtype=np.float32)
        shap_vals = np.array([0.1, -0.5, 0.3, 0.01] + [0.0] * 18, dtype=np.float32)
        top_features, _ = _build_shap_features(shap_vals, features, RiskLevel.low)
        # First should be the one with highest absolute value (-0.5)
        assert top_features[0].feature == FEATURE_NAMES[1]


@pytest.mark.asyncio
class TestPredictRiskAsync:
    """Async prediction entry point (heuristic mode)."""

    async def test_predict_returns_ml_result(self):
        result = await predict_risk(
            make_vitals(), 30, "male", VulnerabilityFlags(), []
        )
        assert result.risk_probability >= 0.0
        assert result.risk_probability <= 1.0
        assert result.risk_level in (RiskLevel.low, RiskLevel.moderate, RiskLevel.high)
        assert result.confidence > 0.0
        assert len(result.shap_features) == 5
        assert len(result.shap_values) == len(FEATURE_NAMES)
        assert len(result.feature_importance) == len(FEATURE_NAMES)
        assert isinstance(result.shap_text, str)

    async def test_feature_importance_sorted(self):
        result = await predict_risk(
            make_vitals(spo2=80.0), 30, "male", VulnerabilityFlags(), []
        )
        importances = [f["importance"] for f in result.feature_importance]
        assert importances == sorted(importances, reverse=True)
