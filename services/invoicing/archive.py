"""Append-only Filesystem-Archiv für finalisierte Rechnungen.

R-10 (8 Jahre, GoBD-konform, append-only) + R-11 (Originale, nicht regenerieren).

Layout::

    archive/invoices/{YYYY}/{number}.pdf
    archive/invoices/{YYYY}/{number}.xml
    archive/invoices/{YYYY}/{number}.sha256
    archive/invoices/{YYYY}/_chain.log

WORM-Strategie:
    1. Hash-Chain in DB + ``_chain.log`` (primäre Detection)
    2. ``chmod 0444`` auf Files nach Write (sekundär)
    3. Optional ``chmod 0555`` auf Year-Dir nach Jahresabschluss (manuell)

Trade-off siehe ``docs/adr/001-archive-storage.md``.
"""
from __future__ import annotations

import os
import stat
from datetime import datetime
from pathlib import Path

from app.core.config import get_settings

from .finalize import ArchivedDocument, RenderedDocument


def get_archive_root() -> Path:
    """Resolve the archive root from ENV.

    Production: ``./archive`` relative to project root.
    Tests: per-test ``tmp_path/archive`` via the ``archive_dir`` fixture.
    """
    root = get_settings().invoice_archive_root
    if root:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent / "archive"


def archive_document(year: int, number: str, doc: RenderedDocument, hash_hex: str) -> ArchivedDocument:
    """Persist PDF + XML + checksum + chain-log entry.

    The files are written 0644 then chmod'd to 0444 so accidental edits via
    the running app fail with permission denied. ``shutil.move`` from a
    finished temp file would be more robust against partial writes; a future
    iteration can split this into write-temp + atomic rename.
    """
    base = get_archive_root() / "invoices" / str(year)
    base.mkdir(parents=True, exist_ok=True)

    pdf_path = base / f"{number}.pdf"
    xml_path = base / f"{number}.xml"
    sha_path = base / f"{number}.sha256"
    chain_path = base / "_chain.log"

    pdf_path.write_bytes(doc.pdf_bytes)
    xml_path.write_bytes(doc.xml_bytes)
    sha_path.write_text(f"{hash_hex}  {number}.pdf+xml\n", encoding="utf-8")

    # Append chain-log line: tab-separated, append-only-flag is on `mode='a'`.
    with chain_path.open("a", encoding="utf-8") as f:
        f.write(f"{number}\t{hash_hex}\t{datetime.utcnow().isoformat(timespec='seconds')}Z\n")

    # WORM: 0444. Year dir stays writable so future invoices can be added.
    for p in (pdf_path, xml_path, sha_path):
        try:
            os.chmod(p, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        except PermissionError:
            # Tests may run as root in CI; skip silently.
            pass

    return ArchivedDocument(
        pdf_path=str(pdf_path.resolve()),
        xml_path=str(xml_path.resolve()),
    )


def read_archived_pdf(path: str) -> bytes:
    return Path(path).read_bytes()


def read_archived_xml(path: str) -> bytes:
    return Path(path).read_bytes()
