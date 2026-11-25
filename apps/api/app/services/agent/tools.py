import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import async_session_factory
from app.models.medication import Medication, RenalDosingGuideline
from app.models.patient import Patient, PatientLab

logger = logging.getLogger(__name__)


def _normalize_metric_name(metric: str) -> str:
    """Normalize raw database guideline metric strings to standardized 'crcl' or 'egfr'."""
    lowered = metric.strip().lower()
    if "crcl" in lowered or "creatinine_clearance" in lowered or "cockcroft" in lowered:
        return "crcl"
    if "egfr" in lowered or "gfr" in lowered:
        return "egfr"
    return lowered


async def get_renal_metric(
    medication_name: str,
    session: Optional[AsyncSession] = None,
) -> Dict[str, Any]:
    """Check which renal metric ('crcl' or 'egfr') and dosage guidelines are required for a prescribed medication.

    Args:
        medication_name: Standard brand or generic name of the medication (e.g. 'Gabapentin', 'Cefepime').
        session: Optional active SQLAlchemy AsyncSession. If omitted, a session is created and closed automatically.

    Returns:
        A dictionary containing the required renal metric, drug metadata, and tiered dosing brackets.
    """
    clean_name = medication_name.strip()
    if not clean_name:
        return {
            "status": "error",
            "message": "Medication name must not be empty.",
        }

    async def _execute(s: AsyncSession) -> Dict[str, Any]:
        # Search by exact name or generic name (case-insensitive)
        stmt = (
            select(Medication)
            .options(selectinload(Medication.renal_guidelines))
            .where(
                or_(
                    func.lower(Medication.name) == clean_name.lower(),
                    func.lower(Medication.generic_name) == clean_name.lower(),
                )
            )
        )
        result = await s.execute(stmt)
        med = result.scalar_one_or_none()

        # If not found by exact match, try substring / ILIKE search
        if med is None:
            like_stmt = (
                select(Medication)
                .options(selectinload(Medication.renal_guidelines))
                .where(
                    or_(
                        Medication.name.ilike(f"%{clean_name}%"),
                        Medication.generic_name.ilike(f"%{clean_name}%"),
                    )
                )
            )
            result = await s.execute(like_stmt)
            med = result.scalar_one_or_none()

        if med is None:
            return {
                "status": "error",
                "message": f"Medication '{clean_name}' was not found in the pharmaceutical database.",
            }

        guidelines = med.renal_guidelines
        if not guidelines:
            return {
                "status": "warning",
                "medication_id": med.id,
                "medication_name": med.name,
                "generic_name": med.generic_name,
                "drug_class": med.drug_class,
                "required_renal_metric": None,
                "message": f"Medication '{med.name}' is registered but has no specific renal dosing guidelines.",
                "guidelines": [],
            }

        # Extract and normalize required renal metric from the guideline
        raw_metric = guidelines[0].renal_metric
        normalized_metric = _normalize_metric_name(raw_metric)

        brackets: List[Dict[str, Any]] = []
        for g in guidelines:
            brackets.append({
                "guideline_id": g.id,
                "renal_metric": g.renal_metric,
                "min_renal_value": float(g.min_value) if g.min_value is not None else None,
                "max_renal_value": float(g.max_value) if g.max_value is not None else None,
                "min_daily_dose_mg": float(g.min_daily_dose) if g.min_daily_dose is not None else None,
                "max_daily_dose_mg": float(g.max_daily_dose) if g.max_daily_dose is not None else None,
            })

        return {
            "status": "success",
            "medication_id": med.id,
            "medication_name": med.name,
            "generic_name": med.generic_name,
            "drug_class": med.drug_class,
            "required_renal_metric": normalized_metric,
            "raw_metric": raw_metric,
            "guideline_count": len(brackets),
            "guidelines": brackets,
        }

    if session is not None:
        return await _execute(session)
    async with async_session_factory() as s:
        return await _execute(s)


async def fetch_patient_crcl(
    patient_id: str,
    session: Optional[AsyncSession] = None,
) -> Dict[str, Any]:
    """Query PostgreSQL for a patient's creatinine clearance (CrCl) and renal laboratory history.

    Accurately scans longitudinal lab panels for the newest non-null Serum Creatinine (SCr)
    and eGFR, ensuring newer eGFR-only panels do not mask older valid SCr measurements.

    Args:
        patient_id: Unique patient identifier (MRN or subject ID).
        session: Optional active SQLAlchemy AsyncSession.

    Returns:
        A dictionary with patient renal lab status. If CrCl is not recorded in the lab table,
        indicates missing status and returns the latest available non-null SCr and eGFR.
    """
    clean_id = patient_id.strip()
    if not clean_id:
        return {
            "status": "error",
            "message": "Patient ID must not be empty.",
        }

    async def _execute(s: AsyncSession) -> Dict[str, Any]:
        stmt = (
            select(Patient)
            .options(selectinload(Patient.labs))
            .where(Patient.patient_id == clean_id)
        )
        result = await s.execute(stmt)
        patient = result.scalar_one_or_none()

        if patient is None:
            return {
                "status": "error",
                "message": f"Patient with identifier '{clean_id}' was not found in the database.",
            }

        labs = patient.labs

        # Scan for the newest panel with a non-null serum creatinine measurement
        newest_scr: Optional[float] = None
        scr_collected_at: Optional[str] = None
        for lab in labs:
            if lab.serum_creatinine_mg_dl is not None:
                newest_scr = float(lab.serum_creatinine_mg_dl)
                scr_collected_at = lab.collected_at.isoformat()
                break

        # Scan for the newest panel with a non-null eGFR measurement
        newest_egfr: Optional[float] = None
        egfr_collected_at: Optional[str] = None
        for lab in labs:
            if lab.egfr_ml_min_1_73m2 is not None:
                newest_egfr = float(lab.egfr_ml_min_1_73m2)
                egfr_collected_at = lab.collected_at.isoformat()
                break

        # Formulate accurate, non-contradictory message based on actual SCr presence
        if newest_scr is not None:
            message = (
                "Creatinine clearance (CrCl) is not directly recorded in the patient labs table. "
                "Serum creatinine is available; please call calculate_crcl to compute CrCl using "
                "the Cockcroft-Gault formula."
            )
        else:
            message = (
                "Creatinine clearance (CrCl) is not directly recorded in the patient labs table, "
                "and no serum creatinine measurements were found in the patient's lab history."
            )

        return {
            "status": "missing",
            "crcl_found": False,
            "patient_id": patient.patient_id,
            "patient_name": patient.name,
            "total_lab_panels": len(labs),
            "latest_serum_creatinine_mg_dl": newest_scr,
            "serum_creatinine_collected_at": scr_collected_at,
            "latest_egfr_ml_min_1_73m2": newest_egfr,
            "egfr_collected_at": egfr_collected_at,
            "message": message,
        }

    if session is not None:
        return await _execute(session)
    async with async_session_factory() as s:
        return await _execute(s)


async def calculate_crcl(
    patient_id: str,
    serum_creatinine_mg_dl: Optional[float] = None,
    session: Optional[AsyncSession] = None,
) -> Dict[str, Any]:
    """Calculate estimated Creatinine Clearance (CrCl) using the clinical Cockcroft-Gault equation.

    Uses patient anthropometrics (age, biological sex, weight in kg) from the patients table,
    combined with either an explicitly provided serum creatinine or the latest lab observation.

    Formula:
        CrCl (mL/min) = [((140 - age) * weight_kg) / (72 * SCr)] * (0.85 if female else 1.0)

    Args:
        patient_id: Unique patient identifier (MRN or subject ID).
        serum_creatinine_mg_dl: Optional explicit serum creatinine in mg/dL. If omitted,
                                the patient's latest lab result is retrieved from PostgreSQL.
        session: Optional active SQLAlchemy AsyncSession.

    Returns:
        A dictionary containing the calculated CrCl, clinical formula parameters, and data lineage.
    """
    clean_id = patient_id.strip()
    if not clean_id:
        return {
            "status": "error",
            "message": "Patient ID must not be empty.",
        }

    async def _execute(s: AsyncSession) -> Dict[str, Any]:
        stmt = (
            select(Patient)
            .options(selectinload(Patient.labs))
            .where(Patient.patient_id == clean_id)
        )
        result = await s.execute(stmt)
        patient = result.scalar_one_or_none()

        if patient is None:
            return {
                "status": "error",
                "message": f"Patient with identifier '{clean_id}' was not found in the database.",
            }

        # Resolve Serum Creatinine (SCr)
        scr_value: Optional[float] = None
        lab_source_date: Optional[str] = None

        if serum_creatinine_mg_dl is not None:
            scr_value = float(serum_creatinine_mg_dl)
        else:
            # Look up newest lab panel with non-null SCr
            for lab in patient.labs:
                if lab.serum_creatinine_mg_dl is not None:
                    scr_value = float(lab.serum_creatinine_mg_dl)
                    lab_source_date = lab.collected_at.isoformat()
                    break

        if scr_value is None:
            return {
                "status": "error",
                "patient_id": patient.patient_id,
                "message": f"Cannot calculate CrCl: No serum creatinine measurement exists for patient '{clean_id}'.",
            }

        if scr_value <= 0:
            return {
                "status": "error",
                "message": f"Invalid serum creatinine measurement: {scr_value} mg/dL. Value must be greater than zero.",
            }

        # Demographics & anthropometrics
        age_years = patient.age_years
        weight_kg = float(patient.actual_weight_kg)
        if weight_kg <= 0:
            return {
                "status": "error",
                "message": f"Invalid patient weight: {weight_kg} kg.",
            }

        biological_sex = patient.biological_sex.strip().lower()
        is_female = biological_sex in ("female", "f", "Female", "F")

        # Cockcroft-Gault Equation
        # CrCl = ((140 - age) * weight_kg) / (72 * SCr)
        # Adjusted by 0.85 for females
        raw_crcl = ((140.0 - float(age_years)) * weight_kg) / (72.0 * scr_value)
        female_factor = 0.85 if is_female else 1.0
        adjusted_crcl = raw_crcl * female_factor

        calculated_crcl = max(0.0, round(adjusted_crcl, 2))

        return {
            "status": "success",
            "patient_id": patient.patient_id,
            "patient_name": patient.name,
            "calculated_crcl_ml_min": calculated_crcl,
            "formula": "Cockcroft-Gault",
            "parameters_used": {
                "age_years": age_years,
                "actual_weight_kg": round(weight_kg, 2),
                "biological_sex": patient.biological_sex,
                "serum_creatinine_mg_dl": round(scr_value, 2),
                "female_adjustment_factor": female_factor,
                "source_lab_collected_at": lab_source_date,
            },
        }

    if session is not None:
        return await _execute(session)
    async with async_session_factory() as s:
        return await _execute(s)
