import json
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


RenalSafetyVerdict = Literal["safe", "dose_adjustment_required", "insufficient_data"]


class RenalAuditRequest(BaseModel):
    """Request payload for Stage 2 renal dosing safety evaluation."""

    discharge_json: str = Field(
        ...,
        min_length=2,
        description="JSON string containing patient_id, prescribed medication, and daily dose.",
    )

    @field_validator("discharge_json")
    @classmethod
    def validate_discharge_json_object(cls, value: str) -> str:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("discharge_json must be valid JSON.") from exc
        if not isinstance(parsed, dict):
            raise ValueError("discharge_json must be a JSON object.")
        return value


class RenalAuditReport(BaseModel):
    """Structured Stage 2 renal dosing safety audit report."""

    patient_id: str = Field(
        ...,
        description="Unique patient identifier from the discharge record.",
    )
    medication_name: str = Field(
        ...,
        description="Prescribed medication name evaluated against renal guidelines.",
    )
    prescribed_daily_dose_mg: Optional[float] = Field(
        default=None,
        description="Prescribed total daily dose in milligrams.",
    )
    required_renal_metric: Optional[Literal["crcl", "egfr"]] = Field(
        default=None,
        description="Required renal biomarker metric for the medication ('crcl' or 'egfr').",
    )
    renal_metric_value: Optional[float] = Field(
        default=None,
        description="Verified patient renal metric value (calculated CrCl or lab eGFR).",
    )
    verdict: RenalSafetyVerdict = Field(
        ...,
        description=(
            "Exact safety determination: 'safe', 'dose_adjustment_required', "
            "or 'insufficient_data'."
        ),
    )
    lab_warning: Optional[str] = Field(
        default=None,
        description="Clinical warning from lab retrieval (e.g., stale labs), if any.",
    )
    rationale: str = Field(
        ...,
        description="Evidence-backed explanation citing tool outputs and guideline brackets.",
    )
    tool_trace: List[str] = Field(
        default_factory=list,
        description="Ordered list of agent tool calls executed during verification.",
    )

    @model_validator(mode="after")
    def forbid_safe_without_renal_evidence(self) -> "RenalAuditReport":
        if self.verdict == "safe" and (
            self.renal_metric_value is None or self.required_renal_metric is None
        ):
            raise ValueError(
                "verdict 'safe' is forbidden when required_renal_metric or renal_metric_value is null."
            )
        return self
