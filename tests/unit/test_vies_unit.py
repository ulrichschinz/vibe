"""Unit-test the VIES module without hitting the real service."""
from __future__ import annotations

import pytest

from app.domains.billing.models import ViesResponseStatus
from services.invoicing.vies import (
    ViesResult,
    _split_vat_id,
    check_vat_id,
)


@pytest.mark.unit
class TestSplitVatId:
    def test_strips_spaces(self):
        assert _split_vat_id("DE 123 456 789") == ("DE", "123456789")

    def test_uppercases_prefix(self):
        # Country prefix is normalized; the number portion is preserved as-is.
        assert _split_vat_id("at u99999999") == ("AT", "u99999999")

    def test_rejects_short(self):
        with pytest.raises(ValueError):
            _split_vat_id("D")

    def test_rejects_non_alpha_prefix(self):
        with pytest.raises(ValueError):
            _split_vat_id("12X12345678")


@pytest.mark.unit
class TestCheckVatIdMocked:
    def test_valid_response(self):
        class FakeResponse:
            __values__ = {"valid": True, "name": "Test GmbH"}
        class FakeService:
            def checkVat(self, **kwargs):
                return FakeResponse()
        class FakeClient:
            service = FakeService()

        r = check_vat_id("ATU99999999", _client_factory=lambda: FakeClient())
        assert r.status == ViesResponseStatus.valid
        assert r.country_code == "AT"

    def test_invalid_response(self):
        class FakeResponse:
            __values__ = {"valid": False}
        class FakeService:
            def checkVat(self, **kwargs):
                return FakeResponse()
        class FakeClient:
            service = FakeService()

        r = check_vat_id("ATU00000000", _client_factory=lambda: FakeClient())
        assert r.status == ViesResponseStatus.invalid

    def test_exception_yields_unavailable(self):
        class FakeService:
            def checkVat(self, **kwargs):
                raise ConnectionError("504 timeout")
        class FakeClient:
            service = FakeService()

        r = check_vat_id("FRZZ12345678", _client_factory=lambda: FakeClient())
        assert r.status == ViesResponseStatus.service_unavailable
        assert r.raw["type"] == "ConnectionError"
