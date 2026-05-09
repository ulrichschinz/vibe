"""Integritätsprüfung der finalisierten Rechnungen — R-12.

Aufruf::

    python -m services.invoicing.integrity_check
    python -m services.invoicing.integrity_check --year 2026
    python -m services.invoicing.integrity_check --json   # maschinenlesbar

Walks alle finalisierten Rechnungen, liest PDF + XML aus dem Archiv, berechnet
den Hash neu und vergleicht ihn gegen den DB-Wert. Prüft ausserdem die
Hash-Kette (``hash_prev``) und schreibt einen ``IntegrityCheckRun``-Eintrag.

Exit-Code:
    0 → alles ok
    1 → mindestens ein Mismatch
    2 → fataler Fehler (z. B. Archiv-Datei fehlt)
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from sqlmodel import Session, select

# Ensure project root is on sys.path when invoked as -m services.invoicing.integrity_check
_THIS_FILE = Path(__file__).resolve()
_ROOT = _THIS_FILE.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from database import engine  # noqa: E402
from models import (  # noqa: E402
    IntegrityCheckResult,
    IntegrityCheckRun,
    Invoice,
    InvoiceStatus,
)
from services.invoicing.hashchain import (  # noqa: E402
    ChainMismatch,
    list_finalized_in_year,
    recompute_invoice_hash,
    verify_chain,
)


def run(year: int | None = None) -> tuple[int, list[ChainMismatch]]:
    """Run an integrity check. Returns (scanned_count, mismatches)."""
    mismatches: list[ChainMismatch] = []
    scanned = 0
    with Session(engine) as s:
        if year is not None:
            years = [year]
        else:
            years = sorted({fy for fy in s.exec(
                select(Invoice.fiscal_year).where(Invoice.status != InvoiceStatus.draft)
            ).all() if fy is not None})

        for y in years:
            invoices = list_finalized_in_year(s, y)
            scanned += len(invoices)

            for inv in invoices:
                if not inv.archive_path_pdf or not inv.archive_path_xml:
                    mismatches.append(ChainMismatch(
                        invoice_id=inv.id,
                        number=inv.number or f"#{inv.id}",
                        reason="missing archive paths",
                        expected="<pdf+xml paths>",
                        actual="(none)",
                    ))
                    continue

                pdf_path = Path(inv.archive_path_pdf)
                xml_path = Path(inv.archive_path_xml)
                if not pdf_path.exists() or not xml_path.exists():
                    mismatches.append(ChainMismatch(
                        invoice_id=inv.id,
                        number=inv.number,
                        reason="archive file missing on disk",
                        expected=f"{pdf_path}, {xml_path}",
                        actual="(missing)",
                    ))
                    continue

                pdf_bytes = pdf_path.read_bytes()
                xml_bytes = xml_path.read_bytes()
                recomputed = recompute_invoice_hash(inv, pdf_bytes, xml_bytes)
                if recomputed != inv.hash_sha256:
                    mismatches.append(ChainMismatch(
                        invoice_id=inv.id,
                        number=inv.number,
                        reason="content hash mismatch",
                        expected=inv.hash_sha256 or "",
                        actual=recomputed,
                    ))

            mismatches.extend(verify_chain(invoices))

        # Persist run record
        result = IntegrityCheckResult.ok if not mismatches else IntegrityCheckResult.mismatch
        record = IntegrityCheckRun(
            scanned_count=scanned,
            mismatches_json=json.dumps([asdict(m) for m in mismatches]),
            result=result,
            notes=f"checked years: {years}",
        )
        s.add(record)
        s.commit()

    return scanned, mismatches


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=None, help="Single fiscal year to check")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    args = parser.parse_args(argv)

    try:
        scanned, mismatches = run(year=args.year)
    except Exception as exc:  # pragma: no cover — fatal path
        if args.json:
            print(json.dumps({"result": "error", "message": str(exc)}))
        else:
            print(f"FATAL: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({
            "result": "ok" if not mismatches else "mismatch",
            "scanned": scanned,
            "mismatches": [asdict(m) for m in mismatches],
        }))
    else:
        print(f"Scanned: {scanned}")
        if not mismatches:
            print("OK — alle Hashes konsistent, Kette intakt.")
        else:
            print(f"MISMATCHES: {len(mismatches)}")
            for m in mismatches:
                print(f"  {m.number}: {m.reason}")
                print(f"    expected: {m.expected}")
                print(f"    actual:   {m.actual}")

    return 0 if not mismatches else 1


if __name__ == "__main__":
    sys.exit(main())
