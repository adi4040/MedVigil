from decimal import Decimal
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.medication import Medication, RenalDosingGuideline


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


def test_medication_model_instantiation():
    """Verifies Medication model attributes and string representation."""
    med = Medication(
        id=1,
        name="Gabapentin",
        generic_name="gabapentin",
        brand_name="Neurontin",
        drug_class="Anticonvulsant / Neuropathic Pain Agent",
    )

    assert med.id == 1
    assert med.name == "Gabapentin"
    assert med.generic_name == "gabapentin"
    assert med.brand_name == "Neurontin"
    assert med.drug_class == "Anticonvulsant / Neuropathic Pain Agent"
    assert "Gabapentin" in repr(med)


def test_renal_dosing_guideline_instantiation():
    """Verifies RenalDosingGuideline model attributes and range bounds."""
    guideline = RenalDosingGuideline(
        id=10,
        medication_id=1,
        renal_metric="crcl",
        min_value=Decimal("30.00"),
        max_value=Decimal("59.90"),
        min_daily_dose=Decimal("400.00"),
        max_daily_dose=Decimal("1400.00"),
    )

    assert guideline.id == 10
    assert guideline.medication_id == 1
    assert guideline.renal_metric == "crcl"
    assert guideline.min_value == Decimal("30.00")
    assert guideline.max_value == Decimal("59.90")
    assert guideline.min_daily_dose == Decimal("400.00")
    assert guideline.max_daily_dose == Decimal("1400.00")
    assert "crcl" in repr(guideline)


@pytest.mark.asyncio
async def test_medication_guidelines_lifecycle_and_cascade(test_db_session: AsyncSession):
    """Tests async insert, one-to-many relationship loading, and cascade deletion."""
    # 1. Create medication with tiered renal dosing guidelines via relationship
    med = Medication(
        name="Gabapentin",
        generic_name="gabapentin",
        brand_name="Neurontin",
        drug_class="Anticonvulsant",
    )
    g1 = RenalDosingGuideline(
        renal_metric="crcl",
        min_value=Decimal("60.00"),
        max_value=None,
        min_daily_dose=Decimal("900.00"),
        max_daily_dose=Decimal("1800.00"),
    )
    g2 = RenalDosingGuideline(
        renal_metric="crcl",
        min_value=Decimal("30.00"),
        max_value=Decimal("59.99"),
        min_daily_dose=Decimal("400.00"),
        max_daily_dose=Decimal("1400.00"),
    )
    g3 = RenalDosingGuideline(
        renal_metric="crcl",
        min_value=Decimal("15.00"),
        max_value=Decimal("29.99"),
        min_daily_dose=Decimal("200.00"),
        max_daily_dose=Decimal("700.00"),
    )
    g4 = RenalDosingGuideline(
        renal_metric="crcl",
        min_value=Decimal("0.00"),
        max_value=Decimal("14.99"),
        min_daily_dose=Decimal("100.00"),
        max_daily_dose=Decimal("300.00"),
    )
    med.renal_guidelines = [g1, g2, g3, g4]
    test_db_session.add(med)
    await test_db_session.commit()

    # 2. Query medication with eager-loaded guidelines
    stmt = select(Medication).where(Medication.name == "Gabapentin")
    result = await test_db_session.execute(stmt)
    loaded_med = result.scalar_one()

    assert loaded_med.id is not None
    assert len(loaded_med.renal_guidelines) == 4
    metrics = {g.renal_metric for g in loaded_med.renal_guidelines}
    assert metrics == {"crcl"}

    # 3. Cascade delete: deleting the medication removes all guidelines
    med_id = loaded_med.id
    await test_db_session.delete(loaded_med)
    await test_db_session.commit()

    guidelines_stmt = select(RenalDosingGuideline).where(RenalDosingGuideline.medication_id == med_id)
    guidelines_result = await test_db_session.execute(guidelines_stmt)
    assert guidelines_result.scalars().all() == []
