"""app.shared — cross-cutting helpers, no domain knowledge.

import-linter end state: shared/* may import `core/*` + stdlib/3rd-party,
**not** `domains/*`/`interfaces/*`.

Entry points (filled by later steps):
  labels.py    STAGE_LABELS/SOURCE_LABELS/… as data, moved out of
               models.py; the Jinja-global injection is repointed here
               (Schritt 4, dashboard characterization test covers it)
  pdf.py       Jinja2→WeasyPrint (today services/pdf.py, already clean)
  numbering.py proposal-number generation (today services/numbering.py)
  money.py     Decimal arithmetic helpers
Empty by design in Schritt 2.
"""
