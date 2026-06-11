"""Collapse roles to ADMIN/EMPLOYEE and add the audit log.

Revision ID: 0005_two_role_audit
Revises: 0004_employee
Create Date: 2026-06-11

Changes:
  * Remove the platform ``super_admin`` (no org, no data) — the app is now a
    pure two-role, per-organization model.
  * Swap the ``user_role`` enum {super_admin, org_admin, employee} -> {admin,
    employee}; ``org_admin`` (and any stray ``super_admin``) map to ``admin``.
  * Every user now belongs to an organization: drop the role/org CHECK and the
    super-admin partial email index, and make ``users.organization_id`` NOT NULL.
  * Add the ``audit_action`` enum and the ``audit_logs`` table.

Note: the deleted super_admin row cannot be restored by downgrade.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_two_role_audit"
down_revision: Union[str, None] = "0004_employee"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TS = postgresql.TIMESTAMP(timezone=True)

# audit_action is created explicitly; the column references it with create_type=False.
audit_action = postgresql.ENUM(
    "role_promoted", "role_demoted", "status_activated", "status_deactivated",
    name="audit_action", create_type=False,
)
# Existing user_role type, referenced (not created) by audit_logs.old/new_role.
user_role_ref = postgresql.ENUM(name="user_role", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Remove the platform super admin (NULL org) before tightening constraints.
    op.execute("DELETE FROM users WHERE role = 'super_admin' AND organization_id IS NULL")

    # 2. Drop the old role/org consistency CHECK and the super-admin email index.
    op.drop_constraint("ck_users_org_role_consistency", "users", type_="check")
    op.drop_index("uq_users_email_superadmin", table_name="users")

    # 3. Swap user_role {super_admin, org_admin, employee} -> {admin, employee}.
    #    Postgres can't drop enum values in place, so build a new type and remap.
    op.execute("CREATE TYPE user_role_new AS ENUM ('admin', 'employee')")
    op.execute(
        "ALTER TABLE users ALTER COLUMN role TYPE user_role_new USING ("
        "  CASE role::text"
        "    WHEN 'org_admin' THEN 'admin'"
        "    WHEN 'super_admin' THEN 'admin'"
        "    ELSE 'employee'"
        "  END"
        ")::user_role_new"
    )
    op.execute("DROP TYPE user_role")
    op.execute("ALTER TYPE user_role_new RENAME TO user_role")

    # 4. Every user belongs to an organization.
    op.alter_column(
        "users", "organization_id",
        existing_type=postgresql.UUID(as_uuid=True), nullable=False,
    )

    # 5. Audit log.
    audit_action.create(bind, checkfirst=True)
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("performed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("affected_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", audit_action, nullable=False),
        sa.Column("old_role", user_role_ref),
        sa.Column("new_role", user_role_ref),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_audit_logs_organization_id", "audit_logs", ["organization_id"])
    op.create_index("ix_audit_logs_performed_by_user_id", "audit_logs", ["performed_by_user_id"])
    op.create_index("ix_audit_logs_affected_user_id", "audit_logs", ["affected_user_id"])


def downgrade() -> None:
    bind = op.get_bind()

    # 5. Drop the audit log.
    op.drop_index("ix_audit_logs_affected_user_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_performed_by_user_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_organization_id", table_name="audit_logs")
    op.drop_table("audit_logs")
    audit_action.drop(bind, checkfirst=True)

    # 4. organization_id becomes nullable again.
    op.alter_column(
        "users", "organization_id",
        existing_type=postgresql.UUID(as_uuid=True), nullable=True,
    )

    # 3. Revert the enum: {admin, employee} -> {super_admin, org_admin, employee}.
    #    admin maps back to org_admin (the deleted super_admin cannot be restored).
    op.execute("CREATE TYPE user_role_old AS ENUM ('super_admin', 'org_admin', 'employee')")
    op.execute(
        "ALTER TABLE users ALTER COLUMN role TYPE user_role_old USING ("
        "  CASE role::text WHEN 'admin' THEN 'org_admin' ELSE 'employee' END"
        ")::user_role_old"
    )
    op.execute("DROP TYPE user_role")
    op.execute("ALTER TYPE user_role_old RENAME TO user_role")

    # 2. Restore the super-admin partial email index and the role/org CHECK.
    op.create_index(
        "uq_users_email_superadmin", "users", ["email"], unique=True,
        postgresql_where=sa.text("organization_id IS NULL"),
    )
    op.create_check_constraint(
        "ck_users_org_role_consistency", "users",
        "(role = 'super_admin' AND organization_id IS NULL) "
        "OR (role <> 'super_admin' AND organization_id IS NOT NULL)",
    )
