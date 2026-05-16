#!/usr/bin/env python3
"""Assert that the Kennzahlen table in ARCHITECTURE.md matches the codebase.

Scaling-roadmap Schritt 0: ARCHITECTURE.md is the CI-verified Ist-contract.
This script does NOT build a call graph and does NOT infer structure — it only
*asserts* the documented numbers against `wc -l`/`grep`-equivalent counts.
If code drifts from the doc (or vice versa), CI fails until both agree.

Single source of truth = the `## Kennzahlen` table in ARCHITECTURE.md. The
expected values are parsed from that table, never hard-coded here, so there is
exactly one place to update.

Scope note: this script lives in `scripts/` and is excluded from the Python-LOC
metrics by design (it is doc-CI tooling, not application/product code) — adding
or editing it must never move the documented numbers.

Exit 0 = all tracked metrics agree. Exit 1 = drift (with a diff). Exit 2 =
the table itself is malformed / a tracked row is missing.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ARCH = REPO / "ARCHITECTURE.md"

# Directories never counted in any metric.
_EXCLUDED_DIRS = {".venv", "scripts", ".git", "__pycache__", "generated_pdfs"}


def _py_files(root: Path) -> list[Path]:
    return [
        p
        for p in root.rglob("*.py")
        if not any(part in _EXCLUDED_DIRS for part in p.relative_to(REPO).parts)
    ]


def _loc(paths) -> int:
    """Newline count — matches `wc -l` semantics."""
    return sum(p.read_bytes().count(b"\n") for p in paths)


# --- live metric computations -------------------------------------------------
# Each returns the current value from the codebase. Keyed by the exact row
# label in the ARCHITECTURE.md Kennzahlen table.


def m_total_loc() -> int:
    return _loc(_py_files(REPO))


def m_test_loc() -> int:
    return _loc(_py_files(REPO / "tests"))


def m_prod_loc() -> int:
    return m_total_loc() - m_test_loc()


def m_tables() -> int:
    text = (REPO / "models.py").read_text(encoding="utf-8")
    return sum(1 for ln in text.splitlines() if "table=True" in ln)


def m_endpoints() -> int:
    pat = re.compile(r"@router\.(get|post|put|patch|delete)\b")
    return sum(
        len(pat.findall(p.read_text(encoding="utf-8")))
        for p in (REPO / "routes").glob("*.py")
    )


def m_route_modules() -> int:
    # routes/*.py minus __init__.py and the mcp.py mount (not a route module).
    excluded = {"__init__.py", "mcp.py"}
    return sum(
        1 for p in (REPO / "routes").glob("*.py") if p.name not in excluded
    )


def m_mcp_tools() -> int:
    text = (REPO / "services" / "mcp_server.py").read_text(encoding="utf-8")
    return sum(1 for ln in text.splitlines() if "@mcp.tool" in ln)


def m_templates() -> int:
    return len(list((REPO / "templates").rglob("*.html")))


def m_invoicing_loc() -> int:
    return _loc(sorted((REPO / "services" / "invoicing").rglob("*.py")))


def m_getenv_files() -> int:
    return sum(
        1
        for p in _py_files(REPO)
        if "os.getenv" in p.read_text(encoding="utf-8")
    )


# Row label in ARCHITECTURE.md  ->  live computation.
METRICS = {
    "Python LOC gesamt": m_total_loc,
    "davon Produktivcode": m_prod_loc,
    "davon Tests": m_test_loc,
    "SQLModel-Tabellen": m_tables,
    "HTTP-Endpoints": m_endpoints,
    "Route-Module": m_route_modules,
    "MCP-Tools": m_mcp_tools,
    "HTML-Templates": m_templates,
    "Invoicing-Subsystem": m_invoicing_loc,
    "os.getenv-Fundstellen": m_getenv_files,
}


def parse_kennzahlen(md: str) -> dict[str, int]:
    """Extract {label: int} from the `## Kennzahlen` markdown table.

    Value cells like `8.737`, `1.819 LOC`, `6 Dateien` are normalized:
    thousands dots stripped, first integer taken. Rows without a clean
    integer (e.g. `~40 %`) are ignored.
    """
    lines = md.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == "## Kennzahlen")
    except StopIteration:
        print("ERROR: '## Kennzahlen' heading not found in ARCHITECTURE.md", file=sys.stderr)
        sys.exit(2)

    out: dict[str, int] = {}
    for ln in lines[start + 1 :]:
        s = ln.strip()
        if s.startswith("## "):  # next section
            break
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 2:
            continue
        label, raw = cells[0].replace("`", ""), cells[1]
        if label in ("Metrik", "") or set(label) <= {"-", ":", " "}:
            continue
        digits = re.search(r"\d+", raw.replace(".", "").replace(" ", ""))
        if digits:
            out[label] = int(digits.group())
    return out


def main() -> int:
    md = ARCH.read_text(encoding="utf-8")
    documented = parse_kennzahlen(md)

    rows: list[tuple[str, int, int, bool]] = []
    missing: list[str] = []
    for label, fn in METRICS.items():
        if label not in documented:
            missing.append(label)
            continue
        actual = fn()
        expected = documented[label]
        rows.append((label, expected, actual, expected == actual))

    if missing:
        print("ERROR: tracked metric(s) absent from ARCHITECTURE.md Kennzahlen table:", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        return 2

    w = max(len(r[0]) for r in rows)
    print(f"{'Metric'.ljust(w)}  {'doc':>8}  {'code':>8}  ok")
    print("-" * (w + 24))
    drift = []
    for label, expected, actual, ok in rows:
        flag = "OK" if ok else "DRIFT"
        print(f"{label.ljust(w)}  {expected:>8}  {actual:>8}  {flag}")
        if not ok:
            drift.append((label, expected, actual))

    if drift:
        print(file=sys.stderr)
        print("ARCHITECTURE.md is out of sync with the codebase:", file=sys.stderr)
        for label, expected, actual in drift:
            print(
                f"  {label}: doc says {expected}, code has {actual}  "
                f"(fix the code OR update ARCHITECTURE.md — they must agree)",
                file=sys.stderr,
            )
        return 1

    print("\nAll documented Kennzahlen match the codebase.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
