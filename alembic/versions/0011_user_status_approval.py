"""Add user account status (registration approval workflow).

Revision ID: 0011_user_status
Revises: 0010_emp_soft_delete
Create Date: 2026-06-11

Adds the ``user_status`` enum {pending_approval, active, inactive} and a
``status`` column on ``users``. Existing rows are backfilled from ``is_active``
(active -> ACTIVE, inactive -> INACTIVE) — no one is retroactively forced into
approval. New self-registrations are created PENDING_APPROVAL by the app.

Also registers two new ``audit_action`` values used by the approve/reject flow.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_user_status"
down_revision: Union[str, None] = "0010_emp_soft_delete"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Created explicitly; the column references it with create_type=False.
user_status = postgresql.ENUM(
    "pending_approval", "active", "inactive", name="user_status", create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Create the enum type.
    user_status.create(bind, checkfirst=True)

    # 2. Add the column nullable, backfill from is_active, then enforce NOT NULL.
    op.add_column("users", sa.Column("status", user_status, nullable=True))
    op.execute(
        "UPDATE users SET status = "
        "(CASE WHEN is_active THEN 'active' ELSE 'inactive' END)::user_status"
    )
    op.alter_column(
        "users", "status", existing_type=user_status, nullable=False,
        server_default="active",
    )
    op.create_index("ix_users_status", "users", ["status"])

    # 3. New audit actions for the approval workflow (not used in this DDL, so
    #    adding the values in this transaction is safe).
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'user_approved'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'user_rejected'")


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_index("ix_users_status", table_name="users")
    op.drop_column("users", "status")
    user_status.drop(bind, checkfirst=True)
    # Note: Postgres can't drop enum values, so the new audit_action values remain.
