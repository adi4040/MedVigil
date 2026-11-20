"""create patients and patient_labs tables

Revision ID: 001_create_patient_and_labs
Revises: 
Create Date: 2026-11-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "001_create_patient_and_labs"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "patients",
        sa.Column("patient_id", sa.String(length=64), nullable=False),
        sa.Column("age_years", sa.Integer(), nullable=False),
        sa.Column("biological_sex", sa.String(length=10), nullable=False),
        sa.Column("actual_weight_kg", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("height_cm", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("patient_id"),
    )
    op.create_index(op.f("ix_patients_patient_id"), "patients", ["patient_id"], unique=False)

    op.create_table(
        "patient_labs",
        sa.Column("lab_id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("patient_id", sa.String(length=64), nullable=False),
        sa.Column("serum_creatinine_mg_dl", sa.Numeric(precision=4, scale=2), nullable=False),
        sa.Column("egfr_ml_min_1_73m2", sa.Numeric(precision=5, scale=1), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.patient_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("lab_id"),
    )
    op.create_index(op.f("ix_patient_labs_patient_id"), "patient_labs", ["patient_id"], unique=False)
    op.create_index(
        "idx_patient_labs_patient_collected",
        "patient_labs",
        ["patient_id", sa.text("collected_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_patient_labs_patient_collected", table_name="patient_labs")
    op.drop_index(op.f("ix_patient_labs_patient_id"), table_name="patient_labs")
    op.drop_table("patient_labs")
    op.drop_index(op.f("ix_patients_patient_id"), table_name="patients")
    op.drop_table("patients")
