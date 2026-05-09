"""Phase 2: ensure the new invoicing tables + lead address columns + triggers exist."""
from __future__ import annotations

import pytest
from sqlalchemy import text


@pytest.mark.integration
def test_lead_has_address_columns(session):
    cols = session.exec(text("PRAGMA table_info(lead)")).all()
    names = {row[1] for row in cols}
    expected = {"street", "street2", "postal_code", "city", "country_code", "vat_id", "is_business", "tax_country"}
    assert expected <= names, f"missing: {expected - names}"


@pytest.mark.integration
def test_invoice_tables_exist(session):
    rows = session.exec(text("SELECT name FROM sqlite_master WHERE type='table'")).all()
    names = {r[0] for r in rows}
    expected = {"invoice", "invoicelineitem", "invoicenumbersequence", "viesauditentry", "integritycheckrun", "issuerprofile"}
    assert expected <= names, f"missing tables: {expected - names}"


@pytest.mark.integration
def test_invoice_immutability_trigger_blocks_total_change_after_finalize(session):
    """R-03: a finalized invoice rejects edits at the DB layer."""
    session.exec(text("""
        INSERT INTO invoice (id, status, kind, total_gross, currency, hash_algo, created_at, updated_at,
                             hint_kleinunternehmer, hint_reverse_charge, hint_third_country)
        VALUES (1, 'finalized', 'invoice', 100.00, 'EUR', 'sha256-v1',
                '2026-05-08 10:00:00', '2026-05-08 10:00:00', 0, 0, 0)
    """))
    session.commit()
    with pytest.raises(Exception, match="immutable"):
        session.exec(text("UPDATE invoice SET total_gross = 0 WHERE id = 1"))
        session.commit()


@pytest.mark.integration
def test_invoice_status_transition_still_allowed(session):
    """Status + post-finalize timestamps must remain mutable for sent/paid/cancelled."""
    session.exec(text("""
        INSERT INTO invoice (id, status, kind, total_gross, currency, hash_algo, created_at, updated_at,
                             hint_kleinunternehmer, hint_reverse_charge, hint_third_country)
        VALUES (2, 'finalized', 'invoice', 100.00, 'EUR', 'sha256-v1',
                '2026-05-08 10:00:00', '2026-05-08 10:00:00', 0, 0, 0)
    """))
    session.commit()
    session.exec(text("UPDATE invoice SET status = 'sent', sent_at = '2026-05-08 10:00:00' WHERE id = 2"))
    session.commit()
    row = session.exec(text("SELECT status FROM invoice WHERE id = 2")).first()
    assert row[0] == "sent"


@pytest.mark.integration
def test_line_item_immutable_after_finalize(session):
    """R-03: line-item table is locked once parent invoice is finalized."""
    session.exec(text("""
        INSERT INTO invoice (id, status, kind, currency, hash_algo, created_at, updated_at,
                             hint_kleinunternehmer, hint_reverse_charge, hint_third_country)
        VALUES (3, 'draft', 'invoice', 'EUR', 'sha256-v1',
                '2026-05-08 10:00:00', '2026-05-08 10:00:00', 0, 0, 0)
    """))
    session.exec(text("""
        INSERT INTO invoicelineitem
            (invoice_id, position, description, quantity, unit, unit_price_net,
             vat_rate, vat_code, line_net, line_vat, line_gross)
        VALUES (3, 1, 'Beratung', 10, 'Std', 100, 19, 'S', 1000, 190, 1190)
    """))
    session.commit()
    # Promote to finalized, then try to mutate the line.
    session.exec(text("UPDATE invoice SET status = 'finalized' WHERE id = 3"))
    session.commit()
    with pytest.raises(Exception, match="immutable"):
        session.exec(text("UPDATE invoicelineitem SET line_net = 0 WHERE invoice_id = 3"))
        session.commit()


@pytest.mark.integration
def test_invoice_number_unique_per_year(session):
    """R-02: (fiscal_year, sequence_number) is UNIQUE."""
    session.exec(text("""
        INSERT INTO invoice (id, status, kind, fiscal_year, sequence_number, number, currency, hash_algo,
                             created_at, updated_at, hint_kleinunternehmer, hint_reverse_charge, hint_third_country)
        VALUES (10, 'finalized', 'invoice', 2026, 1, 'RE-2026-0001', 'EUR', 'sha256-v1',
                '2026-05-08 10:00:00', '2026-05-08 10:00:00', 0, 0, 0)
    """))
    session.commit()
    with pytest.raises(Exception):
        session.exec(text("""
            INSERT INTO invoice (id, status, kind, fiscal_year, sequence_number, number, currency, hash_algo,
                                 created_at, updated_at, hint_kleinunternehmer, hint_reverse_charge, hint_third_country)
            VALUES (11, 'finalized', 'invoice', 2026, 1, 'RE-2026-0001-dup', 'EUR', 'sha256-v1',
                    '2026-05-08 10:00:00', '2026-05-08 10:00:00', 0, 0, 0)
        """))
        session.commit()
