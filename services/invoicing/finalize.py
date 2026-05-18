"""Finalize-Service: draft → finalized + Archive.

Orchestriert R-01 Pflichtangaben, R-02 Nummern, R-03 Immutability-Trigger,
R-04 Snapshot, R-09 Leistungsdatum-Pflicht, R-11 Original-Persistenz,
R-12 Hash-Chain, R-15 6-Monate-Warnung, R-16 VIES-Audit.

Renderer und Archive werden via Callback eingespritzt — Phase 4 nutzt
Stubs für Tests, Phase 5 setzt die echten Implementierungen ein.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Callable, Optional

from sqlmodel import Session, select

from app.contracts.billing_order import BillingCustomer
from app.domains.billing.models import (
    Invoice,
    InvoiceLineItem,
    InvoiceStatus,
    IssuerProfile,
)

from .numbering import assign_next_number
from .state_machine import assert_can_transition
from .vat import (
    CustomerSnapshot,
    IssuerSnapshot,
    LineInput,
    VatResult,
    compute_vat,
)

log = logging.getLogger(__name__)

# ── Errors ─────────────────────────────────────────────────────────────────


class FinalizeError(Exception):
    """Base class for finalize-time errors."""


class InvoiceValidationError(FinalizeError):
    """R-01 — pflichtige Felder fehlen."""


class IdempotencyMismatchError(FinalizeError):
    """Repeated finalize with the same key but different invoice — refuse."""


# ── Renderer / Archive contract ────────────────────────────────────────────


@dataclass(frozen=True)
class RenderedDocument:
    pdf_bytes: bytes
    xml_bytes: bytes


@dataclass(frozen=True)
class ArchivedDocument:
    pdf_path: str
    xml_path: str


# Renderer takes the staged invoice + lines + vat-result and returns bytes.
RendererCallable = Callable[[Invoice, list[InvoiceLineItem], VatResult, IssuerProfile], RenderedDocument]
# Archiver writes bytes to durable storage; returns the paths it persisted.
ArchiverCallable = Callable[[int, str, RenderedDocument, str], ArchivedDocument]


def stub_renderer(invoice, lines, vat, issuer):
    """Phase-4 placeholder: emits a deterministic byte blob covering the data.

    Replaced in Phase 5 by ``services.invoicing.document.render_document``.
    """
    payload = json.dumps({
        "id": invoice.id,
        "number": invoice.number,
        "iss_legal_name": invoice.iss_legal_name,
        "cust_legal_name": invoice.cust_legal_name,
        "leistungsdatum": str(invoice.leistungsdatum),
        "subtotal_net": str(invoice.subtotal_net),
        "vat_total": str(invoice.vat_total),
        "total_gross": str(invoice.total_gross),
        "lines": [
            {"pos": ln.position, "net": str(ln.line_net), "vat": str(ln.line_vat)}
            for ln in lines
        ],
    }, sort_keys=True).encode("utf-8")
    return RenderedDocument(pdf_bytes=b"%PDF-stub\n" + payload, xml_bytes=b"<xml-stub>" + payload + b"</xml-stub>")


def stub_archiver(year, number, doc, hash_hex):
    """Phase-4 placeholder: pretends to write somewhere; returns dummy paths."""
    return ArchivedDocument(
        pdf_path=f"archive/invoices/{year}/{number}.pdf",
        xml_path=f"archive/invoices/{year}/{number}.xml",
    )


# ── Validation helpers ─────────────────────────────────────────────────────


_REQUIRED_CUSTOMER_FIELDS = (
    "cust_legal_name",
    "cust_street",
    "cust_postal_code",
    "cust_city",
    "cust_country_code",
)
_REQUIRED_ISSUER_FIELDS = (
    "legal_name",
    "street",
    "postal_code",
    "city",
    "country_code",
)


def _validate_invoice_for_finalize(invoice: Invoice, lines: list[InvoiceLineItem], issuer: IssuerProfile) -> None:
    """R-01 + R-09 + R-04 (snapshot pre-conditions)."""
    if invoice.status != InvoiceStatus.draft:
        raise InvoiceValidationError(f"Invoice {invoice.id} is not draft (status={invoice.status.value})")
    if invoice.leistungsdatum is None:
        raise InvoiceValidationError("Leistungsdatum (performance date) is required (R-09).")
    if not lines:
        raise InvoiceValidationError("Invoice must have at least one line item.")
    for ln in lines:
        if not ln.description:
            raise InvoiceValidationError(f"Line {ln.position}: description required.")
        if ln.quantity is None or ln.quantity == 0:
            raise InvoiceValidationError(f"Line {ln.position}: quantity must be non-zero.")
        if ln.unit_price_net is None:
            raise InvoiceValidationError(f"Line {ln.position}: unit_price_net required.")
    # Issuer must be complete.
    missing_iss = [f for f in _REQUIRED_ISSUER_FIELDS if not getattr(issuer, f)]
    if missing_iss:
        raise InvoiceValidationError(f"IssuerProfile missing fields: {missing_iss} (configure /admin/issuer).")
    if not issuer.is_kleinunternehmer and not (issuer.steuernummer or issuer.ust_id):
        raise InvoiceValidationError(
            "IssuerProfile must have either Steuernummer or USt-IdNr. (R-01 §14(4) Nr. 2)."
        )


# ── Snapshot helpers ───────────────────────────────────────────────────────


def _snapshot_issuer(invoice: Invoice, issuer: IssuerProfile) -> None:
    """R-04: copy issuer fields onto the invoice. Subsequent edits to the
    IssuerProfile must NOT change historical invoices."""
    invoice.iss_legal_name = issuer.legal_name
    invoice.iss_street = issuer.street
    invoice.iss_postal_code = issuer.postal_code
    invoice.iss_city = issuer.city
    invoice.iss_country_code = issuer.country_code
    invoice.iss_steuernummer = issuer.steuernummer
    invoice.iss_ust_id = issuer.ust_id
    invoice.iss_is_kleinunternehmer = issuer.is_kleinunternehmer
    invoice.iss_bank_holder = issuer.bank_holder
    invoice.iss_bank_iban = issuer.bank_iban
    invoice.iss_bank_bic = issuer.bank_bic
    invoice.iss_contact_email = issuer.contact_email
    invoice.iss_contact_phone = issuer.contact_phone


def _snapshot_customer(invoice: Invoice, customer: Optional[BillingCustomer]) -> None:
    """R-04: copy customer block. ``cust_*`` fields can also be set directly
    on the invoice prior to finalize (e.g. via API/MCP) — we only auto-snapshot
    from the ``BillingCustomer`` contract if one was exported and the invoice
    fields are empty.

    Schritt 5: the data now arrives as the published ``BillingCustomer``
    snapshot built CRM-side (``options.customer_resolver``) instead of a
    direct ``Lead`` read. The merge logic — incl. the ``name or company``
    precedence and "explicit invoice value wins" — is byte-equivalent to the
    pre-split behaviour; only the data *source* changed (the Naht)."""
    if customer is None:
        return
    # Only fill empty fields — explicit invoice-level overrides win.
    invoice.cust_legal_name = invoice.cust_legal_name or customer.name or customer.company
    invoice.cust_company = invoice.cust_company or customer.company
    invoice.cust_salutation = invoice.cust_salutation or customer.salutation
    invoice.cust_street = invoice.cust_street or customer.street
    invoice.cust_street2 = invoice.cust_street2 or customer.street2
    invoice.cust_postal_code = invoice.cust_postal_code or customer.postal_code
    invoice.cust_city = invoice.cust_city or customer.city
    invoice.cust_country_code = invoice.cust_country_code or customer.country_code
    invoice.cust_vat_id = invoice.cust_vat_id or customer.vat_id
    if invoice.cust_is_business is None:
        invoice.cust_is_business = customer.is_business
    invoice.cust_email = invoice.cust_email or customer.email


def _validate_customer_snapshot(invoice: Invoice) -> None:
    missing = [f for f in _REQUIRED_CUSTOMER_FIELDS if not getattr(invoice, f)]
    if missing:
        raise InvoiceValidationError(
            f"Customer block incomplete after snapshot: {missing}. "
            "Set fields on Lead or directly on the invoice draft."
        )


# ── Hash chain ─────────────────────────────────────────────────────────────


def _content_hash(pdf_bytes: bytes, xml_bytes: bytes, header: dict) -> str:
    """sha256 of pdf_hash || xml_hash || canonical(header). See ADR-001."""
    pdf_h = hashlib.sha256(pdf_bytes).hexdigest()
    xml_h = hashlib.sha256(xml_bytes).hexdigest()
    canonical = json.dumps(header, sort_keys=True, default=str).encode("utf-8")
    h = hashlib.sha256()
    h.update(pdf_h.encode("ascii"))
    h.update(b"\n")
    h.update(xml_h.encode("ascii"))
    h.update(b"\n")
    h.update(canonical)
    return h.hexdigest()


def _previous_hash(session: Session, fiscal_year: int) -> str:
    """Return the hash of the previous finalized invoice in this year, or the
    genesis string if this is the first one (sequence_number=1).
    """
    prev = session.exec(
        select(Invoice)
        .where(Invoice.fiscal_year == fiscal_year)
        .where(Invoice.status != InvoiceStatus.draft)
        .order_by(Invoice.sequence_number.desc())
    ).first()
    if prev is None or prev.sequence_number == 0:
        return hashlib.sha256(f"genesis-invoice-chain-{fiscal_year}".encode()).hexdigest()
    return prev.hash_sha256 or hashlib.sha256(f"genesis-invoice-chain-{fiscal_year}".encode()).hexdigest()


# ── Public entrypoint ──────────────────────────────────────────────────────


@dataclass
class FinalizeOptions:
    today: date = field(default_factory=date.today)
    renderer: RendererCallable = stub_renderer
    archiver: ArchiverCallable = stub_archiver
    # If not None, called when leistungsdatum > 6 months ago (R-15).
    on_late_leistungsdatum: Optional[Callable[[Invoice], None]] = None
    # VIES gate (Phase 6 will provide a real impl). Default no-op.
    vies_gate: Optional[Callable[[Invoice, "Session"], None]] = None
    # Schritt 5 — CRM-side BillingOrder export seam. Given the bound
    # ``invoice.lead_id``, returns the published ``BillingCustomer`` snapshot
    # (or None). Injected like renderer/archiver/vies_gate so billing never
    # imports CRM. Default None → no auto-snapshot (e.g. the storno path,
    # whose cust_* are already copied verbatim).
    customer_resolver: Optional[
        Callable[[Optional[int]], Optional[BillingCustomer]]
    ] = None


def finalize_invoice(
    session: Session,
    invoice_id: int,
    *,
    idempotency_key: Optional[str] = None,
    options: Optional[FinalizeOptions] = None,
) -> Invoice:
    """Finalize a draft invoice. Returns the finalized invoice.

    Re-calling with the same ``idempotency_key`` against an already-finalized
    invoice is a no-op and returns the same row. Re-calling against a different
    invoice with the same key raises ``IdempotencyMismatchError``.
    """
    options = options or FinalizeOptions()

    invoice = session.get(Invoice, invoice_id)
    if invoice is None:
        raise FinalizeError(f"Invoice {invoice_id} not found.")

    # ── Idempotency (R-Phase 3.9) ──
    if idempotency_key:
        existing = session.exec(
            select(Invoice).where(Invoice.idempotency_key == idempotency_key)
        ).one_or_none()
        if existing is not None:
            if existing.id != invoice.id:
                raise IdempotencyMismatchError(
                    f"Key {idempotency_key!r} already used for invoice {existing.id}; cannot reuse for {invoice.id}."
                )
            if existing.status != InvoiceStatus.draft:
                # already finalized → return as-is
                return existing
        invoice.idempotency_key = idempotency_key

    # ── Issuer + lines ──
    issuer = session.get(IssuerProfile, 1)
    if issuer is None:
        raise InvoiceValidationError(
            "No IssuerProfile configured. Bootstrap via ENV or create one at /admin/issuer."
        )
    lines = session.exec(
        select(InvoiceLineItem)
        .where(InvoiceLineItem.invoice_id == invoice.id)
        .order_by(InvoiceLineItem.position)
    ).all()

    _validate_invoice_for_finalize(invoice, lines, issuer)

    # ── Snapshot first (R-04) ──
    # Schritt 5: customer arrives via the CRM-built BillingOrder snapshot
    # (injected resolver), not a direct Lead read — billing imports no CRM.
    customer = (
        options.customer_resolver(invoice.lead_id)
        if options.customer_resolver is not None
        else None
    )
    _snapshot_issuer(invoice, issuer)
    _snapshot_customer(invoice, customer)
    _validate_customer_snapshot(invoice)

    # ── VAT engine (R-06) ──
    vat = compute_vat(
        IssuerSnapshot(
            country_code=invoice.iss_country_code,
            ust_id=invoice.iss_ust_id,
            is_kleinunternehmer=bool(invoice.iss_is_kleinunternehmer),
        ),
        CustomerSnapshot(
            country_code=invoice.cust_country_code,
            vat_id=invoice.cust_vat_id,
            is_business=bool(invoice.cust_is_business),
        ),
        [
            LineInput(
                position=ln.position,
                description=ln.description,
                quantity=ln.quantity,
                unit_price_net=ln.unit_price_net,
                vat_rate_hint=ln.vat_rate,
            )
            for ln in lines
        ],
        invoice.leistungsdatum,
    )

    # ── VIES gate (R-16) — Phase 6 plugs in real implementation ──
    if options.vies_gate is not None and vat.hints.get("reverse_charge"):
        options.vies_gate(invoice, session)

    # ── R-15 — 6-Monats-Warnung ──
    if options.on_late_leistungsdatum and (options.today - invoice.leistungsdatum) > timedelta(days=180):
        options.on_late_leistungsdatum(invoice)
    elif (options.today - invoice.leistungsdatum) > timedelta(days=180):
        log.warning(
            "Invoice %s: Leistungsdatum %s is more than 180 days ago (R-15).",
            invoice.id, invoice.leistungsdatum,
        )

    # Persist VAT-engine results onto invoice + lines.
    invoice.subtotal_net = vat.subtotal_net
    invoice.vat_total = vat.vat_total
    invoice.total_gross = vat.total_gross
    invoice.vat_breakdown_json = json.dumps([
        {"rate": str(b.rate), "base": str(b.base), "tax": str(b.tax)}
        for b in vat.breakdown
    ])
    invoice.hint_kleinunternehmer = vat.hints.get("kleinunternehmer", False)
    invoice.hint_reverse_charge = vat.hints.get("reverse_charge", False)
    invoice.hint_third_country = vat.hints.get("third_country", False)

    # Update line items with computed values from the engine.
    by_pos = {l.position: l for l in lines}
    for vl in vat.lines:
        ln = by_pos[vl.position]
        ln.vat_rate = vl.vat_rate
        ln.vat_code = vl.vat_code
        ln.line_net = vl.line_net
        ln.line_vat = vl.line_vat
        ln.line_gross = vl.line_gross
        session.add(ln)

    # Dates + payment terms.
    invoice.invoice_date = options.today
    if invoice.payment_terms_text is None:
        invoice.payment_terms_text = issuer.default_payment_terms_text
    invoice.due_date = options.today + timedelta(days=issuer.default_payment_terms_days)

    # ── Number assignment (R-02) — must occur inside the same transaction ──
    fiscal_year = options.today.year
    sequence, number = assign_next_number(session, fiscal_year)
    invoice.fiscal_year = fiscal_year
    invoice.sequence_number = sequence
    invoice.number = number
    session.add(invoice)
    session.flush()

    # ── Render ──
    rendered = options.renderer(invoice, lines, vat, issuer)

    # ── Hash chain (R-12) ──
    header_for_hash = {
        "number": invoice.number,
        "fiscal_year": invoice.fiscal_year,
        "sequence_number": invoice.sequence_number,
        "invoice_date": invoice.invoice_date,
        "leistungsdatum": invoice.leistungsdatum,
        "iss_legal_name": invoice.iss_legal_name,
        "iss_ust_id": invoice.iss_ust_id,
        "iss_steuernummer": invoice.iss_steuernummer,
        "cust_legal_name": invoice.cust_legal_name,
        "cust_vat_id": invoice.cust_vat_id,
        "subtotal_net": invoice.subtotal_net,
        "vat_total": invoice.vat_total,
        "total_gross": invoice.total_gross,
    }
    hash_prev = _previous_hash(session, fiscal_year)
    invoice.hash_prev = hash_prev
    invoice.hash_sha256 = _content_hash(rendered.pdf_bytes, rendered.xml_bytes, header_for_hash)

    # ── Archive (R-10, R-11) ──
    archived = options.archiver(fiscal_year, number, rendered, invoice.hash_sha256)
    invoice.archive_path_pdf = archived.pdf_path
    invoice.archive_path_xml = archived.xml_path

    # ── Transition (R-03 immutability kicks in after this) ──
    assert_can_transition(invoice.status, InvoiceStatus.finalized)
    invoice.status = InvoiceStatus.finalized
    invoice.finalized_at = datetime.utcnow()
    invoice.updated_at = datetime.utcnow()

    session.add(invoice)
    session.commit()
    session.refresh(invoice)
    return invoice


def mark_sent(session: Session, invoice_id: int) -> Invoice:
    invoice = session.get(Invoice, invoice_id)
    if invoice is None:
        raise FinalizeError(f"Invoice {invoice_id} not found.")
    assert_can_transition(invoice.status, InvoiceStatus.sent)
    invoice.status = InvoiceStatus.sent
    invoice.sent_at = datetime.utcnow()
    invoice.updated_at = datetime.utcnow()
    session.add(invoice)
    session.commit()
    session.refresh(invoice)
    return invoice


def mark_paid(session: Session, invoice_id: int) -> Invoice:
    invoice = session.get(Invoice, invoice_id)
    if invoice is None:
        raise FinalizeError(f"Invoice {invoice_id} not found.")
    assert_can_transition(invoice.status, InvoiceStatus.paid)
    invoice.status = InvoiceStatus.paid
    invoice.paid_at = datetime.utcnow()
    invoice.updated_at = datetime.utcnow()
    session.add(invoice)
    session.commit()
    session.refresh(invoice)
    return invoice


# ── R-05 Storno ────────────────────────────────────────────────────────────


def create_storno(
    session: Session,
    original_invoice_id: int,
    *,
    reason: str | None = None,
    options: Optional[FinalizeOptions] = None,
) -> Invoice:
    """Create a Storno invoice that cancels ``original_invoice_id`` (R-05).

    Steps:
        1. Load the original; must be finalized/sent/paid (not draft, not already cancelled).
        2. Build a draft storno with kind='storno', related_invoice_id, NEGATIVE
           amounts on every line, and the original's customer snapshot copied
           verbatim (so addresses match — required by §14 UStG so the storno is
           clearly identifiable).
        3. Finalize it (assigns its own number).
        4. Mark the original as cancelled.
    """
    from app.domains.billing.models import InvoiceKind, InvoiceLineItem
    options = options or FinalizeOptions()

    original = session.get(Invoice, original_invoice_id)
    if original is None:
        raise FinalizeError(f"Original invoice {original_invoice_id} not found.")
    if original.status == InvoiceStatus.draft:
        raise FinalizeError("Cannot storno a draft — delete it instead.")
    if original.status == InvoiceStatus.cancelled:
        raise FinalizeError("Already cancelled.")

    # Build draft storno. Copy customer snapshot so addresses match exactly.
    storno = Invoice(
        status=InvoiceStatus.draft,
        kind=InvoiceKind.storno,
        lead_id=original.lead_id,
        related_invoice_id=original.id,
        leistungsdatum=original.leistungsdatum,
        currency=original.currency,
        title=f"Storno zu {original.number}",
        intro_text=reason or f"Stornorechnung zu Rechnung {original.number} vom {original.invoice_date}.",
        # Customer snapshot inherited so finalize doesn't need to re-fetch from Lead
        cust_legal_name=original.cust_legal_name,
        cust_company=original.cust_company,
        cust_salutation=original.cust_salutation,
        cust_street=original.cust_street,
        cust_street2=original.cust_street2,
        cust_postal_code=original.cust_postal_code,
        cust_city=original.cust_city,
        cust_country_code=original.cust_country_code,
        cust_vat_id=original.cust_vat_id,
        cust_is_business=original.cust_is_business,
        cust_email=original.cust_email,
        customer_reference=original.customer_reference,
    )
    session.add(storno)
    session.commit()
    session.refresh(storno)

    # Copy lines with NEGATIVE quantity → engine will compute negative line totals.
    original_lines = session.exec(
        select(InvoiceLineItem)
        .where(InvoiceLineItem.invoice_id == original.id)
        .order_by(InvoiceLineItem.position)
    ).all()
    for orig in original_lines:
        ln = InvoiceLineItem(
            invoice_id=storno.id,
            position=orig.position,
            description=f"Storno: {orig.description}",
            quantity=-orig.quantity,
            unit=orig.unit,
            unit_price_net=orig.unit_price_net,
            vat_rate=orig.vat_rate,
            vat_code=orig.vat_code,
            line_net=-orig.line_net,
            line_vat=-orig.line_vat,
            line_gross=-orig.line_gross,
        )
        session.add(ln)
    session.commit()

    # Finalize the storno (assigns own number, archives).
    finalized_storno = finalize_invoice(session, storno.id, options=options)

    # Mark original cancelled. The DB trigger allows status changes.
    original_fresh = session.get(Invoice, original.id)
    assert_can_transition(original_fresh.status, InvoiceStatus.cancelled)
    original_fresh.status = InvoiceStatus.cancelled
    original_fresh.cancelled_at = datetime.utcnow()
    original_fresh.updated_at = datetime.utcnow()
    session.add(original_fresh)
    session.commit()

    return finalized_storno
