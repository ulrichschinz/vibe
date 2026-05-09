# Use the venv interpreter directly so `make` works without `source .venv/bin/activate`.
# Override with `make PY=python` if you've already activated.
PY ?= .venv/bin/python

.PHONY: help install dev-install test test-fast test-unit test-integration test-contract test-e2e test-kosit test-pdfa coverage integrity-check clean

help:
	@echo "Vibe — make targets"
	@echo "  make install          install runtime deps"
	@echo "  make dev-install      install runtime + dev deps"
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

clean:
	rm -rf .pytest_cache __pycache__ */__pycache__ .coverage reports/coverage
	find . -name '*.pyc' -delete
