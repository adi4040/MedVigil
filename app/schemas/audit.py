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
    status: CriterionStatus = Field(
        ...,
        description="Whether the criterion is met, missing, or unclear based strictly on the note.",
    )
    evidence: Optional[str] = Field(
        None,
        description="Verbatim quote from the clinical note supporting the status. Must be null if status is 'missing'.",
    )
    explanation: str = Field(
        ...,
        description="Concise explanation of why the documented evidence meets, fails to meet, or only partially addresses the criterion.",
    )
    suggested_clarification: Optional[str] = Field(
        None,
        description="Specific documentation clarification needed from the treating clinician if status is 'missing' or 'unclear'. Null if 'met'.",
    )

    @model_validator(mode="after")
    def validate_evidence_and_clarification(self):
        if self.status == CriterionStatus.MISSING and self.evidence is not None:
            raise ValueError("Evidence must be null when status is 'missing'.")
        if (
            self.status == CriterionStatus.MET
            and self.suggested_clarification is not None
        ):
            raise ValueError(
                "Suggested clarification must be null when status is 'met'."
            )
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
