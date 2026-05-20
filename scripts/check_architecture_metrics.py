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

import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ARCH = REPO / "ARCHITECTURE.md"
PYPROJECT = REPO / "pyproject.toml"

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
    """Count real SQLModel tables in their post-Schritt-4 homes.

    Before Schritt 4 this was `grep -c 'table=True' models.py`, which also
    counted the literal comment `# … (no table=True)` (hence the documented
    value was 14 while there are 13 tables). The split moved every table to
    `app/domains/*/models.py` + `app/core/{identity,ai_settings}.py`; the
    top-level `models.py` is now a re-export shim with zero tables. We count
    actual `class … table=True` definitions, so the metric is now exact (13).
    """
    pat = re.compile(r"^class\s+\w+\(.*\btable=True\b", re.M)
    return sum(len(pat.findall(p.read_text(encoding="utf-8"))) for p in _py_files(REPO / "app"))


def _interface_router_modules() -> list:
    # Schritt 8: the routers moved routes/ -> app/interfaces/{web,api}.
    # Route modules = the interface modules that define a router
    # (web handlers + the REST router); __init__.py is the register()
    # composition layer and mount.py is the MCP ASGI mount, neither a
    # route module. `routes/*.py` is now thin test-facing re-export shims.
    excluded = {"__init__.py", "mount.py"}
    return [
        p
        for d in ("web", "api")
        for p in (REPO / "app" / "interfaces" / d).glob("*.py")
        if p.name not in excluded
    ]


def m_endpoints() -> int:
    pat = re.compile(r"@router\.(get|post|put|patch|delete)\b")
    return sum(
        len(pat.findall(p.read_text(encoding="utf-8")))
        for p in _interface_router_modules()
    )


def m_route_modules() -> int:
    return len(_interface_router_modules())


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


# --- structure assertions (T6) -----------------------------------------------
# Two tables in ARCHITECTURE.md make structural prose self-verifying:
#   * "Struktur-Verträge (CI-erzwungen)"  — set of import-linter contract names
#   * "Re-Export-Shim-Inventar (CI-erzwungen)" — path + LOC of every shim
#
# The single import-linter / shim set is the gate; drift in either direction
# (doc lists what code doesn't have, or vice versa) is a CI-rot. Detection is
# stdlib-only (regex on pyproject.toml, AST on .py files) so the gate stays
# locally runnable like the rest of this script (no app deps).
#
# Backlog: T6 (`docs/remediation-backlog.md`) — closes audit finding R5.


def _parse_named_table(md: str, heading: str) -> list[list[str]]:
    """Extract data rows (list of cell-lists) from a markdown table under
    a `## heading`. Header row and divider row are skipped. Returns empty
    list if the section exists but has no data rows; raises SystemExit(2)
    when the heading itself is missing — the doc must declare the table.
    """
    lines = md.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == heading)
    except StopIteration:
        print(
            f"ERROR: '{heading}' heading not found in ARCHITECTURE.md",
            file=sys.stderr,
        )
        sys.exit(2)

    out: list[list[str]] = []
    seen_header = False
    for ln in lines[start + 1 :]:
        s = ln.strip()
        if s.startswith("## "):  # next section
            break
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        # divider row like `|---|---|`
        if cells and all(set(c) <= {"-", ":", " "} for c in cells):
            continue
        if not seen_header:
            seen_header = True
            continue
        out.append(cells)
    return out


def parse_importlinter_contract_names() -> set[str]:
    """Extract every `name = "..."` value from `[[tool.importlinter.contracts]]`
    blocks. Pure-stdlib regex parse — `pyproject.toml` keeps multi-line
    `#`-rationale comments per block (ADR-012 §B); a TOML round-trip would
    lose them, so we never round-trip here.
    """
    text = PYPROJECT.read_text(encoding="utf-8")
    names: set[str] = set()
    in_block = False
    for ln in text.splitlines():
        s = ln.strip()
        if s == "[[tool.importlinter.contracts]]":
            in_block = True
            continue
        # any other section header closes the current contracts block
        if s.startswith("[") and s != "[[tool.importlinter.contracts]]":
            in_block = False
            continue
        if in_block:
            m = re.match(r'^name\s*=\s*"(.+)"\s*$', s)
            if m:
                names.add(m.group(1))
    return names


def _is_reexport_shim(tree: ast.Module) -> bool:
    """Classify a parsed module as a "trivial re-export shim".

    A shim's body, after an optional module docstring, contains **only**:
      - `import …` / `from … import …` (incl. `from __future__ import …`)
      - at most one `__all__ = [...]` assignment

    No FunctionDef / ClassDef / non-`__all__` assignment / other statement
    is allowed. This is the structural fingerprint of the five known shims
    (`models.py`, `routes/{leads,proposals}.py`, `services/{ai,linkedin_import}.py`)
    and deliberately excludes e.g. `app/shared/labels.py` (data dicts) or
    `app/__init__.py` (empty docstring-only).
    """
    body = tree.body
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    if not body:
        return False
    has_import = False
    for stmt in body:
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            has_import = True
            continue
        if isinstance(stmt, ast.Assign):
            if (
                len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
                and stmt.targets[0].id == "__all__"
            ):
                continue
            return False
        return False
    return has_import


# Tests live deliberately outside this scope: a test fixture re-exporting
# names is not a structural shim of the production code. Same exclusion set
# as `_EXCLUDED_DIRS` plus tests/.
_SHIM_DISCOVERY_EXCLUDED = _EXCLUDED_DIRS | {"tests"}


def discover_shims() -> list[Path]:
    """AST-walk the production tree, return every file matching the
    re-export-shim fingerprint. Sorted by repo-relative path for stable
    output. Syntax-broken files are skipped (they break elsewhere).
    """
    out: list[Path] = []
    for p in REPO.rglob("*.py"):
        rel = p.relative_to(REPO)
        if any(part in _SHIM_DISCOVERY_EXCLUDED for part in rel.parts):
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        if _is_reexport_shim(tree):
            out.append(p)
    return sorted(out)


def check_importlinter_contracts(md: str) -> list[str]:
    """Compare the documented contract-name set against `pyproject.toml`.
    Returns a list of human-readable drift messages (empty = OK).
    """
    code = parse_importlinter_contract_names()
    rows = _parse_named_table(md, "## Struktur-Verträge (CI-erzwungen)")
    doc = {row[0].strip("`") for row in rows if row and row[0]}

    drift: list[str] = []
    for name in sorted(doc - code):
        snip = name if len(name) <= 80 else name[:77] + "..."
        drift.append(
            f"  doc lists contract not in pyproject.toml:\n    {snip}"
        )
    for name in sorted(code - doc):
        snip = name if len(name) <= 80 else name[:77] + "..."
        drift.append(
            f"  pyproject contract missing from ARCHITECTURE.md table:\n    {snip}"
        )
    return drift


def check_shim_inventory(md: str) -> list[str]:
    """Compare the documented shim inventory against AST-discovered shims.

    Doc table columns (read positionally): `Pfad | LOC | ...`.  Any further
    cells are documentation for humans and not gate-checked.
    """
    rows = _parse_named_table(md, "## Re-Export-Shim-Inventar (CI-erzwungen)")
    documented: dict[str, int] = {}
    drift: list[str] = []

    for row in rows:
        if len(row) < 2:
            continue
        path_cell = row[0].strip("`")
        m = re.search(r"\d+", row[1])
        if not m:
            drift.append(
                f"  shim-inventory row '{path_cell}': LOC cell has no integer"
            )
            continue
        documented[path_cell] = int(m.group())

    discovered_paths = {
        str(p.relative_to(REPO)) for p in discover_shims()
    }
    documented_paths = set(documented.keys())

    for missing in sorted(documented_paths - discovered_paths):
        full = REPO / missing
        if not full.exists():
            drift.append(
                f"  '{missing}' is documented as a shim but the file is gone "
                f"(deleted? then drop the row — see T7 shim-death gates)"
            )
        else:
            drift.append(
                f"  '{missing}' is documented as a shim but its body now has "
                f"def/class or a non-`__all__` assignment (no longer a trivial "
                f"re-export — drop the row or restore the shim)"
            )
    for extra in sorted(discovered_paths - documented_paths):
        drift.append(
            f"  '{extra}' is a trivial re-export shim in code but NOT listed "
            f"in the ARCHITECTURE.md Re-Export-Shim-Inventar table"
        )

    for path, expected_loc in documented.items():
        full = REPO / path
        if not full.exists():
            continue  # already reported as missing above
        actual_loc = full.read_bytes().count(b"\n")
        if actual_loc != expected_loc:
            drift.append(
                f"  '{path}': doc says {expected_loc} LOC, code has {actual_loc}"
            )

    return drift


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

    contract_drift = check_importlinter_contracts(md)
    shim_drift = check_shim_inventory(md)

    if drift or contract_drift or shim_drift:
        print(file=sys.stderr)
        if drift:
            print(
                "ARCHITECTURE.md Kennzahlen are out of sync with the codebase:",
                file=sys.stderr,
            )
            for label, expected, actual in drift:
                print(
                    f"  {label}: doc says {expected}, code has {actual}  "
                    f"(fix the code OR update ARCHITECTURE.md — they must agree)",
                    file=sys.stderr,
                )
        if contract_drift:
            print(
                "ARCHITECTURE.md Struktur-Verträge table is out of sync "
                "with pyproject.toml:",
                file=sys.stderr,
            )
            for line in contract_drift:
                print(line, file=sys.stderr)
        if shim_drift:
            print(
                "ARCHITECTURE.md Re-Export-Shim-Inventar is out of sync "
                "with the codebase:",
                file=sys.stderr,
            )
            for line in shim_drift:
                print(line, file=sys.stderr)
        return 1

    print(
        f"\nAll documented Kennzahlen match the codebase "
        f"(plus {len(parse_importlinter_contract_names())} import-linter "
        f"contracts and {len(discover_shims())} re-export shims accounted for)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
