"""
Integration test — Full PHW Submit → Analyze → DB Verify flow.
Tests the complete pipeline without a running server.
"""

import pytest
import uuid
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select

from app.db.base import Base
from app.models import User, Patient, Case, Vitals, RiskAssessment, CaseMedication, CaseSymptom
from app.core.security import hash_password, encrypt_phi
from app.rules.news2_guardrail import news2_guardrail
from app.rules.medication_engine import run_medication_engine
from app.ml.risk_predictor import predict_risk
from app.schemas.intake import (
    VitalsInput, VulnerabilityFlags, SymptomInput, MedicationInput, RiskLevel,
)


@pytest.fixture
async def db_session():
    """Fresh in-memory database for integration testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session

    await engine.dispose()


class TestFullPatientWorkflow:
    """Test the complete PHW → Analyze → DB flow."""

    @pytest.mark.asyncio
    async def test_full_pipeline(self, db_session):
        """
        Simulates:
        1. PHW user creation
        2. Patient intake
        3. Rule engine evaluation
        4. ML prediction
        5. Medication check
        6. DB persistence
        7. Data retrieval verification
        """
        db = db_session

        # ── 1. Create PHW user ───────────────────────────────────────────
        phw_id = str(uuid.uuid4())
        user = User(
            id=phw_id,
            email="phw_integration@test.in",
            hashed_password=hash_password("test123"),
            full_name="Dr. Integration Test",
            role="phw",
            facility_name="PHC Test Facility",
            is_active=True,
        )
        db.add(user)
        await db.flush()

        # ── 2. Define patient intake data ────────────────────────────────
        vitals = VitalsInput(
            systolic_bp=155, diastolic_bp=95,
            heart_rate=98, respiratory_rate=20,
            spo2=97.0, temperature=37.2,
        )
        flags = VulnerabilityFlags(pregnant=True)
        symptoms = [
            SymptomInput(symptom_name="severe headache", is_red_flag=True),
            SymptomInput(symptom_name="blurred vision", is_red_flag=True),
        ]
        medications = [
            MedicationInput(drug_name="Iron supplement"),
            MedicationInput(drug_name="Folic acid"),
        ]

        # ── 3. Run rule engine ───────────────────────────────────────────
        rule_result = news2_guardrail.evaluate(vitals, flags, symptoms)

        # Pregnant + BP 155/95 should trigger obstetric preeclampsia
        assert rule_result.triggered
        assert rule_result.risk_level == RiskLevel.critical
        assert rule_result.override_ml
        assert "OBSTETRIC_PREECLAMPSIA" in rule_result.triggered_rules

        # ── 4. Run ML prediction ─────────────────────────────────────────
        ml_result = await predict_risk(vitals, 32, "female", flags, symptoms)

        assert ml_result.risk_probability >= 0.0
        assert ml_result.risk_probability <= 1.0
        assert len(ml_result.shap_features) == 5
        assert len(ml_result.shap_values) > 0
        assert len(ml_result.feature_importance) > 0

        # ── 5. Run medication engine ─────────────────────────────────────
        med_warnings, med_override = run_medication_engine(
            medications, symptoms, flags
        )
        # Iron + Folic acid have no known DDIs
        assert med_override is False

        # ── 6. Persist to DB ─────────────────────────────────────────────
        patient = Patient(
            name_encrypted=encrypt_phi("Meena Devi"),
            age=32,
            sex="female",
            village="Test Village",
            district="Wardha",
            vulnerability_flags=flags.model_dump(),
            created_by=phw_id,
        )
        db.add(patient)
        await db.flush()

        case = Case(
            patient_id=patient.id,
            phw_id=phw_id,
            status="analyzed",
            chief_complaint="Severe headache at 34 weeks pregnancy",
        )
        db.add(case)
        await db.flush()

        vitals_record = Vitals(
            case_id=case.id,
            recorded_by=phw_id,
            systolic_bp=155, diastolic_bp=95,
            heart_rate=98, respiratory_rate=20,
            spo2=97.0, temperature=37.2,
        )
        db.add(vitals_record)
        await db.flush()

        for med in medications:
            db.add(CaseMedication(
                case_id=case.id, drug_name=med.drug_name,
            ))

        for sym in symptoms:
            db.add(CaseSymptom(
                case_id=case.id, symptom_name=sym.symptom_name,
                is_red_flag=sym.is_red_flag,
            ))

        assessment = RiskAssessment(
            case_id=case.id,
            vitals_id=vitals_record.id,
            rule_triggered=True,
            rule_level="critical",
            rule_reasons=rule_result.reasons,
            ml_risk_probability=ml_result.risk_probability,
            ml_risk_level=ml_result.risk_level.value,
            shap_values={"raw": ml_result.shap_values},
            shap_top_features=[f.model_dump() for f in ml_result.shap_features],
            shap_text_interpretation=ml_result.shap_text,
            med_warnings=[],
            final_risk_level="critical",
            final_risk_score=0.95,
            recommendation="IMMEDIATE ESCALATION",
            escalation_suggested=True,
        )
        db.add(assessment)
        await db.flush()
        await db.commit()

        # ── 7. Verify retrieval ──────────────────────────────────────────

        # Verify patient stored
        result = await db.execute(select(Patient).where(Patient.id == patient.id))
        stored_patient = result.scalar_one()
        assert stored_patient.age == 32
        assert stored_patient.sex == "female"

        # Verify case stored with correct FK
        result = await db.execute(select(Case).where(Case.id == case.id))
        stored_case = result.scalar_one()
        assert stored_case.patient_id == patient.id
        assert stored_case.phw_id == phw_id
        assert stored_case.status == "analyzed"

        # Verify vitals stored
        result = await db.execute(select(Vitals).where(Vitals.case_id == case.id))
        stored_vitals = result.scalar_one()
        assert stored_vitals.systolic_bp == 155
        assert float(stored_vitals.spo2) == 97.0

        # Verify medications stored
        result = await db.execute(
            select(CaseMedication).where(CaseMedication.case_id == case.id)
        )
        stored_meds = result.scalars().all()
        assert len(stored_meds) == 2

        # Verify symptoms stored
        result = await db.execute(
            select(CaseSymptom).where(CaseSymptom.case_id == case.id)
        )
        stored_symptoms = result.scalars().all()
        assert len(stored_symptoms) == 2
        assert any(s.is_red_flag for s in stored_symptoms)

        # Verify risk assessment stored
        result = await db.execute(
            select(RiskAssessment).where(RiskAssessment.case_id == case.id)
        )
        stored_assessment = result.scalar_one()
        assert stored_assessment.final_risk_level == "critical"
        assert stored_assessment.escalation_suggested is True
        assert stored_assessment.shap_text_interpretation is not None

    @pytest.mark.asyncio
    async def test_data_integrity_patient_scoping(self, db_session):
        """Verify data for one patient doesn't leak to another."""
        db = db_session

        phw_id = str(uuid.uuid4())
        user = User(
            id=phw_id,
            email="phw_scope@test.in",
            hashed_password=hash_password("test"),
            full_name="Scope Test PHW",
            role="phw",
            is_active=True,
        )
        db.add(user)
        await db.flush()

        # Create two patients
        patient1 = Patient(
            name_encrypted="patient1", age=25, sex="male",
            created_by=phw_id,
        )
        patient2 = Patient(
            name_encrypted="patient2", age=60, sex="female",
            created_by=phw_id,
        )
        db.add(patient1)
        db.add(patient2)
        await db.flush()

        case1 = Case(patient_id=patient1.id, phw_id=phw_id, status="analyzed", chief_complaint="Case 1")
        case2 = Case(patient_id=patient2.id, phw_id=phw_id, status="analyzed", chief_complaint="Case 2")
        db.add(case1)
        db.add(case2)
        await db.flush()

        # Add symptoms to case 1 only
        db.add(CaseSymptom(case_id=case1.id, symptom_name="chest pain", is_red_flag=True))
        await db.flush()
        await db.commit()

        # Verify case 2 has no symptoms
        result = await db.execute(
            select(CaseSymptom).where(CaseSymptom.case_id == case2.id)
        )
        case2_symptoms = result.scalars().all()
        assert len(case2_symptoms) == 0

        # Verify case 1 has exactly 1 symptom
        result = await db.execute(
            select(CaseSymptom).where(CaseSymptom.case_id == case1.id)
        )
        case1_symptoms = result.scalars().all()
        assert len(case1_symptoms) == 1
        assert case1_symptoms[0].symptom_name == "chest pain"
