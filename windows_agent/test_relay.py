"""
Self-contained tests for the pluggable door-relay drivers (agent/relay.py).

No real hardware, no network calls, no optional dependencies needed —
``RPi.GPIO``, ``pyserial``, ``pymodbus`` and ``zeroconf`` are forced to be
unavailable, and ``urllib.request.urlopen`` is stubbed so HTTP relays can be
exercised deterministically.

Usage (from repo root):
    cd windows_agent
    python test_relay.py

Exit code 0 = all pass, 1 = at least one failure.
"""

import pathlib
import sys
import urllib.request

_AGENT_DIR = pathlib.Path(__file__).parent
sys.path.insert(0, str(_AGENT_DIR.parent))

from agent.relay import (  # noqa: E402
    build_relay, relay_types, SimulateRelay, HttpRelay, GpioRelay,
    SerialRelay, ModbusTcpRelay, discover_relays, _default_gateway,
)


_MISSING = object()

# ── Force every optional hardware dependency to be unavailable ───────────────
for _mod in ("RPi.GPIO", "serial", "pymodbus", "zeroconf"):
    sys.modules[_mod] = None


# ── Stub urllib.request.urlopen for HttpRelay ────────────────────────────────
class FakeResponse:
    def __init__(self, status=200):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


_captured_urls = []
_urlopen_result = FakeResponse(200)


def _fake_urlopen(req, timeout=None):
    _captured_urls.append(req.full_url)
    if isinstance(_urlopen_result, Exception):
        raise _urlopen_result
    return _urlopen_result


urllib.request.urlopen = _fake_urlopen


results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("PASS  " if cond else "FAIL  ") + name + (f"  {detail}" if detail and not cond else ""))


def set_urlopen(result):
    global _urlopen_result, _captured_urls
    _urlopen_result = result
    _captured_urls = []


# ── Registry / construction ──────────────────────────────────────────────────
print("[1] build_relay — registry and fallbacks")
check("empty config -> simulate", isinstance(build_relay(None), SimulateRelay))
check("unknown type -> simulate", isinstance(build_relay({"relay_type": "bogus"}), SimulateRelay))
check("'modbus' alias -> ModbusTcpRelay", isinstance(build_relay({"relay_type": "modbus"}), ModbusTcpRelay))
check("relay_types() returns 5 entries", len(relay_types()) == 5)
check("simulate actuate always succeeds", SimulateRelay().actuate("d1", "unlock") is True)

# ── HTTP relay ───────────────────────────────────────────────────────────────
print("\n[2] HttpRelay")
set_urlopen(FakeResponse(200))
h = HttpRelay({"http_url": "http://192.168.1.50/relay/0", "http_method": "POST"})
check("http 200 -> success", h.actuate("d1", "unlock") is True)
check("http posts JSON body to configured URL", _captured_urls and _captured_urls[0] == "http://192.168.1.50/relay/0")

set_urlopen(FakeResponse(200))
h2 = HttpRelay({"http_url_template": "http://192.168.1.50/relay/0?turn={action}"})
check("template relay succeeds", h2.actuate("d1", "lock") is True)
check("template substitutes {action}", _captured_urls and _captured_urls[0] == "http://192.168.1.50/relay/0?turn=lock")

set_urlopen(FakeResponse(404))
check("http 404 -> failure", h.actuate("d1", "unlock") is False)

set_urlopen(ConnectionError("boom"))
check("http exception -> failure", h.actuate("d1", "unlock") is False)

check("http with no URL -> failure", HttpRelay({}).actuate("d1", "unlock") is False)

# ── GPIO relay (no RPi.GPIO available) ───────────────────────────────────────
print("\n[3] GpioRelay (no hardware)")
check("gpio degrades to logged no-op success", GpioRelay({"gpio_pin": 17}).actuate("d1", "unlock") is True)

# ── Serial relay (no pyserial available) ─────────────────────────────────────
print("\n[4] SerialRelay (no hardware)")
check("serial missing unlock cmd -> failure", SerialRelay({"serial_port": "/dev/ttyUSB0"}).actuate("d1", "unlock") is False)
check("serial unavailable hardware -> failure", SerialRelay(
    {"serial_port": "/dev/ttyUSB0", "serial_lock_cmd": "LOCK", "serial_unlock_cmd": "UNLOCK"}
).actuate("d1", "lock") is False)

# ── Modbus TCP relay ─────────────────────────────────────────────────────────
print("\n[5] ModbusTcpRelay")
check("modbus missing host -> failure", ModbusTcpRelay({}).actuate("d1", "unlock") is False)
m = ModbusTcpRelay({"modbus_host": "192.168.1.51", "modbus_port": 502, "modbus_unit": 1, "modbus_coil": 0})
check("modbus unavailable hardware -> failure", m.actuate("d1", "unlock") is False)

# ── Discovery helpers (must be non-raising and bounded) ──────────────────────
print("\n[6] discovery helpers")
gw = _default_gateway()
check("_default_gateway returns str or None", gw is None or isinstance(gw, str))
set_urlopen(ConnectionError("no network"))
found = discover_relays()
check("discover_relays returns a list", isinstance(found, list))
check("discover_relays never raises and is empty offline", found == [])

# ── Summary ──────────────────────────────────────────────────────────────────
print(f"\n{'=' * 50}\nResults: {sum(1 for _, ok in results if ok)} passed, "
      f"{sum(1 for _, ok in results if not ok)} failed\n{'=' * 50}")
sys.exit(0 if all(ok for _, ok in results) else 1)
