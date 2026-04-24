"""Regional configuration for India, Singapore, Malaysia."""
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
        "razorpay_key_id": os.getenv("RAZORPAY_KEY_ID_IN", ""),
        "razorpay_key_secret": os.getenv("RAZORPAY_KEY_SECRET_IN", ""),
        "domain": "retailnazar.com",
        "support_email": "support@retail-vantag.com",
    },
    "SG": {
        "name": "Singapore",
        "app_name": "Vantag - Retail Intelligence",
        "currency": "SGD",
        "symbol": "S$",
        "language": "en",
        "languages": ["en", "zh"],
        "razorpay_key_id": os.getenv("RAZORPAY_KEY_ID_SG", ""),
        "razorpay_key_secret": os.getenv("RAZORPAY_KEY_SECRET_SG", ""),
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
        "razorpay_key_id": os.getenv("RAZORPAY_KEY_ID_MY") or os.getenv("RAZORPAY_KEY_ID_SG", ""),
        "razorpay_key_secret": os.getenv("RAZORPAY_KEY_SECRET_MY") or os.getenv("RAZORPAY_KEY_SECRET_SG", ""),
        "domain": "retailjagajaga.com",
        "support_email": "support@retail-vantag.com",
    },
}

SUPPORTED_COUNTRIES = list(REGIONS.keys())


def get_region(country: str) -> dict:
    return REGIONS.get(country.upper(), REGIONS["IN"])
