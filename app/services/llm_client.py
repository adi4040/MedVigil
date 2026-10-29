import logging
import re
from abc import ABC, abstractmethod
from typing import Optional

from fastapi import HTTPException, status
from app.core.config import settings
from app.core.prompts import SYSTEM_PROMPT, create_audit_user_prompt
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
    ) -> ClinicalGapReport:
        user_prompt = create_audit_user_prompt(clinical_note, policy_rubric)

        completion = self.client.beta.chat.completions.parse(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format=ClinicalGapReport,
        )

        report = completion.choices[0].message.parsed
        if report is None:
            raise RuntimeError(
                f"Failed to parse structured ClinicalGapReport from model: {completion.choices[0].message.refusal}"
            )

        if rubric_id and report.rubric_id != rubric_id:
            report.rubric_id = rubric_id

        return report


class GeminiAuditClient(BaseLLMClient):
    """Google Gemini client using native JSON Schema enforcement."""

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
        self.model = model or settings.LLM_MODEL or "gemini-2.5-flash"

    def evaluate_audit(
        self,
        clinical_note: str,
        policy_rubric: str,
        rubric_id: Optional[str] = None,
    ) -> ClinicalGapReport:
        from google.genai import types

        user_prompt = create_audit_user_prompt(clinical_note, policy_rubric)

        response = self.client.models.generate_content(
            model=self.model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
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


class MockAuditClient(BaseLLMClient):
    """Mock client for offline development, local unit testing, and sandbox verification."""

    def evaluate_audit(
        self,
        clinical_note: str,
        policy_rubric: str,
        rubric_id: Optional[str] = None,
    ) -> ClinicalGapReport:
        # Extract rubric ID from text if present
        detected_rubric_id = rubric_id or "RUBRIC_DEFAULT"
        match = re.search(r"RUBRIC ID:\s*(\S+)", policy_rubric, re.IGNORECASE)
        if match:
            detected_rubric_id = match.group(1)

        evaluations = [
            CriterionEvaluation(
                criterion="Symptoms and Duration",
                status=CriterionStatus.MET if "pain" in clinical_note.lower() else CriterionStatus.MISSING,
                evidence="lower-back pain for eight weeks" if "pain" in clinical_note.lower() else None,
                explanation="Patient documented lower-back pain duration in encounter note." if "pain" in clinical_note.lower() else "No duration found.",
                suggested_clarification=None if "pain" in clinical_note.lower() else "Document exact symptom duration.",
            ),
            CriterionEvaluation(
                criterion="Physical Examination Findings",
                status=CriterionStatus.UNCLEAR,
                evidence="Detailed neurological examination findings are not included." if "examination" in clinical_note.lower() else None,
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
    if settings.GEMINI_API_KEY and not settings.OPENAI_API_KEY and active_provider == "openai":
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

