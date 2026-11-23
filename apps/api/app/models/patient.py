from datetime import datetime
from decimal import Decimal
import uuid
from typing import List, Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Uuid,
    desc,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Patient(Base):
    """Represents a patient's core demographic and anthropometric baseline."""

    __tablename__ = "patients"

    patient_id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        index=True,
        doc="Unique patient identifier (MRN or subject ID).",
    )
    name: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        doc="Patient full name.",
    )
    age_years: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Patient age in completed years.",
    )
    biological_sex: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        doc="Biological sex ('male' or 'female') used for renal pharmacokinetics.",
    )
    actual_weight_kg: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        doc="Total measured body weight in kilograms.",
    )
    height_cm: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        doc="Patient standing height in centimeters.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        doc="Record creation timestamp.",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        doc="Record last-updated timestamp.",
    )

    # Relationship to longitudinal lab panels (ordered by newest lab first)
    labs: Mapped[List["PatientLab"]] = relationship(
        "PatientLab",
        back_populates="patient",
        cascade="all, delete-orphan",
        order_by=lambda: desc(PatientLab.collected_at),
        lazy="selectin",
        doc="Historical laboratory measurements for this patient.",
    )

    def __repr__(self) -> str:
        return (
            f"<Patient(patient_id={self.patient_id!r}, "
            f"age={self.age_years}, sex={self.biological_sex!r}, "
            f"weight_kg={self.actual_weight_kg}, height_cm={self.height_cm})>"
        )


class PatientLab(Base):
    """Represents laboratory chemistry results used for renal function monitoring."""

    __tablename__ = "patient_labs"

    lab_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
        doc="Globally unique lab measurement identifier.",
    )
    patient_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("patients.patient_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Reference to the associated patient record.",
    )
    serum_creatinine_mg_dl: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(4, 2),
        nullable=True,
        doc="Serum creatinine concentration in mg/dL (SCr).",
    )
    egfr_ml_min_1_73m2: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 1),
        nullable=True,
        doc="Reported estimated glomerular filtration rate (eGFR).",
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        doc="Sample collection timestamp.",
    )

    # Composite index for rapid query of a patient's latest lab record
    __table_args__ = (
        Index("idx_patient_labs_patient_collected", "patient_id", desc("collected_at")),
    )

    patient: Mapped["Patient"] = relationship(
        "Patient",
        back_populates="labs",
    )

    def __repr__(self) -> str:
        return (
            f"<PatientLab(lab_id={self.lab_id!r}, "
            f"patient_id={self.patient_id!r}, "
            f"SCr={self.serum_creatinine_mg_dl}, collected_at={self.collected_at!r})>"
        )
