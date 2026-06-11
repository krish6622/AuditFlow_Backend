"""Auditor-office work order fields: category, contact, order date.

Revision ID: 0006_wo_category
Revises: 0005_two_role_audit
Create Date: 2026-06-11

Adds the ``work_order_category`` enum and four columns to ``work_orders``:
``category`` (+ ``category_other`` for OTHERS), ``contact_number`` and
``order_date``. All nullable so existing rows remain valid.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_wo_category"
down_revision: Union[str, None] = "0005_two_role_audit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

work_order_category = postgresql.ENUM(
    "income_tax", "gst", "project_report", "audit", "roc",
    "financial_statement", "tds", "accounting", "others",
    name="work_order_category", create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    work_order_category.create(bind, checkfirst=True)

    op.add_column("work_orders", sa.Column("category", work_order_category))
    op.add_column("work_orders", sa.Column("category_other", sa.String(120)))
    op.add_column("work_orders", sa.Column("contact_number", sa.String(40)))
    op.add_column("work_orders", sa.Column("order_date", sa.Date()))


def downgrade() -> None:
    op.drop_column("work_orders", "order_date")
    op.drop_column("work_orders", "contact_number")
    op.drop_column("work_orders", "category_other")
    op.drop_column("work_orders", "category")

    bind = op.get_bind()
    work_order_category.drop(bind, checkfirst=True)
