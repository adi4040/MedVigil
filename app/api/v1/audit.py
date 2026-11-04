import logging
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.schemas.audit import AuditRequest, ClinicalGapReport, StreamChunk
from app.services.llm_client import BaseLLMClient, get_llm_client

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
    llm_client: BaseLLMClient = Depends(get_llm_client),
) -> ClinicalGapReport:
    """Evaluate clinical note against a policy rubric and return a structured gap report."""
    try:
        report = llm_client.evaluate_audit(
            clinical_note=request.clinical_note,
            policy_rubric=request.policy_rubric,
            rubric_id=request.rubric_id,
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
        "'token' for incremental text, 'done' for the complete validated ClinicalGapReport, "
        "or 'error' for failure details."
    ),
    response_class=StreamingResponse,
)
async def stream_clinical_note_evaluation(
    request: AuditRequest,
    llm_client: BaseLLMClient = Depends(get_llm_client),
):
    """Stream clinical audit evaluation as Server-Sent Events (SSE)."""

    async def event_generator():
        try:
            async for chunk in llm_client.stream_audit(
                clinical_note=request.clinical_note,
                policy_rubric=request.policy_rubric,
                rubric_id=request.rubric_id,
            ):
                yield f"event: {chunk.event.value}\ndata: {chunk.model_dump_json()}\n\n"
        except Exception as exc:
            logger.error(f"Error during audit streaming: {exc}", exc_info=True)
            err_chunk = StreamChunk.error_chunk(str(exc))
            yield f"event: {err_chunk.event.value}\ndata: {err_chunk.model_dump_json()}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


