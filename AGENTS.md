# AGENTS.md

The agent contract for this repository lives in **[`CLAUDE.md`](CLAUDE.md)** —
read it first. This file is intentionally a pointer, not a copy: a second
authoritative file would just reintroduce the doc-drift Schritt 0 removes.

Quick map (all details, and all numbers, in the linked docs — never restate
counts here):

- **Agent contract** — edit protocol, import boundaries, scaffold usage:
  [`CLAUDE.md`](CLAUDE.md) → *Agent contract*.
- **Ist-Zustand** (structure + CI-verified Kennzahlen):
  [`ARCHITECTURE.md`](ARCHITECTURE.md).
- **Soll-Zustand** + frozen (Rev. 2) migration path:
  [`docs/scaling-roadmap.md`](docs/scaling-roadmap.md).

Doc-drift gate: `python3 scripts/check_architecture_metrics.py` asserts the
`ARCHITECTURE.md` Kennzahlen table against the codebase. If you change code so
a number no longer holds, update that table in the same change or CI fails.
