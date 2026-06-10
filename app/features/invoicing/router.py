"""Public Invoice API (``/api/v1/invoicing``) — no authentication required."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.features.invoicing import schemas
from app.features.invoicing.service import InvoiceService

router = APIRouter(prefix="/invoicing", tags=["Invoicing (public)"])


def get_service(db: Session = Depends(get_db)) -> InvoiceService:
    return InvoiceService(db)


@router.get("/next-number", response_model=schemas.NextNumberResponse)
def next_number(
    invoice_date: date | None = Query(default=None),
    service: InvoiceService = Depends(get_service),
) -> schemas.NextNumberResponse:
    """Suggest the next auto-generated invoice number for a date (default today)."""
    target = invoice_date or datetime.now(timezone.utc).date()
    return schemas.NextNumberResponse(invoice_number=service.next_number(target))


@router.post("/invoices", response_model=schemas.InvoiceRead, status_code=status.HTTP_201_CREATED)
def create_invoice(
    data: schemas.InvoiceCreate,
    service: InvoiceService = Depends(get_service),
) -> schemas.InvoiceRead:
    """Create and persist an invoice. Totals are computed server-side."""
    return schemas.InvoiceRead.model_validate(service.create(data))


@router.get("/invoices", response_model=list[schemas.InvoiceListItem])
def list_invoices(
    service: InvoiceService = Depends(get_service),
) -> list[schemas.InvoiceListItem]:
    return [schemas.InvoiceListItem.model_validate(r) for r in service.list()]


@router.get("/invoices/{invoice_id}", response_model=schemas.InvoiceRead)
def get_invoice(
    invoice_id: uuid.UUID,
    service: InvoiceService = Depends(get_service),
) -> schemas.InvoiceRead:
    return schemas.InvoiceRead.model_validate(service.get(invoice_id))
