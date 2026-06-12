"""Subscription plan definitions for all regions."""
from __future__ import annotations

PLANS: dict[str, dict] = {
    "starter": {
        "id": "starter",
        "name": "Nazar Starter",
        "max_cameras": 5,
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
            "INR": 2999,
            "SGD": 49,
            "MYR": 149,
        },
        "razorpay_plan_ids": {
            "INR": "",   # fill after creating in Razorpay dashboard
            "SGD": "",
            "MYR": "",
        },
        "trial_days": 14,
    },
    "growth": {
        "id": "growth",
        "name": "Nazar Growth",
        "max_cameras": 15,
        "max_edge_agents": 5,
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
            "INR": 5999,
            "SGD": 99,
            "MYR": 299,
        },
        "razorpay_plan_ids": {
            "INR": "",
            "SGD": "",
            "MYR": "",
        },
        "trial_days": 14,
    },
    "enterprise": {
        "id": "enterprise",
        "name": "Nazar Enterprise",
        "max_cameras": 30,
        "max_edge_agents": 10,
        "features": [
            "Everything in Growth",
            "POS Integration",
            "Multi-location Management",
            "Custom Webhooks",
            "API Access",
            "Unlimited event history",
            "Dedicated Support",
            "SLA 99.9%",
        ],
        "prices": {
            "INR": 11999,
            "SGD": 199,
            "MYR": 599,
        },
        "razorpay_plan_ids": {
            "INR": "",
            "SGD": "",
            "MYR": "",
        },
        "trial_days": 14,
    },
}


def get_plan(plan_id: str) -> dict | None:
    return PLANS.get(plan_id)


def get_plan_price(plan_id: str, currency: str) -> int:
    plan = get_plan(plan_id)
    if not plan:
        return 0
    return plan["prices"].get(currency, 0)
