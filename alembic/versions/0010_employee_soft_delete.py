"""Employee soft delete.

Revision ID: 0010_emp_soft_delete
Revises: 0009_wo_amount_contact
Create Date: 2026-06-11

Adds ``deleted_at`` / ``deleted_by`` / ``deleted_employee_name`` to ``users``
(soft delete — rows are never physically removed) and the ``user_deleted``
audit action.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_emp_soft_delete"
down_revision: Union[str, None] = "0009_wo_amount_contact"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TS = postgresql.TIMESTAMP(timezone=True)


def upgrade() -> None:
    op.add_column("users", sa.Column("deleted_at", _TS))
    op.add_column(
        "users",
        sa.Column(
            "deleted_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
    )
    op.add_column("users", sa.Column("deleted_employee_name", sa.String(255)))
    op.create_index("ix_users_deleted_at", "users", ["deleted_at"])

    # New audit action value (safe: not referenced in this migration's DDL).
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'user_deleted'")


def downgrade() -> None:
    op.drop_index("ix_users_deleted_at", table_name="users")
    op.drop_column("users", "deleted_employee_name")
    op.drop_column("users", "deleted_by")
    op.drop_column("users", "deleted_at")
    # Note: Postgres can't drop an enum value, so 'user_deleted' remains.
