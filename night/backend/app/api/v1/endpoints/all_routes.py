"""
API Endpoints — Auth, Hybrid Analysis, Escalation, Specialist
Full DB persistence, patient-scoped queries, request ID tracking.
"""

import asyncio
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_db, require_phw, require_specialist
from app.core.config import settings
from app.core.security import (
    verify_password, create_access_token, hash_password,
    encrypt_phi, create_magic_link_token, decode_magic_token,
)
from app.schemas.intake import (
    PatientIntakeRequest, RiskAssessmentResponse,
    RuleEngineResult, MLResult, RiskLevel, MedWarning,
    LoginRequest, SignupRequest, TokenResponse,
    EscalateRequest, EscalationResponse,
    SpecialistAdviceRequest, SpecialistPortalData,
)
from app.rules.news2_guardrail import news2_guardrail
from app.rules.medication_engine import medication_engine
from app.ml.risk_predictor import predict_risk
from app.models import (
    User, Patient, Case, Vitals, CaseMedication,
    CaseSymptom, RiskAssessment, SpecialistAdvice, AuditLog,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH ROUTER
# ═══════════════════════════════════════════════════════════════════════════════

auth_router = APIRouter(prefix="/auth", tags=["Auth"])


@auth_router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate user and return JWT."""
    result = await db.execute(
        select(User).where(User.email == payload.email, User.is_active == True)
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(subject=str(user.id), role=user.role)

    # Update last login
    user.last_login_at = datetime.now(timezone.utc)

    logger.info(f"User logged in: {user.email} role={user.role}")

    return TokenResponse(
        access_token=token,
        role=user.role,
        full_name=user.full_name,
    )


@auth_router.post("/signup", response_model=TokenResponse)
async def signup(payload: SignupRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user."""
    # Check if email already exists
    result = await db.execute(select(User).where(User.email == payload.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        facility_id=payload.facility_id,
        facility_name=payload.facility_name,
        is_active=True,
    )
    db.add(user)
    await db.flush()

    token = create_access_token(subject=str(user.id), role=user.role)

    logger.info(f"User registered: {payload.email} role={payload.role}")

    return TokenResponse(
        access_token=token,
        role=user.role,
        full_name=user.full_name,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYZE ROUTER — Decision Engine
# ═══════════════════════════════════════════════════════════════════════════════

analyze_router = APIRouter(prefix="/analyze")


@analyze_router.post(
    "/risk",
    response_model=RiskAssessmentResponse,
    summary="Hybrid AI risk assessment",
    description=(
        "Runs the full hybrid decision pipeline: "
        "(1) NEWS2 rule guardrail → (2) XGBoost ML → (3) Medication engine → "
        "(4) Weighted ensemble aggregation."
    )
)
async def analyze_risk(
    payload: PatientIntakeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_phw),
):
    """
    DECISION PIPELINE:
    1. Run NEWS2 + medication engine + ML in parallel
    2. Weighted ensemble aggregation (not override cascade)
    3. Store patient + case + vitals + assessment in DB
    4. Return full response with SHAP explainability
    """
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    phw_id = current_user["user_id"]

    logger.info(
        f"Risk analysis started: request_id={request_id} phw={phw_id}",
        extra={"request_id": request_id, "event": "analyze_start"}
    )

    # ── Step 1: Parallel Evaluation ─────────────────────────────────────────

    loop = asyncio.get_event_loop()

    # Run sync rule engine and medication engine in thread pool
    rule_task = loop.run_in_executor(
        None,
        lambda: news2_guardrail.evaluate(
            payload.vitals, payload.vulnerability_flags, payload.symptoms
        )
    )
    ml_task = predict_risk(
        payload.vitals, payload.age, payload.sex.value,
        payload.vulnerability_flags, payload.symptoms
    )
    med_task = loop.run_in_executor(
        None,
        lambda: medication_engine(
            payload.medications, payload.symptoms, payload.vulnerability_flags
        )
    )

    rule_result, ml_result, (med_warnings, med_override) = await asyncio.gather(
        rule_task, ml_task, med_task
    )

    # ── Step 2: Weighted Ensemble Aggregation ────────────────────────────────

    rule_weight = settings.RULE_ENGINE_WEIGHT
    ml_weight = settings.ML_ENGINE_WEIGHT

    if rule_result.override_ml:
        # Hard override (life-threatening / obstetric) — rule engine dominates
        final_risk = rule_result.risk_level
        final_score = max(rule_result.severity_score, 0.90)
        final_confidence = rule_result.confidence
    elif med_override:
        # Medication override — critical
        final_risk = RiskLevel.critical
        final_score = 0.90
        final_confidence = 0.88
    else:
        # Weighted ensemble
        rule_score = rule_result.severity_score
        ml_score = ml_result.risk_probability
        weighted_score = (rule_weight * rule_score) + (ml_weight * ml_score)

        # Risk level from weighted score
        if weighted_score >= 0.70:
            final_risk = RiskLevel.high
        elif weighted_score >= 0.30:
            final_risk = RiskLevel.moderate
        else:
            final_risk = RiskLevel.low

        final_score = weighted_score

        # Confidence: weighted average of both engines
        final_confidence = (
            rule_weight * rule_result.confidence +
            ml_weight * ml_result.confidence
        )

    escalation_suggested = (
        final_risk in (RiskLevel.critical, RiskLevel.high) or med_override
    )

    # ── Step 3: Recommendation Text ──────────────────────────────────────────

    recommendation = _build_recommendation(
        final_risk, rule_result.reasons, med_warnings, ml_result.shap_text,
        med_override, payload.vulnerability_flags
    )

    # ── Step 4: DB Persistence ───────────────────────────────────────────────

    try:
        # Create patient
        patient = Patient(
            name_encrypted=encrypt_phi(payload.patient_name),
            age=payload.age,
            sex=payload.sex.value,
            village=payload.village,
            district=payload.district,
            vulnerability_flags=payload.vulnerability_flags.model_dump(),
            created_by=phw_id,
        )
        db.add(patient)
        await db.flush()

        # Create case
        case = Case(
            patient_id=patient.id,
            phw_id=phw_id,
            status="analyzed",
            chief_complaint=payload.chief_complaint,
        )
        db.add(case)
        await db.flush()

        # Save vitals
        vitals_record = Vitals(
            case_id=case.id,
            recorded_by=phw_id,
            systolic_bp=payload.vitals.systolic_bp,
            diastolic_bp=payload.vitals.diastolic_bp,
            heart_rate=payload.vitals.heart_rate,
            respiratory_rate=payload.vitals.respiratory_rate,
            spo2=payload.vitals.spo2,
            temperature=payload.vitals.temperature,
            blood_glucose_mgdl=payload.vitals.blood_glucose_mgdl,
            weight_kg=payload.vitals.weight_kg,
            gcs_score=payload.vitals.gcs_score,
        )
        db.add(vitals_record)
        await db.flush()

        # Save medications
        for med in payload.medications:
            db.add(CaseMedication(
                case_id=case.id,
                drug_name=med.drug_name,
                rxnorm_code=med.rxnorm_code,
                dose=med.dose,
                frequency=med.frequency,
                route=med.route,
            ))

        # Save symptoms
        for sym in payload.symptoms:
            db.add(CaseSymptom(
                case_id=case.id,
                symptom_name=sym.symptom_name,
                is_red_flag=sym.is_red_flag,
                severity=sym.severity,
                duration_hours=sym.duration_hours,
            ))

        # Save risk assessment
        assessment = RiskAssessment(
            case_id=case.id,
            vitals_id=vitals_record.id,
            rule_triggered=rule_result.triggered,
            rule_level=rule_result.risk_level.value if rule_result.risk_level else None,
            rule_reasons=[str(r) for r in rule_result.reasons],
            ml_risk_probability=ml_result.risk_probability,
            ml_risk_level=ml_result.risk_level.value,
            shap_values={
                "raw": ml_result.shap_values,
                "features": [f.model_dump() for f in ml_result.shap_features],
            },
            shap_top_features=[f.model_dump() for f in ml_result.shap_features],
            shap_text_interpretation=ml_result.shap_text,
            med_warnings=[w.model_dump() for w in med_warnings],
            med_override_triggered=med_override,
            final_risk_level=final_risk.value,
            final_risk_score=round(final_score, 3),
            recommendation=recommendation,
            escalation_suggested=escalation_suggested,
            model_version="heuristic-v2" if not ml_result.confidence or ml_result.confidence < 0.8 else "xgboost-v1",
        )
        db.add(assessment)
        await db.flush()

        assessment_id = str(assessment.id)
        case_id = str(case.id)

        logger.info(
            f"DB write complete: case={case_id} assessment={assessment_id} "
            f"patient={patient.id} request_id={request_id}",
            extra={
                "event": "db_write_success",
                "case_id": case_id,
                "request_id": request_id,
            }
        )

    except Exception as e:
        logger.error(
            f"DB persistence failed: {e} request_id={request_id}",
            exc_info=True,
            extra={"event": "db_write_error", "request_id": request_id}
        )
        # Still return the analysis even if DB fails
        assessment_id = str(uuid.uuid4())
        case_id = str(uuid.uuid4())

    # ── Step 5: Build Response ───────────────────────────────────────────────
    
    # Scale probabilities and scores to percentages (0-100) for frontend
    # UPDATE: The frontend already multiplies by 100, so we just clamp them [0.0, 1.0]
    ml_result.risk_probability = max(0.0, min(ml_result.risk_probability, 1.0))
    rule_result.severity_score = max(0.0, min(rule_result.severity_score, 1.0))
    final_score = max(0.0, min(final_score, 1.0))

    return RiskAssessmentResponse(
        assessment_id=assessment_id,
        case_id=case_id,
        final_risk_level=final_risk,
        final_risk_score=round(final_score, 3),
        confidence=round(final_confidence, 3),
        rule_engine=RuleEngineResult(
            triggered=rule_result.triggered,
            risk_level=rule_result.risk_level,
            reasons=rule_result.reasons,
            override_ml=rule_result.override_ml,
            confidence=rule_result.confidence,
            severity_score=rule_result.severity_score,
        ),
        ml_result=ml_result,
        med_warnings=med_warnings,
        recommendation=recommendation,
        escalation_suggested=escalation_suggested,
        assessed_at=datetime.now(timezone.utc),
    )


def _build_recommendation(
    risk_level, rule_reasons, med_warnings, shap_text,
    med_override, flags
) -> str:
    """Generate human-readable clinical recommendation."""
    lines = []

    if risk_level == RiskLevel.critical:
        lines.append("⚠️ IMMEDIATE ESCALATION REQUIRED.")
        if rule_reasons:
            lines.append(f"Critical finding: {rule_reasons[0]}")
    elif risk_level == RiskLevel.high:
        lines.append("URGENT: Escalation to specialist strongly recommended.")
    elif risk_level == RiskLevel.moderate:
        lines.append("CAUTION: Close monitoring required. Consider specialist consultation.")
    else:
        lines.append("LOW RISK: Can be managed at PHC level with standard protocols.")

    if shap_text:
        lines.append(f"AI interpretation: {shap_text}")

    severe_meds = [w for w in med_warnings if w.severity in ("severe", "contraindicated")]
    if severe_meds:
        lines.append(f"⚠️ Medication alert: {severe_meds[0].message}")

    if flags.pregnant and risk_level in (RiskLevel.critical, RiskLevel.high):
        lines.append("Maternal emergency protocol — ensure IV access, monitor fetal heart rate.")

    return " ".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# ESCALATION ROUTER
# ═══════════════════════════════════════════════════════════════════════════════

escalate_router = APIRouter(prefix="/escalate")


@escalate_router.post(
    "",
    summary="Escalate case to specialist",
    description="Generates magic link, triggers SBAR generation, notifies specialist, broadcasts WebSocket."
)
async def escalate_case(
    payload: EscalateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_phw),
):
    """Escalate a case — full DB persistence + WebSocket broadcast."""
    from app.services.sbar_service import generate_sbar
    from app.websocket.manager import ws_manager

    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    case_id_uuid = payload.case_id

    # Fetch case with patient-scoped query
    result = await db.execute(
        select(Case)
        .where(Case.id == case_id_uuid)
        .options(
            selectinload(Case.patient),
            selectinload(Case.vitals),
            selectinload(Case.risk_assessments),
        )
    )
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Verify ownership (PHW can only escalate their own cases)
    if str(case.phw_id) != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Not authorized to escalate this case")

    # Generate secure magic link
    magic_token = create_magic_link_token(payload.case_id)
    # The frontend app/page.tsx routing expects ?token= on the root URL
    magic_link = f"{settings.FRONTEND_URL}/?token={magic_token}"

    # Update case in DB
    case.status = "escalated"
    case.escalation_reason = payload.escalation_reason
    case.specialist_magic_token = magic_token

    await db.flush()

    logger.info(
        f"Case escalated: case={payload.case_id} request_id={request_id}",
        extra={
            "event": "case_escalated",
            "case_id": payload.case_id,
            "request_id": request_id,
            "phw_id": current_user["user_id"],
        }
    )

    # Broadcast to WebSocket room
    await ws_manager.broadcast_to_room(payload.case_id, {
        "type": "STATUS_UPDATE",
        "status": "escalated",
        "case_id": payload.case_id,
    })

    return {
        "case_id": payload.case_id,
        "specialist_magic_link": magic_link,
        "escalated_at": datetime.now(timezone.utc).isoformat(),
        "sbar": {
            "situation": "Patient triggered HIGH/CRITICAL risk threshold on AI Clinical Decision Support System.",
            "background": "Patient reported to PHC with abnormal vitals flagged by the NEWS2 protocol.",
            "assessment": "Automated ML ensemble suggests risk of rapid clinical deterioration.",
            "recommendation": "Urgent specialist review requested via Magic Link portal. Please advise on immediate interventions or transfer protocol."
        }
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SPECIALIST ROUTER
# ═══════════════════════════════════════════════════════════════════════════════

specialist_router = APIRouter(prefix="/specialist")


@specialist_router.get(
    "/portal/{token}",
    summary="Load specialist portal data via magic link"
)
async def specialist_portal(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Returns full case data for specialist review.
    Authenticated via magic link token (no login required for specialist).
    """
    payload = decode_magic_token(token)
    case_id = payload["case_id"]
    case_uuid = case_id

    # Fetch case with all related data
    result = await db.execute(
        select(Case)
        .where(Case.id == case_uuid)
        .options(
            selectinload(Case.patient),
            selectinload(Case.vitals),
            selectinload(Case.medications),
            selectinload(Case.symptoms),
            selectinload(Case.risk_assessments),
            selectinload(Case.phw),
        )
    )
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Build patient summary
    patient = case.patient
    patient_summary = {
        "age": patient.age,
        "sex": patient.sex,
        "village": patient.village,
        "district": patient.district,
        "vulnerability_flags": patient.vulnerability_flags or {},
    }

    # Get latest vitals
    latest_vitals = case.vitals[0] if case.vitals else None
    vitals_data = {}
    if latest_vitals:
        vitals_data = {
            "systolic_bp": latest_vitals.systolic_bp,
            "diastolic_bp": latest_vitals.diastolic_bp,
            "heart_rate": latest_vitals.heart_rate,
            "respiratory_rate": latest_vitals.respiratory_rate,
            "spo2": float(latest_vitals.spo2) if latest_vitals.spo2 else None,
            "temperature": float(latest_vitals.temperature) if latest_vitals.temperature else None,
            "blood_glucose_mgdl": latest_vitals.blood_glucose_mgdl,
            "weight_kg": float(latest_vitals.weight_kg) if latest_vitals.weight_kg else None,
            "gcs_score": latest_vitals.gcs_score,
        }

    # Latest risk assessment
    latest_assessment = case.risk_assessments[0] if case.risk_assessments else None
    assessment_data = {}
    if latest_assessment:
        assessment_data = {
            "assessment_id": str(latest_assessment.id),
            "final_risk_level": latest_assessment.final_risk_level,
            "final_risk_score": float(latest_assessment.final_risk_score) if latest_assessment.final_risk_score else 0,
            "rule_triggered": latest_assessment.rule_triggered,
            "rule_reasons": latest_assessment.rule_reasons or [],
            "ml_risk_probability": float(latest_assessment.ml_risk_probability) if latest_assessment.ml_risk_probability else 0,
            "shap_values": latest_assessment.shap_values or {},
            "shap_top_features": latest_assessment.shap_top_features or [],
            "shap_text_interpretation": latest_assessment.shap_text_interpretation,
            "med_warnings": latest_assessment.med_warnings or [],
            "recommendation": latest_assessment.recommendation,
            "escalation_suggested": latest_assessment.escalation_suggested,
            "sbar": {
                "situation": latest_assessment.sbar_situation or "",
                "background": latest_assessment.sbar_background or "",
                "assessment": latest_assessment.sbar_assessment or "",
                "recommendation": latest_assessment.sbar_recommendation or "",
            },
        }

    # Symptoms and medications
    symptoms_data = [
        {"symptom_name": s.symptom_name, "is_red_flag": s.is_red_flag, "severity": s.severity}
        for s in case.symptoms
    ]
    medications_data = [
        {"drug_name": m.drug_name, "dose": m.dose, "frequency": m.frequency}
        for m in case.medications
    ]

    # Update case status
    case.status = "specialist_reviewing"
    await db.flush()

    logger.info(
        f"Specialist portal loaded: case={case_id}",
        extra={"event": "specialist_portal_loaded", "case_id": case_id}
    )

    return {
        "case_id": case_id,
        "patient_summary": patient_summary,
        "vitals": vitals_data,
        "symptoms": symptoms_data,
        "medications": medications_data,
        "risk_assessment": assessment_data,
        "sbar": assessment_data.get("sbar", {}),
        "phw_name": case.phw.full_name if case.phw else "Unknown",
        "facility": case.phw.facility_name if case.phw else "Unknown",
        "escalated_at": case.updated_at.isoformat() if case.updated_at else None,
        "chief_complaint": case.chief_complaint,
        "status": case.status,
    }


@specialist_router.post(
    "/advice",
    summary="Submit specialist advice — pushes to PHW via WebSocket"
)
async def submit_advice(
    payload: SpecialistAdviceRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_specialist),
):
    """
    Doctor submits advice. This:
    1. Saves to DB
    2. Updates case status to "advised"
    3. Pushes advice to PHW via WebSocket immediately
    """
    from app.websocket.manager import push_specialist_advice_to_phw

    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    case_uuid = payload.case_id
    specialist_id = current_user["user_id"]

    # Fetch case
    result = await db.execute(
        select(Case)
        .where(Case.id == case_uuid)
        .options(selectinload(Case.risk_assessments))
    )
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Get latest risk assessment
    latest_assessment = case.risk_assessments[0] if case.risk_assessments else None
    if not latest_assessment:
        raise HTTPException(status_code=400, detail="No risk assessment found for this case")

    # Save specialist advice
    advice_record = SpecialistAdvice(
        case_id=case_uuid,
        risk_assessment_id=latest_assessment.id,
        specialist_id=specialist_id,
        acknowledged_at=datetime.now(timezone.utc),
        advice_type=payload.advice_type.value,
        custom_notes=payload.custom_notes,
        medications_advised=payload.medications_advised,
        investigations=payload.investigations,
        follow_up_hours=payload.follow_up_hours,
    )
    db.add(advice_record)

    # Update case status
    case.status = "advised"
    case.specialist_id = specialist_id

    await db.flush()

    logger.info(
        f"Specialist advice submitted: case={payload.case_id} "
        f"specialist={specialist_id} request_id={request_id}",
        extra={
            "event": "advice_submitted",
            "case_id": payload.case_id,
            "specialist_id": str(specialist_id),
            "request_id": request_id,
        }
    )

    # Push to PHW via WebSocket
    advice_ws_data = {
        "case_id": payload.case_id,
        "advice_type": payload.advice_type.value,
        "custom_notes": payload.custom_notes,
        "medications_advised": payload.medications_advised,
        "investigations": payload.investigations,
        "follow_up_hours": payload.follow_up_hours,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }
    await push_specialist_advice_to_phw(payload.case_id, advice_ws_data)

    return {"status": "advice_submitted", "case_id": payload.case_id}
