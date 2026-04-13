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
        "languages": ["en", "hi"],
        "razorpay_key_id": os.getenv("RAZORPAY_KEY_ID_IN", ""),
        "razorpay_key_secret": os.getenv("RAZORPAY_KEY_SECRET_IN", ""),
        "domain": "vantag.in",
        "support_email": "support@vantag.in",
    },
    "SG": {
        "name": "Singapore",
        "app_name": "Vantag",
        "currency": "SGD",
        "symbol": "S$",
        "language": "en",
        "languages": ["en", "zh"],
        "razorpay_key_id": os.getenv("RAZORPAY_KEY_ID_SG", ""),
        "razorpay_key_secret": os.getenv("RAZORPAY_KEY_SECRET_SG", ""),
        "domain": "vantag.sg",
        "support_email": "support@vantag.sg",
    },
    "MY": {
        "name": "Malaysia",
        "app_name": "Vantag JagaJaga",
        "currency": "MYR",
        "symbol": "RM",
        "language": "ms",
        "languages": ["en", "ms"],
        "razorpay_key_id": os.getenv("RAZORPAY_KEY_ID_MY", ""),
        "razorpay_key_secret": os.getenv("RAZORPAY_KEY_SECRET_MY", ""),
        "domain": "jagajaga.my",
        "support_email": "support@jagajaga.my",
    },
}

SUPPORTED_COUNTRIES = list(REGIONS.keys())


def get_region(country: str) -> dict:
    return REGIONS.get(country.upper(), REGIONS["IN"])
