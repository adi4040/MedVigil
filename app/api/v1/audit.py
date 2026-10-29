import logging
from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.audit import AuditRequest, ClinicalGapReport
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

