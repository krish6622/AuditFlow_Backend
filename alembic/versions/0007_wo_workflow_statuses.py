"""Auditor-office workflow statuses + requested_by.

Revision ID: 0007_wo_workflow
Revises: 0006_wo_category
Create Date: 2026-06-11

Swaps work_order_status to {awaiting_assignment, assigned, in_progress,
completed, closed, cancelled} (legacy 'pending' -> 'awaiting_assignment') and
adds work_orders.requested_by_id (the employee who raised the request).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_wo_workflow"
down_revision: Union[str, None] = "0006_wo_category"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_VALUES = (
    "awaiting_assignment", "assigned", "in_progress", "completed", "closed", "cancelled",
)
OLD_VALUES = ("assigned", "in_progress", "completed", "cancelled", "pending")


def upgrade() -> None:
    # Swap the enum type (Postgres can't add+use a value in one tx, and we also
    # want to drop 'pending' — so build a new type and remap).
    op.execute("ALTER TABLE work_orders ALTER COLUMN status DROP DEFAULT")
    op.execute(
        "CREATE TYPE work_order_status_new AS ENUM ("
        + ", ".join(f"'{v}'" for v in NEW_VALUES)
        + ")"
    )
    op.execute(
        "ALTER TABLE work_orders ALTER COLUMN status TYPE work_order_status_new "
        "USING (CASE status::text WHEN 'pending' THEN 'awaiting_assignment' "
        "ELSE status::text END)::work_order_status_new"
    )
    op.execute("DROP TYPE work_order_status")
    op.execute("ALTER TYPE work_order_status_new RENAME TO work_order_status")
    op.execute("ALTER TABLE work_orders ALTER COLUMN status SET DEFAULT 'awaiting_assignment'")

    op.add_column(
        "work_orders",
        sa.Column(
            "requested_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
    )
    op.create_index("ix_work_orders_requested_by_id", "work_orders", ["requested_by_id"])


def downgrade() -> None:
    op.drop_index("ix_work_orders_requested_by_id", table_name="work_orders")
    op.drop_column("work_orders", "requested_by_id")

    op.execute("ALTER TABLE work_orders ALTER COLUMN status DROP DEFAULT")
    op.execute(
        "CREATE TYPE work_order_status_old AS ENUM ("
        + ", ".join(f"'{v}'" for v in OLD_VALUES)
        + ")"
    )
    # closed has no pre-image; fold it back into completed.
    op.execute(
        "ALTER TABLE work_orders ALTER COLUMN status TYPE work_order_status_old "
        "USING (CASE status::text "
        "WHEN 'awaiting_assignment' THEN 'pending' "
        "WHEN 'closed' THEN 'completed' "
        "ELSE status::text END)::work_order_status_old"
    )
    op.execute("DROP TYPE work_order_status")
    op.execute("ALTER TYPE work_order_status_old RENAME TO work_order_status")
    op.execute("ALTER TABLE work_orders ALTER COLUMN status SET DEFAULT 'assigned'")
