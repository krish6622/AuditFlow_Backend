"""Initial schema: organizations, users, tokens, customers, work orders, invoices.

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-09
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Native enum types (created once, reused by columns via create_type=False).
subscription_status = postgresql.ENUM(
    "trial", "active", "past_due", "cancelled",
    name="subscription_status", create_type=False,
)
user_role = postgresql.ENUM(
    "super_admin", "org_admin", "employee",
    name="user_role", create_type=False,
)
work_order_status = postgresql.ENUM(
    "assigned", "in_progress", "completed", "cancelled",
    name="work_order_status", create_type=False,
)
work_order_priority = postgresql.ENUM(
    "low", "medium", "high",
    name="work_order_priority", create_type=False,
)
invoice_status = postgresql.ENUM(
    "draft", "issued", "paid", "cancelled",
    name="invoice_status", create_type=False,
)

_TS = postgresql.TIMESTAMP(timezone=True)


def upgrade() -> None:
    bind = op.get_bind()

    # gen_random_uuid() is core in PG13+, but ensure pgcrypto for older servers.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    for enum in (
        subscription_status, user_role, work_order_status,
        work_order_priority, invoice_status,
    ):
        enum.create(bind, checkfirst=True)

    # ------------------------------------------------------------------ #
    # organizations
    # ------------------------------------------------------------------ #
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False),
        sa.Column("email", sa.String(255)),
        sa.Column("phone", sa.String(40)),
        sa.Column("address", sa.Text()),
        sa.Column("gst_number", sa.String(20)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("subscription_status", subscription_status, nullable=False, server_default="trial"),
        sa.Column("subscription_expires_at", sa.Date()),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)

    # ------------------------------------------------------------------ #
    # users
    # ------------------------------------------------------------------ #
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE")),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(40)),
        sa.Column("role", user_role, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("organization_id", "email", name="uq_users_org_email"),
        sa.CheckConstraint(
            "(role = 'super_admin' AND organization_id IS NULL) "
            "OR (role <> 'super_admin' AND organization_id IS NOT NULL)",
            name="ck_users_org_role_consistency",
        ),
    )
    op.create_index("ix_users_organization_id", "users", ["organization_id"])
    op.create_index("ix_users_email", "users", ["email"])
    # Super admins have NULL org, so the composite unique can't enforce email
    # uniqueness for them — a partial unique index does.
    op.create_index(
        "uq_users_email_superadmin",
        "users",
        ["email"],
        unique=True,
        postgresql_where=sa.text("organization_id IS NULL"),
    )

    # ------------------------------------------------------------------ #
    # refresh_tokens
    # ------------------------------------------------------------------ #
    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("jti", sa.String(64), nullable=False),
        sa.Column("expires_at", _TS, nullable=False),
        sa.Column("revoked_at", _TS),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_jti", "refresh_tokens", ["jti"], unique=True)

    # ------------------------------------------------------------------ #
    # password_reset_tokens
    # ------------------------------------------------------------------ #
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("jti", sa.String(64), nullable=False),
        sa.Column("expires_at", _TS, nullable=False),
        sa.Column("used_at", _TS),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])
    op.create_index("ix_password_reset_tokens_jti", "password_reset_tokens", ["jti"], unique=True)

    # ------------------------------------------------------------------ #
    # customers
    # ------------------------------------------------------------------ #
    op.create_table(
        "customers",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255)),
        sa.Column("phone", sa.String(40)),
        sa.Column("address", sa.Text()),
        sa.Column("gst_number", sa.String(20)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_customers_organization_id", "customers", ["organization_id"])

    # ------------------------------------------------------------------ #
    # work_orders
    # ------------------------------------------------------------------ #
    op.create_table(
        "work_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.String(40), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("assignee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("status", work_order_status, nullable=False, server_default="assigned"),
        sa.Column("priority", work_order_priority, nullable=False, server_default="medium"),
        sa.Column("due_date", _TS),
        sa.Column("completed_at", _TS),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_work_orders_organization_id", "work_orders", ["organization_id"])
    op.create_index("ix_work_orders_number", "work_orders", ["number"])
    op.create_index("ix_work_orders_customer_id", "work_orders", ["customer_id"])
    op.create_index("ix_work_orders_assignee_id", "work_orders", ["assignee_id"])
    op.create_unique_constraint("uq_work_orders_org_number", "work_orders", ["organization_id", "number"])

    # ------------------------------------------------------------------ #
    # work_order_notes / attachments / events
    # ------------------------------------------------------------------ #
    op.create_table(
        "work_order_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("work_order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_work_order_notes_work_order_id", "work_order_notes", ["work_order_id"])

    op.create_table(
        "work_order_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("work_order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uploaded_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(120)),
        sa.Column("size_bytes", sa.Integer()),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_work_order_attachments_work_order_id", "work_order_attachments", ["work_order_id"])

    op.create_table(
        "work_order_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("work_order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("event_type", sa.String(60), nullable=False),
        sa.Column("message", sa.Text()),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_work_order_events_work_order_id", "work_order_events", ["work_order_id"])

    # ------------------------------------------------------------------ #
    # invoices / invoice_items
    # ------------------------------------------------------------------ #
    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.String(40), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("work_order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("work_orders.id", ondelete="SET NULL"), unique=True),
        sa.Column("status", invoice_status, nullable=False, server_default="draft"),
        sa.Column("issue_date", sa.Date()),
        sa.Column("due_date", sa.Date()),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("tax_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text()),
        sa.Column("pdf_storage_key", sa.String(512)),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("organization_id", "number", name="uq_invoices_org_number"),
    )
    op.create_index("ix_invoices_organization_id", "invoices", ["organization_id"])
    op.create_index("ix_invoices_number", "invoices", ["number"])

    op.create_table(
        "invoice_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("tax_rate", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("line_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_invoice_items_invoice_id", "invoice_items", ["invoice_id"])


def downgrade() -> None:
    op.drop_table("invoice_items")
    op.drop_table("invoices")
    op.drop_table("work_order_events")
    op.drop_table("work_order_attachments")
    op.drop_table("work_order_notes")
    op.drop_table("work_orders")
    op.drop_table("customers")
    op.drop_table("password_reset_tokens")
    op.drop_table("refresh_tokens")
    op.drop_table("users")
    op.drop_table("organizations")

    bind = op.get_bind()
    for enum in (
        invoice_status, work_order_priority, work_order_status,
        user_role, subscription_status,
    ):
        enum.drop(bind, checkfirst=True)
