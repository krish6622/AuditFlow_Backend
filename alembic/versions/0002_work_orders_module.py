"""Work Orders module: free-text contact fields, amount, notes, pending status.

Adds the columns the Work Orders module needs (customer_name,
assigned_employee_name, amount, notes), relaxes the customer/title NOT NULL
constraints so an order can be raised without pre-existing Customer/Employee
records, switches due_date to a pure DATE, and adds a 'pending' status value.

Revision ID: 0002_work_orders
Revises: 0001_initial
Create Date: 2026-06-09
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_work_orders"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New enum value. Safe inside the migration transaction as long as the value
    # is not *used* in the same transaction (we never reference it in DDL here).
    op.execute("ALTER TYPE work_order_status ADD VALUE IF NOT EXISTS 'pending'")

    op.add_column("work_orders", sa.Column("customer_name", sa.String(255)))
    op.add_column("work_orders", sa.Column("assigned_employee_name", sa.String(255)))
    op.add_column(
        "work_orders",
        sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
    )
    op.add_column("work_orders", sa.Column("notes", sa.Text()))

    # Relax NOT NULLs so an order can be created from free-text fields alone.
    op.alter_column("work_orders", "customer_id", existing_type=sa.dialects.postgresql.UUID(), nullable=True)
    op.alter_column("work_orders", "title", existing_type=sa.String(255), nullable=True)

    # Due date becomes a calendar date (no time component).
    op.alter_column(
        "work_orders",
        "due_date",
        type_=sa.Date(),
        existing_type=sa.DateTime(timezone=True),
        postgresql_using="due_date::date",
    )


def downgrade() -> None:
    op.alter_column(
        "work_orders",
        "due_date",
        type_=sa.DateTime(timezone=True),
        existing_type=sa.Date(),
        postgresql_using="due_date::timestamptz",
    )
    op.alter_column("work_orders", "title", existing_type=sa.String(255), nullable=False)
    op.alter_column("work_orders", "customer_id", existing_type=sa.dialects.postgresql.UUID(), nullable=False)
    op.drop_column("work_orders", "notes")
    op.drop_column("work_orders", "amount")
    op.drop_column("work_orders", "assigned_employee_name")
    op.drop_column("work_orders", "customer_name")
    # Note: PostgreSQL cannot DROP a value from an enum type, so 'pending'
    # remains in work_order_status after downgrade (harmless).
