"""Organization (tenant) model — the root of every tenant-scoped record."""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, List

from sqlalchemy import Date, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import SubscriptionStatus, pg_enum

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.invoice import Invoice
    from app.models.user import User
    from app.models.work_order import WorkOrder


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(40))
    address: Mapped[str | None] = mapped_column(Text)
    gst_number: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    subscription_status: Mapped[SubscriptionStatus] = mapped_column(
        pg_enum(SubscriptionStatus, "subscription_status"),
        default=SubscriptionStatus.TRIAL,
        nullable=False,
    )
    subscription_expires_at: Mapped[date | None] = mapped_column(Date)

    # ---- Relationships ----
    users: Mapped[List["User"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    customers: Mapped[List["Customer"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    work_orders: Mapped[List["WorkOrder"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    invoices: Mapped[List["Invoice"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
