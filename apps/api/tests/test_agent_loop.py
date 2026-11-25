import json
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.medication import Medication, RenalDosingGuideline
from app.models.patient import Patient, PatientLab
from app.schemas.renal import RenalAuditReport
from app.services.agent.loop import RenalAgentRunner
from app.services.agent.tools import execute_tool_call, get_gemini_renal_tools


@pytest_asyncio.fixture
async def loop_test_session():
    """In-memory SQLite session seeded with CrCl and eGFR test cases."""
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
        p1 = Patient(
            patient_id="uuid-p001",
            name="Gavin Thiel",
            age_years=21,
            biological_sex="Male",
            actual_weight_kg=Decimal("81.70"),
            height_cm=Decimal("175.00"),
        )
        p1_lab = PatientLab(
            patient_id="uuid-p001",
            serum_creatinine_mg_dl=Decimal("0.90"),
            egfr_ml_min_1_73m2=Decimal("110.0"),
            collected_at=datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc),
        )

        p2 = Patient(
            patient_id="uuid-p002",
            name="No Labs Patient",
            age_years=65,
            biological_sex="Female",
            actual_weight_kg=Decimal("65.00"),
            height_cm=Decimal("162.00"),
        )

        med_gaba = Medication(
            name="Gabapentin",
            generic_name="gabapentin",
            drug_class="Anticonvulsant",
        )
        med_met = Medication(
            name="Metformin",
            generic_name="metformin",
            drug_class="Biguanide",
        )
        session.add_all([p1, p1_lab, p2, med_gaba, med_met])
        await session.flush()

        session.add_all([
            RenalDosingGuideline(
                medication_id=med_gaba.id,
                renal_metric="CrCl",
                min_value=Decimal("60.0"),
                max_value=Decimal("999.0"),
                min_daily_dose=Decimal("900.0"),
                max_daily_dose=Decimal("3600.0"),
            ),
            RenalDosingGuideline(
                medication_id=med_met.id,
                renal_metric="eGFR",
                min_value=Decimal("45.0"),
                max_value=Decimal("999.0"),
                min_daily_dose=Decimal("500.0"),
                max_daily_dose=Decimal("2000.0"),
            ),
        ])
        await session.commit()
        yield session

    await engine.dispose()


def _make_fc_response(name: str, args: dict):
    fc = SimpleNamespace(name=name, args=args)
    candidate = SimpleNamespace(content=SimpleNamespace(role="model", parts=[]))
    return SimpleNamespace(function_calls=[fc], candidates=[candidate], text=None)


def _make_text_response(payload: dict):
    candidate = SimpleNamespace(content=SimpleNamespace(role="model", parts=[]))
    return SimpleNamespace(
        function_calls=[],
        candidates=[candidate],
        text=json.dumps(payload),
    )


class _FakeAsyncModels:
    def __init__(self, scripted_responses):
        self._responses = list(scripted_responses)
        self.calls = []

    async def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        return self._responses.pop(0)


class _FakeGeminiClient:
    def __init__(self, scripted_responses):
        self.models = _FakeAsyncModels(scripted_responses)
        self.aio = SimpleNamespace(models=self.models)


@pytest.mark.asyncio
async def test_execute_tool_call_unknown_and_invalid_args(loop_test_session):
    unknown = await execute_tool_call("nonexistent_tool", {}, session=loop_test_session)
    assert unknown["status"] == "error"

    bad_args = await execute_tool_call(
        "get_renal_metric",
        {"wrong_param": "Gabapentin"},
        session=loop_test_session,
    )
    assert bad_args["status"] == "error"


@pytest.mark.asyncio
async def test_loop_crcl_full_chain_safe(loop_test_session):
    final_payload = RenalAuditReport(
        patient_id="uuid-p001",
        medication_name="Gabapentin",
        prescribed_daily_dose_mg=1800.0,
        required_renal_metric="crcl",
        renal_metric_value=149.91,
        verdict="safe",
        rationale="Calculated CrCl is 149.91 mL/min; 1800 mg/day is within 900-3600 mg/day.",
    ).model_dump()

    fake_client = _FakeGeminiClient([
        _make_fc_response("get_renal_metric", {"medication_name": "Gabapentin"}),
        _make_fc_response("fetch_patient_crcl", {"patient_id": "uuid-p001"}),
        _make_fc_response("calculate_crcl", {"patient_id": "uuid-p001"}),
        _make_text_response(final_payload),
    ])

    runner = RenalAgentRunner(client=fake_client, model="gemini-3.5-flash")
    report = await runner.run(
        discharge_json='{"patient_id": "uuid-p001", "medication": "Gabapentin", "daily_dose_mg": 1800}',
        session=loop_test_session,
    )

    assert report.verdict == "safe"
    assert report.required_renal_metric == "crcl"
    assert len(report.tool_trace) == 3
    assert report.tool_trace[0].startswith("get_renal_metric")
    assert report.tool_trace[1].startswith("fetch_patient_crcl")
    assert report.tool_trace[2].startswith("calculate_crcl")


@pytest.mark.asyncio
async def test_loop_egfr_skips_calculate_crcl(loop_test_session):
    final_payload = RenalAuditReport(
        patient_id="uuid-p001",
        medication_name="Metformin",
        prescribed_daily_dose_mg=2500.0,
        required_renal_metric="egfr",
        renal_metric_value=110.0,
        verdict="dose_adjustment_required",
        rationale="eGFR is 110.0; prescribed 2500 mg/day exceeds max 2000 mg/day.",
    ).model_dump()

    fake_client = _FakeGeminiClient([
        _make_fc_response("get_renal_metric", {"medication_name": "Metformin"}),
        _make_fc_response("fetch_patient_crcl", {"patient_id": "uuid-p001"}),
        _make_text_response(final_payload),
    ])

    runner = RenalAgentRunner(client=fake_client, model="gemini-3.5-flash")
    report = await runner.run(
        discharge_json='{"patient_id": "uuid-p001", "medication": "Metformin", "daily_dose_mg": 2500}',
        session=loop_test_session,
    )

    assert report.verdict == "dose_adjustment_required"
    assert len(report.tool_trace) == 2
    assert not any(call.startswith("calculate_crcl") for call in report.tool_trace)


@pytest.mark.asyncio
async def test_loop_missing_biomarker_halts_insufficient_data(loop_test_session):
    final_payload = RenalAuditReport(
        patient_id="uuid-p002",
        medication_name="Gabapentin",
        prescribed_daily_dose_mg=900.0,
        required_renal_metric="crcl",
        renal_metric_value=None,
        verdict="insufficient_data",
        rationale="Patient has no serum creatinine labs.",
    ).model_dump()

    fake_client = _FakeGeminiClient([
        _make_fc_response("get_renal_metric", {"medication_name": "Gabapentin"}),
        _make_fc_response("fetch_patient_crcl", {"patient_id": "uuid-p002"}),
        _make_text_response(final_payload),
    ])

    runner = RenalAgentRunner(client=fake_client, model="gemini-3.5-flash")
    report = await runner.run(
        discharge_json='{"patient_id": "uuid-p002", "medication": "Gabapentin", "daily_dose_mg": 900}',
        session=loop_test_session,
    )

    assert report.verdict == "insufficient_data"
    assert len(report.tool_trace) == 2


@pytest.mark.asyncio
async def test_loop_max_iterations_guard(loop_test_session):
    fake_client = _FakeGeminiClient([
        _make_fc_response("get_renal_metric", {"medication_name": "Gabapentin"}),
        _make_fc_response("get_renal_metric", {"medication_name": "Gabapentin"}),
    ])

    runner = RenalAgentRunner(client=fake_client, model="gemini-3.5-flash", max_iterations=2)
    report = await runner.run(
        discharge_json='{"patient_id": "uuid-p001", "medication": "Gabapentin"}',
        session=loop_test_session,
        patient_id_hint="uuid-p001",
        medication_hint="Gabapentin",
    )

    assert report.verdict == "insufficient_data"
    assert "maximum iteration limit" in report.rationale
    assert len(report.tool_trace) == 2


def test_renal_report_forbids_safe_when_metric_is_null():
    with pytest.raises(ValidationError):
        RenalAuditReport(
            patient_id="uuid-p001",
            medication_name="Gabapentin",
            required_renal_metric="crcl",
            renal_metric_value=None,
            verdict="safe",
            rationale="Claimed safe without renal metric.",
        )


@pytest.mark.asyncio
async def test_loop_forces_insufficient_data_when_tools_skipped(loop_test_session):
    hallucinated_payload = RenalAuditReport(
        patient_id="uuid-p001",
        medication_name="Gabapentin",
        prescribed_daily_dose_mg=1800.0,
        required_renal_metric="crcl",
        renal_metric_value=120.0,
        verdict="safe",
        rationale="Claimed safe without calling any database tools.",
    ).model_dump()

    fake_client = _FakeGeminiClient([
        _make_text_response(hallucinated_payload),
    ])

    runner = RenalAgentRunner(client=fake_client, model="gemini-3.5-flash")
    report = await runner.run(
        discharge_json='{"patient_id": "uuid-p001", "medication": "Gabapentin", "daily_dose_mg": 1800}',
        session=loop_test_session,
    )

    assert report.verdict == "insufficient_data"
    assert len(report.tool_trace) == 0
    assert "System Guardrail" in report.rationale


def test_gemini_calculate_crcl_schema_excludes_scr():
    tools = get_gemini_renal_tools()
    declarations = tools[0].function_declarations
    calc_decl = next(d for d in declarations if d.name == "calculate_crcl")
    assert "serum_creatinine_mg_dl" not in calc_decl.parameters.properties


@pytest.mark.asyncio
async def test_loop_forces_verified_patient_id_and_strips_hallucinated_scr(loop_test_session):
    final_payload = RenalAuditReport(
        patient_id="uuid-p001",
        medication_name="Gabapentin",
        prescribed_daily_dose_mg=1800.0,
        required_renal_metric="crcl",
        renal_metric_value=149.91,
        verdict="safe",
        rationale="Verified using DB patient_id and DB SCr.",
    ).model_dump()

    # Model attempts to query wrong patient_id ('uuid-p002') and pass fake SCr (9.9)
    fake_client = _FakeGeminiClient([
        _make_fc_response("get_renal_metric", {"medication_name": "Gabapentin"}),
        _make_fc_response("fetch_patient_crcl", {"patient_id": "uuid-p002"}),
        _make_fc_response("calculate_crcl", {"patient_id": "uuid-p002", "serum_creatinine_mg_dl": 9.9}),
        _make_text_response(final_payload),
    ])

    runner = RenalAgentRunner(client=fake_client, model="gemini-3.5-flash")
    report = await runner.run(
        discharge_json='{"patient_id": "uuid-p001", "medication": "Gabapentin", "daily_dose_mg": 1800}',
        session=loop_test_session,
    )

    assert report.verdict == "safe"
    assert all("uuid-p001" in trace for trace in report.tool_trace[1:])
    assert all("uuid-p002" not in trace for trace in report.tool_trace)
    assert all("serum_creatinine_mg_dl" not in trace for trace in report.tool_trace)
