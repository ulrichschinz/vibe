#!/usr/bin/env python3
"""Outcome-Probe harness — Audit-Remediation T1.

Compares the file set a task's implementation touched against the *sealed*
prediction in ``docs/outcome-probe/<task>.expected``. Pure stdlib (no app
deps) so it runs locally exactly like ``scripts/check_architecture_metrics.py``
— the only locally available lever in the no-local-interpreter environment.

This harness checks the **file set only**. ``make verify`` green per run is a
separate gate (CI / manual). N=3 independent runs is a process discipline the
spec (``docs/outcome-probe/README.md``) defines; this script makes each single
run *verifiable*.

Usage:
    python3 scripts/outcome_probe.py <task>     # check working tree vs sealed set
    python3 scripts/outcome_probe.py --lint     # CI: every .expected well-formed
    make outcome-probe TASK=<task>

Exit 0 = changed-file set exactly matches the sealed set.
Exit 1 = mismatch (missing and/or extra files listed) OR malformed input.
Exit 2 = usage / unknown task.

The probe's own spec directory ``docs/outcome-probe/`` is excluded from the
measured set — editing the sealed prediction must never count as task output
(that would defeat the integrity of the sealing).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROBE_DIR = REPO / "docs" / "outcome-probe"
_SELF_PREFIX = "docs/outcome-probe/"


def _parse_expected(path: Path) -> set[str]:
    """One repo-relative path per line; '#' comments and blanks ignored."""
    out: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            out.add(line)
    return out


def _changed_files() -> set[str]:
    """Tracked modifications + untracked-but-not-ignored files, vs HEAD.

    Mirrors what a reviewer sees as "the diff of this task": staged,
    unstaged, and new files. The sealed-spec dir is excluded.
    """
    tracked = subprocess.run(
        ["git", "-C", str(REPO), "diff", "--name-only", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    untracked = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "--others", "--exclude-standard"],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    return {
        f for f in (*tracked, *untracked)
        if not f.startswith(_SELF_PREFIX)
    }


def _lint_all() -> int:
    if not PROBE_DIR.is_dir():
        print(f"ERROR: {PROBE_DIR.relative_to(REPO)} missing", file=sys.stderr)
        return 1
    expected_files = sorted(PROBE_DIR.glob("*.expected"))
    if not expected_files:
        print("ERROR: no *.expected sealed predictions found", file=sys.stderr)
        return 1
    bad = 0
    for ef in expected_files:
        s = _parse_expected(ef)
        if not s:
            print(f"ERROR: {ef.name} has no path entries", file=sys.stderr)
            bad += 1
            continue
        for p in sorted(s):
            if "/" not in p:  # repo-root file (e.g. ARCHITECTURE.md)
                continue
            # A path need not exist yet — a task may *create* it (the whole
            # point of new-domain is app/domains/<x>/ not existing). Only
            # the top-level segment must exist; that still catches real
            # typos (app/domian/…) without false-flagging task-created dirs.
            top = (REPO / p.split("/", 1)[0])
            if not top.exists():
                print(
                    f"WARN: {ef.name}: top-level dir '{p.split('/', 1)[0]}/' "
                    f"for '{p}' does not exist — typo in sealed set?",
                    file=sys.stderr,
                )
        print(f"  ok  {ef.name}  ({len(s)} files)")
    if bad:
        return 1
    print(f"\n{len(expected_files)} sealed prediction(s) well-formed.")
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    if argv[0] == "--lint":
        return _lint_all()

    task = argv[0]
    expected_path = PROBE_DIR / f"{task}.expected"
    if not expected_path.is_file():
        avail = ", ".join(sorted(p.stem for p in PROBE_DIR.glob("*.expected")))
        print(f"ERROR: unknown task {task!r}. Available: {avail}", file=sys.stderr)
        return 2

    expected = _parse_expected(expected_path)
    actual = _changed_files()

    missing = sorted(expected - actual)
    extra = sorted(actual - expected)

    w = max((len(p) for p in expected | actual), default=10)
    print(f"Task: {task}   (sealed: {len(expected)} files, changed: {len(actual)})")
    print("-" * (w + 12))
    for p in sorted(expected | actual):
        if p in expected and p in actual:
            flag = "OK"
        elif p in expected:
            flag = "MISSING"
        else:
            flag = "EXTRA"
        print(f"{p.ljust(w)}  {flag}")

    if missing or extra:
        print(file=sys.stderr)
        if missing:
            print(f"MISSING ({len(missing)}): predicted but not touched:", file=sys.stderr)
            for p in missing:
                print(f"  - {p}", file=sys.stderr)
        if extra:
            print(f"EXTRA ({len(extra)}): touched but not predicted:", file=sys.stderr)
            for p in extra:
                print(f"  + {p}", file=sys.stderr)
        print(
            "\nFAIL: file set does not exactly match the sealed prediction.",
            file=sys.stderr,
        )
        return 1

    print(f"\nPASS: changed-file set is exactly the sealed prediction ({task}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
