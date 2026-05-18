"""VIES (USt-IdNr.) Validierung — R-16.

Bei Reverse-Charge-Rechnungen muss die EU-USt-IdNr. des Empfängers zum
Finalize-Zeitpunkt gegen die offizielle EU-Datenbank validiert werden. Das
Ergebnis wird unveränderbar archiviert (``ViesAuditEntry``).

Verhalten am Finalize:
    valid               → durch
    invalid             → ``ViesBlockedError`` (kein Override)
    service_unavailable → ``ViesBlockedError`` mit Admin-Override-Pfad

Begründung der Override-Politik in ADR-004.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlmodel import Session

from app.domains.billing.models import Invoice, ViesAuditEntry, ViesResponseStatus

log = logging.getLogger(__name__)

VIES_WSDL_URL = "https://ec.europa.eu/taxation_customs/vies/services/checkVatService.wsdl"


# ── Errors ─────────────────────────────────────────────────────────────────


class ViesBlockedError(Exception):
    """Raised when finalize must not proceed because of a VIES result.

    Carries enough context for an admin override to be re-driven through
    ``finalize_invoice`` with ``override`` set.
    """

    def __init__(self, status: ViesResponseStatus, vat_id: str, raw: dict, message: str):
        super().__init__(message)
        self.status = status
        self.vat_id = vat_id
        self.raw = raw


# ── Result type ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ViesResult:
    status: ViesResponseStatus
    vat_id: str
    country_code: str
    raw: dict   # full response payload, persisted unchanged for audit


# ── Live check ─────────────────────────────────────────────────────────────


def _split_vat_id(vat_id: str) -> tuple[str, str]:
    vat_id = vat_id.strip().replace(" ", "")
    if len(vat_id) < 3 or not vat_id[:2].isalpha():
        raise ValueError(f"Invalid VAT-ID format: {vat_id!r}")
    return vat_id[:2].upper(), vat_id[2:]


def check_vat_id(vat_id: str, *, timeout: float = 10.0, _client_factory=None) -> ViesResult:
    """Live VIES SOAP call. Returns a ``ViesResult`` regardless of outcome.

    ``_client_factory`` is for tests: pass a callable returning a Zeep-shaped
    mock client. In production we use ``zeep.Client`` directly.
    """
    country, number = _split_vat_id(vat_id)

    try:
        if _client_factory is None:
            from zeep import Client  # imported lazily so unit tests don't need zeep
            client = Client(VIES_WSDL_URL)
        else:
            client = _client_factory()
        response = client.service.checkVat(countryCode=country, vatNumber=number)
        # zeep returns a CompoundValue; .__values__ gives a dict.
        raw = dict(response.__values__) if hasattr(response, "__values__") else dict(response)
        # Normalize datetime values for JSON storage
        for k, v in list(raw.items()):
            if isinstance(v, datetime):
                raw[k] = v.isoformat()
        valid = bool(raw.get("valid"))
        if valid:
            return ViesResult(ViesResponseStatus.valid, vat_id, country, raw)
        return ViesResult(ViesResponseStatus.invalid, vat_id, country, raw)
    except Exception as exc:
        log.warning("VIES service unavailable: %s", exc)
        return ViesResult(
            ViesResponseStatus.service_unavailable,
            vat_id,
            country,
            {"error": str(exc), "type": type(exc).__name__},
        )


# ── Audit entry ────────────────────────────────────────────────────────────


def write_audit(
    session: Session,
    *,
    invoice_id: Optional[int],
    result: ViesResult,
    queried_by_user_id: Optional[int] = None,
    override_reason: Optional[str] = None,
    override_status: Optional[ViesResponseStatus] = None,
) -> ViesAuditEntry:
    """Persist a ViesAuditEntry. Returns the row, with ``id`` populated."""
    entry = ViesAuditEntry(
        invoice_id=invoice_id,
        queried_at=datetime.utcnow(),
        vat_id_queried=result.vat_id,
        country_code=result.country_code,
        response_status=override_status or result.status,
        raw_response_json=json.dumps(result.raw, default=str),
        queried_by_user_id=queried_by_user_id,
        override_reason=override_reason,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


# ── Finalize gate (R-16) ───────────────────────────────────────────────────


@dataclass(frozen=True)
class ViesGateOptions:
    """Configures the VIES gate handed to ``finalize_invoice``."""
    override: bool = False
    override_reason: Optional[str] = None
    override_user_id: Optional[int] = None
    # Test injection point — replaces the live check.
    check_callable: Optional[object] = None  # Callable[[str], ViesResult]


def make_vies_gate(options: ViesGateOptions):
    """Return a callable suitable for ``FinalizeOptions.vies_gate``.

    The returned function performs the live check, writes an audit entry,
    raises ``ViesBlockedError`` if the result blocks, and tolerates an
    admin-override on ``service_unavailable``.
    """
    def gate(invoice: Invoice, session: Session) -> None:
        vat_id = invoice.cust_vat_id
        if not vat_id:
            # No VAT-ID → caller shouldn't have flagged reverse-charge; treat as
            # programmer error.
            raise ViesBlockedError(
                ViesResponseStatus.invalid,
                "",
                {"error": "no customer VAT-ID for reverse-charge invoice"},
                "Reverse-charge invoice without customer VAT-ID.",
            )

        check = options.check_callable or check_vat_id
        result: ViesResult = check(vat_id)

        if result.status == ViesResponseStatus.valid:
            write_audit(
                session,
                invoice_id=invoice.id,
                result=result,
                queried_by_user_id=options.override_user_id,
            )
            return

        if result.status == ViesResponseStatus.invalid:
            # Always record the failed attempt before raising.
            write_audit(
                session,
                invoice_id=invoice.id,
                result=result,
                queried_by_user_id=options.override_user_id,
            )
            raise ViesBlockedError(
                ViesResponseStatus.invalid,
                vat_id,
                result.raw,
                f"VIES rejected VAT-ID {vat_id!r}.",
            )

        # service_unavailable → block unless admin override.
        if options.override:
            if not options.override_reason:
                raise ViesBlockedError(
                    ViesResponseStatus.service_unavailable,
                    vat_id,
                    result.raw,
                    "VIES override requires a reason.",
                )
            write_audit(
                session,
                invoice_id=invoice.id,
                result=result,
                queried_by_user_id=options.override_user_id,
                override_reason=options.override_reason,
                override_status=ViesResponseStatus.override,
            )
            return

        write_audit(
            session,
            invoice_id=invoice.id,
            result=result,
            queried_by_user_id=options.override_user_id,
        )
        raise ViesBlockedError(
            ViesResponseStatus.service_unavailable,
            vat_id,
            result.raw,
            f"VIES service unavailable for {vat_id!r}; admin override required.",
        )

    return gate
