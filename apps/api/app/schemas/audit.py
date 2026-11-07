from enum import Enum
from typing import AsyncIterator, List, Optional
from pydantic import BaseModel, Field, model_validator


class CriterionStatus(str, Enum):
    MET = "met"
    MISSING = "missing"
    UNCLEAR = "unclear"


class CriterionEvaluation(BaseModel):
    criterion: str = Field(
        ..., description="Exact name of the criterion from the supplied rubric."
    )
    evidence: Optional[str] = Field(
        None,
        description=(
            "Verbatim quote from the clinical note addressing this criterion. "
            "Must be extracted first if any relevant documentation exists. "
            "Must be null if status is 'missing'."
        ),
    )
    explanation: str = Field(
        ...,
        description=(
            "Concise analysis of whether the documented quote satisfies the rubric requirement, "
            "only partially addresses it with vague/incomplete details, or completely fails to document it."
        ),
    )
    status: CriterionStatus = Field(
        ...,
        description=(
            "Evaluation status determined AFTER reviewing evidence and explanation: "
            "'met' if fully satisfied; "
            "'unclear' if mentioned but details, timeframe, or required thresholds are vague, incomplete, or ambiguous; "
            "'missing' if the required clinical findings/prerequisites are absent or unfulfilled."
        ),
    )
    suggested_clarification: Optional[str] = Field(
        None,
        description=(
            "Specific documentation clarification needed from the treating clinician "
            "if status is 'missing' or 'unclear'. Must be null if status is 'met'."
        ),
    )

    @model_validator(mode="after")
    def validate_and_sanitize_evidence_and_clarification(self):
        # Enforce schema constraints safely
        if self.status == CriterionStatus.MISSING and self.evidence is not None:
            self.evidence = None
        if (
            self.status == CriterionStatus.MET
            and self.suggested_clarification is not None
        ):
            self.suggested_clarification = None
        return self


class ClinicalGapReport(BaseModel):
    rubric_id: str = Field(
        ..., description="Identifier of the rubric used for evaluation."
    )
    evaluations: List[CriterionEvaluation] = Field(
        ..., description="Evaluation results for every criterion in the rubric."
    )
    missing_or_unclear_summary: List[str] = Field(
        ...,
        description="List of actionable documentation gaps requiring clinician clarification.",
    )


class AuditRequest(BaseModel):
    clinical_note: str = Field(
        ...,
        min_length=1,
        max_length=100_000,
        description="Raw text of the clinical encounter note.",
    )
    policy_rubric: str = Field(
        ...,
        min_length=1,
        max_length=50_000,
        description="Raw text or formatted policy rubric.",
    )
    rubric_id: Optional[str] = Field(
        None,
        max_length=200,
        description="Optional override/explicit rubric ID.",
    )
    temperature: Optional[float] = Field(
        0.0,
        ge=0.0,
        le=2.0,
        description="Sampling temperature for the LLM (default: 0.0).",
    )


class StreamEventType(str, Enum):
    STATUS = "status"
    TOKEN = "token"
    DONE = "done"
    ERROR = "error"


class StreamChunk(BaseModel):
    """Structured streaming item emitted during LLM token streaming.

    Designed for clean serialization to Server-Sent Events (SSE) by the API layer.
    """

    event: StreamEventType = Field(
        default=StreamEventType.TOKEN,
        description="Type of stream event: 'status', 'token', 'done', or 'error'.",
    )
    message: Optional[str] = Field(
        None,
        description="Informational status or progress message (present when event='status').",
    )
    text: Optional[str] = Field(
        None,
        description="Text delta/token emitted by the LLM (present when event='token').",
    )
    report: Optional[ClinicalGapReport] = Field(
        None,
        description="Full parsed and validated report (present when event='done').",
    )
    error: Optional[str] = Field(
        None,
        description="Error description if streaming or validation failed (present when event='error').",
    )
    retries: Optional[int] = Field(
        0, description="Number of retries attempted prior to or during the event."
    )
    request_id: Optional[str] = Field(
        None, description="Support identifier associated with an error event."
    )

    @model_validator(mode="after")
    def validate_event_payload(self):
        required_payloads = {
            StreamEventType.STATUS: self.message,
            StreamEventType.TOKEN: self.text,
            StreamEventType.DONE: self.report,
            StreamEventType.ERROR: self.error,
        }
        if required_payloads[self.event] is None:
            raise ValueError(f"A '{self.event.value}' event is missing its payload.")
        return self

    @classmethod
    def status_chunk(cls, message: str, retries: int = 0) -> "StreamChunk":
        return cls(event=StreamEventType.STATUS, message=message, retries=retries)

    @classmethod
    def token_chunk(cls, text: str) -> "StreamChunk":
        return cls(event=StreamEventType.TOKEN, text=text)

    @classmethod
    def done_chunk(cls, report: ClinicalGapReport, retries: int = 0) -> "StreamChunk":
        return cls(event=StreamEventType.DONE, report=report, retries=retries)

    @classmethod
    def error_chunk(cls, error: str, request_id: Optional[str] = None) -> "StreamChunk":
        return cls(event=StreamEventType.ERROR, error=error, request_id=request_id)


class AuditStreamAccumulator:
    """Helper to consume an AsyncIterator[StreamChunk], collecting tokens and the final report."""

    def __init__(self):
        self.tokens: List[str] = []
        self.status_messages: List[str] = []
        self.final_report: Optional[ClinicalGapReport] = None
        self.error: Optional[str] = None
        self.retries: int = 0

    async def consume(
        self, stream: AsyncIterator[StreamChunk]
    ) -> "AuditStreamAccumulator":
        async for chunk in stream:
            if chunk.event == StreamEventType.STATUS and chunk.message:
                self.status_messages.append(chunk.message)
                if chunk.retries:
                    self.retries = max(self.retries, chunk.retries)
            elif chunk.event == StreamEventType.TOKEN and chunk.text:
                self.tokens.append(chunk.text)
            elif chunk.event == StreamEventType.DONE and chunk.report:
                self.final_report = chunk.report
                if chunk.retries:
                    self.retries = max(self.retries, chunk.retries)
            elif chunk.event == StreamEventType.ERROR and chunk.error:
                self.error = chunk.error
        return self

    @property
    def accumulated_text(self) -> str:
        return "".join(self.tokens)
