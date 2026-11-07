#!/usr/bin/env python3
"""CLI Verification Script for Stage 1 Token Streaming.

Streams tokens from the LLM (or mock) to the console in real-time,
measuring Time-To-First-Token (TTFT), streaming duration, and report validation.
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
API_ROOT = PROJECT_ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.core.config import settings
from app.schemas.audit import AuditStreamAccumulator, StreamEventType
from app.services.llm_client import MockAuditClient, get_llm_client


def parse_args():
    parser = argparse.ArgumentParser(
        description="Stream LLM audit tokens to backend console (Stage 1)"
    )
    parser.add_argument(
        "--provider",
        type=str,
        default=None,
        help="LLM provider ('mock', 'gemini', 'openai'). Defaults to settings.LLM_PROVIDER.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model override (e.g., 'gemini-3.5-flash', 'gpt-4o').",
    )
    parser.add_argument(
        "--note",
        type=str,
        default="clinical_notes/note_001.txt",
        help="Path to clinical note file.",
    )
    parser.add_argument(
        "--rubric",
        type=str,
        default="policy_rubrics/mri_lumbar_spine.txt",
        help="Path to policy rubric file.",
    )
    parser.add_argument(
        "--chunk-delay",
        type=float,
        default=0.015,
        help="Delay in seconds between tokens for mock client (default: 0.015s).",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="LLM sampling temperature (default: 0.0).",
    )
    return parser.parse_args()


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

    provider = (args.provider or settings.LLM_PROVIDER or "mock").strip().lower()

    if provider == "mock":
        client = MockAuditClient(chunk_delay=args.chunk_delay, chunk_size=16)
    else:
        client = get_llm_client(provider)
        if args.model and hasattr(client, "model"):
            client.model = args.model

    model_name = getattr(client, "model", "mock-generator")

    print("=" * 80)
    print(f" MedV Clinical Audit System - Stage 1 Token Streaming Test")
    print(f" Provider: {provider} | Model: {model_name}")
    print(f" Note: {args.note} | Rubric: {args.rubric}")
    print("=" * 80)
    print("\n--- STREAMING OUTPUT START ---\n")

    start_time = time.time()
    ttft: float | None = None
    token_count = 0
    total_chars = 0

    accumulator = AuditStreamAccumulator()

    async for chunk in client.stream_audit(clinical_note, policy_rubric, temperature=args.temperature):
        if chunk.event == StreamEventType.TOKEN and chunk.text:
            if ttft is None:
                ttft = time.time() - start_time
            token_count += 1
            total_chars += len(chunk.text)
            accumulator.tokens.append(chunk.text)
            # Print token delta directly to stdout
            sys.stdout.write(chunk.text)
            sys.stdout.flush()
        elif chunk.event == StreamEventType.DONE and chunk.report:
            accumulator.final_report = chunk.report
        elif chunk.event == StreamEventType.ERROR and chunk.error:
            accumulator.error = chunk.error
            print(f"\n[STREAM ERROR]: {chunk.error}")

    total_time = time.time() - start_time
    print("\n\n--- STREAMING OUTPUT END ---")
    print("=" * 80)
    print(f" STREAM PERFORMANCE METRICS:")
    print(f" Time-To-First-Token (TTFT) : {ttft:.3f}s" if ttft else " TTFT: N/A")
    print(f" Total Streaming Duration   : {total_time:.3f}s")
    print(f" Total Stream Chunks        : {token_count}")
    print(f" Total Characters Streamed  : {total_chars}")

    if accumulator.final_report:
        report = accumulator.final_report
        print(f" Report Validated           : YES (rubric_id: {report.rubric_id})")
        print(f" Criteria Evaluated         : {len(report.evaluations)}")
        for ev in report.evaluations:
            print(f"   - {ev.criterion}: {ev.status.value.upper()}")
        print(f" Missing/Unclear Gaps       : {len(report.missing_or_unclear_summary)}")
    elif accumulator.error:
        print(f" Validation Failed          : Error: {accumulator.error}")
    else:
        print(" Validation Failed          : Incomplete stream without report")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
