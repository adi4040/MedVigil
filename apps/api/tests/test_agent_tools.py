from datetime import datetime, timezone
from decimal import Decimal
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.medication import Medication, RenalDosingGuideline
from app.models.patient import Patient, PatientLab
from app.services.agent.tools import (
    calculate_crcl,
    fetch_patient_crcl,
    get_renal_metric,
)


@pytest_asyncio.fixture
async def test_session():
    """Isolated in-memory SQLite fixture pre-seeded with sample patient and medication records."""
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
        # Seed Patient 1 (Male)
        p1 = Patient(
            patient_id="uuid-p001",
            generic_patient_id="PAT-001",
            name="Gavin481 Thiel172",
            age_years=21,
            biological_sex="Male",
            actual_weight_kg=Decimal("81.70"),
            height_cm=Decimal("175.00"),
        )
        session.add(p1)

        # Seed Labs for Patient 1
        lab1 = PatientLab(
            patient_id="uuid-p001",
            serum_creatinine_mg_dl=Decimal("0.90"),
            egfr_ml_min_1_73m2=Decimal("110.0"),
            collected_at=datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc),
        )
        session.add(lab1)

        # Seed Patient 2 (Female)
        p2 = Patient(
            patient_id="uuid-p004",
            generic_patient_id="PAT-004",
            name="Charlotte28 Muller251",
            age_years=35,
            biological_sex="Female",
            actual_weight_kg=Decimal("60.00"),
            height_cm=Decimal("165.00"),
        )
        session.add(p2)

        lab2 = PatientLab(
            patient_id="uuid-p004",
            serum_creatinine_mg_dl=Decimal("0.80"),
            egfr_ml_min_1_73m2=Decimal("95.0"),
            collected_at=datetime(2026, 11, 21, 14, 0, tzinfo=timezone.utc),
        )
        session.add(lab2)

        # Seed Medication with Renal Guidelines
        med = Medication(
            id=1,
            name="Gabapentin",
            generic_name="gabapentin",
            brand_name="Neurontin",
            drug_class="Anticonvulsant",
        )
        session.add(med)

        g1 = RenalDosingGuideline(
            id=1,
            medication_id=1,
            renal_metric="creatinine_clearance",
            min_value=Decimal("60.00"),
            max_value=Decimal("100.00"),
            min_daily_dose=Decimal("900.00"),
            max_daily_dose=Decimal("3600.00"),
        )
        g2 = RenalDosingGuideline(
            id=2,
            medication_id=1,
            renal_metric="creatinine_clearance",
            min_value=Decimal("30.00"),
            max_value=Decimal("59.00"),
            min_daily_dose=Decimal("400.00"),
            max_daily_dose=Decimal("1400.00"),
        )
        session.add_all([g1, g2])

        await session.commit()
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.mark.asyncio
async def test_get_renal_metric_gabapentin_success(test_session: AsyncSession):
    result = await get_renal_metric("Gabapentin", session=test_session)
    assert result["status"] == "success"
    assert result["medication_name"] == "Gabapentin"
    assert result["generic_name"] == "gabapentin"
    assert result["required_renal_metric"] == "crcl"
    assert result["raw_metric"] == "creatinine_clearance"
    assert result["guideline_count"] == 2
    assert len(result["guidelines"]) == 2

    # Verify first guideline bracket
    first_bracket = result["guidelines"][0]
    assert first_bracket["min_renal_value"] == 60.0
    assert first_bracket["max_renal_value"] == 100.0
    assert first_bracket["min_daily_dose_mg"] == 900.0
    assert first_bracket["max_daily_dose_mg"] == 3600.0


@pytest.mark.asyncio
async def test_get_renal_metric_case_insensitive(test_session: AsyncSession):
    result = await get_renal_metric("gabapentin", session=test_session)
    assert result["status"] == "success"
    assert result["medication_name"] == "Gabapentin"
    assert result["required_renal_metric"] == "crcl"


@pytest.mark.asyncio
async def test_get_renal_metric_not_found(test_session: AsyncSession):
    result = await get_renal_metric("NonExistentAntibiotic999", session=test_session)
    assert result["status"] == "error"
    assert "was not found" in result["message"]


@pytest.mark.asyncio
async def test_get_renal_metric_empty(test_session: AsyncSession):
    result = await get_renal_metric("   ", session=test_session)
    assert result["status"] == "error"
    assert "must not be empty" in result["message"]


@pytest.mark.asyncio
async def test_fetch_patient_crcl_generic_id_success(test_session: AsyncSession):
    result = await fetch_patient_crcl("PAT-001", session=test_session)
    assert result["status"] == "missing"
    assert result["crcl_found"] is False
    assert result["generic_patient_id"] == "PAT-001"
    assert result["patient_name"] == "Gavin481 Thiel172"
    assert result["total_lab_panels"] == 1
    assert result["latest_serum_creatinine_mg_dl"] == 0.90
    assert result["latest_egfr_ml_min_1_73m2"] == 110.0
    assert "calculate_crcl" in result["message"]


@pytest.mark.asyncio
async def test_fetch_patient_crcl_case_insensitive(test_session: AsyncSession):
    result = await fetch_patient_crcl("pat-001", session=test_session)
    assert result["status"] == "missing"
    assert result["generic_patient_id"] == "PAT-001"


@pytest.mark.asyncio
async def test_fetch_patient_crcl_by_internal_uuid(test_session: AsyncSession):
    result = await fetch_patient_crcl("uuid-p001", session=test_session)
    assert result["status"] == "missing"
    assert result["generic_patient_id"] == "PAT-001"
    assert result["patient_id"] == "uuid-p001"


@pytest.mark.asyncio
async def test_fetch_patient_crcl_not_found(test_session: AsyncSession):
    result = await fetch_patient_crcl("PAT-99999", session=test_session)
    assert result["status"] == "error"
    assert "was not found" in result["message"]


@pytest.mark.asyncio
async def test_fetch_patient_crcl_empty(test_session: AsyncSession):
    result = await fetch_patient_crcl("", session=test_session)
    assert result["status"] == "error"
    assert "must not be empty" in result["message"]


@pytest.mark.asyncio
async def test_calculate_crcl_with_db_latest_lab(test_session: AsyncSession):
    # Gavin: 21 yo, Male, 81.70 kg, SCr in DB = 0.90 mg/dL
    # Cockcroft-Gault: ((140 - 21) * 81.70) / (72 * 0.90) = (119 * 81.70) / 64.8 = 9722.3 / 64.8 = 150.035... => 150.04
    result = await calculate_crcl("PAT-001", session=test_session)
    assert result["status"] == "success"
    assert result["generic_patient_id"] == "PAT-001"
    assert result["calculated_crcl_ml_min"] == 150.04
    assert result["formula"] == "Cockcroft-Gault"
    assert result["parameters_used"]["age_years"] == 21
    assert result["parameters_used"]["actual_weight_kg"] == 81.70
    assert result["parameters_used"]["biological_sex"] == "Male"
    assert result["parameters_used"]["serum_creatinine_mg_dl"] == 0.90
    assert result["parameters_used"]["female_adjustment_factor"] == 1.0


@pytest.mark.asyncio
async def test_calculate_crcl_with_explicit_scr(test_session: AsyncSession):
    # Gavin: 21 yo, Male, 81.70 kg, explicit SCr = 1.0 mg/dL
    # ((140 - 21) * 81.70) / (72 * 1.0) = 9722.3 / 72 = 135.0319... => 135.03
    result = await calculate_crcl("PAT-001", serum_creatinine_mg_dl=1.0, session=test_session)
    assert result["status"] == "success"
    assert result["calculated_crcl_ml_min"] == 135.03
    assert result["parameters_used"]["serum_creatinine_mg_dl"] == 1.0


@pytest.mark.asyncio
async def test_calculate_crcl_female_patient_applies_point_eight_five(test_session: AsyncSession):
    # Charlotte: 35 yo, Female, 60.00 kg, SCr in DB = 0.80 mg/dL
    # ((140 - 35) * 60.00) / (72 * 0.80) * 0.85 = (105 * 60) / 57.6 * 0.85 = 6300 / 57.6 * 0.85 = 109.375 * 0.85 = 92.96875 => 92.97
    result = await calculate_crcl("PAT-004", session=test_session)
    assert result["status"] == "success"
    assert result["parameters_used"]["female_adjustment_factor"] == 0.85
    assert result["calculated_crcl_ml_min"] == 92.97


@pytest.mark.asyncio
async def test_calculate_crcl_invalid_scr_error(test_session: AsyncSession):
    result = await calculate_crcl("PAT-001", serum_creatinine_mg_dl=-0.5, session=test_session)
    assert result["status"] == "error"
    assert "Invalid serum creatinine" in result["message"]

    zero_res = await calculate_crcl("PAT-001", serum_creatinine_mg_dl=0.0, session=test_session)
    assert zero_res["status"] == "error"


@pytest.mark.asyncio
async def test_calculate_crcl_patient_not_found(test_session: AsyncSession):
    result = await calculate_crcl("UNKNOWN_PATIENT_XYZ", session=test_session)
    assert result["status"] == "error"
    assert "was not found" in result["message"]
