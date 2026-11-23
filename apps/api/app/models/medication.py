from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Medication(Base):
    """Represents a pharmaceutical medication in the safety catalog."""

    __tablename__ = "medications"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        index=True,
        doc="Unique primary key for the medication.",
    )
    name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
        doc="Standard medication display name.",
    )
    generic_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        doc="Generic active pharmaceutical ingredient name.",
    )
    brand_name: Mapped[Optional[str]] = mapped_column(
        String(256),
        nullable=True,
        doc="Common brand / trade name(s).",
    )
    drug_class: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        doc="Pharmacological or therapeutic classification.",
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
        doc="Record last updated timestamp.",
    )

    # One-to-many relationship: One medication has multiple renal dosing guidelines
    renal_guidelines: Mapped[List["RenalDosingGuideline"]] = relationship(
        "RenalDosingGuideline",
        back_populates="medication",
        cascade="all, delete-orphan",
        lazy="selectin",
        doc="Tiered renal dosing guidelines for this medication.",
    )

    def __repr__(self) -> str:
        return (
            f"<Medication(id={self.id}, name={self.name!r}, "
            f"generic_name={self.generic_name!r}, drug_class={self.drug_class!r})>"
        )


class RenalDosingGuideline(Base):
    """Represents a renal dosage adjustment rule bracket for a specific medication."""

    __tablename__ = "renal_dosing_guidelines"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        index=True,
        doc="Unique primary key for the guideline rule.",
    )
    medication_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("medications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Foreign key referencing medications.id.",
    )
    renal_metric: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        doc="Target renal function metric: 'crcl' or 'egfr'.",
    )
    min_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(6, 2),
        nullable=True,
        doc="Lower renal threshold bound in mL/min (inclusive).",
    )
    max_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(6, 2),
        nullable=True,
        doc="Upper renal threshold bound in mL/min (exclusive or upper cap).",
    )
    min_daily_dose: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(8, 2),
        nullable=True,
        doc="Minimum recommended total daily dose in mg.",
    )
    max_daily_dose: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(8, 2),
        nullable=True,
        doc="Maximum recommended total daily dose in mg.",
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
        doc="Record last updated timestamp.",
    )

    # Relationship back to medication
    medication: Mapped["Medication"] = relationship(
        "Medication",
        back_populates="renal_guidelines",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<RenalDosingGuideline(id={self.id}, medication_id={self.medication_id}, "
            f"metric={self.renal_metric!r}, range=[{self.min_value}, {self.max_value}), "
            f"daily_dose=[{self.min_daily_dose}, {self.max_daily_dose}])>"
        )
