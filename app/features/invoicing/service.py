"""Invoice module business logic (no authentication / no tenancy).

Totals are always computed here from the line items + MCA charge + discount, so
the persisted figures can never disagree with the inputs even if a client sends
wrong totals:

    gross_total     = sum(item.amount) + mca_charges
    discount_amount = gross_total * discount_percent / 100   (rounded, 2dp)
    net_total       = gross_total - discount_amount
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError
from app.features.invoicing import schemas
from app.models.invoice_record import InvoiceLineItem, InvoiceRecord

_CENTS = Decimal("0.01")
_MAX_NUMBER_RETRIES = 5


def _money(value: Decimal) -> Decimal:
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


def compute_totals(
    items: list[schemas.LineItemIn], mca_charges: Decimal, discount_percent: Decimal
) -> tuple[Decimal, Decimal, Decimal]:
    services = sum((i.amount for i in items), Decimal("0"))
    gross = _money(services + mca_charges)
    discount_amount = _money(gross * discount_percent / Decimal("100"))
    net = _money(gross - discount_amount)
    return gross, discount_amount, net


class InvoiceService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def next_number(self, invoice_date: date) -> str:
        """Next ``{PREFIX}-YYYYMMDD-NNN`` for the given date (NNN resets per date)."""
        prefix = f"{settings.INVOICE_NUMBER_PREFIX}-{invoice_date:%Y%m%d}-"
        rows = self.db.execute(
            select(InvoiceRecord.invoice_number).where(
                InvoiceRecord.invoice_number.like(prefix + "%")
            )
        ).scalars().all()
        max_seq = 0
        for number in rows:
            tail = (number or "").rsplit("-", 1)[-1]
            if tail.isdigit():
                max_seq = max(max_seq, int(tail))
        return f"{prefix}{max_seq + 1:03d}"

    def create(self, data: schemas.InvoiceCreate) -> InvoiceRecord:
        gross, discount_amount, net = compute_totals(
            data.items, data.mca_charges, data.discount_percent
        )

        def build(number: str) -> InvoiceRecord:
            return InvoiceRecord(
                invoice_number=number,
                invoice_date=data.invoice_date,
                customer_name=data.customer_name.strip(),
                customer_address=(data.customer_address or "").strip() or None,
                mca_charges=data.mca_charges,
                discount_percent=data.discount_percent,
                gross_total=gross,
                discount_amount=discount_amount,
                net_total=net,
                items=[
                    InvoiceLineItem(
                        position=idx,
                        description=item.description.strip(),
                        amount=item.amount,
                    )
                    for idx, item in enumerate(data.items)
                ],
            )

        explicit = (data.invoice_number or "").strip()

        # Explicit number: store as-is, surface a clean conflict on duplicates.
        if explicit:
            record = build(explicit)
            self.db.add(record)
            try:
                self.db.commit()
            except IntegrityError as exc:
                self.db.rollback()
                raise ConflictError(
                    f"An invoice with number '{explicit}' already exists"
                ) from exc
            self.db.refresh(record)
            return record

        # Auto-generated number: retry on the rare concurrent-collision.
        for attempt in range(_MAX_NUMBER_RETRIES):
            record = build(self.next_number(data.invoice_date))
            self.db.add(record)
            try:
                self.db.commit()
            except IntegrityError:
                self.db.rollback()
                if attempt == _MAX_NUMBER_RETRIES - 1:
                    raise ConflictError("Could not allocate an invoice number")
                continue
            self.db.refresh(record)
            return record
        raise ConflictError("Could not allocate an invoice number")  # pragma: no cover

    def get(self, invoice_id: uuid.UUID) -> InvoiceRecord:
        record = self.db.get(InvoiceRecord, invoice_id)
        if record is None:
            raise NotFoundError("Invoice not found")
        return record

    def list(self, *, limit: int = 100) -> list[InvoiceRecord]:
        rows = self.db.execute(
            select(InvoiceRecord).order_by(InvoiceRecord.created_at.desc()).limit(limit)
        ).scalars().all()
        return list(rows)
