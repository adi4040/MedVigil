import json
import logging
from typing import Any, Dict, List, Optional

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.prompts import STAGE2_SYSTEM_PROMPT, create_renal_agent_user_prompt
from app.schemas.renal import RenalAuditReport
from app.services.agent.tools import execute_tool_call, get_gemini_renal_tools

logger = logging.getLogger(__name__)


class RenalAgentRunner:
    """Autonomous Stage 2 Gemini tool-calling loop for renal dosing verification."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        client: Optional[Any] = None,
        max_iterations: int = 8,
    ):
        if client is not None:
            self.client = client
        else:
            from google import genai

            effective_key = api_key or settings.GEMINI_API_KEY or settings.LLM_API_KEY
            if not effective_key:
                raise ValueError(
                    "Gemini API Key is required. Please set GEMINI_API_KEY or LLM_API_KEY."
                )
            self.client = genai.Client(api_key=effective_key)

        self.model = model or settings.LLM_MODEL or "gemini-3.5-flash"
        self.max_iterations = max_iterations

    async def run(
        self,
        discharge_json: str,
        session: Optional[AsyncSession] = None,
        patient_id_hint: str = "unknown",
        medication_hint: str = "unknown",
    ) -> RenalAuditReport:
        """Execute the Stage 2 autonomous tool-calling loop and return a validated RenalAuditReport."""
        from google.genai import types

        user_prompt = create_renal_agent_user_prompt(discharge_json)
        tools = get_gemini_renal_tools()
        tool_trace: List[str] = []

        verified_patient_id: Optional[str] = None
        try:
            payload = json.loads(discharge_json)
            if isinstance(payload, dict):
                raw_pid = payload.get("patient_id")
                if isinstance(raw_pid, str) and raw_pid.strip():
                    verified_patient_id = raw_pid.strip()
        except json.JSONDecodeError:
            pass

        metric_result: Optional[Dict[str, Any]] = None
        lab_result: Optional[Dict[str, Any]] = None
        crcl_result: Optional[Dict[str, Any]] = None

        contents: List[Any] = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_prompt)],
            )
        ]

        for iteration in range(1, self.max_iterations + 1):
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=STAGE2_SYSTEM_PROMPT,
                    temperature=0.0,
                    tools=tools,
                ),
            )

            function_calls = getattr(response, "function_calls", None) or []
            if function_calls:
                # Preserve the model's function-call turn in conversation history
                if getattr(response, "candidates", None):
                    contents.append(response.candidates[0].content)

                response_parts: List[Any] = []
                for fc in function_calls:
                    fc_name = fc.name
                    fc_args = dict(fc.args or {})
                    if verified_patient_id and fc_name in ("fetch_patient_crcl", "calculate_crcl"):
                        fc_args["patient_id"] = verified_patient_id
                    if fc_name == "calculate_crcl":
                        fc_args.pop("serum_creatinine_mg_dl", None)

                    tool_trace.append(f"{fc_name}({fc_args})")
                    logger.info(
                        "[RenalAgentRunner] Iter %d executing %s(%s)",
                        iteration,
                        fc_name,
                        fc_args,
                    )

                    result = await execute_tool_call(
                        name=fc_name,
                        args=fc_args,
                        session=session,
                        forced_patient_id=verified_patient_id,
                    )
                    if fc_name == "get_renal_metric":
                        metric_result = result
                    elif fc_name == "fetch_patient_crcl":
                        lab_result = result
                    elif fc_name == "calculate_crcl":
                        crcl_result = result

                    response_parts.append(
                        types.Part.from_function_response(
                            name=fc_name,
                            response=result,
                        )
                    )

                contents.append(types.Content(role="user", parts=response_parts))
                continue

            # No further tool calls: parse or finalize into RenalAuditReport
            raw_text = (getattr(response, "text", None) or "").strip()
            if raw_text:
                try:
                    report = RenalAuditReport.model_validate_json(raw_text)
                    report.tool_trace = tool_trace
                    return _enforce_tool_evidence(report, metric_result, lab_result, crcl_result)
                except ValidationError:
                    pass

            # Finalize with a single structured-output pass (no tools) to guarantee schema compliance
            if getattr(response, "candidates", None):
                contents.append(response.candidates[0].content)
            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(
                            text=(
                                "Return your final determination strictly as a JSON object "
                                "matching the RenalAuditReport schema."
                            )
                        )
                    ],
                )
            )
            structured_resp = await self.client.aio.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=STAGE2_SYSTEM_PROMPT,
                    temperature=0.0,
                    response_mime_type="application/json",
                    response_schema=RenalAuditReport,
                ),
            )
            structured_text = (getattr(structured_resp, "text", None) or "").strip()
            report = RenalAuditReport.model_validate_json(structured_text)
            report.tool_trace = tool_trace
            return _enforce_tool_evidence(report, metric_result, lab_result, crcl_result)

        logger.warning(
            "[RenalAgentRunner] Reached max_iterations (%d) without final verdict.",
            self.max_iterations,
        )
        return RenalAuditReport(
            patient_id=patient_id_hint,
            medication_name=medication_hint,
            verdict="insufficient_data",
            rationale=(
                f"Agent execution halted after reaching the maximum iteration limit "
                f"({self.max_iterations}) without a completed determination."
            ),
            tool_trace=tool_trace,
        )


def _has_verified_tool_evidence(
    metric_result: Optional[Dict[str, Any]],
    lab_result: Optional[Dict[str, Any]],
    crcl_result: Optional[Dict[str, Any]],
) -> bool:
    """Verify that required DB tools executed and produced valid renal evidence."""
    if not metric_result or metric_result.get("status") != "success":
        return False

    required_metric = metric_result.get("required_renal_metric")
    if required_metric not in ("crcl", "egfr"):
        return False

    if not lab_result or lab_result.get("status") == "error":
        return False

    if required_metric == "egfr":
        return lab_result.get("latest_egfr_ml_min_1_73m2") is not None

    # required_metric == "crcl"
    if lab_result.get("crcl_found") is True:
        return True

    return bool(crcl_result and crcl_result.get("status") == "success")


def _enforce_tool_evidence(
    report: RenalAuditReport,
    metric_result: Optional[Dict[str, Any]],
    lab_result: Optional[Dict[str, Any]],
    crcl_result: Optional[Dict[str, Any]],
) -> RenalAuditReport:
    """Force verdict to 'insufficient_data' if required DB tools were skipped or lacked evidence."""
    if report.verdict == "insufficient_data":
        return report

    if not _has_verified_tool_evidence(metric_result, lab_result, crcl_result):
        logger.warning(
            "[RenalAgentRunner] Overriding verdict '%s' to 'insufficient_data' due to missing tool evidence.",
            report.verdict,
        )
        report.verdict = "insufficient_data"
        report.rationale = (
            f"{report.rationale} [System Guardrail: Required database tool verification "
            f"was incomplete or skipped; verdict forced to 'insufficient_data'.]"
        )

    return report
