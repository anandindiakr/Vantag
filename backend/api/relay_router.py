"""
backend/api/relay_router.py
============================
Door-relay (access-control) configuration router for the relay setup wizard.

The tenant's ``relay_settings`` describe how the on-site edge agent actuates a
physical door relay (see ``windows_agent/agent/relay.py``). The settings are
stored on the Tenant, served to the agent via ``/api/edge/config`` (as
``door_control``), and editable here through the dashboard wizard.

Endpoints
---------
GET  /api/relay/types        – supported relay types (wizard catalogue)
GET  /api/relay/settings     – current relay settings
PUT  /api/relay/settings     – save relay settings
POST /api/relay/test         – fire a test lock/unlock command via MQTT
GET  /api/relay/drivers      – download example driver pack (zip)
"""

from __future__ import annotations

import io
import zipfile

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select

from ..db.database import get_session
from ..db.models.tenant import Tenant
from ..middleware.tenant_middleware import get_current_user_id
from ..mqtt.door_controller import _get_controller

from sqlalchemy.ext.asyncio import AsyncSession

relay_router = APIRouter(prefix="/api/relay", tags=["Relay"])

# Keep this in one place so the wizard and the agent driver stay in sync.
RELAY_TYPES = [
    {"type": "simulate", "label": "Simulate (no hardware)", "needs": []},
    {
        "type": "http",
        "label": "WiFi / HTTP relay (Shelly, Tasmota, ESPHome, Sonoff, custom REST)",
        "needs": ["http_url", "http_url_template", "http_method"],
    },
    {"type": "gpio", "label": "GPIO relay (Raspberry Pi / SBC)", "needs": ["gpio_pin", "gpio_active_high"]},
    {
        "type": "serial",
        "label": "Serial / USB / RS-485 relay",
        "needs": ["serial_port", "serial_baud", "serial_lock_cmd", "serial_unlock_cmd"],
    },
    {
        "type": "modbus_tcp",
        "label": "Modbus TCP relay",
        "needs": ["modbus_host", "modbus_port", "modbus_unit", "modbus_coil"],
    },
]


@relay_router.get("/types")
async def relay_types() -> dict:
    return {"types": RELAY_TYPES}


@relay_router.get("/settings")
async def get_relay_settings(
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    tenant = await session.get(Tenant, user["tenant_id"])
    return {"settings": tenant.relay_settings or {} if tenant else {}}


@relay_router.put("/settings")
async def save_relay_settings(
    body: dict,
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    tenant = await session.get(Tenant, user["tenant_id"])
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    settings = dict(body or {})
    # Only persist known, safe scalar keys — never let arbitrary nested junk
    # reach the agent config blob.
    allowed = {
        "relay_type", "http_url", "http_url_template", "http_method",
        "http_timeout", "gpio_pin", "gpio_active_high", "serial_port",
        "serial_baud", "serial_lock_cmd", "serial_unlock_cmd",
        "modbus_host", "modbus_port", "modbus_unit", "modbus_coil",
        "modbus_unlock_value",
    }
    tenant.relay_settings = {k: v for k, v in settings.items() if k in allowed}
    await session.commit()
    return {"ok": True, "settings": tenant.relay_settings}


@relay_router.post("/test")
async def test_relay(
    body: dict,
    user: dict = Depends(get_current_user_id),
) -> dict:
    """Fire a test command so the wizard can verify the relay actuates."""
    controller = _get_controller()
    store_id = user["tenant_id"]
    door_id = str(body.get("door_id", "test-door"))
    action = str(body.get("action", "unlock"))
    if action not in ("lock", "unlock"):
        raise HTTPException(status_code=400, detail="action must be 'lock' or 'unlock'")

    if action == "unlock":
        ok = controller.unlock_door(store_id, door_id, issued_by="relay-wizard")
    else:
        ok = controller.lock_door(store_id, door_id, issued_by="relay-wizard")

    if not ok:
        raise HTTPException(status_code=502, detail="Failed to publish test command to MQTT broker.")
    return {"ok": True, "message": f"Test {action} command sent to door '{door_id}'."}


@relay_router.post("/scan")
async def scan_relays(user: dict = Depends(get_current_user_id)) -> dict:
    """Ask the tenant's edge agent to discover relay hardware on the LAN.

    The agent picks up the flag on its next heartbeat (within a few seconds),
    scans the store network for common relay boards, and reports the
    candidates back in a subsequent heartbeat. They then appear via
    ``GET /api/relay/discovered``.
    """
    tenant_id = user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant in session")
    from .edge_router import request_relay_scan
    request_relay_scan(tenant_id)
    return {"ok": True, "message": "Relay scan requested. Your edge agent will scan shortly."}


@relay_router.get("/discovered")
async def discovered_relays(user: dict = Depends(get_current_user_id)) -> dict:
    """Return plug-and-play relay candidates found by the tenant's agent."""
    from .edge_router import get_discovered_relays
    return {"relays": get_discovered_relays(user.get("tenant_id", ""))}


@relay_router.get("/drivers")
async def download_driver_pack() -> Response:
    """Serve a zip of example driver scripts + wiring notes for common relays."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "README.md",
            "# Vantag Door Relay — Driver Pack\n\n"
            "Plug-and-play examples for common relay hardware. Pick the file "
            "that matches your board, edit the connection details, and enter "
            "the same values in the Door Relay setup wizard.\n\n"
            "- Shelly / Tasmota / ESPHome / Sonoff / custom REST → use the "
            "\"WiFi / HTTP relay\" type (http_url).\n"
            "- Raspberry Pi / SBC GPIO → use the \"GPIO relay\" type.\n"
            "- USB / RS-485 serial boards → use the \"Serial relay\" type.\n"
            "- Modbus TCP boards → use the \"Modbus TCP relay\" type.\n\n"
            "Example `door_control` config (saved by the wizard):\n"
            "```json\n"
            '{"relay_type": "http", "http_url": "http://192.168.1.50/relay/0"}\n'
            "```\n",
        )
        zf.writestr(
            "shelly_curl.sh",
            "#!/usr/bin/env sh\n# Shelly relay example (replace with your device IP)\n"
            'curl -s http://192.168.1.50/relay/0?turn=on   # unlock\n'
            'curl -s http://192.168.1.50/relay/0?turn=off  # lock\n',
        )
        zf.writestr(
            "raspberry_pi_gpio.py",
            '"""Raspberry Pi GPIO relay example (BCM pin 17)."""\n'
            "import RPi.GPIO as GPIO\n"
            "GPIO.setmode(GPIO.BCM)\n"
            "GPIO.setup(17, GPIO.OUT)\n"
            'GPIO.output(17, GPIO.HIGH)  # unlock\n'
            'GPIO.output(17, GPIO.LOW)   # lock\n',
        )
        zf.writestr(
            "arduino_relay.ino",
            "// Arduino relay example — listens on Serial at 9600 baud.\n"
            "// Commands: \"UNLOCK\" and \"LOCK\".\n"
            "const int RELAY_PIN = 7;\n"
            "void setup() { Serial.begin(9600); pinMode(RELAY_PIN, OUTPUT); }\n"
            "void loop() {\n"
            '  if (Serial.available()) {\n'
            '    String cmd = Serial.readStringUntil(\'\\n\');\n'
            '    cmd.trim();\n'
            '    if (cmd == "UNLOCK") digitalWrite(RELAY_PIN, HIGH);\n'
            '    if (cmd == "LOCK")   digitalWrite(RELAY_PIN, LOW);\n'
            "  }\n"
            "}\n",
        )
        zf.writestr(
            "relay_config_example.json",
            '{\n'
            '  "relay_type": "serial",\n'
            '  "serial_port": "/dev/ttyUSB0",\n'
            '  "serial_baud": 9600,\n'
            '  "serial_lock_cmd": "LOCK",\n'
            '  "serial_unlock_cmd": "UNLOCK"\n'
            '}\n',
        )
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="vantag-relay-drivers.zip"'},
    )
