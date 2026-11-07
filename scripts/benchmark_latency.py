#!/usr/bin/env python3
"""Temperature vs Latency Benchmark Runner for MedV Clinical Audit.

Evaluates streaming latency metrics (TTFT, Generation Time, Total Latency, Throughput, Validity)
across varying temperature settings and outputs a statistical comparison table.
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
API_ROOT = PROJECT_ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.core.config import settings
from app.schemas.audit import AuditStreamAccumulator, ClinicalGapReport, StreamEventType
from app.services.llm_client import MockAuditClient, get_llm_client


def parse_args():
    parser = argparse.ArgumentParser(
        description="Benchmark LLM streaming latency across different temperatures."
    )
    parser.add_argument(
        "--provider",
        type=str,
        default=None,
        help="LLM provider ('gemini', 'openai', 'mock'). Defaults to settings.LLM_PROVIDER.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model override (e.g., 'gemini-3.5-flash-lite', 'gpt-4o').",
    )
    parser.add_argument(
        "--temperatures",
        type=str,
        default="0.0,0.3,0.7,1.0",
        help="Comma-separated list of temperatures to evaluate (default: '0.0,0.3,0.7,1.0').",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of runs per temperature to calculate averages (default: 3).",
    )
    parser.add_argument(
        "--note",
        type=str,
        default="clinical_notes/note_001.txt",
        help="Path to clinical encounter note.",
    )
    parser.add_argument(
        "--rubric",
        type=str,
        default="policy_rubrics/mri_lumbar_spine.txt",
        help="Path to policy rubric.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Delay in seconds between calls to prevent rate limits (default: 1.5s).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="eval_cases/temperature_latency_results.json",
        help="Path to save benchmark JSON results.",
    )
    return parser.parse_args()


async def run_single_iteration(
    client: Any,
    clinical_note: str,
    policy_rubric: str,
    temperature: float,
) -> Dict[str, Any]:
    """Execute one streaming audit run and record exact latency and validity metrics."""
    start_time = time.perf_counter()
    first_token_time: float | None = None
    chunks_count = 0
    total_chars = 0
    retries_count = 0
    accumulator = AuditStreamAccumulator()
    error_msg: str | None = None

    try:
        async for chunk in client.stream_audit(
            clinical_note=clinical_note,
            policy_rubric=policy_rubric,
            temperature=temperature,
        ):
            if chunk.event == StreamEventType.STATUS:
                if chunk.retries:
                    retries_count = max(retries_count, chunk.retries)
            elif chunk.event == StreamEventType.TOKEN and chunk.text:
                if first_token_time is None:
                    first_token_time = time.perf_counter()
                chunks_count += 1
                total_chars += len(chunk.text)
                accumulator.tokens.append(chunk.text)
            elif chunk.event == StreamEventType.DONE and chunk.report:
                accumulator.final_report = chunk.report
                if chunk.retries:
                    retries_count = max(retries_count, chunk.retries)
            elif chunk.event == StreamEventType.ERROR and chunk.error:
                error_msg = chunk.error
                accumulator.error = chunk.error
    except Exception as exc:
        error_msg = str(exc)

    end_time = time.perf_counter()
    total_latency = end_time - start_time

    if first_token_time is not None:
        ttft = first_token_time - start_time
        gen_time = end_time - first_token_time
    else:
        ttft = total_latency
        gen_time = 0.0

    # Validate JSON integrity
    is_valid_schema = False
    if accumulator.final_report is not None:
        is_valid_schema = True
    elif accumulator.accumulated_text:
        try:
            ClinicalGapReport.model_validate_json(accumulator.accumulated_text)
            is_valid_schema = True
        except Exception:
            is_valid_schema = False

    chars_per_sec = (total_chars / total_latency) if total_latency > 0 else 0.0

    return {
        "temperature": temperature,
        "ttft_sec": round(ttft, 3),
        "gen_time_sec": round(gen_time, 3),
        "total_latency_sec": round(total_latency, 3),
        "chunks_count": chunks_count,
        "total_chars": total_chars,
        "retries_count": retries_count,
        "chars_per_sec": round(chars_per_sec, 1),
        "valid_schema": is_valid_schema,
        "error": error_msg,
    }


async def main():
    args = parse_args()

    note_path = PROJECT_ROOT / args.note
    rubric_path = PROJECT_ROOT / args.rubric

    if not note_path.exists():
        print(f"Error: Note file not found at {note_path}")
        sys.exit(1)
    if not rubric_path.exists():
        print(f"Error: Rubric file not found at {rubric_path}")
        sys.exit(1)

    clinical_note = note_path.read_text(encoding="utf-8")
    policy_rubric = rubric_path.read_text(encoding="utf-8")

    temperatures = [float(t.strip()) for t in args.temperatures.split(",") if t.strip()]
    provider = (args.provider or settings.LLM_PROVIDER or "mock").strip().lower()

    if provider == "mock":
        client = MockAuditClient(chunk_delay=0.005, chunk_size=25)
    else:
        client = get_llm_client(provider)
        if args.model and hasattr(client, "model"):
            client.model = args.model

    model_name = getattr(client, "model", "mock")

    print("=" * 82)
    print(" MedV Clinical Audit - Temperature vs Latency Benchmark")
    print(f" Provider     : {provider} | Model: {model_name}")
    print(f" Temperatures : {temperatures}")
    print(f" Runs/Temp    : {args.runs} (Total requests: {len(temperatures) * args.runs})")
    print(f" Clinical Note: {args.note}")
    print(f" Policy Rubric: {args.rubric}")
    print("=" * 82)

    all_results: Dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "provider": provider,
        "model": model_name,
        "temperatures_tested": temperatures,
        "runs_per_temperature": args.runs,
        "temperature_benchmarks": [],
    }

    summary_rows = []

    for temp in temperatures:
        print(f"\n[Evaluating Temperature: {temp}] Running {args.runs} iteration(s)...")
        temp_runs = []

        for run_idx in range(1, args.runs + 1):
            run_data = await run_single_iteration(client, clinical_note, policy_rubric, temp)
            temp_runs.append(run_data)

            valid_str = "VALID" if run_data["valid_schema"] else "INVALID"
            print(
                f"  Run {run_idx}/{args.runs}: TTFT={run_data['ttft_sec']}s | "
                f"Total={run_data['total_latency_sec']}s | "
                f"Speed={run_data['chars_per_sec']} char/s | "
                f"Retries={run_data['retries_count']} | "
                f"Schema={valid_str}"
            )

            if args.delay > 0:
                await asyncio.sleep(args.delay)

        # Aggregate metrics
        avg_ttft = statistics.mean([r["ttft_sec"] for r in temp_runs])
        avg_gen = statistics.mean([r["gen_time_sec"] for r in temp_runs])
        avg_total = statistics.mean([r["total_latency_sec"] for r in temp_runs])
        avg_speed = statistics.mean([r["chars_per_sec"] for r in temp_runs])
        avg_retries = statistics.mean([r["retries_count"] for r in temp_runs])
        valid_count = sum(1 for r in temp_runs if r["valid_schema"])
        valid_rate = (valid_count / len(temp_runs)) * 100

        temp_summary = {
            "temperature": temp,
            "avg_ttft_sec": round(avg_ttft, 3),
            "avg_gen_time_sec": round(avg_gen, 3),
            "avg_total_latency_sec": round(avg_total, 3),
            "avg_chars_per_sec": round(avg_speed, 1),
            "avg_retries": round(avg_retries, 2),
            "valid_schema_rate_pct": round(valid_rate, 1),
            "runs": temp_runs,
        }
        all_results["temperature_benchmarks"].append(temp_summary)

        summary_rows.append(temp_summary)

    # Print Final Comparison Table
    print("\n" + "=" * 94)
    print(" TEMPERATURE LATENCY BENCHMARK SUMMARY")
    print("=" * 94)
    print(
        f"{'Temp':<6} | {'Avg TTFT':<10} | {'Avg Gen Time':<13} | "
        f"{'Avg Total Latency':<18} | {'Speed (char/s)':<15} | {'Avg Retries':<11} | {'Valid JSON %':<12}"
    )
    print("-" * 94)
    for row in summary_rows:
        print(
            f"{row['temperature']:<6.1f} | "
            f"{row['avg_ttft_sec']:>7.3f}s   | "
            f"{row['avg_gen_time_sec']:>10.3f}s   | "
            f"{row['avg_total_latency_sec']:>15.3f}s   | "
            f"{row['avg_chars_per_sec']:>12.1f}    | "
            f"{row['avg_retries']:>9.2f}   | "
            f"{row['valid_schema_rate_pct']:>9.1f}%"
        )
    print("=" * 94)

    # Save output JSON
    output_path = PROJECT_ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)

    print(f"\nDetailed benchmark metrics saved to: {args.output}\n")


if __name__ == "__main__":
    asyncio.run(main())
