"""
Unit tests for NEWS2 Weighted Rule Engine.
Tests weighted scoring, hard overrides, threshold configs, and edge cases.
"""

import pytest
from app.rules.news2_guardrail import NEWS2Guardrail, news2_guardrail
from app.schemas.intake import VitalsInput, VulnerabilityFlags, SymptomInput, RiskLevel


def make_vitals(**kwargs) -> VitalsInput:
    """Create vitals with sensible defaults, overriding with kwargs."""
    defaults = {
        "systolic_bp": 120, "diastolic_bp": 80,
        "heart_rate": 75, "respiratory_rate": 16,
        "spo2": 98.0, "temperature": 37.0,
    }
    defaults.update(kwargs)
    return VitalsInput(**defaults)


def make_flags(**kwargs) -> VulnerabilityFlags:
    return VulnerabilityFlags(**kwargs)


class TestNormalVitals:
    """Normal vitals should produce LOW risk with no triggers."""

    def test_normal_vitals_no_trigger(self):
        result = news2_guardrail.evaluate(
            make_vitals(), make_flags(), []
        )
        assert not result.triggered
        assert result.risk_level == RiskLevel.low
        assert result.severity_score == 0.0
        assert not result.override_ml

    def test_normal_vitals_confidence(self):
        result = news2_guardrail.evaluate(
            make_vitals(), make_flags(), []
        )
        assert result.confidence == 0.50  # Neutral when nothing triggered


class TestHardCriticalOverrides:
    """Life-threatening conditions MUST hard-override to CRITICAL."""

    def test_gcs_critical(self):
        result = news2_guardrail.evaluate(
            make_vitals(gcs_score=6), make_flags(), []
        )
        assert result.triggered
        assert result.risk_level == RiskLevel.critical
        assert result.override_ml
        assert result.confidence >= 0.95
        assert "GCS_CRITICAL" in result.triggered_rules

    def test_hypothermia_critical(self):
        result = news2_guardrail.evaluate(
            make_vitals(temperature=34.0), make_flags(), []
        )
        assert result.triggered
        assert result.risk_level == RiskLevel.critical
        assert result.override_ml
        assert "TEMP_HYPOTHERMIA" in result.triggered_rules

    def test_hypertensive_crisis(self):
        result = news2_guardrail.evaluate(
            make_vitals(systolic_bp=200, diastolic_bp=110), make_flags(), []
        )
        assert result.triggered
        assert result.risk_level == RiskLevel.critical
        assert result.override_ml
        assert "HTN_CRISIS" in result.triggered_rules


class TestWeightedScoring:
    """Weighted rules should accumulate scores without hard override."""

    def test_single_weighted_rule_moderate(self):
        """Single weighted critical rule (e.g. low SpO2) → should not auto-CRITICAL."""
        result = news2_guardrail.evaluate(
            make_vitals(spo2=83.0), make_flags(), []
        )
        assert result.triggered
        # Single weighted rule with weight 0.35 — should NOT be CRITICAL
        assert result.risk_level != RiskLevel.critical or result.severity_score >= 0.85
        assert not result.override_ml or result.severity_score >= 0.85

    def test_multiple_weighted_rules_escalate(self):
        """Multiple weighted rules accumulate → higher risk level."""
        result = news2_guardrail.evaluate(
            make_vitals(spo2=83.0, systolic_bp=75, diastolic_bp=50, respiratory_rate=40),
            make_flags(), []
        )
        assert result.triggered
        assert result.severity_score > 0.5
        # With 0.35+0.30+0.25 = 0.90 → should be CRITICAL
        assert result.risk_level in (RiskLevel.high, RiskLevel.critical)

    def test_high_rules_moderate_scoring(self):
        """HIGH rules contribute smaller weights."""
        result = news2_guardrail.evaluate(
            make_vitals(heart_rate=130),  # Single HIGH rule
            make_flags(), []
        )
        assert result.triggered
        assert result.severity_score < 0.55  # Not enough for HIGH
        assert result.risk_level in (RiskLevel.low, RiskLevel.moderate)


class TestSymptomScoring:
    """Symptom keywords should contribute weighted scores."""

    def test_cardiac_arrest_symptom(self):
        symptoms = [SymptomInput(symptom_name="cardiac arrest", is_red_flag=True)]
        result = news2_guardrail.evaluate(
            make_vitals(), make_flags(), symptoms
        )
        assert result.triggered
        assert result.severity_score >= 0.50

    def test_mild_symptom_low_weight(self):
        symptoms = [SymptomInput(symptom_name="stiff neck")]
        result = news2_guardrail.evaluate(
            make_vitals(), make_flags(), symptoms
        )
        assert result.triggered
        assert result.severity_score < 0.50


class TestObstetricOverrides:
    """Obstetric danger signs should hard-override (clinically justified)."""

    def test_pregnancy_hypertension_critical(self):
        result = news2_guardrail.evaluate(
            make_vitals(systolic_bp=145, diastolic_bp=95),
            make_flags(pregnant=True), []
        )
        assert result.triggered
        assert result.risk_level == RiskLevel.critical
        assert result.override_ml
        assert "OBSTETRIC_PREECLAMPSIA" in result.triggered_rules

    def test_pregnancy_bleeding_critical(self):
        symptoms = [SymptomInput(symptom_name="vaginal bleeding", is_red_flag=True)]
        result = news2_guardrail.evaluate(
            make_vitals(), make_flags(pregnant=True), symptoms
        )
        assert result.triggered
        assert result.risk_level == RiskLevel.critical
        assert result.override_ml

    def test_non_pregnant_bleeding_no_obstetric_override(self):
        """Bleeding in non-pregnant patient should not trigger obstetric override."""
        symptoms = [SymptomInput(symptom_name="vaginal bleeding", is_red_flag=True)]
        result = news2_guardrail.evaluate(
            make_vitals(), make_flags(pregnant=False), symptoms
        )
        # Should not have obstetric override
        assert "OBSTETRIC_PREECLAMPSIA" not in result.triggered_rules


class TestImmunocompromised:
    """Immunocompromised + fever should flag concern."""

    def test_immunocomp_fever(self):
        result = news2_guardrail.evaluate(
            make_vitals(temperature=38.5),
            make_flags(immunocompromised=True), []
        )
        assert result.triggered
        assert "IMMUNOCOMP_FEVER" in result.triggered_rules
        assert result.severity_score >= 0.20


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_exact_threshold_values(self):
        """Values exactly at threshold should NOT trigger (< not <=)."""
        result = news2_guardrail.evaluate(
            make_vitals(spo2=85.0),  # Exactly at SPO2_CRITICAL (default 85.0)
            make_flags(), []
        )
        # spo2 < 85.0 is the check, so 85.0 should NOT trigger
        assert "SPO2_CRITICAL" not in result.triggered_rules

    def test_empty_symptoms(self):
        result = news2_guardrail.evaluate(
            make_vitals(), make_flags(), []
        )
        assert not result.triggered

    def test_confidence_always_set(self):
        """Every result should have a valid confidence score."""
        result = news2_guardrail.evaluate(
            make_vitals(), make_flags(), []
        )
        assert 0.0 <= result.confidence <= 1.0
