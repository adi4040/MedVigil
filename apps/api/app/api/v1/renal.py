import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

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
        return await runner.run(
            discharge_json=request.discharge_json,
            session=db,
        )
    except ValueError as exc:
        logger.warning("Configuration or validation error in Stage 2 evaluation: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error("Stage 2 renal evaluation failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Renal safety evaluation failed: {exc}",
        )
