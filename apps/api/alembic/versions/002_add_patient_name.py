"""add name and nullable height to patients table

Revision ID: 002_add_patient_name
Revises: 001_create_patient_and_labs
Create Date: 2026-11-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "002_add_patient_name"
down_revision: Union[str, None] = "001_create_patient_and_labs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("patients", sa.Column("name", sa.String(length=128), nullable=True))
    op.alter_column(
        "patients",
        "height_cm",
        existing_type=sa.Numeric(precision=5, scale=2),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "patients",
        "height_cm",
        existing_type=sa.Numeric(precision=5, scale=2),
        nullable=False,
    )
    op.drop_column("patients", "name")
