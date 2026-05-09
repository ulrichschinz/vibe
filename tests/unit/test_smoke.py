"""Smoke test: confirms pytest collects and runs."""
import pytest


@pytest.mark.unit
def test_pytest_runs():
    assert 1 + 1 == 2
