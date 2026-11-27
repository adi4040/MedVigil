import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.prompts import STAGE2_SYSTEM_PROMPT, create_renal_agent_user_prompt
from app.core.retry import (
    AuditEvaluationExhaustedError,
    RetryConfig,
    calculate_backoff,
    is_transient_error,
)
from app.schemas.renal import RenalAuditReport
from app.services.agent.tools import execute_tool_call, get_gemini_renal_tools

logger = logging.getLogger(__name__)

_DEFAULT_STAGE2_RETRY_CONFIG = RetryConfig(
    max_retries=4,
    base_delay=2.0,
    max_delay=32.0,
    jitter=True,
)
_RETRY_HINT_RE = re.compile(
    r"retry\s+(?:in|delay['\"]?\s*:\s*['\"]?)\s*(\d+(?:\.\d+)?)s",
    re.IGNORECASE,
)


class RenalAgentRunner:
    """Autonomous Stage 2 Gemini tool-calling loop for renal dosing verification."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        client: Optional[Any] = None,
        max_iterations: int = 8,
        temperature: float = 0.0,
        retry_config: Optional[RetryConfig] = None,
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
        self.temperature = temperature
        self.retry_config = retry_config or _DEFAULT_STAGE2_RETRY_CONFIG

    async def _generate_with_retry(
        self,
        *,
        contents: List[Any],
        config: Any,
        retry_cfg: RetryConfig,
    ) -> Any:
        """Call Gemini generate_content with exponential backoff on transient errors."""
        last_error: Optional[Exception] = None

        for attempt in range(retry_cfg.max_retries + 1):
            try:
                return await self.client.aio.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=config,
                )
            except Exception as exc:
                last_error = exc
                if not is_transient_error(exc) or attempt >= retry_cfg.max_retries:
                    if is_transient_error(exc):
                        raise AuditEvaluationExhaustedError(
                            f"Stage 2 LLM call failed after {retry_cfg.max_retries + 1} attempts: {exc}"
                        ) from exc
                    raise

                delay = calculate_backoff(attempt, retry_cfg)
                hint_match = _RETRY_HINT_RE.search(str(exc))
                if hint_match and retry_cfg.max_delay > 0:
                    hinted_delay = float(hint_match.group(1))
                    delay = min(retry_cfg.max_delay, max(delay, hinted_delay))

                logger.warning(
                    "[RenalAgentRunner] Transient LLM error on attempt %d/%d (%s). Retrying in %.2fs...",
                    attempt + 1,
                    retry_cfg.max_retries + 1,
                    type(exc).__name__,
                    delay,
                )
                await asyncio.sleep(delay)

        raise AuditEvaluationExhaustedError(
            f"Stage 2 LLM call exhausted retries: {last_error}"
        )

    async def run(
        self,
        discharge_json: str,
        session: Optional[AsyncSession] = None,
        patient_id_hint: str = "unknown",
        medication_hint: str = "unknown",
        retry_config: Optional[RetryConfig] = None,
    ) -> Dict[str, Any]:
        """Execute the Stage 2 autonomous tool-calling loop and return report + telemetry."""
        from google.genai import types

        active_retry_cfg = retry_config or self.retry_config
        user_prompt = create_renal_agent_user_prompt(discharge_json)
        tools = get_gemini_renal_tools()
        tool_trace: List[str] = []
        tools_called: List[str] = []
        steps = 0
        input_tokens = 0
        output_tokens = 0

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
            response = await self._generate_with_retry(
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=STAGE2_SYSTEM_PROMPT,
                    temperature=self.temperature,
                    tools=tools,
                ),
                retry_cfg=active_retry_cfg,
            )
            steps += 1
            in_tok, out_tok = _extract_token_usage(response)
            input_tokens += in_tok
            output_tokens += out_tok

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

                    tools_called.append(fc_name)
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
            raw_text = _strip_json_fences(getattr(response, "text", None) or "")
            if raw_text:
                try:
                    report = RenalAuditReport.model_validate_json(raw_text)
                    report.tool_trace = tool_trace
                    report = _enforce_tool_evidence(report, metric_result, lab_result, crcl_result)
                    return {
                        "report": report,
                        "tools_called": tools_called,
                        "steps": steps,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                    }
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
            structured_resp = await self._generate_with_retry(
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=STAGE2_SYSTEM_PROMPT,
                    temperature=self.temperature,
                    response_mime_type="application/json",
                    response_schema=RenalAuditReport,
                ),
                retry_cfg=active_retry_cfg,
            )
            steps += 1
            in_tok, out_tok = _extract_token_usage(structured_resp)
            input_tokens += in_tok
            output_tokens += out_tok

            structured_text = (getattr(structured_resp, "text", None) or "").strip()
            report = RenalAuditReport.model_validate_json(structured_text)
            report.tool_trace = tool_trace
            report = _enforce_tool_evidence(report, metric_result, lab_result, crcl_result)
            return {
                "report": report,
                "tools_called": tools_called,
                "steps": steps,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            }

        logger.warning(
            "[RenalAgentRunner] Reached max_iterations (%d) without final verdict.",
            self.max_iterations,
        )
        fallback_report = RenalAuditReport(
            patient_id=verified_patient_id or patient_id_hint,
            medication_name=medication_hint,
            verdict="insufficient_data",
            rationale=(
                f"Agent execution halted after reaching the maximum iteration limit "
                f"({self.max_iterations}) without a completed determination."
            ),
            tool_trace=tool_trace,
        )
        return {
            "report": fallback_report,
            "tools_called": tools_called,
            "steps": steps,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }


def _strip_json_fences(text: str) -> str:
    """Strip optional markdown code fences around a JSON object response."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _extract_token_usage(response: Any) -> tuple[int, int]:
    """Extract (input_tokens, output_tokens) from Gemini usage_metadata safely."""
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return 0, 0
    prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
    candidate_tokens = getattr(usage, "candidates_token_count", 0) or 0
    return int(prompt_tokens), int(candidate_tokens)


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
