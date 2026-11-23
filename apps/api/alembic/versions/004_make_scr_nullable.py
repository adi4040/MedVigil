"""make serum_creatinine_mg_dl nullable in patient_labs

Revision ID: 004_make_scr_nullable
Revises: 003_create_meds_guidelines
Create Date: 2026-11-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "004_make_scr_nullable"
down_revision: Union[str, None] = "003_create_meds_guidelines"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "patient_labs",
        "serum_creatinine_mg_dl",
        existing_type=sa.Numeric(precision=4, scale=2),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "patient_labs",
        "serum_creatinine_mg_dl",
        existing_type=sa.Numeric(precision=4, scale=2),
        nullable=False,
    )
