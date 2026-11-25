import logging
from typing import Any, List, Optional

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
                    )
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
                    return report
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
            return report

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
