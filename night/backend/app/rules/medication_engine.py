"""
Medication–Symptom Danger Correlation Engine
=============================================
Checks three categories:
  1. Drug–Drug Interactions (DDI)
  2. Drug–Condition conflicts (e.g., beta-blocker + asthma)
  3. Drug–Symptom danger patterns (e.g., anticoagulant + head injury)

Rule 3 can trigger AUTO-ESCALATION override.
"""

from typing import List, Tuple
from app.schemas.intake import MedicationInput, SymptomInput, VulnerabilityFlags, MedWarning
import logging

logger = logging.getLogger(__name__)


# ─── DDI Database (Abbreviated — use DrugBank API in production) ──────────────

DDI_RULES: dict = {
    frozenset(["warfarin", "aspirin"]): {
        "severity": "severe",
        "message": "Warfarin + Aspirin: Additive bleeding risk. Monitor INR closely.",
    },
    frozenset(["warfarin", "ibuprofen"]): {
        "severity": "severe",
        "message": "Warfarin + Ibuprofen: Significantly increased bleeding. Avoid NSAIDs.",
    },
    frozenset(["warfarin", "cotrimoxazole"]): {
        "severity": "severe",
        "message": "Warfarin + Cotrimoxazole: Potentiates anticoagulation. Reduce warfarin dose.",
    },
    frozenset(["metformin", "contrast_dye"]): {
        "severity": "severe",
        "message": "Metformin + Contrast: Hold metformin 48h before/after contrast. Lactic acidosis risk.",
    },
    frozenset(["glibenclamide", "fluconazole"]): {
        "severity": "severe",
        "message": "Glibenclamide + Fluconazole: Severe hypoglycaemia risk. Reduce glibenclamide dose.",
    },
    frozenset(["metronidazole", "alcohol"]): {
        "severity": "severe",
        "message": "Metronidazole + Alcohol: Disulfiram-like reaction. Counsel patient strictly.",
    },
    frozenset(["clarithromycin", "carbamazepine"]): {
        "severity": "severe",
        "message": "Clarithromycin + Carbamazepine: Toxic carbamazepine levels. Use azithromycin instead.",
    },
    frozenset(["diazepam", "morphine"]): {
        "severity": "severe",
        "message": "Benzodiazepine + Opioid: Respiratory depression risk. Avoid combination.",
    },
    frozenset(["misoprostol", "oxytocin"]): {
        "severity": "contraindicated",
        "message": "Misoprostol + Oxytocin: ABSOLUTELY CONTRAINDICATED. Risk of uterine rupture.",
    },
    frozenset(["lisinopril", "potassium"]): {
        "severity": "moderate",
        "message": "ACE inhibitor + Potassium supplement: Hyperkalemia risk. Monitor electrolytes.",
    },
    frozenset(["amlodipine", "simvastatin"]): {
        "severity": "moderate",
        "message": "Amlodipine + Simvastatin: Elevated statin levels. Limit simvastatin to 20mg.",
    },
}

# ─── Drug–Condition Conflicts ─────────────────────────────────────────────────

DRUG_CONDITION_RULES = [
    {
        "drugs": ["atenolol", "metoprolol", "propranolol", "bisoprolol"],
        "condition_flag": "has_asthma",  # Check against patient conditions
        "severity": "severe",
        "message": "Beta-blocker in possible asthma/COPD patient: May precipitate bronchospasm. Review necessity.",
        "override": False,
    },
    {
        "drugs": ["ibuprofen", "diclofenac", "naproxen", "indomethacin"],
        "condition_flag": "heart_disease",
        "severity": "severe",
        "message": "NSAID + cardiovascular disease: Increased MI/HF risk. Use paracetamol instead.",
        "override": False,
    },
    {
        "drugs": ["metformin"],
        "condition_flag": "renal_impairment",
        "severity": "severe",
        "message": "Metformin + renal impairment: Lactic acidosis risk. Check eGFR.",
        "override": False,
    },
]

# ─── Drug–Symptom Danger Patterns (Can force escalation) ─────────────────────

DRUG_SYMPTOM_DANGER_RULES = [
    {
        "drug_keywords": ["warfarin", "heparin", "apixaban", "rivaroxaban", "clopidogrel"],
        "symptom_keywords": ["head injury", "head trauma", "fall", "bleeding", "blood"],
        "severity": "severe",
        "message": "Anticoagulant/antiplatelet + head injury/bleeding: HIGH risk of intracranial hemorrhage. IMMEDIATE escalation required.",
        "override_escalation": True,  # Forces escalation regardless of risk score
    },
    {
        "drug_keywords": ["atenolol", "metoprolol", "propranolol", "bisoprolol", "carvedilol"],
        "symptom_keywords": ["bradycardia", "slow heart", "dizziness", "syncope", "fainted"],
        "severity": "moderate",
        "message": "Beta-blocker + bradycardia symptoms: Monitor heart rate. Consider dose reduction.",
        "override_escalation": False,
    },
    {
        "drug_keywords": ["insulin", "glibenclamide", "glipizide", "gliclazide"],
        "symptom_keywords": ["unconscious", "confusion", "seizure", "sweating", "shaking"],
        "severity": "severe",
        "message": "Insulin/sulfonylurea + altered consciousness: Severe hypoglycaemia likely. Give IV dextrose immediately.",
        "override_escalation": True,
    },
    {
        "drug_keywords": [
            drug for drug_set in [
                ["prednisolone", "dexamethasone", "methylprednisolone"],
                ["tacrolimus", "cyclosporine", "azathioprine"],
            ] for drug in drug_set
        ],
        "symptom_keywords": ["fever", "infection", "sepsis"],
        "severity": "severe",
        "message": "Immunosuppressant + fever: Serious infection / sepsis must be excluded urgently.",
        "override_escalation": True,
    },
    {
        "drug_keywords": ["lithium"],
        "symptom_keywords": ["tremor", "confusion", "diarrhea", "vomiting"],
        "severity": "severe",
        "message": "Lithium + GI symptoms/neurological: Possible lithium toxicity. Check serum levels urgently.",
        "override_escalation": True,
    },
    {
        "drug_keywords": ["methotrexate"],
        "symptom_keywords": ["mouth ulcer", "stomatitis", "breathlessness", "cough"],
        "severity": "severe",
        "message": "Methotrexate + respiratory/oral symptoms: Possible methotrexate pneumonitis or toxicity.",
        "override_escalation": True,
    },
]


def _normalize(name: str) -> str:
    return name.lower().strip()


def check_drug_interactions(medications: List[MedicationInput]) -> List[MedWarning]:
    """Check all drug pairs against DDI database."""
    warnings = []
    drug_names = [_normalize(m.drug_name) for m in medications]

    for i in range(len(drug_names)):
        for j in range(i + 1, len(drug_names)):
            pair = frozenset([drug_names[i], drug_names[j]])
            if pair in DDI_RULES:
                rule = DDI_RULES[pair]
                warnings.append(MedWarning(
                    drug1=medications[i].drug_name,
                    drug2=medications[j].drug_name,
                    warning_type="ddi",
                    severity=rule["severity"],
                    message=rule["message"],
                    action_required=rule["severity"] in ("severe", "contraindicated"),
                    override_triggered=rule["severity"] == "contraindicated",
                ))
                logger.warning(
                    f"DDI: {drug_names[i]} + {drug_names[j]} → {rule['severity']}"
                )

    return warnings


def check_drug_symptom_patterns(
    medications: List[MedicationInput],
    symptoms: List[SymptomInput],
    flags: VulnerabilityFlags,
) -> Tuple[List[MedWarning], bool]:
    """
    Check drug-symptom danger patterns.
    Returns (warnings, escalation_override_triggered).
    """
    warnings = []
    escalation_override = False

    drug_names = [_normalize(m.drug_name) for m in medications]
    symptom_names = [_normalize(s.symptom_name) for s in symptoms]

    for rule in DRUG_SYMPTOM_DANGER_RULES:
        drug_match = any(
            any(kw in d for kw in rule["drug_keywords"])
            for d in drug_names
        )
        symptom_match = any(
            any(kw in s for kw in rule["symptom_keywords"])
            for s in symptom_names
        )

        if drug_match and symptom_match:
            warnings.append(MedWarning(
                drug1=", ".join(
                    m.drug_name for m in medications
                    if any(kw in _normalize(m.drug_name) for kw in rule["drug_keywords"])
                ),
                warning_type="drug_symptom",
                severity=rule["severity"],
                message=rule["message"],
                action_required=True,
                override_triggered=rule["override_escalation"],
            ))
            if rule["override_escalation"]:
                escalation_override = True
                logger.critical(
                    f"ESCALATION OVERRIDE: Drug-symptom danger pattern triggered. "
                    f"Drug keywords: {rule['drug_keywords']}"
                )

    # Immunocompromised + fever special case
    if flags.immunocompromised:
        fever_symptoms = [s for s in symptom_names if "fever" in s or "temperature" in s]
        if fever_symptoms:
            warnings.append(MedWarning(
                drug1="Immunosuppressant therapy",
                warning_type="drug_condition",
                severity="severe",
                message="Immunocompromised patient with fever: Sepsis must be excluded. Urgent blood cultures and antibiotics.",
                action_required=True,
                override_triggered=True,
            ))
            escalation_override = True

    return warnings, escalation_override


def run_medication_engine(
    medications: List[MedicationInput],
    symptoms: List[SymptomInput],
    flags: VulnerabilityFlags,
) -> Tuple[List[MedWarning], bool]:
    """
    Main entry point for medication safety engine.
    Returns (all_warnings, escalation_override_triggered).
    """
    ddi_warnings = check_drug_interactions(medications)
    symptom_warnings, escalation_override = check_drug_symptom_patterns(
        medications, symptoms, flags
    )

    all_warnings = ddi_warnings + symptom_warnings
    # Also trigger escalation override if contraindicated DDI found
    if any(w.override_triggered for w in ddi_warnings):
        escalation_override = True

    return all_warnings, escalation_override


# Shorthand for import
medication_engine = run_medication_engine
