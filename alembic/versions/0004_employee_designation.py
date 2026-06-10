"""Add employee designation and a phone index (login by email or phone).

Revision ID: 0004_employee
Revises: 0003_invoice_records
Create Date: 2026-06-09
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_employee"
down_revision: Union[str, None] = "0003_invoice_records"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("designation", sa.String(120)))
    op.create_index("ix_users_phone", "users", ["phone"])
    # Email is optional for employees (they can sign in with phone instead).
    op.alter_column("users", "email", existing_type=sa.String(255), nullable=True)


def downgrade() -> None:
    op.alter_column("users", "email", existing_type=sa.String(255), nullable=False)
    op.drop_index("ix_users_phone", table_name="users")
    op.drop_column("users", "designation")
