import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.retry import AuditEvaluationExhaustedError
from app.db.session import get_db
from app.schemas.renal import RenalAuditReport, RenalAuditRequest
from app.services.agent.loop import RenalAgentRunner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/renal", tags=["Renal Safety Auditor"])


@router.post(
    "/evaluate",
    response_model=RenalAuditReport,
    summary="Evaluate Renal Dosing Safety (Stage 2)",
    description=(
        "Runs the Stage 2 Gemini tool-calling agent against the clinical database "
        "to verify prescribed medication dosing against renal guidelines."
    ),
)
async def evaluate_renal_dosing(
    request: RenalAuditRequest,
    db: AsyncSession = Depends(get_db),
) -> RenalAuditReport:
    """Execute the Stage 2 renal dosing verification agent loop."""
    try:
        runner = RenalAgentRunner()
    except ValueError as exc:
        logger.error("Stage 2 LLM configuration error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Renal safety service is not configured.",
        )

    try:
        result = await runner.run(
            discharge_json=request.discharge_json,
            session=db,
        )
        return result["report"]
    except ValidationError as exc:
        logger.error("Stage 2 model returned invalid report schema: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Upstream model returned an invalid renal audit report.",
        )
    except AuditEvaluationExhaustedError as exc:
        logger.error("Stage 2 upstream LLM service unavailable after retries: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Upstream LLM service is temporarily unavailable. Please try again.",
        )
    except Exception as exc:
        logger.error("Stage 2 renal evaluation failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Renal safety evaluation failed due to an internal error.",
        )
