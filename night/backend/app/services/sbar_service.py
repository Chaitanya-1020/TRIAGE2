"""
Gemini 1.5 Flash — AI SBAR Generation Service
===============================================
SBAR: Situation, Background, Assessment, Recommendation
Generated once per escalation, stored in DB.
"""

import google.generativeai as genai
import json
import logging
from typing import Optional

from app.core.config import settings
from app.schemas.intake import (
    VitalsInput, VulnerabilityFlags, SymptomInput,
    MedicationInput, RiskAssessmentResponse
)

logger = logging.getLogger(__name__)

# Configure Gemini
if settings.GEMINI_API_KEY:
    genai.configure(api_key=settings.GEMINI_API_KEY)


async def generate_sbar(
    patient_age: int,
    patient_sex: str,
    flags: VulnerabilityFlags,
    chief_complaint: str,
    vitals: VitalsInput,
    symptoms: list,
    medications: list,
    risk_assessment: RiskAssessmentResponse,
    escalation_reason: str,
) -> dict:
    """
    Generate SBAR clinical summary using Gemini 1.5 Flash.
    Returns structured dict with four SBAR sections.
    """

    if not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set — returning structured placeholder SBAR")
        return _build_fallback_sbar(
            patient_age, patient_sex, chief_complaint, vitals, risk_assessment
        )

    prompt = _build_prompt(
        patient_age, patient_sex, flags, chief_complaint,
        vitals, symptoms, medications, risk_assessment, escalation_reason
    )

    try:
        model = genai.GenerativeModel(settings.GEMINI_MODEL)

        # Use async generation
        response = await model.generate_content_async(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.2,          # Low temperature for clinical accuracy
                max_output_tokens=800,
                candidate_count=1,
            )
        )

        raw_text = response.text.strip()

        # Parse structured JSON from response
        # Prompt instructs Gemini to return JSON
        if raw_text.startswith("{"):
            sbar = json.loads(raw_text)
        else:
            # Extract JSON block if wrapped in markdown
            import re
            json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if json_match:
                sbar = json.loads(json_match.group())
            else:
                sbar = _parse_text_sbar(raw_text)

        logger.info(f"SBAR generated via Gemini for case (risk={risk_assessment.final_risk_level})")
        return sbar

    except Exception as e:
        logger.error(f"Gemini SBAR generation failed: {e}")
        return _build_fallback_sbar(
            patient_age, patient_sex, chief_complaint, vitals, risk_assessment
        )


def _build_prompt(
    age, sex, flags, chief_complaint, vitals, symptoms,
    medications, risk_assessment, escalation_reason
) -> str:

    sym_list = ", ".join([s.symptom_name for s in symptoms]) if symptoms else "None documented"
    med_list = ", ".join([m.drug_name for m in medications]) if medications else "None"
    vuln_flags = [k for k, v in flags.model_dump().items() if v]

    shap_summary = ""
    if risk_assessment.ml_result and risk_assessment.ml_result.shap_features:
        top3 = risk_assessment.ml_result.shap_features[:3]
        shap_summary = "; ".join([f.label for f in top3])

    return f"""You are a clinical AI assistant generating an SBAR (Situation-Background-Assessment-Recommendation) 
summary for a specialist doctor reviewing an escalated patient case in a rural Indian primary health centre (PHC).

PATIENT DATA:
- Age: {age} years, Sex: {sex}
- Vulnerability flags: {vuln_flags or 'none'}
- Chief complaint: {chief_complaint}
- Reason for escalation: {escalation_reason}

VITALS:
- SpO₂: {vitals.spo2}% | BP: {vitals.systolic_bp}/{vitals.diastolic_bp} mmHg
- HR: {vitals.heart_rate} bpm | RR: {vitals.respiratory_rate}/min | Temp: {vitals.temperature}°C
- Blood glucose: {vitals.blood_glucose_mgdl or 'not recorded'} mg/dL

SYMPTOMS: {sym_list}
CURRENT MEDICATIONS: {med_list}

AI RISK ASSESSMENT:
- Final risk level: {risk_assessment.final_risk_level.upper()}
- Risk score: {risk_assessment.final_risk_score:.1%}
- Rule engine triggered: {risk_assessment.rule_engine.triggered} — {'; '.join(risk_assessment.rule_engine.reasons)}
- ML interpretation: {risk_assessment.ml_result.shap_text if risk_assessment.ml_result else 'N/A'}
- Top risk drivers: {shap_summary}
- Medication warnings: {len(risk_assessment.med_warnings)} detected

INSTRUCTIONS:
Generate a concise, clinically accurate SBAR summary for the specialist. 
Use clear medical language. Be specific. Do not fabricate findings not listed.
Output ONLY a valid JSON object in this exact format:

{{
    "situation": "2-3 sentences: Who is the patient, what is the immediate concern, risk level",
    "background": "3-4 sentences: Relevant history, medications, vulnerability flags, timeline",
    "assessment": "3-4 sentences: AI risk assessment interpretation, key vital signs, SHAP explanation, medication concerns",
    "recommendation": "2-3 sentences: Suggested specialist actions, investigations, urgency level"
}}"""


def _build_fallback_sbar(age, sex, chief_complaint, vitals, risk_assessment) -> dict:
    """Structured fallback when Gemini is unavailable."""
    risk_level = risk_assessment.final_risk_level.upper()
    reasons = "; ".join(risk_assessment.rule_engine.reasons) if risk_assessment.rule_engine.reasons else "AI model assessment"

    return {
        "situation": (
            f"A {age}-year-old {sex} patient presenting with {chief_complaint} has been escalated "
            f"with risk level: {risk_level}. SpO₂ {vitals.spo2}%, BP {vitals.systolic_bp}/{vitals.diastolic_bp} mmHg."
        ),
        "background": (
            f"HR {vitals.heart_rate} bpm, RR {vitals.respiratory_rate}/min, Temp {vitals.temperature}°C. "
            f"Risk assessment score: {risk_assessment.final_risk_score:.1%}. "
            f"Escalation triggered by: {reasons}."
        ),
        "assessment": (
            f"AI hybrid decision engine classified as {risk_level} risk. "
            f"{'Rule-based guardrail override applied. ' if risk_assessment.rule_engine.triggered and risk_assessment.rule_engine.override_ml else ''}"
            f"ML risk probability: {risk_assessment.ml_result.risk_probability:.1%}." 
            if risk_assessment.ml_result else f"Rule engine triggered: {reasons}."
        ),
        "recommendation": (
            f"Specialist review required. Please assess vitals trend, consider investigations, "
            f"and advise on management plan. Case marked {risk_level} priority."
        ),
    }


def _parse_text_sbar(text: str) -> dict:
    """Best-effort parse if Gemini returns plain text instead of JSON."""
    sections = {"situation": "", "background": "", "assessment": "", "recommendation": ""}
    current = None
    for line in text.splitlines():
        line_lower = line.lower().strip()
        if line_lower.startswith("s"):  current = "situation"
        elif line_lower.startswith("b"): current = "background"
        elif line_lower.startswith("a"): current = "assessment"
        elif line_lower.startswith("r"): current = "recommendation"
        elif current:
            sections[current] += line.strip() + " "
    return {k: v.strip() for k, v in sections.items()}
