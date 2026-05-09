"""§14 UStG-konformes Rechnungs-Modul.

Submodule:
    money         — Decimal-Helpers, ROUND_HALF_UP
    eu_countries  — ISO alpha-2 Liste der EU-Mitgliedsstaaten (ohne DE)
    vat           — Pure VAT-Engine (compute_vat)
    numbering     — Race-safe Rechnungsnummern-Vergabe
    finalize      — Draft → Finalized State-Transition
    document      — InvoiceDocumentData + render_pdf + render_xml
    archive       — Append-only Filesystem-Storage
    hashchain     — sha256 Per-Year Hash-Chain
    vies          — EU-USt-IdNr.-Validierung
    immutability  — SQLAlchemy Event-Listener gegen Edits nach Finalize
    integrity_check — CLI-Tool für Audits
"""
