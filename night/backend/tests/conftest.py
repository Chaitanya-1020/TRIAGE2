"""
Shared test fixtures for all test files.
"""
import pytest
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.db.base import Base
from app.models import User, Patient, Case, Vitals, RiskAssessment
from app.core.security import hash_password, create_access_token
import uuid


@pytest.fixture(scope="session")
def event_loop():
    """Override default event loop for session-scoped async fixtures."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def async_db():
    """Create a fresh in-memory database for each test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def seeded_db(async_db):
    """DB with a test PHW user, patient, and case pre-created."""
    phw_id = str(uuid.uuid4())
    user = User(
        id=phw_id,
        email="phw@test.in",
        hashed_password=hash_password("test123"),
        full_name="Test PHW",
        role="phw",
        is_active=True,
    )
    async_db.add(user)

    patient = Patient(
        name_encrypted="encrypted_name",
        age=32,
        sex="female",
        village="Test Village",
        vulnerability_flags={"pregnant": True},
        created_by=phw_id,
    )
    async_db.add(patient)
    await async_db.flush()

    case = Case(
        patient_id=patient.id,
        phw_id=phw_id,
        status="analyzed",
        chief_complaint="Test complaint",
    )
    async_db.add(case)
    await async_db.flush()

    await async_db.commit()
    return {
        "db": async_db,
        "phw_id": phw_id,
        "patient_id": patient.id,
        "case_id": case.id,
        "phw_token": create_access_token(phw_id, "phw"),
    }
