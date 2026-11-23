from datetime import datetime, timezone
from decimal import Decimal
import uuid
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.models.patient import Patient, PatientLab


@pytest_asyncio.fixture
async def test_db_session():
    """In-memory async SQLite session fixture for isolated schema & model testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


def test_patient_model_instantiation():
    """Verifies Patient model attributes, types, and string representation."""
    patient = Patient(
        patient_id="PT-9901",
        name="John Doe",
        age_years=68,
        biological_sex="female",
        actual_weight_kg=Decimal("64.50"),
        height_cm=Decimal("162.50"),
    )

    assert patient.patient_id == "PT-9901"
    assert patient.name == "John Doe"
    assert patient.age_years == 68
    assert patient.biological_sex == "female"
    assert patient.actual_weight_kg == Decimal("64.50")
    assert patient.height_cm == Decimal("162.50")
    assert "PT-9901" in repr(patient)


def test_patient_lab_model_instantiation():
    """Verifies PatientLab model attributes and defaults."""
    lab_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    lab = PatientLab(
        lab_id=lab_id,
        patient_id="PT-9901",
        serum_creatinine_mg_dl=Decimal("1.45"),
        egfr_ml_min_1_73m2=Decimal("41.2"),
        collected_at=now,
    )

    assert lab.lab_id == lab_id
    assert lab.patient_id == "PT-9901"
    assert lab.serum_creatinine_mg_dl == Decimal("1.45")
    assert lab.egfr_ml_min_1_73m2 == Decimal("41.2")
    assert lab.collected_at == now
    assert "1.45" in repr(lab)


@pytest.mark.asyncio
async def test_patient_and_labs_db_lifecycle(test_db_session: AsyncSession):
    """Tests async insertion, relationship ordering (newest first), and cascade deletion."""
    # 1. Insert patient
    patient = Patient(
        patient_id="PT-RENAL-001",
        age_years=72,
        biological_sex="male",
        actual_weight_kg=Decimal("82.00"),
        height_cm=Decimal("178.00"),
    )
    test_db_session.add(patient)
    await test_db_session.commit()

    # 2. Add two longitudinal labs (older and newer)
    t1_older = datetime(2026, 11, 1, 9, 0, 0, tzinfo=timezone.utc)
    t2_newer = datetime(2026, 11, 15, 14, 30, 0, tzinfo=timezone.utc)

    lab_older = PatientLab(
        patient_id=patient.patient_id,
        serum_creatinine_mg_dl=Decimal("1.10"),
        egfr_ml_min_1_73m2=Decimal("68.0"),
        collected_at=t1_older,
    )
    lab_newer = PatientLab(
        patient_id=patient.patient_id,
        serum_creatinine_mg_dl=Decimal("1.65"),
        egfr_ml_min_1_73m2=Decimal("42.0"),
        collected_at=t2_newer,
    )
    test_db_session.add_all([lab_older, lab_newer])
    await test_db_session.commit()

    # 3. Query patient with labs loaded
    stmt = select(Patient).where(Patient.patient_id == "PT-RENAL-001")
    result = await test_db_session.execute(stmt)
    loaded_patient = result.scalar_one()

    # Must be sorted by collected_at DESC (newest first)
    assert len(loaded_patient.labs) == 2
    assert loaded_patient.labs[0].collected_at == t2_newer
    assert loaded_patient.labs[0].serum_creatinine_mg_dl == Decimal("1.65")
    assert loaded_patient.labs[1].collected_at == t1_older

    # 4. Cascade delete: deleting patient must remove associated labs
    await test_db_session.delete(loaded_patient)
    await test_db_session.commit()

    labs_stmt = select(PatientLab).where(PatientLab.patient_id == "PT-RENAL-001")
    labs_result = await test_db_session.execute(labs_stmt)
    assert labs_result.scalars().all() == []


def test_database_url_configuration():
    """Validates PostgreSQL async and sync connection string helpers."""
    # When DATABASE_URL is explicitly configured
    custom_settings = settings.model_copy(
        update={
            "DATABASE_URL": "postgresql://custom_user:secret@custom_host:5432/custom_db"
        }
    )
    assert custom_settings.get_async_database_url() == (
        "postgresql+asyncpg://custom_user:secret@custom_host:5432/custom_db"
    )
    assert custom_settings.get_sync_database_url() == (
        "postgresql://custom_user:secret@custom_host:5432/custom_db"
    )

    # When fallback components are used
    fallback_settings = settings.model_copy(
        update={
            "DATABASE_URL": None,
            "POSTGRES_USER": "fallback_user",
            "POSTGRES_PASSWORD": "fallback_pass",
            "POSTGRES_SERVER": "localhost",
            "POSTGRES_PORT": 5432,
            "POSTGRES_DB": "fallback_db",
        }
    )
    assert fallback_settings.get_async_database_url() == (
        "postgresql+asyncpg://fallback_user:fallback_pass@localhost:5432/fallback_db"
    )
    assert fallback_settings.get_sync_database_url() == (
        "postgresql+psycopg://fallback_user:fallback_pass@localhost:5432/fallback_db"
    )
