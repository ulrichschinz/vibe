# ADR-006: PDF-Rendering-Pipeline

**Status:** Akzeptiert (2026-05-09)

## Kontext

Das CRM nutzt bereits **WeasyPrint** für die Angebots-PDF-Generierung
(`services/pdf.py`). Für Rechnungen brauchen wir zusätzlich PDF/A-3 mit
eingebettetem Factur-X-XML.

WeasyPrint produziert nativ PDF 1.7, kein PDF/A-3.

## Optionen geprüft

1. **WeasyPrint → pikepdf-Post-Process** *(gewählt)*
2. **Reine LaTeX-Pipeline** (z. B. via `pdflatex`, ZUGFeRD-Pakete)
3. **Headless Chrome / Puppeteer**
4. **Ghostscript CLI** (`-sDEVICE=pdfwrite -dPDFA=3`)

## Entscheidung

**Option 1.** WeasyPrint rendert das HTML-Template zu PDF 1.7. Der
Post-Processor in `services/invoicing/document.py:render_pdf` öffnet das PDF
mit pikepdf, setzt PDF/A-3b-XMP-Metadaten, registriert die Factur-X-Namespace,
embeds `factur-x.xml` mit `AFRelationship=/Alternative` und speichert.

## Begründung

- **WeasyPrint bleibt:** Wir haben bereits die Brand-CSS und das Layout-Pattern
  für Proposals; das Invoice-Template folgt derselben Struktur. Ein zweiter
  Renderer wäre doppelte Wartung.
- **pikepdf** ist BSD, aktiv, kann XMP + Embedded Files manipulieren und
  Linearisierung steuern.
- **Kein Ghostscript:** Vermeidet die LGPL/AGPL-Doppellizenz, vermeidet zusätzliche
  apt-Pakete im Container, vermeidet einen externen Prozess pro PDF.

## Konsequenzen

**Positiv:**
- Eine einzige Render-Pipeline für Proposals und Invoices (mit Post-Process-
  Schicht für letztere).
- pikepdf ist auch für andere PDF-Operationen wiederverwendbar (z. B. zukünftiges
  Signing).

**Negativ:**
- pikepdf-only PDF/A-3 ist *nicht* von veraPDF zertifiziert. Wir haben Tests, die
  prüfen, dass das XML eingebettet ist und die XMP-Metadaten gesetzt sind, aber
  eine vollständige PDF/A-3-Konformitätsprüfung mit veraPDF wäre eine sinnvolle
  Ergänzung.
- WeasyPrint kann manche CSS-Properties (z. B. `print-color-adjust: exact`)
  nicht. Workaround: alternative CSS-Hooks.

## Alternativen verworfen

- **LaTeX:** Hoher Eintrittsaufwand für Layout-Anpassungen, schwer zu pflegen für
  jemand, der mit CSS gut zurechtkommt. Brand-Konsistenz mit Proposals wäre
  schwierig.
- **Headless Chrome:** Bringt Chromium ins Docker-Image. Overkill für statische
  PDFs.
- **Ghostscript:** Zusätzliche apt-Dependency, Lizenz-Komplexität, externe
  Prozess-Aufrufe.

## Verifikation

- `tests/integration/test_document_renderer.py::test_render_pdf_a3_with_embedded_xml`
  prüft `factur-x.xml`-Anwesenheit + Byte-Identität mit Standalone-XML.
- `tests/integration/test_document_renderer.py::test_consistency_check_detects_mismatch`
  belegt, dass `verify_consistency` Manipulationen erkennt.
- (Geplant, in `docs/open-questions.md`:) veraPDF-Validation als zusätzliches
  CI-Gate.
