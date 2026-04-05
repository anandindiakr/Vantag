"""
backend/webhooks/webhook_engine.py
====================================
Outbound webhook engine for the Vantag platform.

Dispatches platform events to external systems (Slack, Microsoft Teams,
Twilio SMS, or generic HTTP endpoints) based on configurable subscriptions
loaded from ``webhooks.yaml``.

Subscription schema (webhooks.yaml)
------------------------------------
webhooks:
  - id: str                     # unique identifier
    name: str                   # human-readable label
    connector: slack | teams | twilio | generic
    url: str                    # target URL (not used by twilio)
    event_types: list[str]      # ["sweeping", "*"] (* = all)
    severity_threshold: LOW | MEDIUM | HIGH
    headers: dict               # extra HTTP headers (generic connector)
    payload_template: dict      # JSON template with {{field}} placeholders
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_from: str
    twilio_to: str

Retry policy
------------
3 attempts per subscription with exponential back-off: 2 s, 4 s, 8 s.

Delivery log
------------
Each dispatch attempt is appended as a JSON line to
``webhooks/delivery_log.jsonl`` relative to the repo root.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from abc import ABC, abstractmethod
from base64 import b64encode
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import yaml

logger = logging.getLogger(__name__)

# ─── Paths ────────────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DELIVERY_LOG = _REPO_ROOT / "webhooks" / "delivery_log.jsonl"

# ─── Severity ordering ────────────────────────────────────────────────────────

_SEVERITY_ORDER = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}

# ─── Retry parameters ────────────────────────────────────────────────────────

_RETRY_DELAYS = [2.0, 4.0, 8.0]


# ─── Base Connector ──────────────────────────────────────────────────────────

class BaseConnector(ABC):
    """Abstract base class for all webhook connectors."""

    def __init__(self, subscription: dict) -> None:
        self.subscription = subscription

    @abstractmethod
    async def send(self, event: dict, client: httpx.AsyncClient) -> httpx.Response:
        """Format and send the event.  Returns the HTTP response."""

    def subscription_id(self) -> str:
        return self.subscription.get("id", "unknown")


# ─── Slack Connector ─────────────────────────────────────────────────────────

class SlackConnector(BaseConnector):
    """
    Formats and delivers a Slack Block Kit message.

    Uses Slack's incoming webhook URL.  Includes:
      - Severity-coloured side bar
      - Camera name, event type, timestamp
      - Compact details field
    """

    _COLOUR_MAP = {"LOW": "#22C55E", "MEDIUM": "#F59E0B", "HIGH": "#EF4444"}

    async def send(self, event: dict, client: httpx.AsyncClient) -> httpx.Response:
        url = self.subscription["url"]
        colour = self._COLOUR_MAP.get(
            str(event.get("severity", "LOW")).upper(), "#6B7280"
        )
        timestamp = event.get("timestamp", datetime.now(tz=timezone.utc).isoformat())
        event_type = str(event.get("type", "event")).replace("_", " ").title()
        camera_id = event.get("camera_id", "unknown")
        store_id = event.get("store_id", "unknown")
        description = event.get("description", "No description provided.")

        payload = {
            "attachments": [
                {
                    "color": colour,
                    "blocks": [
                        {
                            "type": "header",
                            "text": {
                                "type": "plain_text",
                                "text": f"Vantag Alert: {event_type}",
                                "emoji": True,
                            },
                        },
                        {
                            "type": "section",
                            "fields": [
                                {
                                    "type": "mrkdwn",
                                    "text": f"*Severity*\n{event.get('severity', 'LOW')}",
                                },
                                {
                                    "type": "mrkdwn",
                                    "text": f"*Store*\n{store_id}",
                                },
                                {
                                    "type": "mrkdwn",
                                    "text": f"*Camera*\n{camera_id}",
                                },
                                {
                                    "type": "mrkdwn",
                                    "text": f"*Time*\n{timestamp}",
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"*Description*\n{description}",
                            },
                        },
                        {
                            "type": "context",
                            "elements": [
                                {
                                    "type": "mrkdwn",
                                    "text": f"Event ID: {event.get('id', 'N/A')}",
                                }
                            ],
                        },
                    ],
                }
            ]
        }

        return await client.post(url, json=payload)


# ─── Teams Connector ─────────────────────────────────────────────────────────

class TeamsConnector(BaseConnector):
    """
    Formats and delivers a Microsoft Teams Adaptive Card via incoming webhook.
    """

    _COLOUR_MAP = {
        "LOW": "Good",
        "MEDIUM": "Warning",
        "HIGH": "Attention",
    }

    async def send(self, event: dict, client: httpx.AsyncClient) -> httpx.Response:
        url = self.subscription["url"]
        severity = str(event.get("severity", "LOW")).upper()
        colour_key = self._COLOUR_MAP.get(severity, "Default")
        event_type = str(event.get("type", "event")).replace("_", " ").title()

        payload = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "contentUrl": None,
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": f"Vantag Alert — {event_type}",
                                "weight": "Bolder",
                                "size": "Medium",
                                "color": colour_key,
                            },
                            {
                                "type": "FactSet",
                                "facts": [
                                    {
                                        "title": "Severity",
                                        "value": severity,
                                    },
                                    {
                                        "title": "Store",
                                        "value": str(event.get("store_id", "N/A")),
                                    },
                                    {
                                        "title": "Camera",
                                        "value": str(event.get("camera_id", "N/A")),
                                    },
                                    {
                                        "title": "Timestamp",
                                        "value": str(
                                            event.get(
                                                "timestamp",
                                                datetime.now(tz=timezone.utc).isoformat(),
                                            )
                                        ),
                                    },
                                ],
                            },
                            {
                                "type": "TextBlock",
                                "text": str(
                                    event.get("description", "No description.")
                                ),
                                "wrap": True,
                            },
                        ],
                    },
                }
            ],
        }

        return await client.post(url, json=payload)


# ─── Twilio Connector ─────────────────────────────────────────────────────────

class TwilioConnector(BaseConnector):
    """
    Sends an SMS via the Twilio REST API.

    Required subscription keys:
      twilio_account_sid, twilio_auth_token, twilio_from, twilio_to
    """

    async def send(self, event: dict, client: httpx.AsyncClient) -> httpx.Response:
        sub = self.subscription
        account_sid = sub.get("twilio_account_sid", "")
        auth_token = sub.get("twilio_auth_token", "")
        from_number = sub.get("twilio_from", "")
        to_number = sub.get("twilio_to", "")

        if not all([account_sid, auth_token, from_number, to_number]):
            raise ValueError(
                "TwilioConnector: missing twilio_account_sid, twilio_auth_token, "
                "twilio_from, or twilio_to in subscription config."
            )

        event_type = str(event.get("type", "event")).replace("_", " ").title()
        severity = str(event.get("severity", "UNKNOWN"))
        store_id = str(event.get("store_id", "N/A"))
        timestamp = str(event.get("timestamp", datetime.now(tz=timezone.utc).isoformat()))[:19]

        body = (
            f"[VANTAG {severity}] {event_type}\n"
            f"Store: {store_id}\n"
            f"Camera: {event.get('camera_id', 'N/A')}\n"
            f"Time: {timestamp}\n"
            f"{event.get('description', '')}"
        )[:1600]  # Twilio SMS limit

        url = (
            f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
        )

        # Basic auth: account_sid:auth_token → base64
        credentials = b64encode(f"{account_sid}:{auth_token}".encode()).decode()
        headers = {"Authorization": f"Basic {credentials}"}
        data = {"From": from_number, "To": to_number, "Body": body}

        return await client.post(url, data=data, headers=headers)


# ─── Generic Webhook Connector ───────────────────────────────────────────────

class GenericWebhookConnector(BaseConnector):
    """
    HTTP POST with configurable JSON payload.

    Supports ``{{field}}`` placeholders in ``payload_template`` that are
    replaced with matching event fields at dispatch time.
    """

    async def send(self, event: dict, client: httpx.AsyncClient) -> httpx.Response:
        url = self.subscription["url"]
        extra_headers: Dict[str, str] = self.subscription.get("headers", {})
        template: Optional[dict] = self.subscription.get("payload_template")

        if template:
            payload = self._render_template(template, event)
        else:
            # Default: send the full event dict
            payload = {
                "event_type": event.get("type"),
                "severity": event.get("severity"),
                "store_id": event.get("store_id"),
                "camera_id": event.get("camera_id"),
                "timestamp": event.get("timestamp"),
                "description": event.get("description"),
                "payload": event.get("payload", {}),
            }

        return await client.post(url, json=payload, headers=extra_headers)

    def _render_template(self, template: Any, event: dict) -> Any:
        """Recursively replace {{field}} placeholders in the template."""
        if isinstance(template, str):
            def replace(m: re.Match) -> str:
                key = m.group(1).strip()
                # Support nested keys with dot notation
                val = event
                for part in key.split("."):
                    if isinstance(val, dict):
                        val = val.get(part, "")
                    else:
                        val = ""
                        break
                return str(val) if val is not None else ""

            return re.sub(r"\{\{(.+?)\}\}", replace, template)
        elif isinstance(template, dict):
            return {k: self._render_template(v, event) for k, v in template.items()}
        elif isinstance(template, list):
            return [self._render_template(v, event) for v in template]
        return template


# ─── Connector factory ────────────────────────────────────────────────────────

def _make_connector(subscription: dict) -> BaseConnector:
    connector_type = subscription.get("connector", "generic").lower()
    dispatch_map = {
        "slack": SlackConnector,
        "teams": TeamsConnector,
        "twilio": TwilioConnector,
        "generic": GenericWebhookConnector,
    }
    cls = dispatch_map.get(connector_type, GenericWebhookConnector)
    return cls(subscription)


# ─── Delivery log ─────────────────────────────────────────────────────────────

def _append_delivery_log(entry: dict) -> None:
    """Append a delivery log entry as JSON line (best-effort, non-blocking)."""
    try:
        _DELIVERY_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _DELIVERY_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Delivery log write failed: %s", exc)


# ─── WebhookEngine ────────────────────────────────────────────────────────────

class WebhookEngine:
    """
    Outbound webhook dispatcher for the Vantag platform.

    Parameters
    ----------
    config_path:
        Path to ``webhooks.yaml``.  Defaults to
        ``backend/webhooks/webhooks.yaml`` relative to the repo root.
    """

    def __init__(self, config_path: Optional[str] = None) -> None:
        if config_path is None:
            config_path = str(
                _REPO_ROOT / "backend" / "webhooks" / "webhooks.yaml"
            )
        self._config_path = config_path
        self._subscriptions: List[dict] = []
        self._load_config()

    @property
    def subscriptions(self) -> List[dict]:
        """Public read-only access to loaded webhook subscriptions."""
        return list(self._subscriptions)

    # ── Config ───────────────────────────────────────────────────────────────

    def _load_config(self) -> None:
        path = Path(self._config_path)
        if not path.exists():
            logger.warning(
                "WebhookEngine: config not found at %s — no webhooks will fire.",
                self._config_path,
            )
            return
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            self._subscriptions = data.get("webhooks", [])
            logger.info(
                "WebhookEngine: loaded %d subscription(s) from %s",
                len(self._subscriptions),
                self._config_path,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("WebhookEngine: failed to load config: %s", exc)

    def reload_config(self) -> None:
        """Reload the YAML config (can be called at runtime)."""
        self._subscriptions = []
        self._load_config()

    # ── Event matching ────────────────────────────────────────────────────────

    def _matches(self, subscription: dict, event: dict) -> bool:
        """Return True if the event matches the subscription's filters."""
        # Event type filter
        event_types: List[str] = subscription.get("event_types", ["*"])
        event_type = str(event.get("type", ""))
        if "*" not in event_types and event_type not in event_types:
            return False

        # Severity threshold filter
        threshold = str(subscription.get("severity_threshold", "LOW")).upper()
        event_severity = str(event.get("severity", "LOW")).upper()
        if _SEVERITY_ORDER.get(event_severity, 0) < _SEVERITY_ORDER.get(threshold, 0):
            return False

        return True

    # ── Single subscription dispatch with retry ───────────────────────────────

    async def _dispatch_to_subscription(
        self,
        subscription: dict,
        event: dict,
        client: httpx.AsyncClient,
    ) -> None:
        connector = _make_connector(subscription)
        sub_id = subscription.get("id", "unknown")
        event_id = str(event.get("id", ""))

        for attempt, delay in enumerate(_RETRY_DELAYS, start=1):
            try:
                response = await connector.send(event, client)
                status = response.status_code

                if 200 <= status < 300:
                    logger.info(
                        "Webhook delivered | sub=%s event=%s attempt=%d status=%d",
                        sub_id,
                        event_id,
                        attempt,
                        status,
                    )
                    _append_delivery_log(
                        {
                            "subscription_id": sub_id,
                            "event_id": event_id,
                            "status": "delivered",
                            "http_status": status,
                            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                            "attempt": attempt,
                        }
                    )
                    return  # Success

                logger.warning(
                    "Webhook non-2xx | sub=%s event=%s attempt=%d status=%d",
                    sub_id,
                    event_id,
                    attempt,
                    status,
                )

            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Webhook error | sub=%s event=%s attempt=%d error=%s",
                    sub_id,
                    event_id,
                    attempt,
                    exc,
                )

            # Not the last attempt — back off
            if attempt < len(_RETRY_DELAYS):
                await asyncio.sleep(delay)

        # All attempts exhausted
        logger.error(
            "Webhook delivery failed after %d attempts | sub=%s event=%s",
            len(_RETRY_DELAYS),
            sub_id,
            event_id,
        )
        _append_delivery_log(
            {
                "subscription_id": sub_id,
                "event_id": event_id,
                "status": "failed",
                "http_status": None,
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "attempt": len(_RETRY_DELAYS),
            }
        )

    # ── Main dispatch method ──────────────────────────────────────────────────

    async def dispatch(self, event: dict) -> None:
        """
        Dispatch a platform event to all matching webhook subscriptions.

        Matching subscriptions are notified concurrently via asyncio.gather.
        Each subscription delivery is independently retried up to 3 times.

        Parameters
        ----------
        event:
            Event dict with at minimum:
              - type: str
              - severity: 'LOW' | 'MEDIUM' | 'HIGH'
              - id: str
              - store_id: str
              - camera_id: str
              - timestamp: str (ISO-8601)
              - description: str
        """
        if not self._subscriptions:
            return

        matching = [s for s in self._subscriptions if self._matches(s, event)]
        if not matching:
            logger.debug(
                "WebhookEngine: no subscriptions matched event type='%s' severity='%s'",
                event.get("type"),
                event.get("severity"),
            )
            return

        logger.info(
            "WebhookEngine: dispatching event type='%s' to %d subscription(s)",
            event.get("type"),
            len(matching),
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            tasks = [
                self._dispatch_to_subscription(sub, event, client)
                for sub in matching
            ]
            await asyncio.gather(*tasks, return_exceptions=True)
