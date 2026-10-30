import json
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

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
    ClinicalGapReport,
    CriterionEvaluation,
    CriterionStatus,
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
    ) -> ClinicalGapReport:
        """Evaluate a clinical note against a policy rubric and return a ClinicalGapReport."""
        pass


class OpenAIAuditClient(BaseLLMClient):
    """OpenAI / OpenAI-compatible client using native Pydantic structured outputs."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        from openai import OpenAI

        effective_key = api_key or settings.get_effective_api_key()
        if not effective_key and not base_url:
            raise ValueError(
                "OpenAI API Key is required. Please set OPENAI_API_KEY or LLM_API_KEY in your .env file."
            )

        self.client = OpenAI(
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
    ) -> ClinicalGapReport:
        user_prompt = create_audit_user_prompt(clinical_note, policy_rubric)
        retry_cfg = retry_config or RetryConfig()

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
    ) -> ClinicalGapReport:
        from google.genai import types

        user_prompt = create_audit_user_prompt(clinical_note, policy_rubric)
        retry_cfg = retry_config or RetryConfig()

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
                        temperature=0.0,
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


class MockAuditClient(BaseLLMClient):
    """Mock client for offline development, local unit testing, and sandbox verification."""

    def evaluate_audit(
        self,
        clinical_note: str,
        policy_rubric: str,
        rubric_id: Optional[str] = None,
        retry_config: Optional[RetryConfig] = None,
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
