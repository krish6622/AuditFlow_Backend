"""Customer model — tenant-scoped client master record.

Elangovan Associates keeps two client registers (GST and Income-Tax); both live
here, distinguished by ``customer_type``. A customer is the single source of
truth a work order or invoice is raised against — its contact and tax details
are looked up, never re-typed. Each carries a human-friendly per-org code
(``CUS-0001``). ``is_active`` is the lifecycle flag (surfaced as ACTIVE/INACTIVE).
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING, List

from sqlalchemy import Boolean, Date, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import CustomerType, pg_enum

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.invoice import Invoice
    from app.models.user import User
    from app.models.work_order import WorkOrder


class Customer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (
        # Customer codes (CUS-0001) are unique within an organization.
        UniqueConstraint(
            "organization_id", "customer_code", name="uq_customers_org_code"
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # Human-friendly sequential identifier, e.g. "CUS-0001" (per organization).
    customer_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    customer_type: Mapped[CustomerType] = mapped_column(
        pg_enum(CustomerType, "customer_type"), nullable=False, index=True
    )

    # ---- Basic information ----
    client_name: Mapped[str] = mapped_column(String(255), nullable=False)
    business_name: Mapped[str | None] = mapped_column(String(255))
    proprietor_name: Mapped[str | None] = mapped_column(String(255))
    mobile_number: Mapped[str | None] = mapped_column(String(40), index=True)
    alternate_mobile_number: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(255))
    date_of_birth: Mapped[date | None] = mapped_column(Date)

    # ---- Tax information ----
    gst_number: Mapped[str | None] = mapped_column(String(20), index=True)
    pan_number: Mapped[str | None] = mapped_column(String(20), index=True)
    aadhaar_number: Mapped[str | None] = mapped_column(String(20))

    # ---- Address information ----
    address_line_1: Mapped[str | None] = mapped_column(Text)
    address_line_2: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(120), index=True)
    state: Mapped[str | None] = mapped_column(String(120))
    pincode: Mapped[str | None] = mapped_column(String(12))

    remarks: Mapped[str | None] = mapped_column(Text)

    # Lifecycle flag. Surfaced through the API as status ACTIVE / INACTIVE.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # The admin who created the record (history survives if that user is removed).
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    organization: Mapped["Organization"] = relationship(back_populates="customers")
    creator: Mapped["User | None"] = relationship(foreign_keys=[created_by])
    work_orders: Mapped[List["WorkOrder"]] = relationship(back_populates="customer")
    invoices: Mapped[List["Invoice"]] = relationship(back_populates="customer")
