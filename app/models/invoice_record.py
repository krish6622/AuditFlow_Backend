"""Standalone (auth-free) invoice documents for the printable Invoice module.

Kept separate from the org-scoped ``Invoice``/``InvoiceItem`` aggregate so this
public module never depends on tenancy or authentication. Monetary values use
``Numeric`` (never float). Totals are computed and stored server-side.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, List

from sqlalchemy import Date, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    pass


class InvoiceRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "invoice_records"

    invoice_number: Mapped[str] = mapped_column(String(60), nullable=False, unique=True, index=True)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_address: Mapped[str | None] = mapped_column(Text)

    mca_charges: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"), nullable=False)

    gross_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    net_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)

    items: Mapped[List["InvoiceLineItem"]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceLineItem.position",
    )


class InvoiceLineItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "invoice_line_items"

    invoice_record_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("invoice_records.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    position: Mapped[int] = mapped_column(default=0, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)

    invoice: Mapped["InvoiceRecord"] = relationship(back_populates="items")
