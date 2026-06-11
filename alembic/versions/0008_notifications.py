"""In-app notifications.

Revision ID: 0008_notifications
Revises: 0007_wo_workflow
Create Date: 2026-06-11
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_notifications"
down_revision: Union[str, None] = "0007_wo_workflow"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TS = postgresql.TIMESTAMP(timezone=True)

notification_type = postgresql.ENUM(
    "workorder_requested", "workorder_assigned", "workorder_completed", "workorder_closed",
    name="notification_type", create_type=False,
)


def upgrade() -> None:
    notification_type.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", notification_type, nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("body", sa.Text()),
        sa.Column("work_order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("work_orders.id", ondelete="SET NULL")),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_notifications_organization_id", "notifications", ["organization_id"])
    op.create_index("ix_notifications_work_order_id", "notifications", ["work_order_id"])
    # Drives the per-user inbox + unread badge query.
    op.create_index("ix_notifications_user_read", "notifications", ["user_id", "is_read"])


def downgrade() -> None:
    op.drop_index("ix_notifications_user_read", table_name="notifications")
    op.drop_index("ix_notifications_work_order_id", table_name="notifications")
    op.drop_index("ix_notifications_organization_id", table_name="notifications")
    op.drop_table("notifications")
    notification_type.drop(op.get_bind(), checkfirst=True)
