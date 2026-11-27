import json
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.benchmark_renal import (
    calculate_cost_usd,
    create_benchmark_session_factory,
    evaluate_cases,
)
from app.schemas.renal import RenalAuditReport
from app.services.agent.loop import RenalAgentRunner


EVAL_CASES_PATH = PROJECT_ROOT / "eval_cases" / "renal_eval_cases.json"


def test_renal_eval_cases_json_has_15_valid_cases():
    cases = json.loads(EVAL_CASES_PATH.read_text(encoding="utf-8"))
    assert len(cases) == 15

    ids = set()
    for case in cases:
        assert set(["id", "desc", "input_discharge", "expected_verdict", "expected_tools"]).issubset(
            case.keys()
        )
        assert case["id"] not in ids
        ids.add(case["id"])
        assert case["expected_verdict"] in ("safe", "dose_adjustment_required", "insufficient_data")
        assert isinstance(case["expected_tools"], list) and len(case["expected_tools"]) >= 1
        assert isinstance(case["input_discharge"], dict)


def test_model_pricing_gemini_35_flash_lite():
    cost = calculate_cost_usd(
        model="gemini-3.5-flash-lite",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
    )
    assert cost["input_cost_usd"] == 0.30
    assert cost["output_cost_usd"] == 2.50
    assert cost["total_cost_usd"] == 2.80


@pytest.mark.asyncio
async def test_benchmark_evaluate_cases_metrics_aggregation():
    engine, session_factory = await create_benchmark_session_factory()
    try:
        cases = json.loads(EVAL_CASES_PATH.read_text(encoding="utf-8"))[:2]

        class _FakeModels:
            def __init__(self):
                self.turn = 0

            async def generate_content(self, *, model, contents, config):
                # Case 1 (3 tools + 1 text) and Case 2 (3 tools + 1 text)
                scripted = [
                    SimpleNamespace(
                        function_calls=[SimpleNamespace(name="get_renal_metric", args={"medication_name": "Gabapentin"})],
                        candidates=[SimpleNamespace(content=SimpleNamespace(role="model", parts=[]))],
                        text=None,
                        usage_metadata=SimpleNamespace(prompt_token_count=200, candidates_token_count=20),
                    ),
                    SimpleNamespace(
                        function_calls=[SimpleNamespace(name="fetch_patient_crcl", args={"patient_id": "bench-pt-01"})],
                        candidates=[SimpleNamespace(content=SimpleNamespace(role="model", parts=[]))],
                        text=None,
                        usage_metadata=SimpleNamespace(prompt_token_count=250, candidates_token_count=20),
                    ),
                    SimpleNamespace(
                        function_calls=[SimpleNamespace(name="calculate_crcl", args={"patient_id": "bench-pt-01"})],
                        candidates=[SimpleNamespace(content=SimpleNamespace(role="model", parts=[]))],
                        text=None,
                        usage_metadata=SimpleNamespace(prompt_token_count=300, candidates_token_count=20),
                    ),
                    SimpleNamespace(
                        function_calls=[],
                        candidates=[SimpleNamespace(content=SimpleNamespace(role="model", parts=[]))],
                        text=RenalAuditReport(
                            patient_id="bench-pt-01",
                            medication_name="Gabapentin",
                            prescribed_daily_dose_mg=1800.0,
                            required_renal_metric="crcl",
                            renal_metric_value=100.0,
                            verdict="safe",
                            rationale="Safe.",
                        ).model_dump_json(),
                        usage_metadata=SimpleNamespace(prompt_token_count=350, candidates_token_count=40),
                    ),
                ]
                resp = scripted[self.turn % len(scripted)]
                self.turn += 1
                return resp

        fake_client = SimpleNamespace(aio=SimpleNamespace(models=_FakeModels()))
        runner = RenalAgentRunner(
            client=fake_client,
            model="gemini-3.5-flash-lite",
            temperature=0.0,
        )

        results = await evaluate_cases(
            cases=cases,
            runner=runner,
            session_factory=session_factory,
            delay_seconds=0.0,
        )

        summary = results["summary"]
        assert summary["total_cases"] == 2
        assert summary["completed_cases"] == 2
        assert summary["errored_cases"] == 0
        assert summary["task_passed"] == 2
        assert summary["task_pass_rate_pct"] == 100.0
        assert summary["completed_task_pass_rate_pct"] == 100.0
        assert summary["tool_exact_matches"] == 2
        assert summary["tool_selection_accuracy_pct"] == 100.0
        assert summary["completed_tool_accuracy_pct"] == 100.0
        assert summary["avg_steps"] == 4.0
        assert summary["total_input_tokens"] == 2200
        assert summary["total_output_tokens"] == 200
        assert summary["total_cost_usd"] == round(
            (2200 / 1_000_000) * 0.30 + (200 / 1_000_000) * 2.50, 6
        )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_benchmark_separates_errored_cases_from_completed_metrics():
    engine, session_factory = await create_benchmark_session_factory()
    try:
        cases = json.loads(EVAL_CASES_PATH.read_text(encoding="utf-8"))[:2]

        class _PartialErrorRunner:
            model = "gemini-3.5-flash-lite"
            temperature = 0.0

            def __init__(self):
                self.calls = 0

            async def run(self, *, discharge_json, session):
                self.calls += 1
                if self.calls == 1:
                    return {
                        "report": RenalAuditReport(
                            patient_id="bench-pt-01",
                            medication_name="Gabapentin",
                            prescribed_daily_dose_mg=1800.0,
                            required_renal_metric="crcl",
                            renal_metric_value=100.0,
                            verdict="safe",
                            rationale="Safe.",
                        ),
                        "tools_called": ["get_renal_metric", "fetch_patient_crcl", "calculate_crcl"],
                        "steps": 4,
                        "input_tokens": 1000,
                        "output_tokens": 100,
                    }
                raise RuntimeError("503 UNAVAILABLE")

        results = await evaluate_cases(
            cases=cases,
            runner=_PartialErrorRunner(),  # type: ignore[arg-type]
            session_factory=session_factory,
            delay_seconds=0.0,
        )

        s = results["summary"]
        assert s["total_cases"] == 2
        assert s["completed_cases"] == 1
        assert s["errored_cases"] == 1
        assert s["task_passed"] == 1
        assert s["task_failed"] == 0  # No reasoning failure; 1 API error
        assert s["task_pass_rate_pct"] == 50.0
        assert s["completed_task_pass_rate_pct"] == 100.0
        assert s["completed_tool_accuracy_pct"] == 100.0
        assert s["avg_steps"] == 4.0  # Not dragged down to 2.0 by the 503 error
    finally:
        await engine.dispose()
