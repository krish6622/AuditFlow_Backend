"""Tests for the one-time customer seed: header mapping + duplicate detection.

The dedup logic (GST > PAN > Mobile > Email) is exercised directly through the
importer's ``_import_register`` with synthetic rows, so no network/sheet access
is needed. DB-backed tests require ``TEST_DATABASE_URL`` (see conftest).
"""
from __future__ import annotations

from app.features.customers.repository import CustomerRepository
from app.features.customers.seed import _build_header_map, _import_register
from app.models.customer import Customer
from app.models.enums import CustomerType


# --------------------------------------------------------------------------- #
# Header mapping (pure, no DB)
# --------------------------------------------------------------------------- #
def test_header_map_disambiguates_similar_columns() -> None:
    headers = [
        "Client Name", "Business Name", "Mobile No", "Alternate Mobile",
        "Email ID", "GSTIN", "PAN No", "Aadhaar", "Date of Birth",
        "Address Line 1", "Address 2", "City", "State", "Pincode", "Remarks",
    ]
    m = _build_header_map(headers)
    assert m["client_name"] == "Client Name"
    assert m["business_name"] == "Business Name"
    assert m["mobile_number"] == "Mobile No"
    assert m["alternate_mobile_number"] == "Alternate Mobile"
    assert m["address_line_1"] == "Address Line 1"
    assert m["address_line_2"] == "Address 2"
    assert m["gst_number"] == "GSTIN"
    assert m["pan_number"] == "PAN No"


# --------------------------------------------------------------------------- #
# Duplicate detection (DB-backed)
# --------------------------------------------------------------------------- #
def _run(db_session, org_admin, customer_type, rows):
    repo = CustomerRepository(db_session)
    summary = _import_register(
        db_session,
        repo,
        organization_id=org_admin.organization_id,
        created_by=org_admin.id,
        customer_type=customer_type,
        rows=rows,
    )
    db_session.commit()
    return summary


def test_seed_creates_then_dedups_by_gst(client, org_admin, db_session) -> None:
    rows = [
        {"Client Name": "Ramesh Traders", "GSTIN": "33ABCDE1234F1Z5", "Mobile": "9876500001"},
    ]
    s1 = _run(db_session, org_admin, CustomerType.GST, rows)
    assert (s1.created, s1.updated, s1.skipped) == (1, 0, 0)

    # Same GST again, no new info -> skipped (exact duplicate).
    s2 = _run(db_session, org_admin, CustomerType.GST, rows)
    assert (s2.created, s2.skipped) == (0, 1)

    # Same GST, new blank field (email) -> updates the missing field only.
    rows_more = [
        {"Client Name": "Ramesh Traders", "GSTIN": "33ABCDE1234F1Z5", "Email": "ramesh@example.com"},
    ]
    s3 = _run(db_session, org_admin, CustomerType.GST, rows_more)
    assert s3.updated == 1

    customers = CustomerRepository(db_session).list(organization_id=org_admin.organization_id)
    assert len(customers) == 1
    assert customers[0].email == "ramesh@example.com"
    assert customers[0].customer_code == "CUS-0001"


def test_seed_dedup_priority_pan_then_mobile(client, org_admin, db_session) -> None:
    # Seed one with PAN + mobile.
    _run(
        db_session, org_admin, CustomerType.INCOME_TAX,
        [{"Client Name": "Beta", "PAN No": "ABCDE1234F", "Mobile": "9000000002"}],
    )
    # New row, no GST, same PAN -> matches by PAN (not a new record).
    s = _run(
        db_session, org_admin, CustomerType.INCOME_TAX,
        [{"Client Name": "Beta Renamed", "PAN No": "ABCDE1234F", "City": "Salem"}],
    )
    assert s.created == 0 and s.updated == 1
    customers = CustomerRepository(db_session).list(organization_id=org_admin.organization_id)
    assert len(customers) == 1
    # Existing client_name preserved (never renamed on import); blank city filled.
    assert customers[0].client_name == "Beta"
    assert customers[0].city == "Salem"


def test_seed_distinct_records_when_no_match(client, org_admin, db_session) -> None:
    s = _run(
        db_session, org_admin, CustomerType.GST,
        [
            {"Client Name": "One", "GSTIN": "33AAAAA0000A1Z5"},
            {"Client Name": "Two", "GSTIN": "33BBBBB0000B1Z5"},
        ],
    )
    assert s.created == 2
    codes = sorted(
        c.customer_code
        for c in CustomerRepository(db_session).list(organization_id=org_admin.organization_id)
    )
    assert codes == ["CUS-0001", "CUS-0002"]
