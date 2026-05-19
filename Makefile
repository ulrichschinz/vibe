# Use the venv interpreter directly so `make` works without `source .venv/bin/activate`.
# Override with `make PY=python` if you've already activated.
PY ?= .venv/bin/python
# import-linter ships only a console script (no `python -m` entrypoint).
# CI runs with PY=python (system) so the script is on PATH; locally it's in
# the venv. Override with `make LINT_IMPORTS=.venv/bin/lint-imports` if needed.
LINT_IMPORTS ?= lint-imports

.PHONY: help install dev-install test test-fast test-unit test-integration test-contract test-e2e test-kosit test-pdfa coverage integrity-check clean verify lint lint-all format-check fmt typecheck contracts doc-gate new-domain outcome-probe

help:
	@echo "Vibe — make targets"
	@echo "  make install          install runtime deps"
	@echo "  make dev-install      install runtime + dev deps"
	@echo "  make verify           the gate: lint+format+typecheck+contracts+test-fast+doc-gate"
	@echo "  make lint             ruff lint"
	@echo "  make format-check     ruff format --check (new Soll surface)"
	@echo "  make fmt              ruff format (write)"
	@echo "  make typecheck        mypy (lax global, app.* strict)"
	@echo "  make contracts        import-linter (executable import boundaries)"
	@echo "  make doc-gate         assert ARCHITECTURE.md Kennzahlen vs. code"
	@echo "  make new-domain X     scaffold a new domain (app/domains/X + test)"
	@echo "  make outcome-probe TASK=x  check task file set vs sealed prediction"
	@echo "  make test             run full test suite + coverage"
	@echo "  make test-fast        run unit + integration only (skip contract/e2e)"
	@echo "  make test-unit        unit tests only"
	@echo "  make test-integration integration tests only"
	@echo "  make test-contract    KoSIT + veraPDF contract tests"
	@echo "  make test-e2e         end-to-end tests (FastAPI TestClient)"
	@echo "  make test-kosit       KoSIT validator only"
	@echo "  make test-pdfa        PDF/A-3 validation only"
	@echo "  make coverage         open HTML coverage report"
	@echo "  make integrity-check  run invoice integrity check CLI"
	@echo "  make clean            remove caches"

install:
	uv pip install -r requirements.txt

dev-install:
	uv pip install -r requirements-dev.txt

test:
	$(PY) -m pytest -n auto --cov

test-fast:
	$(PY) -m pytest -n auto -m "not contract and not e2e"

test-unit:
	$(PY) -m pytest tests/unit -n auto

test-integration:
	$(PY) -m pytest tests/integration -n auto

test-contract:
	$(PY) -m pytest tests/contract

test-e2e:
	$(PY) -m pytest tests/e2e

test-kosit:
	$(PY) -m pytest tests/contract/test_kosit.py

test-pdfa:
	$(PY) -m pytest tests/contract/test_pdfa3.py

coverage:
	@if [ -f reports/coverage/html/index.html ]; then \
		xdg-open reports/coverage/html/index.html 2>/dev/null || open reports/coverage/html/index.html 2>/dev/null || echo "report at reports/coverage/html/index.html"; \
	else \
		echo "No coverage report yet. Run 'make test' first."; \
	fi

integrity-check:
	$(PY) -m services.invoicing.integrity_check

# --- Schritt 1: Tooling-Fundament ------------------------------------------
# `verify` is THE acceptance gate for every migration step (roadmap: ruff +
# mypy + pytest + import-linter), with the Schritt-0 doc-gate folded in.
verify: lint format-check typecheck contracts test-fast doc-gate

# Lint, like format-check and mypy, gates only the new Soll surface
# (scripts/ tooling + app/). Legacy modules carry pre-existing style debt
# (semicolons, unused locals); fixing it repo-wide is churn that belongs to
# no step and would touch services/invoicing/ (move-not-rewrite) and the
# test suite. Each legacy module gets lint-clean when it moves into app/.
# `make lint-all` runs it everywhere (non-gating, for those cleanup steps).
lint:
	$(PY) -m ruff check scripts $$( [ -d app ] && echo app )

lint-all:
	$(PY) -m ruff check .

# Format is enforced only on `app/` — the generated Soll surface that the
# scaffold controls byte-for-byte (Scaffold-Vertrag: "import-linter- &
# format-conformant by construction"). Legacy modules and scripts/ tooling
# are NOT reformatted in Schritt 1 (repo-wide churn; services/invoicing/ is
# move-not-rewrite). No-op until app/ exists.
format-check:
	@if [ -d app ]; then $(PY) -m ruff format --check app; else echo "format-check: app/ not present yet (created by 'make new-domain') — skipped"; fi

fmt:
	@if [ -d app ]; then $(PY) -m ruff format app; else echo "fmt: app/ not present yet — nothing to format"; fi

typecheck:
	$(PY) -m mypy scripts $$( [ -d app ] && echo app )

contracts:
	$(LINT_IMPORTS)

doc-gate:
	$(PY) scripts/check_architecture_metrics.py

# Audit-Remediation T1: compare a task implementation's changed-file set
# against the sealed prediction in docs/outcome-probe/<task>.expected.
# Pure stdlib (like doc-gate) — locally runnable without app deps.
#   make outcome-probe TASK=lead-field
#   make outcome-probe TASK=--lint        (CI: every .expected well-formed)
outcome-probe:
	@test -n "$(TASK)" || { echo "usage: make outcome-probe TASK=<task|--lint>"; exit 2; }
	$(PY) scripts/outcome_probe.py $(TASK)

# One-command new domain (the anti-"random files" mechanism). Usage:
#   make new-domain X            (web router by default)
#   make new-domain X KIND=api   (REST router)
new-domain:
	@test -n "$(filter-out new-domain,$(MAKECMDGOALS))$(NAME)" || { echo "usage: make new-domain <name> [KIND=web|api]"; exit 2; }
	$(PY) scripts/new_domain.py $(if $(NAME),$(NAME),$(filter-out new-domain,$(MAKECMDGOALS))) $(if $(KIND),--kind $(KIND))
# Swallow the bare domain-name arg so `make new-domain leads` doesn't try to
# build a target called `leads`.
%:
	@:

clean:
	rm -rf .pytest_cache __pycache__ */__pycache__ .coverage reports/coverage
	find . -name '*.pyc' -delete
