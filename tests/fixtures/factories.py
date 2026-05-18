"""Test factories — produce realistic but synthetic objects for tests."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlmodel import Session

from models import (
    Invoice,
    InvoiceLineItem,
    InvoiceStatus,
    IssuerProfile,
    Lead,
    PlanningMessage,
)


def make_issuer(session: Session, **overrides) -> IssuerProfile:
    """Default issuer = Agentic Reach (matches .env.example)."""
    defaults = dict(
        id=1,
        legal_name="Agentic Reach · Ulrich Schinz",
        street="Staltacher Straße 59A",
        postal_code="82393",
        city="Iffeldorf",
        country_code="DE",
        steuernummer="100/000/00000",
        ust_id=None,
        is_kleinunternehmer=False,
        bank_holder="Ulrich Schinz",
        bank_iban="DE89370400440532013000",
        bank_bic="COBADEFFXXX",
        contact_email="hello@agentic-reach.com",
        default_payment_terms_days=14,
        default_payment_terms_text="Zahlbar innerhalb 14 Tagen ohne Abzug.",
    )
    defaults.update(overrides)
    issuer = IssuerProfile(**defaults)
    session.merge(issuer)
    session.commit()
    return session.get(IssuerProfile, 1)


def make_lead_de_b2b(session: Session, **overrides) -> Lead:
    defaults = dict(
        name="Max Müller",
        company="Müller GmbH",
        email="max@mueller-gmbh.de",
        phone="+49 89 12345678",
        salutation="Herr",
        street="Testweg 1",
        postal_code="80331",
        city="München",
        country_code="DE",
        is_business=True,
    )
    defaults.update(overrides)
    lead = Lead(**defaults)
    session.add(lead)
    session.commit()
    session.refresh(lead)
    return lead


def make_lead_de_b2c(session: Session, **overrides) -> Lead:
    return make_lead_de_b2b(session, company=None, is_business=False, **overrides)


def make_lead_eu_b2b_at(session: Session, **overrides) -> Lead:
    """Österreich-Lead mit Test-USt-IdNr. ATU99999999 (laut VIES-Test).

    Beim Finalize muss eine VIES-Mock-Antwort eingespielt werden — ohne Mock
    blockt das Live-VIES.
    """
    defaults = dict(
        name="Anna Wiesinger",
        company="Wiener Beratungs-AG",
        email="kontakt@beratung-wien.at",
        salutation="Frau",
        street="Stephansplatz 1",
        postal_code="1010",
        city="Wien",
        country_code="AT",
        vat_id="ATU99999999",
        is_business=True,
    )
    defaults.update(overrides)
    lead = Lead(**defaults)
    session.add(lead)
    session.commit()
    session.refresh(lead)
    return lead


def make_lead_drittland_us(session: Session, **overrides) -> Lead:
    defaults = dict(
        name="Jane Doe",
        company="Acme Inc",
        email="jane@acme.example",
        street="1 Market St",
        postal_code="94105",
        city="San Francisco",
        country_code="US",
        is_business=True,
    )
    defaults.update(overrides)
    lead = Lead(**defaults)
    session.add(lead)
    session.commit()
    session.refresh(lead)
    return lead


def make_planning_messages(session: Session, lead: Lead, count: int = 4) -> list[PlanningMessage]:
    """Seed a planning chat with alternating user/assistant turns."""
    msgs = []
    for i in range(count):
        role = "user" if i % 2 == 0 else "assistant"
        msg = PlanningMessage(
            lead_id=lead.id,
            role=role,
            content=f"{role.capitalize()}-Nachricht {i + 1}: Test-Inhalt für Planung.",
        )
        session.add(msg)
        msgs.append(msg)
    session.commit()
    for m in msgs:
        session.refresh(m)
    return msgs


_SENTINEL = object()


def make_draft_invoice(session: Session, lead: Lead, *, leistungsdatum=_SENTINEL,
                       lines: list[dict] | None = None, **overrides) -> Invoice:
    if leistungsdatum is _SENTINEL:
        leistungsdatum = date(2026, 5, 1)
    defaults = dict(
        status=InvoiceStatus.draft,
        lead_id=lead.id,
        leistungsdatum=leistungsdatum,
        title="Beratungsleistung",
        currency="EUR",
        # Scaling-roadmap Schritt 5 — the customer snapshot is no longer
        # auto-read from Lead *inside* finalize; it arrives via the CRM-built
        # BillingOrder seam (`FinalizeOptions.customer_resolver`), wired only
        # in the prod callers (routes/api/mcp). These integration helpers call
        # `finalize_invoice` directly with no resolver, so we pre-fill cust_*
        # from the lead here — byte-equivalent to the old in-finalize
        # `_snapshot_customer(lead)` (same `name or company` precedence;
        # explicit `cust_*` overrides below still win). Assertions unchanged →
        # the 90 % invoicing safety net stays green; the seam itself is
        # covered by the characterization tests through the prod callers.
        cust_legal_name=lead.name or lead.company,
        cust_company=lead.company,
        cust_salutation=lead.salutation,
        cust_street=lead.street,
        cust_street2=lead.street2,
        cust_postal_code=lead.postal_code,
        cust_city=lead.city,
        cust_country_code=lead.country_code,
        cust_vat_id=lead.vat_id,
        cust_is_business=lead.is_business,
        cust_email=lead.email,
    )
    defaults.update(overrides)
    inv = Invoice(**defaults)
    session.add(inv)
    session.commit()
    session.refresh(inv)

    line_specs = lines if lines is not None else [
        {"description": "Beratung", "quantity": Decimal("10"), "unit": "Std",
         "unit_price_net": Decimal("100"), "vat_rate": Decimal("19")},
    ]
    for i, spec in enumerate(line_specs, start=1):
        qty = Decimal(spec["quantity"])
        unit_price = Decimal(spec["unit_price_net"])
        rate = Decimal(spec["vat_rate"])
        line_net = qty * unit_price
        line_vat = (line_net * rate / Decimal(100)).quantize(Decimal("0.01"))
        ln = InvoiceLineItem(
            invoice_id=inv.id,
            position=i,
            description=spec["description"],
            quantity=qty,
            unit=spec.get("unit", "Std"),
            unit_price_net=unit_price,
            vat_rate=rate,
            vat_code=spec.get("vat_code", "S"),
            line_net=line_net,
            line_vat=line_vat,
            line_gross=line_net + line_vat,
        )
        session.add(ln)
    session.commit()
    session.refresh(inv)
    return inv
