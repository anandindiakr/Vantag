"""
Pluggable door-relay drivers for the Vantag Edge Agent.

One ``RelayDriver`` interface, many hardware backends, so the same on-site
agent can drive almost any door relay without code changes:

    simulate     – no hardware; logs and reports state (default / demo)
    http         – any WiFi/Ethernet relay exposing a simple HTTP API
                   (Shelly, Tasmota, ESPHome, Sonoff, custom REST boards)
    gpio         – a relay wired to a GPIO pin on a Raspberry Pi / SBC
    serial       – USB or RS-485 relay boards controlled over a serial port
    modbus_tcp   – network Modbus relay boards (write a single coil)

Configuration comes from ``AgentConfig.door_control``, for example::

    {"relay_type": "http", "http_url": "http://192.168.1.50/relay/0"}
    {"relay_type": "gpio", "gpio_pin": 17}
    {"relay_type": "serial", "serial_port": "/dev/ttyUSB0", "serial_baud": 9600}
    {"relay_type": "modbus_tcp", "modbus_host": "192.168.1.51",
     "modbus_port": 502, "modbus_unit": 1, "modbus_coil": 0}

Every backend imports its optional dependency (RPi.GPIO, pyserial, pymodbus)
lazily and degrades to a logged no-op when the dependency or hardware is
missing, so the agent always keeps running.

``discover_relays()`` is best-effort plug-and-play: it probes common relay
HTTP endpoints on the local network and returns whatever it can identify.
"""

from __future__ import annotations

import json
import logging
import socket
import urllib.request
from typing import Dict, List, Optional

log = logging.getLogger("vantag.relay")


class RelayDriver:
    """Base class for door-relay actuators."""

    name = "relay"

    def actuate(self, door_id: str, action: str) -> bool:
        """Drive the relay. ``action`` is ``'lock'`` or ``'unlock'``."""
        raise NotImplementedError

    def describe(self) -> dict:
        return {"relay_type": self.name}


class SimulateRelay(RelayDriver):
    name = "simulate"

    def __init__(self, config: Optional[dict] = None):
        # Accept an (ignored) config so build_relay() can construct every
        # driver uniformly through cls(config).
        pass

    def actuate(self, door_id: str, action: str) -> bool:
        log.info("Relay (simulate) | door=%s action=%s", door_id, action)
        return True


class HttpRelay(RelayDriver):
    """Drives a relay through a generic HTTP endpoint.

    Supports two URL styles:
      * ``http_url`` — POSTed with ``{door_id, action}`` (generic REST relay)
      * ``http_url_template`` — a template with ``{action}`` substituted,
        e.g. ``http://192.168.1.50/relay/0?turn={action}`` (Shelly/Tasmota style)
    """

    name = "http"

    def __init__(self, config: dict, timeout: float = 5.0):
        self._url = config.get("http_url", "")
        self._template = config.get("http_url_template", "")
        self._method = str(config.get("http_method", "POST")).upper()
        self._timeout = float(config.get("http_timeout", timeout))

    def actuate(self, door_id: str, action: str) -> bool:
        url = self._template.replace("{action}", action) if self._template else self._url
        if not url:
            log.error("Relay (http) has no URL configured")
            return False
        body = json.dumps({"door_id": door_id, "action": action}).encode()
        req = urllib.request.Request(
            url,
            data=body if self._method == "POST" else None,
            headers={"Content-Type": "application/json"},
            method=self._method,
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return 200 <= resp.status < 300
        except Exception as exc:  # noqa: BLE001
            log.error("Relay (http) request failed | url=%s error=%s", url, exc)
            return False


class GpioRelay(RelayDriver):
    name = "gpio"

    def __init__(self, config: dict):
        self._pin = int(config.get("gpio_pin", 17))
        self._active_high = bool(config.get("gpio_active_high", True))
        self._gpio = None
        try:
            import RPi.GPIO as GPIO  # type: ignore[import]

            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self._pin, GPIO.OUT)
            self._gpio = GPIO
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "Relay (gpio) unavailable (%s) — commands logged only.", exc
            )
            self._gpio = None

    def actuate(self, door_id: str, action: str) -> bool:
        if self._gpio is None:
            log.info("Relay (gpio->simulate) | door=%s action=%s", door_id, action)
            return True
        try:
            on = self._gpio.HIGH if self._active_high else self._gpio.LOW
            off = self._gpio.LOW if self._active_high else self._gpio.HIGH
            self._gpio.output(self._pin, on if action == "unlock" else off)
            log.info("Relay (gpio) | door=%s action=%s pin=%d", door_id, action, self._pin)
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Relay (gpio) failed: %s", exc)
            return False


class SerialRelay(RelayDriver):
    """USB / RS-485 relay boards driven over a serial port."""

    name = "serial"

    def __init__(self, config: dict):
        self._port = config.get("serial_port", "")
        self._baud = int(config.get("serial_baud", 9600))
        self._lock_cmd = config.get("serial_lock_cmd", "")
        self._unlock_cmd = config.get("serial_unlock_cmd", "")

    def _write(self, command: str) -> bool:
        if not command or not self._port:
            return False
        try:
            import serial  # type: ignore[import]

            with serial.Serial(self._port, self._baud, timeout=1) as ser:
                ser.write((command + "\r\n").encode("ascii"))
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Relay (serial) write failed | port=%s error=%s", self._port, exc)
            return False

    def actuate(self, door_id: str, action: str) -> bool:
        cmd = self._unlock_cmd if action == "unlock" else self._lock_cmd
        if not cmd:
            log.warning(
                "Relay (serial) missing %s command — configure serial_%s_cmd",
                action, action,
            )
            return False
        ok = self._write(cmd)
        log.info("Relay (serial) | door=%s action=%s ok=%s", door_id, action, ok)
        return ok


class ModbusTcpRelay(RelayDriver):
    """Network Modbus relay board — write a single coil."""

    name = "modbus_tcp"

    def __init__(self, config: dict):
        self._host = config.get("modbus_host", "")
        self._port = int(config.get("modbus_port", 502))
        self._unit = int(config.get("modbus_unit", 1))
        self._coil = int(config.get("modbus_coil", 0))
        self._unlock_value = bool(config.get("modbus_unlock_value", True))

    def actuate(self, door_id: str, action: str) -> bool:
        if not self._host:
            log.error("Relay (modbus_tcp) has no host configured")
            return False
        value = self._unlock_value if action == "unlock" else (not self._unlock_value)
        try:
            from pymodbus.client import ModbusTcpClient  # type: ignore[import]

            client = ModbusTcpClient(self._host, port=self._port)
            client.connect()
            try:
                client.write_coil(self._coil, value, unit=self._unit)
            finally:
                client.close()
            log.info(
                "Relay (modbus_tcp) | door=%s action=%s coil=%d=%s",
                door_id, action, self._coil, value,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Relay (modbus_tcp) failed | host=%s error=%s", self._host, exc)
            return False


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: Dict[str, type] = {
    "simulate": SimulateRelay,
    "http": HttpRelay,
    "gpio": GpioRelay,
    "serial": SerialRelay,
    "modbus_tcp": ModbusTcpRelay,
    "modbus": ModbusTcpRelay,  # friendly alias
}


def relay_types() -> List[dict]:
    """Human-readable catalogue of supported relay types (for the wizard)."""
    return [
        {"type": "simulate", "label": "Simulate (no hardware)", "needs": []},
        {"type": "http", "label": "WiFi / HTTP relay (Shelly, Tasmota, ESPHome, Sonoff, custom)", "needs": ["http_url", "http_url_template"]},
        {"type": "gpio", "label": "GPIO relay (Raspberry Pi / SBC)", "needs": ["gpio_pin"]},
        {"type": "serial", "label": "Serial / USB / RS-485 relay", "needs": ["serial_port", "serial_baud", "serial_lock_cmd", "serial_unlock_cmd"]},
        {"type": "modbus_tcp", "label": "Modbus TCP relay", "needs": ["modbus_host", "modbus_port", "modbus_unit", "modbus_coil"]},
    ]


def build_relay(door_control: Optional[dict]) -> RelayDriver:
    cfg = dict(door_control or {})
    kind = str(cfg.get("relay_type", "simulate")).lower()
    cls = _REGISTRY.get(kind)
    if cls is None:
        log.warning("Unknown relay_type=%r — falling back to simulate.", kind)
        cls = SimulateRelay
    try:
        return cls(cfg)
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to construct relay (%s) — falling back to simulate.", exc)
        return SimulateRelay()


# ---------------------------------------------------------------------------
# Best-effort plug-and-play discovery
# ---------------------------------------------------------------------------

# Common HTTP relay endpoints, probed on the local gateway with a short timeout.
_HTTP_PROBES = [
    ("Shelly", "http://{host}/relay/0"),
    ("Shelly", "http://{host}/relay/0?turn=on"),
    ("Tasmota", "http://{host}/cm?cmnd=Power"),
    ("ESPHome", "http://{host}/switch/door/turn_on"),
    ("Custom REST", "http://{host}/relay"),
]


def discover_relays(timeout: float = 1.2) -> List[dict]:
    """Return a best-effort list of discovered relay candidates.

    Never blocks for long and never raises — the wizard uses this to offer
    plug-and-play options, but the user can always configure manually.
    """
    found: List[dict] = []

    # 1. mDNS discovery for Shelly / ESPHome / _http._tcp devices.
    try:
        from zeroconf import ServiceBrowser, Zeroconf  # type: ignore[import]

        zc = Zeroconf()
        try:
            seen: set = set()

            class _Listener:
                def add_service(self, zc_, type_, name):
                    if name in seen:
                        return
                    seen.add(name)
                    info = zc.get_service_info(type_, name)
                    if info and info.server:
                        host = socket.inet_ntoa(info.addresses[0]) if info.addresses else info.server.rstrip(".")
                        found.append({
                            "type": "http",
                            "name": f"{info.server or name} (mDNS)",
                            "http_url": f"http://{host}/relay/0",
                            "discovered": True,
                        })

            ServiceBrowser(zc, "_http._tcp.local.", _Listener())
            import time as _t
            _t.sleep(0.8)
        finally:
            zc.close()
    except Exception:  # noqa: BLE001 — zeroconf is optional
        pass

    # 2. Probe common relay endpoints on the default gateway.
    try:
        host = _default_gateway()
        if host:
            for label, path in _HTTP_PROBES:
                url = path.format(host=host)
                try:
                    with urllib.request.urlopen(url, timeout=timeout) as resp:
                        if 200 <= resp.status < 300:
                            found.append({
                                "type": "http",
                                "name": f"{label} ({url})",
                                "http_url": url,
                                "discovered": True,
                            })
                except Exception:  # noqa: BLE001
                    continue
    except Exception:  # noqa: BLE001
        pass

    return found


def _default_gateway() -> Optional[str]:
    """Best-effort IPv4 default gateway address."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0].rsplit(".", 1)[0] + ".1"
    except Exception:  # noqa: BLE001
        return None
