"""Work order aggregate: the order plus its notes, attachments, and timeline."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, List

from sqlalchemy import Date, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    WorkOrderCategory,
    WorkOrderPriority,
    WorkOrderStatus,
    pg_enum,
)

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.invoice import Invoice
    from app.models.organization import Organization
    from app.models.user import User


class WorkOrder(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "work_orders"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    number: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)  # "Work Description"

    # Service category (auditor office). ``category_other`` holds the free-text
    # description when category is OTHERS. Nullable so legacy rows remain valid.
    category: Mapped[WorkOrderCategory | None] = mapped_column(
        pg_enum(WorkOrderCategory, "work_order_category")
    )
    category_other: Mapped[str | None] = mapped_column(String(120))

    # The date the order was raised (paper-form "Date"); defaults to today.
    order_date: Mapped[date | None] = mapped_column(Date)

    # Free-text contact fields used by the Work Orders module. The normalized
    # FK columns below remain for future Customer/Employee management features.
    customer_name: Mapped[str | None] = mapped_column(String(255))
    contact_number: Mapped[str] = mapped_column(String(40), nullable=False)
    assigned_employee_name: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)

    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        index=True,
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    # The employee who raised the request (auditor-office workflow). NULL for
    # legacy/admin-created orders.
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )

    status: Mapped[WorkOrderStatus] = mapped_column(
        pg_enum(WorkOrderStatus, "work_order_status"),
        default=WorkOrderStatus.AWAITING_ASSIGNMENT,
        nullable=False,
    )
    priority: Mapped[WorkOrderPriority] = mapped_column(
        pg_enum(WorkOrderPriority, "work_order_priority"),
        default=WorkOrderPriority.MEDIUM,
        nullable=False,
    )
    due_date: Mapped[date | None] = mapped_column(Date)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    organization: Mapped["Organization"] = relationship(back_populates="work_orders")
    customer: Mapped["Customer"] = relationship(back_populates="work_orders")
    assignee: Mapped["User | None"] = relationship(
        back_populates="assigned_work_orders", foreign_keys=[assignee_id]
    )
    requested_by: Mapped["User | None"] = relationship(foreign_keys=[requested_by_id])
    note_entries: Mapped[List["WorkOrderNote"]] = relationship(
        back_populates="work_order", cascade="all, delete-orphan"
    )
    attachments: Mapped[List["WorkOrderAttachment"]] = relationship(
        back_populates="work_order", cascade="all, delete-orphan"
    )
    history: Mapped[List["WorkOrderEvent"]] = relationship(
        back_populates="work_order",
        cascade="all, delete-orphan",
        order_by="WorkOrderEvent.created_at",
    )
    invoice: Mapped["Invoice | None"] = relationship(back_populates="work_order")


class WorkOrderNote(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "work_order_notes"

    work_order_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("work_orders.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)

    work_order: Mapped["WorkOrder"] = relationship(back_populates="note_entries")


class WorkOrderAttachment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "work_order_attachments"

    work_order_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("work_orders.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    # Object key in Cloudflare R2; never a public URL (signed on read).
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120))
    size_bytes: Mapped[int | None] = mapped_column()

    work_order: Mapped["WorkOrder"] = relationship(back_populates="attachments")


class WorkOrderEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Immutable timeline entry (status changes, assignment, completion, …)."""

    __tablename__ = "work_order_events"

    work_order_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("work_orders.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    message: Mapped[str | None] = mapped_column(Text)

    work_order: Mapped["WorkOrder"] = relationship(back_populates="history")
