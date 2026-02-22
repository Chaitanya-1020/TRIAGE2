"""
Unit tests for Medication Safety Engine.
Tests DDI checks, drug-symptom patterns, and escalation overrides.
"""

import pytest
from app.rules.medication_engine import (
    check_drug_interactions,
    check_drug_symptom_patterns,
    run_medication_engine,
)
from app.schemas.intake import MedicationInput, SymptomInput, VulnerabilityFlags


def make_med(name: str) -> MedicationInput:
    return MedicationInput(drug_name=name)


def make_sym(name: str, red_flag: bool = False) -> SymptomInput:
    return SymptomInput(symptom_name=name, is_red_flag=red_flag)


class TestDrugDrugInteractions:
    """DDI pair detection."""

    def test_warfarin_aspirin_ddi(self):
        meds = [make_med("Warfarin"), make_med("Aspirin")]
        warnings = check_drug_interactions(meds)
        assert len(warnings) == 1
        assert warnings[0].warning_type == "ddi"
        assert warnings[0].severity == "severe"

    def test_no_ddi(self):
        meds = [make_med("Paracetamol"), make_med("Omeprazole")]
        warnings = check_drug_interactions(meds)
        assert len(warnings) == 0

    def test_contraindicated_ddi(self):
        meds = [make_med("Misoprostol"), make_med("Oxytocin")]
        warnings = check_drug_interactions(meds)
        assert len(warnings) == 1
        assert warnings[0].severity == "contraindicated"
        assert warnings[0].override_triggered

    def test_multiple_ddi(self):
        meds = [make_med("Warfarin"), make_med("Aspirin"), make_med("Ibuprofen")]
        warnings = check_drug_interactions(meds)
        # warfarin+aspirin AND warfarin+ibuprofen
        assert len(warnings) == 2

    def test_case_insensitive(self):
        meds = [make_med("WARFARIN"), make_med("aspirin")]
        warnings = check_drug_interactions(meds)
        assert len(warnings) == 1


class TestDrugSymptomPatterns:
    """Drug-symptom danger pattern detection."""

    def test_anticoagulant_head_injury_override(self):
        meds = [make_med("Warfarin")]
        symptoms = [make_sym("head injury", red_flag=True)]
        warnings, override = check_drug_symptom_patterns(
            meds, symptoms, VulnerabilityFlags()
        )
        assert len(warnings) >= 1
        assert override is True

    def test_insulin_unconscious_override(self):
        meds = [make_med("Insulin")]
        symptoms = [make_sym("unconscious")]
        warnings, override = check_drug_symptom_patterns(
            meds, symptoms, VulnerabilityFlags()
        )
        assert override is True

    def test_beta_blocker_bradycardia_no_override(self):
        meds = [make_med("Atenolol")]
        symptoms = [make_sym("bradycardia")]
        warnings, override = check_drug_symptom_patterns(
            meds, symptoms, VulnerabilityFlags()
        )
        assert len(warnings) >= 1
        assert override is False  # Beta-blocker + bradycardia is moderate, not override

    def test_no_match(self):
        meds = [make_med("Paracetamol")]
        symptoms = [make_sym("headache")]
        warnings, override = check_drug_symptom_patterns(
            meds, symptoms, VulnerabilityFlags()
        )
        assert len(warnings) == 0
        assert override is False


class TestImmunocompromisedFever:
    """Immunocompromised + fever special case."""

    def test_immunocomp_fever_override(self):
        meds = []
        symptoms = [make_sym("fever")]
        warnings, override = check_drug_symptom_patterns(
            meds, symptoms, VulnerabilityFlags(immunocompromised=True)
        )
        assert override is True
        assert any("sepsis" in w.message.lower() for w in warnings)


class TestFullMedicationEngine:
    """Integration test for run_medication_engine."""

    def test_combined_output(self):
        meds = [make_med("Warfarin"), make_med("Aspirin")]
        symptoms = [make_sym("head injury", red_flag=True)]
        warnings, override = run_medication_engine(
            meds, symptoms, VulnerabilityFlags()
        )
        # Should have DDI warning + drug-symptom warning
        assert len(warnings) >= 2
        assert override is True

    def test_empty_inputs(self):
        warnings, override = run_medication_engine(
            [], [], VulnerabilityFlags()
        )
        assert len(warnings) == 0
        assert override is False
