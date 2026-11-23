"""create medications and renal_dosing_guidelines tables

Revision ID: 003_create_meds_guidelines
Revises: 002_add_patient_name
Create Date: 2026-11-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "003_create_meds_guidelines"
down_revision: Union[str, None] = "002_add_patient_name"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Medications table
    op.create_table(
        "medications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("generic_name", sa.String(length=128), nullable=False),
        sa.Column("brand_name", sa.String(length=256), nullable=True),
        sa.Column("drug_class", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_medications_id"), "medications", ["id"], unique=False)
    op.create_index(op.f("ix_medications_name"), "medications", ["name"], unique=False)

    # 2. Renal dosing guidelines table
    op.create_table(
        "renal_dosing_guidelines",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("medication_id", sa.Integer(), nullable=False),
        sa.Column("renal_metric", sa.String(length=20), nullable=False),
        sa.Column("min_value", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("max_value", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("min_daily_dose", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("max_daily_dose", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["medication_id"], ["medications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_renal_dosing_guidelines_id"), "renal_dosing_guidelines", ["id"], unique=False)
    op.create_index(op.f("ix_renal_dosing_guidelines_medication_id"), "renal_dosing_guidelines", ["medication_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_renal_dosing_guidelines_medication_id"), table_name="renal_dosing_guidelines")
    op.drop_index(op.f("ix_renal_dosing_guidelines_id"), table_name="renal_dosing_guidelines")
    op.drop_table("renal_dosing_guidelines")
    op.drop_index(op.f("ix_medications_name"), table_name="medications")
    op.drop_index(op.f("ix_medications_id"), table_name="medications")
    op.drop_table("medications")
