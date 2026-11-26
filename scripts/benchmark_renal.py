#!/usr/bin/env python3
"""Stage 2 Renal Safety Auditor Benchmark Runner.

Evaluates the autonomous Gemini tool-calling loop against eval_cases/renal_eval_cases.json
and reports:
1. Task Pass/Fail Rate (verdict accuracy)
2. Exact Tool Selection Sequence Accuracy
3. Average Steps per Case
4. Average Latency, Token Usage, and Estimated Cost (USD)
"""

import argparse
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parent.parent
API_ROOT = PROJECT_ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.db.base import Base
from app.models.medication import Medication, RenalDosingGuideline
from app.models.patient import Patient, PatientLab
from app.services.agent.loop import RenalAgentRunner

# Pricing per 1M tokens (USD)
MODEL_PRICING_PER_1M_TOKENS: Dict[str, Dict[str, float]] = {
    "gemini-3.5-flash-lite": {"input": 0.30, "output": 2.50},
    "gemini-3.5-flash": {"input": 0.30, "output": 2.50},
}

DEFAULT_MODEL = "gemini-3.5-flash-lite"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Stage 2 Renal Safety Auditor Evaluation Benchmark"
    )
    parser.add_argument(
        "--eval-file",
        type=str,
        default="eval_cases/renal_eval_cases.json",
        help="Path to Stage 2 eval cases JSON (default: eval_cases/renal_eval_cases.json)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="eval_cases/renal_eval_results.json",
        help="Path to write detailed benchmark results JSON",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"Gemini model name (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--case-id",
        type=str,
        default=None,
        help="Optional single case ID filter (e.g., renal_001)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=4.5,
        help="Pause in seconds between requests for free-tier RPM quotas (default: 4.5s)",
    )
    return parser.parse_args()


def calculate_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> Dict[str, float]:
    """Calculate USD cost for input and output tokens using model pricing."""
    pricing = MODEL_PRICING_PER_1M_TOKENS.get(
        model,
        MODEL_PRICING_PER_1M_TOKENS[DEFAULT_MODEL],
    )
    input_cost = (input_tokens / 1_000_000.0) * pricing["input"]
    output_cost = (output_tokens / 1_000_000.0) * pricing["output"]
    return {
        "input_cost_usd": round(input_cost, 6),
        "output_cost_usd": round(output_cost, 6),
        "total_cost_usd": round(input_cost + output_cost, 6),
        "input_rate_per_1m": pricing["input"],
        "output_rate_per_1m": pricing["output"],
    }


async def create_benchmark_session_factory():
    """Create and seed an isolated in-memory SQLite DB covering all 15 Stage 2 scenarios."""
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
        # Medications
        med_gaba = Medication(
            name="Gabapentin",
            generic_name="gabapentin",
            brand_name="Neurontin",
            drug_class="Anticonvulsant",
        )
        med_met = Medication(
            name="Metformin",
            generic_name="metformin",
            brand_name="Glucophage",
            drug_class="Biguanide",
        )
        session.add_all([med_gaba, med_met])
        await session.flush()

        session.add_all([
            # Gabapentin guidelines (CrCl)
            RenalDosingGuideline(
                medication_id=med_gaba.id,
                renal_metric="creatinine_clearance",
                min_value=Decimal("60.0"),
                max_value=Decimal("999.0"),
                min_daily_dose=Decimal("900.0"),
                max_daily_dose=Decimal("3600.0"),
            ),
            RenalDosingGuideline(
                medication_id=med_gaba.id,
                renal_metric="creatinine_clearance",
                min_value=Decimal("30.0"),
                max_value=Decimal("59.99"),
                min_daily_dose=Decimal("400.0"),
                max_daily_dose=Decimal("1400.0"),
            ),
            RenalDosingGuideline(
                medication_id=med_gaba.id,
                renal_metric="creatinine_clearance",
                min_value=Decimal("15.0"),
                max_value=Decimal("29.99"),
                min_daily_dose=Decimal("200.0"),
                max_daily_dose=Decimal("700.0"),
            ),
            RenalDosingGuideline(
                medication_id=med_gaba.id,
                renal_metric="creatinine_clearance",
                min_value=Decimal("0.0"),
                max_value=Decimal("14.99"),
                min_daily_dose=Decimal("100.0"),
                max_daily_dose=Decimal("300.0"),
            ),
            # Metformin guidelines (eGFR)
            RenalDosingGuideline(
                medication_id=med_met.id,
                renal_metric="egfr",
                min_value=Decimal("45.0"),
                max_value=Decimal("999.0"),
                min_daily_dose=Decimal("500.0"),
                max_daily_dose=Decimal("2000.0"),
            ),
            RenalDosingGuideline(
                medication_id=med_met.id,
                renal_metric="egfr",
                min_value=Decimal("30.0"),
                max_value=Decimal("44.99"),
                min_daily_dose=Decimal("500.0"),
                max_daily_dose=Decimal("1000.0"),
            ),
            RenalDosingGuideline(
                medication_id=med_met.id,
                renal_metric="egfr",
                min_value=Decimal("0.0"),
                max_value=Decimal("29.99"),
                min_daily_dose=Decimal("0.0"),
                max_daily_dose=Decimal("0.0"),
            ),
        ])

        # Patients & longitudinal labs
        patients = [
            Patient(
                patient_id="bench-pt-01",
                name="Normal Function Patient",
                age_years=40,
                biological_sex="Male",
                actual_weight_kg=Decimal("72.00"),
                height_cm=Decimal("175.00"),
            ),
            Patient(
                patient_id="bench-pt-02",
                name="Moderate Impairment Female",
                age_years=68,
                biological_sex="Female",
                actual_weight_kg=Decimal("60.00"),
                height_cm=Decimal("162.00"),
            ),
            Patient(
                patient_id="bench-pt-03",
                name="Severe Impairment Male",
                age_years=76,
                biological_sex="Male",
                actual_weight_kg=Decimal("64.00"),
                height_cm=Decimal("170.00"),
            ),
            Patient(
                patient_id="bench-pt-05",
                name="Longitudinal Lab Patient",
                age_years=40,
                biological_sex="Male",
                actual_weight_kg=Decimal("72.00"),
                height_cm=Decimal("176.00"),
            ),
            Patient(
                patient_id="bench-pt-06",
                name="eGFR Only Patient",
                age_years=55,
                biological_sex="Female",
                actual_weight_kg=Decimal("65.00"),
                height_cm=Decimal("165.00"),
            ),
            Patient(
                patient_id="bench-pt-07",
                name="SCr Only Patient",
                age_years=50,
                biological_sex="Male",
                actual_weight_kg=Decimal("80.00"),
                height_cm=Decimal("178.00"),
            ),
        ]
        session.add_all(patients)

        labs = [
            # bench-pt-01: CrCl = 100.0, eGFR = 92.0
            PatientLab(
                patient_id="bench-pt-01",
                serum_creatinine_mg_dl=Decimal("1.00"),
                egfr_ml_min_1_73m2=Decimal("92.0"),
                collected_at=datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc),
            ),
            # bench-pt-02: CrCl = ((140-68)*60)/(72*1.2)*0.85 = 42.5, eGFR = 42.0
            PatientLab(
                patient_id="bench-pt-02",
                serum_creatinine_mg_dl=Decimal("1.20"),
                egfr_ml_min_1_73m2=Decimal("42.0"),
                collected_at=datetime(2026, 11, 21, 9, 0, tzinfo=timezone.utc),
            ),
            # bench-pt-03: CrCl = ((140-76)*64)/(72*2.5) = 22.76, eGFR = 24.0
            PatientLab(
                patient_id="bench-pt-03",
                serum_creatinine_mg_dl=Decimal("2.50"),
                egfr_ml_min_1_73m2=Decimal("24.0"),
                collected_at=datetime(2026, 11, 22, 9, 0, tzinfo=timezone.utc),
            ),
            # bench-pt-05: older panel has SCr 1.0, newer panel is eGFR-only
            PatientLab(
                patient_id="bench-pt-05",
                serum_creatinine_mg_dl=Decimal("1.00"),
                egfr_ml_min_1_73m2=Decimal("90.0"),
                collected_at=datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc),
            ),
            PatientLab(
                patient_id="bench-pt-05",
                serum_creatinine_mg_dl=None,
                egfr_ml_min_1_73m2=Decimal("95.0"),
                collected_at=datetime(2026, 11, 24, 9, 0, tzinfo=timezone.utc),
            ),
            # bench-pt-06: eGFR-only everywhere (no SCr)
            PatientLab(
                patient_id="bench-pt-06",
                serum_creatinine_mg_dl=None,
                egfr_ml_min_1_73m2=Decimal("75.0"),
                collected_at=datetime(2026, 11, 23, 9, 0, tzinfo=timezone.utc),
            ),
            # bench-pt-07: SCr-only everywhere (no eGFR)
            PatientLab(
                patient_id="bench-pt-07",
                serum_creatinine_mg_dl=Decimal("1.10"),
                egfr_ml_min_1_73m2=None,
                collected_at=datetime(2026, 11, 23, 9, 0, tzinfo=timezone.utc),
            ),
        ]
        session.add_all(labs)
        await session.commit()

    return engine, session_factory


async def evaluate_cases(
    cases: List[Dict[str, Any]],
    runner: RenalAgentRunner,
    session_factory: Any,
    delay_seconds: float,
) -> Dict[str, Any]:
    """Run all benchmark cases and aggregate pass/fail, tool accuracy, steps, latency, tokens, cost."""
    case_results: List[Dict[str, Any]] = []

    for idx, case in enumerate(cases):
        case_id = case["id"]
        desc = case["desc"]
        discharge_json = json.dumps(case["input_discharge"])
        expected_verdict = case["expected_verdict"]
        expected_tools = case["expected_tools"]

        print(f"[{idx + 1}/{len(cases)}] Running {case_id}: {desc}")

        started = time.perf_counter()
        error_msg: Optional[str] = None
        actual_verdict: Optional[str] = None
        tools_called: List[str] = []
        steps = 0
        input_tokens = 0
        output_tokens = 0
        rationale = ""

        try:
            async with session_factory() as session:
                run_out = await runner.run(
                    discharge_json=discharge_json,
                    session=session,
                )
            report = run_out["report"]
            actual_verdict = report.verdict
            rationale = report.rationale
            tools_called = list(run_out["tools_called"])
            steps = int(run_out["steps"])
            input_tokens = int(run_out["input_tokens"])
            output_tokens = int(run_out["output_tokens"])
        except Exception as exc:
            error_msg = str(exc)

        latency_s = round(time.perf_counter() - started, 3)
        verdict_pass = (error_msg is None) and (actual_verdict == expected_verdict)
        tool_match = (error_msg is None) and (tools_called == expected_tools)

        status_label = "PASS" if verdict_pass else "FAIL"
        tool_label = "EXACT" if tool_match else "MISMATCH"
        print(
            f"   -> Verdict: {actual_verdict} (expected {expected_verdict}) [{status_label}] | "
            f"Tools: {tools_called} [{tool_label}] | "
            f"Steps: {steps} | Latency: {latency_s:.2f}s | "
            f"Tokens: {input_tokens} in / {output_tokens} out"
        )
        if error_msg:
            print(f"   -> Error: {error_msg}")

        case_results.append({
            "id": case_id,
            "desc": desc,
            "expected_verdict": expected_verdict,
            "actual_verdict": actual_verdict,
            "verdict_pass": verdict_pass,
            "expected_tools": expected_tools,
            "tools_called": tools_called,
            "tool_selection_match": tool_match,
            "steps": steps,
            "latency_seconds": latency_s,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "rationale": rationale,
            "error": error_msg,
        })

        if delay_seconds > 0 and idx < len(cases) - 1:
            await asyncio.sleep(delay_seconds)

    total = len(case_results)
    verdict_passes = sum(1 for r in case_results if r["verdict_pass"])
    tool_matches = sum(1 for r in case_results if r["tool_selection_match"])
    total_steps = sum(r["steps"] for r in case_results)
    total_input_tokens = sum(r["input_tokens"] for r in case_results)
    total_output_tokens = sum(r["output_tokens"] for r in case_results)
    latencies = [r["latency_seconds"] for r in case_results]

    cost_summary = calculate_cost_usd(
        model=runner.model,
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
    )

    summary = {
        "model": runner.model,
        "temperature": runner.temperature,
        "total_cases": total,
        "task_passed": verdict_passes,
        "task_failed": total - verdict_passes,
        "task_pass_rate_pct": round((verdict_passes / total) * 100, 2) if total else 0.0,
        "tool_exact_matches": tool_matches,
        "tool_selection_accuracy_pct": round((tool_matches / total) * 100, 2) if total else 0.0,
        "avg_steps": round(total_steps / total, 2) if total else 0.0,
        "avg_latency_seconds": round(statistics.mean(latencies), 3) if latencies else 0.0,
        "total_latency_seconds": round(sum(latencies), 3),
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_tokens": total_input_tokens + total_output_tokens,
        **cost_summary,
    }

    return {"summary": summary, "cases": case_results}


async def async_main() -> None:
    args = parse_args()
    eval_path = PROJECT_ROOT / args.eval_file
    if not eval_path.exists():
        print(f"Error: Eval file not found at {eval_path}")
        sys.exit(1)

    cases: List[Dict[str, Any]] = json.loads(eval_path.read_text(encoding="utf-8"))
    if args.case_id:
        cases = [c for c in cases if c.get("id") == args.case_id]
        if not cases:
            print(f"Error: Case '{args.case_id}' not found in {eval_path}")
            sys.exit(1)

    engine, session_factory = await create_benchmark_session_factory()
    try:
        runner = RenalAgentRunner(
            model=args.model,
            temperature=0.0,
        )

        print("=" * 84)
        print(" MedV Stage 2 Renal Safety Auditor - Evaluation Benchmark")
        print(
            f" Model: {runner.model} | Temperature: {runner.temperature} | "
            f"Cases: {len(cases)} | Inter-case pause: {args.delay}s"
        )
        print("=" * 84)

        results = await evaluate_cases(
            cases=cases,
            runner=runner,
            session_factory=session_factory,
            delay_seconds=args.delay,
        )
    finally:
        await engine.dispose()

    s = results["summary"]
    print("\n" + "=" * 84)
    print(" STAGE 2 BENCHMARK SUMMARY")
    print("=" * 84)
    print(f" Task Pass/Fail Rate      : {s['task_passed']}/{s['total_cases']} ({s['task_pass_rate_pct']}%)")
    print(f" Tool Selection Accuracy  : {s['tool_exact_matches']}/{s['total_cases']} ({s['tool_selection_accuracy_pct']}%)")
    print(f" Average Steps per Case   : {s['avg_steps']}")
    print(f" Average Latency          : {s['avg_latency_seconds']:.3f}s (Total: {s['total_latency_seconds']:.3f}s)")
    print(f" Total Tokens             : {s['total_input_tokens']} input + {s['total_output_tokens']} output = {s['total_tokens']}")
    print(
        f" Money Burnt ({s['model']} @ ${s['input_rate_per_1m']:.2f}/1M in, "
        f"${s['output_rate_per_1m']:.2f}/1M out): "
        f"${s['total_cost_usd']:.6f} "
        f"(in: ${s['input_cost_usd']:.6f}, out: ${s['output_cost_usd']:.6f})"
    )
    print("=" * 84)

    out_path = PROJECT_ROOT / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Saved detailed results to {out_path}")


if __name__ == "__main__":
    asyncio.run(async_main())
