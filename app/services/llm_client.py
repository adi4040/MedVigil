import asyncio
import json
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import HTTPException, status
from pydantic import ValidationError

from app.core.config import settings
from app.core.prompts import SYSTEM_PROMPT, create_audit_user_prompt
from app.core.retry import (
    AuditEvaluationExhaustedError,
    RetryConfig,
    calculate_backoff,
    format_validation_feedback,
    is_transient_error,
)
from app.schemas.audit import (
    AuditStreamAccumulator,
    ClinicalGapReport,
    CriterionEvaluation,
    CriterionStatus,
    StreamChunk,
    StreamEventType,
)

logger = logging.getLogger(__name__)


class BaseLLMClient(ABC):
    """Abstract base class for LLM audit evaluation clients."""

    @abstractmethod
    def evaluate_audit(
        self,
        clinical_note: str,
        policy_rubric: str,
        rubric_id: Optional[str] = None,
        retry_config: Optional[RetryConfig] = None,
        temperature: Optional[float] = None,
    ) -> ClinicalGapReport:
        """Evaluate a clinical note against a policy rubric and return a ClinicalGapReport."""
        pass

    @abstractmethod
    async def stream_audit(
        self,
        clinical_note: str,
        policy_rubric: str,
        rubric_id: Optional[str] = None,
        retry_config: Optional[RetryConfig] = None,
        temperature: Optional[float] = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream audit evaluation tokens as StreamChunk objects, concluding with a validated report."""
        pass


class OpenAIAuditClient(BaseLLMClient):
    """OpenAI / OpenAI-compatible client using native Pydantic structured outputs."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        from openai import AsyncOpenAI, OpenAI

        effective_key = api_key or settings.get_effective_api_key()
        if not effective_key and not base_url:
            raise ValueError(
                "OpenAI API Key is required. Please set OPENAI_API_KEY or LLM_API_KEY in your .env file."
            )

        self.client = OpenAI(
            api_key=effective_key or "dummy-key-for-local",
            base_url=base_url or settings.LLM_BASE_URL,
        )
        self.async_client = AsyncOpenAI(
            api_key=effective_key or "dummy-key-for-local",
            base_url=base_url or settings.LLM_BASE_URL,
        )
        self.model = model or settings.LLM_MODEL or "gpt-4o"

    def evaluate_audit(
        self,
        clinical_note: str,
        policy_rubric: str,
        rubric_id: Optional[str] = None,
        retry_config: Optional[RetryConfig] = None,
        temperature: Optional[float] = None,
    ) -> ClinicalGapReport:
        user_prompt = create_audit_user_prompt(clinical_note, policy_rubric)
        retry_cfg = retry_config or RetryConfig()
        temp = 0.0 if temperature is None else temperature

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        last_error: Optional[Exception] = None

        for attempt in range(retry_cfg.max_retries + 1):
            try:
                completion = self.client.beta.chat.completions.parse(
                    model=self.model,
                    messages=messages,
                    response_format=ClinicalGapReport,
                    temperature=temp,
                )

                choice = completion.choices[0]
                if choice.message.refusal:
                    raise RuntimeError(f"Model refused request: {choice.message.refusal}")

                report = choice.message.parsed
                if report is None:
                    raw_content = choice.message.content or ""
                    report = ClinicalGapReport.model_validate_json(raw_content)

                if rubric_id and report.rubric_id != rubric_id:
                    report.rubric_id = rubric_id
                return report

            except (ValidationError, json.JSONDecodeError) as val_err:
                last_error = val_err
                logger.warning(
                    f"[OpenAIAuditClient] Validation failure on attempt {attempt + 1}/{retry_cfg.max_retries + 1}: {val_err}"
                )
                if attempt < retry_cfg.max_retries:
                    delay = calculate_backoff(attempt, retry_cfg)
                    logger.info(f"Applying backoff delay of {delay}s before self-correction attempt...")
                    time.sleep(delay)

                    raw_output = ""
                    if "completion" in locals() and completion and completion.choices:
                        raw_output = completion.choices[0].message.content or ""

                    errors_list = (
                        val_err.errors()
                        if isinstance(val_err, ValidationError)
                        else [{"loc": ["json"], "msg": str(val_err)}]
                    )
                    feedback = format_validation_feedback(errors_list, raw_output)

                    messages.append({"role": "assistant", "content": raw_output})
                    messages.append({"role": "user", "content": feedback})
                else:
                    raise AuditEvaluationExhaustedError(
                        f"Failed to produce a valid ClinicalGapReport after {retry_cfg.max_retries + 1} attempts. Last validation error: {val_err}"
                    ) from val_err

            except Exception as exc:
                last_error = exc
                if is_transient_error(exc) and attempt < retry_cfg.max_retries:
                    delay = calculate_backoff(attempt, retry_cfg)
                    logger.warning(
                        f"[OpenAIAuditClient] Transient failure on attempt {attempt + 1}/{retry_cfg.max_retries + 1}: {exc}. Backing off for {delay}s..."
                    )
                    time.sleep(delay)
                    continue
                elif is_transient_error(exc):
                    raise AuditEvaluationExhaustedError(
                        f"Exhausted {retry_cfg.max_retries + 1} attempts due to transient errors. Last error: {exc}"
                    ) from exc
                else:
                    raise

        raise AuditEvaluationExhaustedError(
            f"Evaluation attempts exhausted without response. Last error: {last_error}"
        )

    async def stream_audit(
        self,
        clinical_note: str,
        policy_rubric: str,
        rubric_id: Optional[str] = None,
        retry_config: Optional[RetryConfig] = None,
        temperature: Optional[float] = None,
    ) -> AsyncIterator[StreamChunk]:
        user_prompt = create_audit_user_prompt(clinical_note, policy_rubric)
        retry_cfg = retry_config or RetryConfig()
        temp = 0.0 if temperature is None else temperature

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        accumulated_text: List[str] = []
        first_chunk_received = False
        last_error: Optional[Exception] = None

        for attempt in range(retry_cfg.max_retries + 1):
            try:
                async with self.async_client.beta.chat.completions.stream(
                    model=self.model,
                    messages=messages,
                    response_format=ClinicalGapReport,
                    temperature=temp,
                ) as stream:
                    async for event in stream:
                        if event.type == "content.delta" and event.delta:
                            first_chunk_received = True
                            accumulated_text.append(event.delta)
                            yield StreamChunk.token_chunk(text=event.delta)

                    final_completion = await stream.get_final_completion()
                    report = None
                    if (
                        final_completion.choices
                        and final_completion.choices[0].message.parsed
                    ):
                        report = final_completion.choices[0].message.parsed
                    else:
                        full_text = "".join(accumulated_text)
                        report = ClinicalGapReport.model_validate_json(full_text)

                    if rubric_id and report.rubric_id != rubric_id:
                        report.rubric_id = rubric_id
                    yield StreamChunk.done_chunk(report=report, retries=attempt)
                    return

            except Exception as exc:
                last_error = exc
                if (
                    not first_chunk_received
                    and is_transient_error(exc)
                    and attempt < retry_cfg.max_retries
                ):
                    delay = calculate_backoff(attempt, retry_cfg)
                    logger.warning(
                        f"[OpenAIAuditClient] Transient error before stream start on attempt {attempt + 1}: {exc}. Retrying in {delay}s..."
                    )
                    yield StreamChunk.status_chunk(
                        message=f"Transient provider error ({exc}). Retrying in {delay}s (attempt {attempt + 1}/{retry_cfg.max_retries})...",
                        retries=attempt + 1,
                    )
                    await asyncio.sleep(delay)
                    continue
                elif not first_chunk_received and is_transient_error(exc):
                    raise AuditEvaluationExhaustedError(
                        f"Exhausted {retry_cfg.max_retries + 1} stream attempts due to transient errors. Last error: {exc}"
                    ) from exc
                else:
                    logger.error(
                        f"[OpenAIAuditClient] Stream failed: {exc}", exc_info=True
                    )
                    yield StreamChunk.error_chunk(error=str(exc))
                    return

        raise AuditEvaluationExhaustedError(
            f"Evaluation stream attempts exhausted without response. Last error: {last_error}"
        )


class GeminiAuditClient(BaseLLMClient):
    """Google Gemini client using native JSON Schema enforcement and retry feedback loop."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        from google import genai

        effective_key = api_key or settings.get_effective_api_key()
        if not effective_key:
            raise ValueError(
                "Gemini API Key is required. Please set GEMINI_API_KEY or LLM_API_KEY in your .env file."
            )

        self.client = genai.Client(api_key=effective_key)
        self.model = model or settings.LLM_MODEL or "gemini-3.5-flash"

    def evaluate_audit(
        self,
        clinical_note: str,
        policy_rubric: str,
        rubric_id: Optional[str] = None,
        retry_config: Optional[RetryConfig] = None,
        temperature: Optional[float] = None,
    ) -> ClinicalGapReport:
        from google.genai import types

        user_prompt = create_audit_user_prompt(clinical_note, policy_rubric)
        retry_cfg = retry_config or RetryConfig()
        temp = 0.0 if temperature is None else temperature

        contents: List[Any] = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_prompt)],
            )
        ]

        last_error: Optional[Exception] = None

        for attempt in range(retry_cfg.max_retries + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        temperature=temp,
                        response_mime_type="application/json",
                        response_schema=ClinicalGapReport,
                    ),
                )

                if not response.text:
                    raise RuntimeError("Gemini returned an empty response.")

                report = ClinicalGapReport.model_validate_json(response.text)
                if rubric_id and report.rubric_id != rubric_id:
                    report.rubric_id = rubric_id
                return report

            except (ValidationError, json.JSONDecodeError) as val_err:
                last_error = val_err
                logger.warning(
                    f"[GeminiAuditClient] Validation failure on attempt {attempt + 1}/{retry_cfg.max_retries + 1}: {val_err}"
                )
                if attempt < retry_cfg.max_retries:
                    delay = calculate_backoff(attempt, retry_cfg)
                    logger.info(f"Applying backoff delay of {delay}s before self-correction attempt...")
                    time.sleep(delay)

                    raw_output = response.text if "response" in locals() and response and response.text else "{}"
                    errors_list = (
                        val_err.errors()
                        if isinstance(val_err, ValidationError)
                        else [{"loc": ["json"], "msg": str(val_err)}]
                    )
                    feedback = format_validation_feedback(errors_list, raw_output)

                    contents.append(
                        types.Content(
                            role="model",
                            parts=[types.Part.from_text(text=raw_output)],
                        )
                    )
                    contents.append(
                        types.Content(
                            role="user",
                            parts=[types.Part.from_text(text=feedback)],
                        )
                    )
                else:
                    raise AuditEvaluationExhaustedError(
                        f"Failed to produce a valid ClinicalGapReport after {retry_cfg.max_retries + 1} attempts. Last validation error: {val_err}"
                    ) from val_err

            except Exception as exc:
                last_error = exc
                if is_transient_error(exc) and attempt < retry_cfg.max_retries:
                    delay = calculate_backoff(attempt, retry_cfg)
                    logger.warning(
                        f"[GeminiAuditClient] Transient failure on attempt {attempt + 1}/{retry_cfg.max_retries + 1}: {exc}. Backing off for {delay}s..."
                    )
                    time.sleep(delay)
                    continue
                elif is_transient_error(exc):
                    raise AuditEvaluationExhaustedError(
                        f"Exhausted {retry_cfg.max_retries + 1} attempts due to transient errors. Last error: {exc}"
                    ) from exc
                else:
                    raise

        raise AuditEvaluationExhaustedError(
            f"Evaluation attempts exhausted without response. Last error: {last_error}"
        )

    async def stream_audit(
        self,
        clinical_note: str,
        policy_rubric: str,
        rubric_id: Optional[str] = None,
        retry_config: Optional[RetryConfig] = None,
        temperature: Optional[float] = None,
    ) -> AsyncIterator[StreamChunk]:
        from google.genai import types

        user_prompt = create_audit_user_prompt(clinical_note, policy_rubric)
        retry_cfg = retry_config or RetryConfig()
        temp = 0.0 if temperature is None else temperature

        contents: List[Any] = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_prompt)],
            )
        ]

        accumulated_text: List[str] = []
        first_chunk_received = False
        last_error: Optional[Exception] = None

        for attempt in range(retry_cfg.max_retries + 1):
            try:
                response_stream = await self.client.aio.models.generate_content_stream(
                    model=self.model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        temperature=temp,
                        response_mime_type="application/json",
                        response_schema=ClinicalGapReport,
                    ),
                )

                async for chunk in response_stream:
                    if chunk.text:
                        first_chunk_received = True
                        accumulated_text.append(chunk.text)
                        yield StreamChunk.token_chunk(text=chunk.text)

                full_text = "".join(accumulated_text)
                if not full_text.strip():
                    raise RuntimeError("Gemini returned an empty response stream.")

                report = ClinicalGapReport.model_validate_json(full_text)
                if rubric_id and report.rubric_id != rubric_id:
                    report.rubric_id = rubric_id
                yield StreamChunk.done_chunk(report=report, retries=attempt)
                return

            except Exception as exc:
                last_error = exc
                if (
                    not first_chunk_received
                    and is_transient_error(exc)
                    and attempt < retry_cfg.max_retries
                ):
                    delay = calculate_backoff(attempt, retry_cfg)
                    logger.warning(
                        f"[GeminiAuditClient] Transient error before stream start on attempt {attempt + 1}: {exc}. Retrying in {delay}s..."
                    )
                    yield StreamChunk.status_chunk(
                        message=f"Transient provider error ({exc}). Retrying in {delay}s (attempt {attempt + 1}/{retry_cfg.max_retries})...",
                        retries=attempt + 1,
                    )
                    await asyncio.sleep(delay)
                    continue
                elif not first_chunk_received and is_transient_error(exc):
                    raise AuditEvaluationExhaustedError(
                        f"Exhausted {retry_cfg.max_retries + 1} stream attempts due to transient errors. Last error: {exc}"
                    ) from exc
                else:
                    logger.error(
                        f"[GeminiAuditClient] Stream failed: {exc}", exc_info=True
                    )
                    yield StreamChunk.error_chunk(error=str(exc))
                    return

        raise AuditEvaluationExhaustedError(
            f"Evaluation stream attempts exhausted without response. Last error: {last_error}"
        )


class MockAuditClient(BaseLLMClient):
    """Mock client for offline development, local unit testing, and sandbox verification."""

    def __init__(self, chunk_delay: float = 0.0, chunk_size: int = 20):
        self.chunk_delay = chunk_delay
        self.chunk_size = chunk_size

    def evaluate_audit(
        self,
        clinical_note: str,
        policy_rubric: str,
        rubric_id: Optional[str] = None,
        retry_config: Optional[RetryConfig] = None,
        temperature: Optional[float] = None,
    ) -> ClinicalGapReport:
        # Extract rubric ID from text if present
        detected_rubric_id = rubric_id or "RUBRIC_DEFAULT"
        match = re.search(r"RUBRIC ID:\s*(\S+)", policy_rubric, re.IGNORECASE)
        if match:
            detected_rubric_id = match.group(1)

        evaluations = [
            CriterionEvaluation(
                criterion="Symptoms and Duration",
                status=(
                    CriterionStatus.MET
                    if "pain" in clinical_note.lower()
                    else CriterionStatus.MISSING
                ),
                evidence=(
                    "lower-back pain for eight weeks"
                    if "pain" in clinical_note.lower()
                    else None
                ),
                explanation=(
                    "Patient documented lower-back pain duration in encounter note."
                    if "pain" in clinical_note.lower()
                    else "No duration found."
                ),
                suggested_clarification=(
                    None
                    if "pain" in clinical_note.lower()
                    else "Document exact symptom duration."
                ),
            ),
            CriterionEvaluation(
                criterion="Physical Examination Findings",
                status=CriterionStatus.UNCLEAR,
                evidence=(
                    "Detailed neurological examination findings are not included."
                    if "examination" in clinical_note.lower()
                    else None
                ),
                explanation="Physical exam mentioned but objective clinical findings are omitted.",
                suggested_clarification="Provide objective physical examination findings including motor and sensory testing.",
            ),
            CriterionEvaluation(
                criterion="Previous Diagnostic Testing",
                status=CriterionStatus.MISSING,
                evidence=None,
                explanation="No prior lumbar spine plain-film radiograph (X-ray) results documented.",
                suggested_clarification="Document results of prior plain-film lumbar X-ray or document clinical contraindication.",
            ),
        ]

        missing_summary = [
            ev.suggested_clarification
            for ev in evaluations
            if ev.suggested_clarification is not None
        ]

        return ClinicalGapReport(
            rubric_id=detected_rubric_id,
            evaluations=evaluations,
            missing_or_unclear_summary=missing_summary,
        )

    async def stream_audit(
        self,
        clinical_note: str,
        policy_rubric: str,
        rubric_id: Optional[str] = None,
        retry_config: Optional[RetryConfig] = None,
        temperature: Optional[float] = None,
    ) -> AsyncIterator[StreamChunk]:
        report = self.evaluate_audit(clinical_note, policy_rubric, rubric_id, retry_config, temperature)
        raw_json = report.model_dump_json(indent=2)

        chunk_size = self.chunk_size or 20
        for i in range(0, len(raw_json), chunk_size):
            chunk = raw_json[i : i + chunk_size]
            yield StreamChunk.token_chunk(text=chunk)
            if self.chunk_delay > 0:
                await asyncio.sleep(self.chunk_delay)

        yield StreamChunk.done_chunk(report=report, retries=0)


def get_llm_client(provider: Optional[str] = None) -> BaseLLMClient:
    """Factory to retrieve the configured LLM client instance."""
    active_provider = (provider or settings.LLM_PROVIDER or "gemini").strip().lower()

    # Smart fallback: if GEMINI key is present, default to gemini
    if (
        settings.GEMINI_API_KEY
        and not settings.OPENAI_API_KEY
        and active_provider == "openai"
    ):
        active_provider = "gemini"

    try:
        if active_provider in ("openai", "ollama", "azure", "vllm", "groq"):
            return OpenAIAuditClient()
        elif active_provider in ("gemini", "google"):
            return GeminiAuditClient()
        elif active_provider == "mock":
            return MockAuditClient()
        else:
            raise ValueError(
                f"Unsupported LLM provider: '{active_provider}'. Supported options: 'openai', 'gemini', 'mock'."
            )
    except ValueError as e:
        if "API Key is required" in str(e):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(e),
            )
        raise
