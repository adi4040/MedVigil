from enum import Enum
from typing import List, Optional
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
        ..., description="Raw text of the clinical encounter note."
    )
    policy_rubric: str = Field(..., description="Raw text or formatted policy rubric.")
    rubric_id: Optional[str] = Field(
        None, description="Optional override/explicit rubric ID."
    )
