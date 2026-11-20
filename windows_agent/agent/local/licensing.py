from __future__ import annotations

import base64
import json
import math
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


@dataclass(frozen=True)
class EntitlementStatus:
    state: str
    reason: str = ""
    claims: dict = field(default_factory=dict)

    @property
    def can_process(self) -> bool:
        return self.state in {"active", "grace"}

    def as_dict(self) -> dict:
        return {"state": self.state, "reason": self.reason, "can_process": self.can_process, "claims": self.claims}


def evaluate_entitlement(envelope: dict, trusted_keys: dict, device_id: str, now: datetime | None = None, expected_tenant: str | None = None, last_seen: float = 0) -> EntitlementStatus:
    current = (now or datetime.now(timezone.utc)).timestamp()
    try:
        payload = envelope["payload"]
        if not isinstance(payload, str) or len(payload) > 32768:
            raise ValueError("Invalid entitlement size")
        claims = json.loads(base64.b64decode(payload, altchars=b"-_", validate=True))
        key = serialization.load_pem_public_key(trusted_keys[claims["key_id"]].encode())
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError("An Ed25519 verification key is required")
        key.verify(base64.b64decode(envelope["signature"], altchars=b"-_", validate=True), payload.encode("ascii"))
        if claims["version"] != 1 or claims["grace_days"] != 7:
            raise ValueError("Unsupported entitlement policy")
        licence_type = claims.get("licence_type", "customer")
        if licence_type not in {"customer", "evaluation", "internal_demo"}:
            raise ValueError("Unsupported licence type")
        permanent = licence_type == "internal_demo"
        if licence_type != "customer":
            binding = claims.get("device_id")
            if claims.get("issuing_role") != "super_admin" or not isinstance(binding, str) or len(binding) != 64 or any(character not in "0123456789abcdef" for character in binding):
                raise ValueError("Demo grants require superadmin authority and device binding")
        date_names = ("issued_at", "not_before") if permanent else ("issued_at", "not_before", "expires_at")
        for name in date_names:
            if isinstance(claims[name], bool) or not isinstance(claims[name], (int, float)) or not math.isfinite(claims[name]):
                raise ValueError("Invalid entitlement date")
        if permanent and claims.get("expires_at", "missing") is not None:
            raise ValueError("Internal demo policy requires an explicit non-expiring grant")
        if (not permanent and claims["expires_at"] <= claims["not_before"]) or claims["issued_at"] > current + 300:
            raise ValueError("Invalid entitlement date range")
        if current < claims["not_before"] or current < last_seen - 300:
            raise ValueError("Clock rollback or entitlement not yet valid; correct the clock or import a renewal")
        if not isinstance(claims["camera_limit"], int) or isinstance(claims["camera_limit"], bool) or not 1 <= claims["camera_limit"] <= 256:
            raise ValueError("Invalid camera limit")
        if not isinstance(claims["revision"], int) or claims["revision"] < 1:
            raise ValueError("Invalid entitlement revision")
        if not isinstance(claims["features"], list) or not all(isinstance(feature, str) for feature in claims["features"]):
            raise ValueError("Invalid feature list")
        if not all(isinstance(claims.get(name), str) and claims[name] for name in ("tenant_id", "issuer", "entitlement_id")):
            raise ValueError("Missing entitlement identity")
        if expected_tenant and claims["tenant_id"] != expected_tenant:
            raise ValueError("This entitlement belongs to another account")
        if claims.get("device_id") not in (None, device_id):
            raise ValueError("This entitlement belongs to another device")
        state = "active" if permanent or current < claims["expires_at"] else "grace" if current < claims["expires_at"] + 7 * 86400 else "expired"
        return EntitlementStatus(state, claims=claims)
    except Exception:
        return EntitlementStatus("invalid", "Entitlement signature, identity, dates, clock or policy validation failed")


class LicenceManager:
    def __init__(self, store, trusted_keys: dict, device_id: str):
        self.store = store
        self.trusted_keys = trusted_keys
        self.device_id = device_id
        self.lock = threading.RLock()

    def status(self, now: datetime | None = None) -> EntitlementStatus:
        with self.lock:
            record = self.store.get("entitlement")
            if not record:
                return EntitlementStatus("missing", "Import a signed offline entitlement")
            result = evaluate_entitlement(record["envelope"], self.trusted_keys, self.device_id, now, record["tenant_id"], record["last_seen"])
            if record["device_id"] != self.device_id:
                return EntitlementStatus("invalid", "Local activation belongs to another device")
            current = (now or datetime.now(timezone.utc)).timestamp()
            if result.state != "invalid" and current >= record["last_seen"] + 30:
                record["last_seen"] = current
                self.store.set("entitlement", record)
            return result

    def install(self, envelope: dict, now: datetime | None = None) -> EntitlementStatus:
        with self.lock:
            previous = self.store.get("entitlement")
            result = evaluate_entitlement(envelope, self.trusted_keys, self.device_id, now, previous["tenant_id"] if previous else None, previous["last_seen"] if previous else 0)
            if result.state in {"invalid", "expired"}:
                raise ValueError(result.reason or "Entitlement has expired")
            if previous:
                old = evaluate_entitlement(previous["envelope"], self.trusted_keys, self.device_id, now)
                if not old.claims or result.claims["issuer"] != old.claims["issuer"] or result.claims["issued_at"] < old.claims["issued_at"]:
                    raise ValueError("Entitlement issuer or issuance rollback rejected")
                if result.claims["revision"] <= old.claims["revision"] or result.claims.get("device_id") != self.device_id:
                    raise ValueError("A newer, device-bound renewal is required")
                if result.claims["camera_limit"] < len(self.store.cameras()):
                    raise ValueError("Remove excess cameras before importing a lower camera limit")
            self.store.set("entitlement", {"envelope": envelope, "tenant_id": result.claims["tenant_id"], "device_id": self.device_id, "last_seen": (now or datetime.now(timezone.utc)).timestamp()})
            self.store.audit("Signed offline entitlement imported")
            return result

    def request(self) -> dict:
        record = self.store.get("entitlement", {})
        return {"version": 1, "device_id": self.device_id, "tenant_id": record.get("tenant_id"), "purpose": "offline_entitlement_renewal"}
