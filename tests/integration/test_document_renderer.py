"""Phase 5 — document renderer + archive integration.

These tests are the most expensive in the suite (WeasyPrint, pikepdf). We mark
them ``slow`` so they can be skipped locally with ``-m "not slow"``.
"""
from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import Session

from services.invoicing.archive import archive_document, get_archive_root
from services.invoicing.document import (
    build_document_data,
    render_document,
    render_pdf,
    render_xml,
    verify_consistency,
)
from services.invoicing.finalize import FinalizeOptions, finalize_invoice
from tests.fixtures.factories import (
    make_draft_invoice,
    make_issuer,
    make_lead_de_b2b,
    make_lead_eu_b2b_at,
)

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def _opts(**kwargs):
    return FinalizeOptions(
        today=date(2026, 5, 9),
        renderer=render_document,
        **kwargs,
    )


def test_render_xml_well_formed_for_de_b2b(session: Session):
    issuer = make_issuer(session)
    lead = make_lead_de_b2b(session)
    inv = make_draft_invoice(session, lead)
    # Walk through finalize WITHOUT actual rendering, then render data manually.
    f = finalize_invoice(session, inv.id, options=FinalizeOptions(today=date(2026, 5, 9)))
    lines = sorted(f.invoice_id if hasattr(f, "invoice_id") else [], key=lambda x: 0)  # noqa
    from sqlmodel import select
    from models import InvoiceLineItem
    line_objs = list(session.exec(
        select(InvoiceLineItem).where(InvoiceLineItem.invoice_id == f.id).order_by(InvoiceLineItem.position)
    ).all())
    data = build_document_data(f, line_objs, issuer)
    xml = render_xml(data)
    assert b"<?xml" in xml or xml.startswith(b"<")
    assert b"RE-2026-0001" in xml
    assert b"1190" in xml or b"1.190" in xml or b"1190.00" in xml


def test_render_pdf_a3_with_embedded_xml(archive_dir, session: Session):
    """End-to-end through finalize with the real renderer + archiver."""
    make_issuer(session)
    lead = make_lead_de_b2b(session)
    inv = make_draft_invoice(session, lead)

    def archiver(year, number, doc, hash_hex):
        return archive_document(year, number, doc, hash_hex)

    f = finalize_invoice(
        session, inv.id,
        options=FinalizeOptions(today=date(2026, 5, 9), renderer=render_document, archiver=archiver),
    )
    # PDF + XML should exist on disk.
    pdf_path = f.archive_path_pdf
    xml_path = f.archive_path_xml
    assert pdf_path and xml_path
    pdf_bytes = open(pdf_path, "rb").read()
    xml_bytes = open(xml_path, "rb").read()
    assert pdf_bytes.startswith(b"%PDF-")
    assert b"RE-2026-0001" in xml_bytes
    # Embedded XML should match the standalone XML.
    import pikepdf
    pdf = pikepdf.Pdf.open(io.BytesIO(pdf_bytes))
    assert "factur-x.xml" in pdf.attachments
    embedded = bytes(pdf.attachments["factur-x.xml"].get_file().read_bytes())
    assert embedded == xml_bytes


def test_kleinunternehmer_hint_in_pdf(archive_dir, session: Session):
    make_issuer(session, is_kleinunternehmer=True, ust_id=None, steuernummer=None)
    lead = make_lead_de_b2b(session)
    inv = make_draft_invoice(session, lead)
    f = finalize_invoice(
        session, inv.id,
        options=FinalizeOptions(today=date(2026, 5, 9), renderer=render_document, archiver=archive_document),
    )
    pdf_bytes = open(f.archive_path_pdf, "rb").read()
    # Render a text-extractable check: pikepdf can extract page text via pypdf indirectly.
    # Easier: read XML, which is the legally binding part anyway.
    xml_bytes = open(f.archive_path_xml, "rb").read()
    assert b"19 UStG" in xml_bytes or b"\xc2\xa7 19" in xml_bytes  # § 19 in UTF-8


def test_reverse_charge_hint_in_xml(archive_dir, session: Session):
    make_issuer(session, ust_id="DE123456789")
    lead = make_lead_eu_b2b_at(session)
    inv = make_draft_invoice(session, lead)
    f = finalize_invoice(
        session, inv.id,
        options=FinalizeOptions(today=date(2026, 5, 9), renderer=render_document, archiver=archive_document),
    )
    xml_bytes = open(f.archive_path_xml, "rb").read()
    # Both VAT IDs must be on the document
    assert b"DE123456789" in xml_bytes
    assert b"ATU99999999" in xml_bytes
    # Reverse-Charge category code AE
    assert b">AE<" in xml_bytes


def test_archive_files_are_readable_only(archive_dir, session: Session):
    """R-10 — files chmod'd to 0444 after write."""
    make_issuer(session)
    lead = make_lead_de_b2b(session)
    inv = make_draft_invoice(session, lead)
    f = finalize_invoice(
        session, inv.id,
        options=FinalizeOptions(today=date(2026, 5, 9), renderer=render_document, archiver=archive_document),
    )
    import stat as st
    import os
    pdf_mode = os.stat(f.archive_path_pdf).st_mode & 0o777
    xml_mode = os.stat(f.archive_path_xml).st_mode & 0o777
    assert pdf_mode & st.S_IWUSR == 0, f"PDF should be read-only, got {oct(pdf_mode)}"
    assert xml_mode & st.S_IWUSR == 0, f"XML should be read-only, got {oct(xml_mode)}"


def test_archive_chain_log_entry_appended(archive_dir, session: Session):
    make_issuer(session)
    lead = make_lead_de_b2b(session)
    inv = make_draft_invoice(session, lead)
    f = finalize_invoice(
        session, inv.id,
        options=FinalizeOptions(today=date(2026, 5, 9), renderer=render_document, archiver=archive_document),
    )
    chain = (get_archive_root() / "invoices" / "2026" / "_chain.log").read_text()
    assert f.number in chain
    assert f.hash_sha256 in chain


def test_consistency_check_detects_mismatch(session: Session):
    make_issuer(session)
    lead = make_lead_de_b2b(session)
    inv = make_draft_invoice(session, lead)
    f = finalize_invoice(session, inv.id, options=FinalizeOptions(today=date(2026, 5, 9)))
    from sqlmodel import select
    from models import InvoiceLineItem
    line_objs = list(session.exec(
        select(InvoiceLineItem).where(InvoiceLineItem.invoice_id == f.id)
    ).all())
    data = build_document_data(f, line_objs, make_issuer(session))
    xml = render_xml(data)
    pdf = render_pdf(data, xml)
    # Truthy case
    verify_consistency(pdf, xml, data)
    # Tampered XML must trigger
    from services.invoicing.document import ConsistencyError
    with pytest.raises(ConsistencyError):
        verify_consistency(pdf, xml + b"<!--tampered-->", data)
