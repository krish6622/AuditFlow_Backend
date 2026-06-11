"""Drop work-order expected amount; make contact_number required.

Revision ID: 0009_wo_amount_contact
Revises: 0008_notifications
Create Date: 2026-06-11

- Removes ``work_orders.amount`` (the "Expected Amount" field).
- Backfills NULL ``contact_number`` with 'N/A' and makes the column NOT NULL.

(``due_date`` is already nullable; the per-org unique ``number`` already exists.)
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_wo_amount_contact"
down_revision: Union[str, None] = "0008_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("work_orders", "amount")

    op.execute("UPDATE work_orders SET contact_number = 'N/A' WHERE contact_number IS NULL")
    op.alter_column(
        "work_orders", "contact_number", existing_type=sa.String(40), nullable=False
    )


def downgrade() -> None:
    op.alter_column(
        "work_orders", "contact_number", existing_type=sa.String(40), nullable=True
    )
    op.add_column(
        "work_orders",
        sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
    )
