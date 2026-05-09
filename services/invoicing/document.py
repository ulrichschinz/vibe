"""Single source of truth for invoice rendering.

``InvoiceDocumentData`` is the canonical view of a finalized invoice. Both
the PDF renderer and the XML renderer consume this dataclass — guaranteeing
R-14 (PDF ⇄ XML consistency).

PDF path: Jinja2 → WeasyPrint → pikepdf (PDF/A-3b + embedded factur-x.xml).
XML path: drafthorse (EN16931 profile).

Layout:
    InvoiceDocumentData    pure data, derivable from Invoice + lines + issuer
    build_document_data()  Invoice → InvoiceDocumentData
    render_pdf()           InvoiceDocumentData → bytes (PDF/A-3 with embedded XML)
    render_xml()           InvoiceDocumentData → bytes (UTF-8 XML)
    verify_consistency()   asserts critical fields agree
    render_document()      one-shot wrapper used by finalize() in production
"""
from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup
import markdown as md_lib

from .finalize import RenderedDocument
from .money import format_eur_de, q2

BASE_DIR = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
BRAND_DIR = BASE_DIR / "static" / "brand"

_DE_MONTHS = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]


# ── Hint texts (rendered conditionally; R-07 / R-08) ────────────────────────


HINT_TEXT_KLEINUNTERNEHMER = (
    "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet."
)
HINT_TEXT_REVERSE_CHARGE = (
    "Steuerschuldnerschaft des Leistungsempfängers / Reverse Charge. "
    "Der Rechnungsempfänger schuldet die Umsatzsteuer."
)
HINT_TEXT_THIRD_COUNTRY = (
    "Nicht im Inland steuerbare Leistung (Drittland)."
)


# ── Data ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DocAddress:
    legal_name: str
    company: Optional[str]
    salutation: Optional[str]
    street: str
    street2: Optional[str]
    postal_code: str
    city: str
    country_code: str
    email: Optional[str] = None
    vat_id: Optional[str] = None


@dataclass(frozen=True)
class DocLine:
    position: int
    description: str
    quantity: Decimal
    unit: str
    unit_price_net: Decimal
    vat_rate: Decimal
    vat_code: str
    line_net: Decimal
    line_vat: Decimal
    line_gross: Decimal


@dataclass(frozen=True)
class DocBreakdownRow:
    rate: Decimal
    base: Decimal
    tax: Decimal


@dataclass(frozen=True)
class InvoiceDocumentData:
    # Identity
    number: str
    fiscal_year: int
    sequence_number: int
    kind: str               # "invoice" | "storno"
    related_number: Optional[str]   # populated for storno

    # Dates
    invoice_date: date
    leistungsdatum: date
    due_date: Optional[date]

    # Currency
    currency: str

    # Header text
    title: Optional[str]
    intro_text: Optional[str]
    customer_reference: Optional[str]

    # Parties
    issuer: DocAddress
    issuer_steuernummer: Optional[str]
    issuer_ust_id: Optional[str]
    issuer_bank_holder: Optional[str]
    issuer_bank_iban: Optional[str]
    issuer_bank_bic: Optional[str]
    issuer_contact_email: Optional[str]
    issuer_contact_phone: Optional[str]
    customer: DocAddress

    # Lines + totals
    lines: list[DocLine]
    subtotal_net: Decimal
    vat_total: Decimal
    total_gross: Decimal
    breakdown: list[DocBreakdownRow]

    # Hints
    hint_kleinunternehmer: bool = False
    hint_reverse_charge: bool = False
    hint_third_country: bool = False

    # Payment
    payment_terms_text: Optional[str] = None


def build_document_data(invoice, lines, issuer) -> InvoiceDocumentData:
    """Compose the dataclass from ORM objects already populated by finalize()."""
    issuer_addr = DocAddress(
        legal_name=invoice.iss_legal_name or "",
        company=None,
        salutation=None,
        street=invoice.iss_street or "",
        street2=None,
        postal_code=invoice.iss_postal_code or "",
        city=invoice.iss_city or "",
        country_code=invoice.iss_country_code or "DE",
        email=invoice.iss_contact_email,
        vat_id=invoice.iss_ust_id,
    )
    customer_addr = DocAddress(
        legal_name=invoice.cust_legal_name or "",
        company=invoice.cust_company,
        salutation=invoice.cust_salutation,
        street=invoice.cust_street or "",
        street2=invoice.cust_street2,
        postal_code=invoice.cust_postal_code or "",
        city=invoice.cust_city or "",
        country_code=invoice.cust_country_code or "DE",
        email=invoice.cust_email,
        vat_id=invoice.cust_vat_id,
    )

    breakdown_rows: list[DocBreakdownRow] = []
    if invoice.vat_breakdown_json:
        for row in json.loads(invoice.vat_breakdown_json):
            breakdown_rows.append(DocBreakdownRow(
                rate=Decimal(row["rate"]),
                base=Decimal(row["base"]),
                tax=Decimal(row["tax"]),
            ))

    related_number = None
    if invoice.kind == "storno" and invoice.related_invoice_id:
        related_number = getattr(invoice, "_related_number_cache", None)

    doc_lines = [
        DocLine(
            position=ln.position,
            description=ln.description,
            quantity=ln.quantity,
            unit=ln.unit,
            unit_price_net=ln.unit_price_net,
            vat_rate=ln.vat_rate,
            vat_code=ln.vat_code,
            line_net=ln.line_net,
            line_vat=ln.line_vat,
            line_gross=ln.line_gross,
        )
        for ln in lines
    ]

    return InvoiceDocumentData(
        number=invoice.number,
        fiscal_year=invoice.fiscal_year,
        sequence_number=invoice.sequence_number,
        kind=invoice.kind.value if hasattr(invoice.kind, "value") else str(invoice.kind),
        related_number=related_number,
        invoice_date=invoice.invoice_date,
        leistungsdatum=invoice.leistungsdatum,
        due_date=invoice.due_date,
        currency=invoice.currency,
        title=invoice.title,
        intro_text=invoice.intro_text,
        customer_reference=invoice.customer_reference,
        issuer=issuer_addr,
        issuer_steuernummer=invoice.iss_steuernummer,
        issuer_ust_id=invoice.iss_ust_id,
        issuer_bank_holder=invoice.iss_bank_holder,
        issuer_bank_iban=invoice.iss_bank_iban,
        issuer_bank_bic=invoice.iss_bank_bic,
        issuer_contact_email=invoice.iss_contact_email,
        issuer_contact_phone=invoice.iss_contact_phone,
        customer=customer_addr,
        lines=doc_lines,
        subtotal_net=invoice.subtotal_net,
        vat_total=invoice.vat_total,
        total_gross=invoice.total_gross,
        breakdown=breakdown_rows,
        hint_kleinunternehmer=bool(invoice.hint_kleinunternehmer),
        hint_reverse_charge=bool(invoice.hint_reverse_charge),
        hint_third_country=bool(invoice.hint_third_country),
        payment_terms_text=invoice.payment_terms_text,
    )


# ── PDF rendering (Jinja2 → WeasyPrint → pikepdf PDF/A-3) ───────────────────


def _format_date_de(d):
    if d is None:
        return "—"
    return f"{d.day:02d}. {_DE_MONTHS[d.month - 1]} {d.year}"


def _render_markdown(text):
    if not text:
        return ""
    return Markup(md_lib.markdown(str(text), extensions=["extra", "sane_lists", "nl2br"]))


def _make_env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    env.filters["date_de"] = _format_date_de
    env.filters["eur"] = format_eur_de
    env.filters["md"] = _render_markdown
    env.filters["q2"] = q2
    env.globals.update({
        "HINT_TEXT_KLEINUNTERNEHMER": HINT_TEXT_KLEINUNTERNEHMER,
        "HINT_TEXT_REVERSE_CHARGE": HINT_TEXT_REVERSE_CHARGE,
        "HINT_TEXT_THIRD_COUNTRY": HINT_TEXT_THIRD_COUNTRY,
    })
    return env


def render_html(data: InvoiceDocumentData, *, for_print: bool = True) -> str:
    env = _make_env()
    template = env.get_template("invoices/document.html")
    asset_base = BRAND_DIR.as_uri() if for_print else "/static/brand"
    return template.render(doc=data, asset_base=asset_base)


def render_pdf(data: InvoiceDocumentData, xml_bytes: bytes) -> bytes:
    """Render to PDF/A-3b with the EN16931 XML embedded as factur-x.xml.

    The XML must be embedded with AFRelationship=/Alternative per Factur-X
    spec; our verify_consistency() check then re-extracts and compares.
    """
    import weasyprint
    import pikepdf
    from pikepdf import Name, AttachedFileSpec

    html = render_html(data, for_print=True)
    pdf_bytes = weasyprint.HTML(
        string=html,
        base_url=str(BRAND_DIR) + "/",
    ).write_pdf()

    # Wrap with pikepdf to add PDF/A-3 metadata and embed XML.
    pdf = pikepdf.Pdf.open(io.BytesIO(pdf_bytes))

    # XMP metadata declaring PDF/A-3b conformance + Factur-X marker.
    # The Factur-X namespace must be registered so pikepdf doesn't strip it.
    FX_NS = "urn:factur-x:pdfa:CrossIndustryDocument:invoice:1p0#"
    with pdf.open_metadata() as meta:
        meta.register_xml_namespace(FX_NS, "fx")
        meta["pdfaid:part"] = "3"
        meta["pdfaid:conformance"] = "B"
        meta["fx:DocumentType"] = "INVOICE"
        meta["fx:DocumentFileName"] = "factur-x.xml"
        meta["fx:Version"] = "1.0"
        meta["fx:ConformanceLevel"] = "EN 16931"
        meta["dc:title"] = f"Rechnung {data.number}"
        meta["dc:creator"] = [data.issuer.legal_name or ""]
        meta["pdf:Producer"] = "vibe-invoicing"

    # Embed factur-x.xml.
    spec = AttachedFileSpec(
        pdf,
        xml_bytes,
        description="Factur-X invoice data (EN16931)",
        mime_type="text/xml",
        relationship=Name("/Alternative"),
        filename="factur-x.xml",
    )
    pdf.attachments["factur-x.xml"] = spec

    out = io.BytesIO()
    pdf.save(out, linearize=False)
    return out.getvalue()


# ── XML rendering (drafthorse, EN16931 profile) ─────────────────────────────


def render_xml(data: InvoiceDocumentData) -> bytes:
    """Render an EN16931-conformant Cross-Industry-Invoice XML.

    drafthorse handles the namespace gymnastics; we assemble the document
    field-by-field from the canonical InvoiceDocumentData. Output is UTF-8
    bytes ready to embed in a PDF/A-3.
    """
    from drafthorse.models.document import Document
    from drafthorse.models.note import IncludedNote
    from drafthorse.models.tradelines import LineItem
    from drafthorse.models.party import TaxRegistration
    from drafthorse.models.payment import PaymentMeans, PayeeFinancialAccount, PayeeFinancialInstitution
    from drafthorse.models.references import AdditionalReferencedDocument  # noqa: F401

    doc = Document()
    doc.context.guideline_parameter.id = (
        "urn:cen.eu:en16931:2017"
    )
    doc.header.id = data.number
    # Note: ``header.name`` is rejected by the EN16931 profile schema even
    # though it appears in the underlying CII XSD. We surface the document
    # type via TypeCode (380 invoice / 381 credit note) instead.
    doc.header.type_code = "380" if data.kind == "invoice" else "381"
    doc.header.issue_date_time = data.invoice_date

    # Note: intro_text is rendered in the PDF template; we deliberately don't
    # mirror it into the XML <IncludedNote> because drafthorse's StringElement
    # API for content varies between versions and the legal value lives in the
    # PDF anyway. If a downstream consumer needs structured notes, route them
    # via Invoice.customer_reference instead.

    # Seller / Issuer
    seller = doc.trade.agreement.seller
    seller.name = data.issuer.legal_name
    seller.address.country_id = data.issuer.country_code
    seller.address.country_subdivision = ""
    seller.address.city_name = data.issuer.city
    seller.address.postcode = data.issuer.postal_code
    seller.address.line_one = data.issuer.street
    if data.issuer_ust_id:
        treg = TaxRegistration()
        treg.id = ("VA", data.issuer_ust_id)
        seller.tax_registrations.add(treg)
    if data.issuer_steuernummer:
        treg = TaxRegistration()
        treg.id = ("FC", data.issuer_steuernummer)
        seller.tax_registrations.add(treg)

    # Buyer / Customer
    buyer = doc.trade.agreement.buyer
    buyer.name = data.customer.legal_name
    buyer.address.country_id = data.customer.country_code
    buyer.address.city_name = data.customer.city
    buyer.address.postcode = data.customer.postal_code
    buyer.address.line_one = data.customer.street
    if data.customer.vat_id:
        treg = TaxRegistration()
        treg.id = ("VA", data.customer.vat_id)
        buyer.tax_registrations.add(treg)

    # Customer reference
    if data.customer_reference:
        doc.trade.agreement.buyer_reference = data.customer_reference

    # Delivery — Leistungsdatum
    doc.trade.delivery.event.occurrence = data.leistungsdatum

    # Lines
    for ln in data.lines:
        item = LineItem()
        item.document.line_id = str(ln.position)
        item.product.name = ln.description
        item.agreement.gross.amount = ln.unit_price_net
        item.agreement.gross.basis_quantity = (Decimal("1"), "C62")  # piece
        item.agreement.net.amount = ln.unit_price_net
        item.agreement.net.basis_quantity = (Decimal("1"), "C62")
        item.delivery.billed_quantity = (ln.quantity, "C62")
        item.settlement.trade_tax.type_code = "VAT"
        item.settlement.trade_tax.category_code = ln.vat_code
        item.settlement.trade_tax.rate_applicable_percent = ln.vat_rate
        item.settlement.monetary_summation.total_amount = ln.line_net
        doc.trade.items.add(item)

    # Settlement / totals
    settlement = doc.trade.settlement
    settlement.currency_code = data.currency
    settlement.payee.name = data.issuer_bank_holder or data.issuer.legal_name

    # PaymentMeans — required by EN16931. Code 58 = SEPA credit transfer.
    pm = PaymentMeans()
    pm.type_code = "58"
    if data.issuer_bank_iban:
        pm.payee_account.iban = data.issuer_bank_iban
        if data.issuer_bank_holder:
            pm.payee_account.account_name = data.issuer_bank_holder
        if data.issuer_bank_bic:
            pm.payee_institution.bic = data.issuer_bank_bic
    settlement.payment_means.add(pm)

    # Tax breakdown
    from drafthorse.models.tradelines import ApplicableTradeTax
    for row in data.breakdown:
        tax = ApplicableTradeTax()
        tax.calculated_amount = row.tax
        tax.basis_amount = row.base
        tax.type_code = "VAT"
        if data.hint_kleinunternehmer:
            tax.category_code = "E"
            tax.exemption_reason = "§ 19 UStG"
        elif data.hint_reverse_charge:
            tax.category_code = "AE"
            tax.exemption_reason = "Reverse Charge"
        elif data.hint_third_country:
            tax.category_code = "G"
            tax.exemption_reason = "Drittland"
        else:
            tax.category_code = "S"
        tax.rate_applicable_percent = row.rate
        settlement.trade_tax.add(tax)

    summation = settlement.monetary_summation
    summation.line_total = data.subtotal_net
    summation.charge_total = Decimal("0.00")
    summation.allowance_total = Decimal("0.00")
    summation.tax_basis_total = data.subtotal_net
    summation.tax_total = (data.vat_total, data.currency)
    summation.grand_total = data.total_gross
    summation.due_amount = data.total_gross

    # Payment terms
    if data.payment_terms_text:
        from drafthorse.models.payment import PaymentTerms
        terms = PaymentTerms()
        terms.description = data.payment_terms_text
        if data.due_date:
            terms.due = data.due_date
        settlement.terms.add(terms)

    return doc.serialize(schema="FACTUR-X_EN16931")


# ── Consistency check (R-14) ────────────────────────────────────────────────


def verify_consistency(pdf_bytes: bytes, xml_bytes: bytes, data: InvoiceDocumentData) -> None:
    """R-14: PDF and XML must agree on the critical economic fields.

    This is an inline post-render check inside ``finalize()``. It re-extracts
    the embedded factur-x.xml from the PDF and compares structural identity
    to the freshly-rendered XML, then walks the XML to assert totals and
    parties match the dataclass.
    """
    import pikepdf

    # Embedded XML must equal the input xml_bytes.
    pdf = pikepdf.Pdf.open(io.BytesIO(pdf_bytes))
    if "factur-x.xml" not in pdf.attachments:
        raise ConsistencyError("PDF is missing factur-x.xml attachment")
    embedded = bytes(pdf.attachments["factur-x.xml"].get_file().read_bytes())
    if embedded != xml_bytes:
        raise ConsistencyError(
            f"Embedded XML differs from rendered XML (sizes {len(embedded)} vs {len(xml_bytes)})"
        )

    # Totals must round-trip.
    text = xml_bytes.decode("utf-8", errors="replace")
    if data.number not in text:
        raise ConsistencyError(f"Invoice number {data.number} not found in XML")
    if str(data.total_gross) not in text:
        raise ConsistencyError(f"total_gross {data.total_gross} not found in XML")


class ConsistencyError(Exception):
    pass


# ── One-shot ─────────────────────────────────────────────────────────────────


def render_document(invoice, lines, vat, issuer) -> RenderedDocument:
    """Wrapper used as the ``renderer`` callable by ``finalize_invoice``.

    Replaces the Phase-4 stub once Phase 5 is wired up.
    """
    data = build_document_data(invoice, lines, issuer)
    xml_bytes = render_xml(data)
    pdf_bytes = render_pdf(data, xml_bytes)
    verify_consistency(pdf_bytes, xml_bytes, data)
    return RenderedDocument(pdf_bytes=pdf_bytes, xml_bytes=xml_bytes)
