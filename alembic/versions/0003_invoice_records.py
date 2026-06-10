"""Standalone invoice records for the public Invoice module.

Revision ID: 0003_invoice_records
Revises: 0002_work_orders
Create Date: 2026-06-09
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_invoice_records"
down_revision: Union[str, None] = "0002_work_orders"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TS = postgresql.TIMESTAMP(timezone=True)


def upgrade() -> None:
    op.create_table(
        "invoice_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("invoice_number", sa.String(60), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("customer_name", sa.String(255), nullable=False),
        sa.Column("customer_address", sa.Text()),
        sa.Column("mca_charges", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("discount_percent", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("gross_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("discount_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("net_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_invoice_records_invoice_number", "invoice_records", ["invoice_number"], unique=True)

    op.create_table(
        "invoice_line_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("invoice_record_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("invoice_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_invoice_line_items_invoice_record_id", "invoice_line_items", ["invoice_record_id"])


def downgrade() -> None:
    op.drop_table("invoice_line_items")
    op.drop_table("invoice_records")
