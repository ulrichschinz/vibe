"""Cover the CLI main() entrypoint of integrity_check."""
from __future__ import annotations

from datetime import date

import pytest
from sqlmodel import Session

from services.invoicing.archive import archive_document
from services.invoicing.document import render_document
from services.invoicing.finalize import FinalizeOptions, finalize_invoice
from tests.fixtures.factories import make_draft_invoice, make_issuer, make_lead_de_b2b


@pytest.fixture
def patched_engine(engine, monkeypatch):
    import services.invoicing.integrity_check as ic
    monkeypatch.setattr(ic, "engine", engine)
    return engine


@pytest.mark.integration
@pytest.mark.slow
def test_cli_main_returns_zero_on_clean_archive(patched_engine, archive_dir, capsys):
    with Session(patched_engine) as session:
        make_issuer(session)
        lead = make_lead_de_b2b(session)
        inv = make_draft_invoice(session, lead)
        finalize_invoice(
            session, inv.id,
            options=FinalizeOptions(today=date(2026, 5, 9), renderer=render_document, archiver=archive_document),
        )

    from services.invoicing.integrity_check import main as cli_main
    rc = cli_main([])
    assert rc == 0
    captured = capsys.readouterr()
    assert "Scanned: 1" in captured.out
    assert "OK" in captured.out


@pytest.mark.integration
@pytest.mark.slow
def test_cli_main_json_mode(patched_engine, archive_dir, capsys):
    with Session(patched_engine) as session:
        make_issuer(session)
        lead = make_lead_de_b2b(session)
        inv = make_draft_invoice(session, lead)
        finalize_invoice(
            session, inv.id,
            options=FinalizeOptions(today=date(2026, 5, 9), renderer=render_document, archiver=archive_document),
        )

    import json
    from services.invoicing.integrity_check import main as cli_main
    rc = cli_main(["--json"])
    assert rc == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["result"] == "ok"
    assert payload["scanned"] == 1


@pytest.mark.integration
@pytest.mark.slow
def test_cli_main_specific_year(patched_engine, archive_dir):
    with Session(patched_engine) as session:
        make_issuer(session)
        lead = make_lead_de_b2b(session)
        inv = make_draft_invoice(session, lead)
        finalize_invoice(
            session, inv.id,
            options=FinalizeOptions(today=date(2026, 5, 9), renderer=render_document, archiver=archive_document),
        )

    from services.invoicing.integrity_check import main as cli_main
    rc = cli_main(["--year", "2026"])
    assert rc == 0
    rc = cli_main(["--year", "2099"])  # empty year → still ok
    assert rc == 0
