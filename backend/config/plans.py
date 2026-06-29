"""Subscription plan definitions for all regions."""
from __future__ import annotations

PLANS: dict[str, dict] = {
    "starter": {
        "id": "starter",
        "name": "Nazar Starter",
        "max_cameras": 4,
        "max_edge_agents": 2,
        "features": [
            "AI Detection (Sweep, Dwell, Empty Shelf)",
            "Real-time Dashboard",
            "One-Tap Door Lock",
            "Email Alerts",
            "7-day event history",
            "PDF Reports",
        ],
        "prices": {
            "INR": 1999,
            "SGD": 49,
            "MYR": 149,
        },
        "razorpay_plan_ids": {
            "INR": "",   # fill after creating in Razorpay dashboard
            "SGD": "",
            "MYR": "",
        },
        "trial_days": 3,
    },
    "growth": {
        "id": "growth",
        "name": "Nazar Growth",
        "max_cameras": 10,
        "max_edge_agents": 4,
        "features": [
            "Everything in Starter",
            "Face Recognition & Watchlist",
            "Heatmap Analytics",
            "Queue Detection",
            "Slack / Teams Webhooks",
            "30-day event history",
            "Priority Support",
        ],
        "prices": {
            "INR": 4499,
            "SGD": 99,
            "MYR": 299,
        },
        "razorpay_plan_ids": {
            "INR": "",
            "SGD": "",
            "MYR": "",
        },
        "trial_days": 3,
    },
    "pro": {
        "id": "pro",
        "name": "Nazar Pro",
        "max_cameras": 20,
        "max_edge_agents": 8,
        "features": [
            "Everything in Growth",
            "Watchlist Matching",
            "Multi-location Management",
            "Custom Webhooks + API",
            "Unlimited event history",
            "Dedicated Support",
        ],
        "prices": {
            "INR": 9999,
            "SGD": 149,
            "MYR": 449,
        },
        "razorpay_plan_ids": {
            "INR": "",
            "SGD": "",
            "MYR": "",
        },
        "trial_days": 3,
    },
    "proplus": {
        "id": "proplus",
        "name": "Nazar Pro Plus",
        "max_cameras": 30,
        "max_edge_agents": 12,
        "features": [
            "Everything in Pro",
            "Custom AI Training",
            "SLA Uptime Guarantee",
            "Dedicated Account Manager",
            "On-site Support",
        ],
        "prices": {
            "INR": 15000,
            "SGD": 199,
            "MYR": 599,
        },
        "razorpay_plan_ids": {
            "INR": "",
            "SGD": "",
            "MYR": "",
        },
        "trial_days": 3,
    },
}


def get_plan(plan_id: str) -> dict | None:
    return PLANS.get(plan_id)


def get_plan_price(plan_id: str, currency: str) -> int:
    plan = get_plan(plan_id)
    if not plan:
        return 0
    return plan["prices"].get(currency, 0)
