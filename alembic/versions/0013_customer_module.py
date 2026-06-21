"""Customer module: expand the customers master + customer audit trail.

Revision ID: 0013_customer_module
Revises: 0012_drop_user_status
Create Date: 2026-06-13

Grows the minimal ``customers`` table into the full client master Elangovan
Associates maintains (GST + Income-Tax registers):

- New ``customer_type`` enum (gst / income_tax).
- Renames the legacy columns to the master vocabulary
  (``name`` -> ``client_name``, ``phone`` -> ``mobile_number``,
  ``address`` -> ``address_line_1``) and adds business / tax / address fields,
  a per-org ``customer_code`` (CUS-0001), ``date_of_birth``, ``remarks`` and
  ``created_by``.
- Backfills ``customer_code`` (sequential per organization) and ``customer_type``
  (gst when a GST number is present, else income_tax) for any existing rows, then
  makes both NOT NULL and adds the per-org unique code constraint.
- Extends ``audit_logs`` with ``customer_id`` + ``entity_name`` and registers the
  five customer audit actions (Postgres can't drop enum values later, but these
  are first-class for the customer module).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_customer_module"
down_revision: Union[str, None] = "0012_drop_user_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

customer_type = postgresql.ENUM("gst", "income_tax", name="customer_type", create_type=False)

_CUSTOMER_AUDIT_ACTIONS = (
    "customer_created",
    "customer_updated",
    "customer_deleted",
    "customer_activated",
    "customer_deactivated",
)


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Customer category enum.
    customer_type.create(bind, checkfirst=True)

    # 2. Rename legacy columns to the master vocabulary.
    op.alter_column("customers", "name", new_column_name="client_name")
    op.alter_column("customers", "phone", new_column_name="mobile_number")
    op.alter_column("customers", "address", new_column_name="address_line_1")

    # 3. Add the new columns (nullable for now so existing rows survive).
    op.add_column("customers", sa.Column("customer_code", sa.String(20)))
    op.add_column("customers", sa.Column("customer_type", customer_type))
    op.add_column("customers", sa.Column("business_name", sa.String(255)))
    op.add_column("customers", sa.Column("proprietor_name", sa.String(255)))
    op.add_column("customers", sa.Column("alternate_mobile_number", sa.String(40)))
    op.add_column("customers", sa.Column("date_of_birth", sa.Date()))
    op.add_column("customers", sa.Column("pan_number", sa.String(20)))
    op.add_column("customers", sa.Column("aadhaar_number", sa.String(20)))
    op.add_column("customers", sa.Column("address_line_2", sa.Text()))
    op.add_column("customers", sa.Column("city", sa.String(120)))
    op.add_column("customers", sa.Column("state", sa.String(120)))
    op.add_column("customers", sa.Column("pincode", sa.String(12)))
    op.add_column("customers", sa.Column("remarks", sa.Text()))
    op.add_column(
        "customers",
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
    )

    # 4. Backfill required columns for any pre-existing rows.
    op.execute(
        """
        UPDATE customers SET customer_type = (
            CASE WHEN gst_number IS NOT NULL AND gst_number <> ''
                 THEN 'gst' ELSE 'income_tax' END
        )::customer_type
        WHERE customer_type IS NULL
        """
    )
    op.execute(
        """
        WITH numbered AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY organization_id ORDER BY created_at, id
                   ) AS rn
            FROM customers
        )
        UPDATE customers c
        SET customer_code = 'CUS-' || LPAD(numbered.rn::text, 4, '0')
        FROM numbered
        WHERE c.id = numbered.id AND c.customer_code IS NULL
        """
    )

    # 5. Enforce NOT NULL + per-org uniqueness of the code.
    op.alter_column("customers", "customer_code", existing_type=sa.String(20), nullable=False)
    op.alter_column("customers", "customer_type", existing_type=customer_type, nullable=False)
    op.create_unique_constraint(
        "uq_customers_org_code", "customers", ["organization_id", "customer_code"]
    )

    # 6. Lookup indexes (search by code / type / mobile / GST / PAN / city).
    op.create_index("ix_customers_customer_code", "customers", ["customer_code"])
    op.create_index("ix_customers_customer_type", "customers", ["customer_type"])
    op.create_index("ix_customers_mobile_number", "customers", ["mobile_number"])
    op.create_index("ix_customers_gst_number", "customers", ["gst_number"])
    op.create_index("ix_customers_pan_number", "customers", ["pan_number"])
    op.create_index("ix_customers_city", "customers", ["city"])

    # 7. Customer audit trail: reference the customer + snapshot its name.
    op.add_column(
        "audit_logs",
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="SET NULL"),
        ),
    )
    op.add_column("audit_logs", sa.Column("entity_name", sa.String(255)))
    op.create_index("ix_audit_logs_customer_id", "audit_logs", ["customer_id"])

    # 8. Register the customer audit actions (no-op if already present).
    for value in _CUSTOMER_AUDIT_ACTIONS:
        op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_index("ix_audit_logs_customer_id", table_name="audit_logs")
    op.drop_column("audit_logs", "entity_name")
    op.drop_column("audit_logs", "customer_id")

    op.drop_index("ix_customers_city", table_name="customers")
    op.drop_index("ix_customers_pan_number", table_name="customers")
    op.drop_index("ix_customers_gst_number", table_name="customers")
    op.drop_index("ix_customers_mobile_number", table_name="customers")
    op.drop_index("ix_customers_customer_type", table_name="customers")
    op.drop_index("ix_customers_customer_code", table_name="customers")
    op.drop_constraint("uq_customers_org_code", "customers", type_="unique")

    op.drop_column("customers", "created_by")
    op.drop_column("customers", "remarks")
    op.drop_column("customers", "pincode")
    op.drop_column("customers", "state")
    op.drop_column("customers", "city")
    op.drop_column("customers", "address_line_2")
    op.drop_column("customers", "aadhaar_number")
    op.drop_column("customers", "pan_number")
    op.drop_column("customers", "date_of_birth")
    op.drop_column("customers", "alternate_mobile_number")
    op.drop_column("customers", "proprietor_name")
    op.drop_column("customers", "business_name")
    op.drop_column("customers", "customer_type")
    op.drop_column("customers", "customer_code")

    op.alter_column("customers", "address_line_1", new_column_name="address")
    op.alter_column("customers", "mobile_number", new_column_name="phone")
    op.alter_column("customers", "client_name", new_column_name="name")

    customer_type.drop(bind, checkfirst=True)
    # Note: Postgres can't drop enum values, so the customer_* audit actions remain.
