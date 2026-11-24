"""add generic_patient_id to patients table

Revision ID: 005_add_generic_patient_id
Revises: 004_make_scr_nullable
Create Date: 2026-11-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "005_add_generic_patient_id"
down_revision: Union[str, None] = "004_make_scr_nullable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "patients",
        sa.Column("generic_patient_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        op.f("ix_patients_generic_patient_id"),
        "patients",
        ["generic_patient_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_patients_generic_patient_id"), table_name="patients")
    op.drop_column("patients", "generic_patient_id")
