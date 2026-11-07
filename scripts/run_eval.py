#!/usr/bin/env python3
"""Stage 1 Evaluation Benchmark Runner for MedV Clinical Audit System.

Evaluates clinical notes against policy rubrics using the configured LLM,
compares results against ground-truth expectations in eval_cases/eval_cases.json,
and generates performance metrics and detailed output reports.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
API_ROOT = PROJECT_ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.core.config import settings
from app.schemas.audit import ClinicalGapReport
from app.services.llm_client import get_llm_client


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run MedV Stage 1 Clinical Audit Evaluation Benchmark"
    )
    parser.add_argument(
        "--eval-file",
        type=str,
        default="eval_cases/eval_cases.json",
        help="Path to evaluation cases JSON file (default: eval_cases/eval_cases.json)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="eval_cases/eval_results.json",
        help="Path to save detailed evaluation results JSON (default: eval_cases/eval_results.json)",
    )
    parser.add_argument(
        "--case-id",
        type=str,
        default=None,
        help="Run only a specific case ID (e.g., eval_001)",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default=None,
        help="LLM provider override ('gemini', 'openai', 'mock')",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="LLM model override (e.g., 'gemini-3.5-flash', 'gpt-4o')",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Delay in seconds between LLM calls to prevent rate limits (default: 1.5s)",
    )
    return parser.parse_args()


def load_file_content(relative_or_abs_path: str) -> str:
    path = Path(relative_or_abs_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return path.read_text(encoding="utf-8")


def match_criterion(
    target_criterion: str,
    evaluations: List[Any],
) -> Optional[Any]:
    target_clean = target_criterion.strip().lower()
    for ev in evaluations:
        ev_clean = ev.criterion.strip().lower()
        if ev_clean == target_clean or target_clean in ev_clean or ev_clean in target_clean:
            return ev
    return None


def run_eval():
    args = parse_args()
    eval_file_path = PROJECT_ROOT / args.eval_file

    if not eval_file_path.exists():
        print(f"Error: Evaluation file not found at {eval_file_path}")
        sys.exit(1)

    with open(eval_file_path, "r", encoding="utf-8") as f:
        cases: List[Dict[str, Any]] = json.load(f)

    if args.case_id:
        cases = [c for c in cases if c.get("case_id") == args.case_id]
        if not cases:
            print(f"Error: No case found with ID '{args.case_id}' in {eval_file_path}")
            sys.exit(1)

    provider = args.provider or settings.LLM_PROVIDER
    model = args.model or settings.LLM_MODEL
    print("=" * 80)
    print(f" MedV Clinical Audit System - Evaluation Benchmark (Stage 1)")
    print(f" Provider: {provider} | Model: {model}")
    print(f" Test Cases: {len(cases)} case(s) loaded from {args.eval_file}")
    print("=" * 80)

    # Initialize client
    client = get_llm_client(provider)
    if hasattr(client, "model") and args.model:
        client.model = args.model

    total_criteria = 0
    matched_criteria = 0
    results_data = []

    for idx, case in enumerate(cases, 1):
        case_id = case.get("case_id", f"case_{idx}")
        desc = case.get("description", "")
        note_path = case.get("note_file")
        rubric_path = case.get("rubric_file")
        expected_evals = case.get("expected_evaluations", [])

        print(f"\n[{idx}/{len(cases)}] Running {case_id}: {desc}")
        print(f"  Note: {note_path} | Rubric: {rubric_path}")

        try:
            clinical_note = load_file_content(note_path)
            policy_rubric = load_file_content(rubric_path)
        except Exception as e:
            print(f"  [ERROR] Failed to load input files: {e}")
            continue

        start_time = time.time()
        try:
            report: ClinicalGapReport = client.evaluate_audit(
                clinical_note=clinical_note,
                policy_rubric=policy_rubric,
                rubric_id=case.get("rubric_id"),
            )
            elapsed = time.time() - start_time
            print(f"  Audit generated in {elapsed:.2f}s")
        except Exception as e:
            print(f"  [ERROR] LLM evaluation failed: {e}")
            continue

        case_eval_records = []
        case_matches = 0

        print("\n  " + "-" * 76)
        print(f"  {'Criterion':<32} | {'Expected':<8} | {'Actual':<8} | {'Status'}")
        print("  " + "-" * 76)

        for expected in expected_evals:
            total_criteria += 1
            crit_name = expected.get("criterion", "")
            exp_status = expected.get("expected_status", "").lower()
            exp_evidence = expected.get("expected_evidence")

            actual_ev = match_criterion(crit_name, report.evaluations)
            actual_status = actual_ev.status.value.lower() if actual_ev else "missing_from_report"
            actual_evidence = actual_ev.evidence if actual_ev else None
            actual_explanation = actual_ev.explanation if actual_ev else ""
            actual_clarification = actual_ev.suggested_clarification if actual_ev else None

            is_status_match = (actual_status == exp_status)
            if is_status_match:
                matched_criteria += 1
                case_matches += 1
                status_icon = "MATCH [PASS]"
            else:
                status_icon = f"MISMATCH [FAIL] (Exp: {exp_status})"

            print(f"  {crit_name[:32]:<32} | {exp_status:<8} | {actual_status:<8} | {status_icon}")

            case_eval_records.append({
                "criterion": crit_name,
                "expected_status": exp_status,
                "actual_status": actual_status,
                "status_match": is_status_match,
                "expected_evidence": exp_evidence,
                "actual_evidence": actual_evidence,
                "explanation": actual_explanation,
                "suggested_clarification": actual_clarification,
            })

        print("  " + "-" * 76)
        case_acc = (case_matches / len(expected_evals) * 100) if expected_evals else 0
        print(f"  Case Accuracy: {case_matches}/{len(expected_evals)} ({case_acc:.1f}%)\n")

        results_data.append({
            "case_id": case_id,
            "description": desc,
            "note_file": note_path,
            "rubric_file": rubric_path,
            "rubric_id": report.rubric_id,
            "case_accuracy_percent": round(case_acc, 2),
            "evaluations_comparison": case_eval_records,
            "missing_or_unclear_summary": report.missing_or_unclear_summary,
        })

        if idx < len(cases) and args.delay > 0:
            time.sleep(args.delay)

    # Save detailed JSON results
    output_path = PROJECT_ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "provider": provider,
                "model": model,
                "total_criteria": total_criteria,
                "matched_criteria": matched_criteria,
                "overall_accuracy_percent": round((matched_criteria / total_criteria * 100), 2) if total_criteria else 0,
                "cases": results_data,
            },
            f,
            indent=2,
        )

    # Print Final Summary
    overall_acc = (matched_criteria / total_criteria * 100) if total_criteria else 0
    print("=" * 80)
    print(" EVALUATION BENCHMARK SUMMARY")
    print(f" Total Criteria Evaluated : {total_criteria}")
    print(f" Criteria Matches         : {matched_criteria}")
    print(f" Criteria Mismatches      : {total_criteria - matched_criteria}")
    print(f" Overall Agreement Rate   : {overall_acc:.1f}%")
    print(f" Detailed results saved to: {args.output}")
    print("=" * 80)


if __name__ == "__main__":
    run_eval()
