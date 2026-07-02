"""Regional configuration — India, Singapore, Malaysia, Philippines."""
from __future__ import annotations

import os

REGIONS: dict[str, dict] = {
    "IN": {
        "name": "India",
        "app_name": "Vantag - Retail Nazar",
        "currency": "INR",
        "symbol": "₹",
        "language": "hi",
        "languages": ["en", "hi", "ta", "te", "kn", "ml", "mr", "gu", "bn", "pa"],
        "payment_gateway": "razorpay",
        "razorpay_key_id": os.getenv("RAZORPAY_KEY_ID_IN", ""),
        "razorpay_key_secret": os.getenv("RAZORPAY_KEY_SECRET_IN", ""),
        "domain": "retailnazar.com",
        "support_email": "support@retailnazar.com",
    },
    "SG": {
        "name": "Singapore",
        "app_name": "Vantag - Retail Intelligence",
        "currency": "SGD",
        "symbol": "S$",
        "language": "en",
        "languages": ["en", "zh"],
        "payment_gateway": "xendit",
        "xendit_public_key": os.getenv("XENDIT_PUBLIC_KEY_SG", ""),
        "xendit_secret_key": os.getenv("XENDIT_SECRET_KEY_SG", ""),
        "xendit_webhook_token": os.getenv("XENDIT_WEBHOOK_TOKEN_SG", ""),
        "domain": "retail-vantag.com",
        "support_email": "support@retail-vantag.com",
    },
    "MY": {
        "name": "Malaysia",
        "app_name": "Vantag JagaJaga",
        "currency": "MYR",
        "symbol": "RM",
        "language": "ms",
        "languages": ["en", "ms"],
        "payment_gateway": "xendit",
        "xendit_public_key": os.getenv("XENDIT_PUBLIC_KEY_MY", ""),
        "xendit_secret_key": os.getenv("XENDIT_SECRET_KEY_MY", ""),
        "xendit_webhook_token": os.getenv("XENDIT_WEBHOOK_TOKEN_MY", ""),
        "domain": "retailjagajaga.com",
        "support_email": "support@retail-vantag.com",
    },
    "PH": {
        "name": "Philippines",
        "app_name": "Vantag - Retail Bantay",
        "currency": "PHP",
        "symbol": "₱",
        "language": "en",
        "languages": ["en", "fil"],
        "payment_gateway": "xendit",
        "xendit_public_key": os.getenv("XENDIT_PUBLIC_KEY_PH", ""),
        "xendit_secret_key": os.getenv("XENDIT_SECRET_KEY_PH", ""),
        "xendit_webhook_token": os.getenv("XENDIT_WEBHOOK_TOKEN_PH", ""),
        "domain": "retailbantay.com",
        "support_email": "support@retailbantay.com",
    },
}

SUPPORTED_COUNTRIES = list(REGIONS.keys())


def get_region(country: str) -> dict:
    return REGIONS.get(country.upper(), REGIONS["IN"])
