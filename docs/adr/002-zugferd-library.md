# ADR-002: ZUGFeRD/Factur-X Library-Auswahl

**Status:** Akzeptiert (2026-05-09)

## Kontext

R-13 fordert eine ZUGFeRD-2.x / Factur-X-konforme PDF/A-3 mit eingebetteter
EN16931-XML. Wir brauchen:
1. einen XML-Generator für die EN16931-Profilstruktur,
2. einen PDF-Renderer (haben wir schon: WeasyPrint),
3. ein Tool, das WeasyPrint-PDF (PDF 1.7) zu PDF/A-3 konvertiert und das
   `factur-x.xml` mit `AFRelationship=/Alternative` einbettet.

## Optionen geprüft

| Komponente | Optionen | Entscheidung |
|---|---|---|
| XML-Generator | `drafthorse`, `factur-x` (akretion), Eigenbau via `lxml` | **drafthorse** |
| PDF/A-3 + Embed | `pikepdf`, `pyhanko`, `factur-x`, `ghostscript` (CLI) | **pikepdf** |

## Entscheidung

- **`drafthorse>=2024.4`** für XML-Generierung (FACTUR-X_EN16931 Profil,
  Schema-Validierung gegen die offizielle XSD eingebaut).
- **`pikepdf>=9.0`** für PDF/A-3-Konversion + EmbeddedFile.

## Begründung

**drafthorse**:
- Aktiv gepflegt (Stand 2026-05).
- Apache-2.0 Lizenz, kein Copyleft.
- Validiert beim `serialize()` selbst gegen die offizielle XSD —
  fängt Fehler früh ab statt erst im KoSIT-Validator.
- Strukturiertes Datenmodell (Document → Trade → Items) statt String-Templates.

**pikepdf**:
- BSD-Lizenz, Wrapper um QPDF.
- Sauberes API für `AttachedFileSpec`, `pdf.attachments`, XMP-Metadaten.
- Unterstützt das Setzen von `AFRelationship=/Alternative` direkt.

## Konsequenzen

**Positiv:**
- Beide Libraries sind stable; XML-Validierung ist eingebaut.
- `pikepdf` ist auch für andere PDF-Manipulationen nutzbar (z. B. zukünftiges
  Signing).

**Negativ:**
- API von `drafthorse` ist nicht überall intuitiv. Beispiele:
  - `header.name` wird vom EN16931-Profil rejected, obwohl in der zugrundeliegenden
    CII-XSD erlaubt — wir lassen es weg und kodieren den Doc-Typ über `type_code`.
  - `payee_account` und `payee_institution` sind read-only Field-Instanzen — man
    setzt deren Sub-Attribute (`pm.payee_account.iban = …`) statt eine neue
    Instanz zu assignen.
  - `header.notes` ist ein Container, dessen `IncludedNote.content`
    (`StringElement`) in der installierten Version nicht direkt befüllbar ist;
    wir umgehen den Punkt, indem wir Intro-Text nur ins PDF rendern (XML enthält
    den ohnehin nicht für die rechtliche Bewertung).
- WeasyPrint produziert kein PDF/A-3 nativ. Wir müssen einen Post-Process über
  pikepdf laufen lassen. Das funktioniert, ist aber eine extra Schicht.

## Alternativen verworfen

- **`factur-x` (akretion):** Wrapper um `facturx-python` — weniger aktiv, weniger
  klares API.
- **`pyhanko`:** Fokus auf PDF-Signing, ZUGFeRD-Embed nur als Nebenprodukt;
  Komplexität für unseren Anwendungsfall zu hoch.
- **Eigenbau via `lxml`:** Wir würden uns die XSD-Validierung, die korrekte
  Element-Reihenfolge und die Namespace-Verhandlung selbst aufhalsen. Drafthorse
  macht das alles bereits.
- **Ghostscript CLI:** LGPL/AGPL-Doppellizenz; manche Builds problematisch.
  pikepdf reicht für unseren Bedarf.

## Verifikation

- `tests/integration/test_document_renderer.py::test_render_pdf_a3_with_embedded_xml`
  prüft, dass das embedded XML byte-identisch zum Standalone-XML ist.
- KoSIT-Validator (in `tests/contract/test_kosit.py`, CI-pinned) ist das
  externe Akzeptanz-Gate.
