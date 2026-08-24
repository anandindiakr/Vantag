"""Regression tests for the payment and authentication hardening batch."""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.api.billing_router import _provider_event_id
from backend.config import regions
from backend.services import email_service, razorpay_service


@pytest.fixture
def restore_payment_environment(monkeypatch):
    original_secret = regions.REGIONS["IN"].get("razorpay_key_secret", "")
    monkeypatch.setitem(regions.REGIONS["IN"], "razorpay_key_secret", "")
    monkeypatch.setenv("VANTAG_ENV", "production")
    monkeypatch.delenv("VANTAG_PAYMENT_TEST_MODE", raising=False)
    yield
    regions.REGIONS["IN"]["razorpay_key_secret"] = original_secret


def test_missing_razorpay_credentials_fail_closed(restore_payment_environment):
    assert not razorpay_service.verify_payment_signature(
        "order_1", "pay_1", "anything", "IN"
    )
    assert not razorpay_service.verify_webhook_signature(
        b'{"event":"payment.captured"}', "anything", "IN"
    )


def test_unsigned_payment_requires_explicit_non_production_test_mode(monkeypatch):
    monkeypatch.setitem(regions.REGIONS["IN"], "razorpay_key_secret", "")
    monkeypatch.setenv("VANTAG_ENV", "development")
    monkeypatch.setenv("VANTAG_PAYMENT_TEST_MODE", "1")

    assert razorpay_service.verify_payment_signature("o", "p", "", "IN")
    assert razorpay_service.verify_webhook_signature(b"payload", "", "IN")


def test_provider_event_id_is_stable_even_without_provider_id():
    payload = b'{"event":"payment.captured"}'
    expected_hash = hashlib.sha256(payload).hexdigest()

    first = _provider_event_id("razorpay", payload, None)
    second = _provider_event_id("razorpay", payload, None)

    assert first == second == f"razorpay:{expected_hash}"
    assert first


def test_otp_is_numeric_and_has_requested_length(monkeypatch):
    monkeypatch.setattr(email_service.secrets, "choice", lambda digits: digits[0])
    otp = email_service.generate_otp(8)

    assert otp == "0" * 8
    assert otp.isdigit()
    assert len(otp) == 8


def test_otp_rejects_non_positive_length():
    with pytest.raises(ValueError):
        email_service.generate_otp(0)
