import asyncio
import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.schemas.audit import AuditRequest, ClinicalGapReport, StreamChunk
from app.services.llm_client import BaseLLMClient, get_configured_llm_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit", tags=["Clinical Audit"])


@router.post(
    "/evaluate",
    response_model=ClinicalGapReport,
    summary="Audit Clinical Note Against Policy Rubric",
    description=(
        "Compares a supplied clinical encounter note against a policy rubric "
        "and produces a structured gap report indicating met, missing, or unclear criteria."
    ),
)
def evaluate_clinical_note(
    request: AuditRequest,
    llm_client: BaseLLMClient = Depends(get_configured_llm_client),
) -> ClinicalGapReport:
    """Evaluate clinical note against a policy rubric and return a structured gap report."""
    try:
        report = llm_client.evaluate_audit(
            clinical_note=request.clinical_note,
            policy_rubric=request.policy_rubric,
            rubric_id=request.rubric_id,
            temperature=request.temperature,
        )
        return report
    except ValueError as e:
        logger.warning(f"Validation or configuration error in audit evaluation: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except RuntimeError as e:
        logger.error(f"LLM execution error during audit: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM provider error: {str(e)}",
        )
    except Exception as e:
        logger.error(f"Unexpected error during clinical audit: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal audit service error: {str(e)}",
        )


@router.post(
    "/evaluate/stream",
    summary="Stream Clinical Audit Evaluation via SSE",
    description=(
        "Streams token deltas from the LLM in real-time using Server-Sent Events (SSE). "
        "Each SSE event contains a JSON-serialized StreamChunk with an event type: "
        "'status' for progress, 'token' for incremental text, 'done' for the complete "
        "validated ClinicalGapReport, or 'error' for failure details."
    ),
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Server-Sent Events containing JSON-serialized StreamChunk payloads.",
            "content": {
                "text/event-stream": {
                    "schema": {
                        "type": "string",
                        "description": "SSE frames terminated by a blank line.",
                    }
                }
            },
        }
    },
)
async def stream_clinical_note_evaluation(
    audit_request: AuditRequest,
    request: Request,
    llm_client: BaseLLMClient = Depends(get_configured_llm_client),
):
    """Stream clinical audit evaluation as Server-Sent Events (SSE)."""

    async def event_generator():
        request_id = uuid4().hex
        # Emit an immediate status event to give instantaneous feedback to the client
        initial_status = StreamChunk.status_chunk("Evaluating clinical note against rubric...")
        yield f"event: {initial_status.event.value}\ndata: {initial_status.model_dump_json()}\n\n"

        stream = llm_client.stream_audit(
            clinical_note=audit_request.clinical_note,
            policy_rubric=audit_request.policy_rubric,
            rubric_id=audit_request.rubric_id,
            temperature=audit_request.temperature,
        )
        try:
            async for chunk in stream:
                if await request.is_disconnected():
                    logger.info("Audit stream disconnected", extra={"request_id": request_id})
                    return
                yield f"event: {chunk.event.value}\ndata: {chunk.model_dump_json()}\n\n"
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(
                "Error during audit streaming request %s: %s",
                request_id,
                exc,
                exc_info=True,
            )
            err_chunk = StreamChunk.error_chunk(
                "The audit stream failed. Please retry or contact support.",
                request_id=request_id,
            )
            yield f"event: {err_chunk.event.value}\ndata: {err_chunk.model_dump_json()}\n\n"
        finally:
            await stream.aclose()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
