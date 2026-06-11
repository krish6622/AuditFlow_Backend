"""Drop the user account status column (registration approval reverted).

Revision ID: 0012_drop_user_status
Revises: 0011_user_status
Create Date: 2026-06-11

The self-registration approval workflow was removed: new sign-ups are active
employees who can log in immediately, so the ``users.status`` lifecycle column
and the ``user_status`` enum are no longer needed (``is_active`` is again the
sole flag). The ``audit_action`` values ``user_approved``/``user_rejected`` added
in 0011 cannot be dropped in Postgres, so they simply remain unused.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_drop_user_status"
down_revision: Union[str, None] = "0011_user_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

user_status = postgresql.ENUM(
    "pending_approval", "active", "inactive", name="user_status", create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    op.drop_index("ix_users_status", table_name="users")
    op.drop_column("users", "status")
    user_status.drop(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    user_status.create(bind, checkfirst=True)
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
