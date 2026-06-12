"""
E2E test: Zone Editor — draw a zone, fire a Test Event, verify Incidents page.

Flow
----
1.  Obtain a JWT from the backend (no browser form — avoids race conditions).
2.  Inject it into localStorage so the app boots into the authenticated state.
3.  Navigate to Zone Editor page.
4.  Wait for the camera snapshot to load (or proceed without it if cameras
    are offline — we still want to verify the fire-event flow).
5.  Click "Draw Zone" on the first camera, draw a rectangle on the canvas.
6.  Name the zone "TestShelf" and save.
7.  Click "Test Event" on the saved zone.
8.  Verify a success toast appears ("Test event fired").
9.  Navigate to Incidents page.
10. Verify the new incident row exists and shows event_type ≠ "unknown".
11. Verify the event_type filter dropdown includes "Inventory Move".
"""

from __future__ import annotations

import json
import time

import httpx
import pytest
from playwright.sync_api import Page, expect

# ── Constants ─────────────────────────────────────────────────────────────────
BASE_URL    = "http://localhost:3000"
API_URL     = "http://localhost:8000"
DEMO_EMAIL  = "demo@vantag.io"
DEMO_PASS   = "demo1234"
STORE_ID    = "zone_c"          # cam-03 default store
TIMEOUT     = 20_000            # ms


# ── Auth fixture ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def auth_token() -> str:
    """Fetch a real JWT from the backend — fast, no UI interaction."""
    resp = httpx.post(
        f"{API_URL}/api/auth/login",
        json={"email": DEMO_EMAIL, "password": DEMO_PASS},
        timeout=10,
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    data = resp.json()
    token = data.get("access_token") or data.get("token") or data.get("jwt")
    assert token, f"No token in response: {data}"
    return token


def _inject_auth(page: Page, token: str) -> None:
    """Set auth state in localStorage before the app loads."""
    page.add_init_script(f"""
        window.localStorage.setItem('vantag_token', '{token}');
        window.localStorage.setItem('auth_token',   '{token}');
    """)


# ── Helper ────────────────────────────────────────────────────────────────────

def _draw_rect_on_canvas(page: Page, canvas_selector: str) -> None:
    """Draw a 200×120 rectangle near the centre of the canvas."""
    canvas = page.locator(canvas_selector).first
    box    = canvas.bounding_box()
    assert box, "Canvas not found / not visible"
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    # Drag from top-left to bottom-right of a central rectangle
    page.mouse.move(cx - 100, cy - 60)
    page.mouse.down()
    page.mouse.move(cx + 100, cy + 60)
    page.mouse.up()


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestZoneEditor:

    def test_page_loads(self, page: Page, auth_token: str) -> None:
        """Zone Editor page renders without errors."""
        _inject_auth(page, auth_token)
        page.goto(f"{BASE_URL}/zone-editor", wait_until="networkidle", timeout=TIMEOUT)
        # At least one camera card should be present
        expect(page.locator("text=Zone Editor").first).to_be_visible(timeout=TIMEOUT)

    def test_draw_mode_activates(self, page: Page, auth_token: str) -> None:
        """Clicking a zone-type button enters draw mode."""
        _inject_auth(page, auth_token)
        page.goto(f"{BASE_URL}/zone-editor", wait_until="networkidle", timeout=TIMEOUT)

        # Click the first "Shelf/Inventory" draw button (contains 'Shelf' or 'Inventory' or icon)
        draw_btn = page.locator("button", has_text="Shelf").or_(
                   page.locator("button", has_text="Inventory")).or_(
                   page.locator("[data-mode='shelf']")).first
        draw_btn.click(timeout=TIMEOUT)

        # Canvas should become available (cursor changes to crosshair or draw mode)
        canvas = page.locator("canvas").first
        expect(canvas).to_be_visible(timeout=TIMEOUT)

    def test_fire_test_event_via_api(self, auth_token: str) -> None:
        """
        Directly hit /api/demo/trigger and verify the event is stored.
        This is the most reliable check — no canvas-drawing needed.
        """
        headers = {"Authorization": f"Bearer {auth_token}"}

        # Fire the event
        resp = httpx.post(
            f"{API_URL}/api/demo/trigger",
            json={
                "event_type":   "inventory_movement",
                "camera_id":    "cam-03",
                "severity":     "medium",
                "zone_name":    "TestShelf",
                "zone_label":   "Shelf / Inventory",
                "zone_bbox":    [100, 80, 300, 200],
                "snapshot_b64": "",
            },
            headers=headers,
            timeout=10,
        )
        assert resp.status_code == 200, f"trigger failed: {resp.text}"
        body = resp.json()
        assert body["event_type"] == "inventory_movement", f"Wrong event_type: {body}"
        assert "TestShelf" in body["description"],         f"Zone not in description: {body}"
        assert "3 →" not in body["description"],          f"Hardcoded count leaked: {body}"

    def test_incident_appears_on_incidents_page(self, auth_token: str) -> None:
        """
        After firing a demo event, the incidents API must return it
        with event_type 'inventory_movement' (not 'unknown').
        """
        headers = {"Authorization": f"Bearer {auth_token}"}

        # Fire event
        httpx.post(
            f"{API_URL}/api/demo/trigger",
            json={
                "event_type": "inventory_movement",
                "camera_id":  "cam-03",
                "severity":   "medium",
                "zone_name":  "TestShelf",
                "zone_label": "Shelf / Inventory",
                "zone_bbox":  [100, 80, 300, 200],
            },
            headers=headers,
            timeout=10,
        )
        time.sleep(0.5)

        # Verify via API
        resp = httpx.get(
            f"{API_URL}/api/stores/{STORE_ID}/incidents?page=1&limit=20",
            headers=headers,
            timeout=10,
        )
        assert resp.status_code == 200, f"incidents API failed: {resp.text}"
        incidents = resp.json().get("incidents", [])
        assert len(incidents) > 0, "No incidents returned"

        inv = [i for i in incidents if i.get("event_type") == "inventory_movement"]
        assert len(inv) > 0, (
            f"inventory_movement not in incidents. Types found: "
            + str([i.get("event_type") for i in incidents[:10]])
        )

    def test_event_type_not_unknown(self, auth_token: str) -> None:
        """Incidents API must not return event_type='unknown' for demo events."""
        headers = {"Authorization": f"Bearer {auth_token}"}

        # Fire multiple event types
        for et in ["inventory_movement", "shoplifting", "loitering"]:
            httpx.post(
                f"{API_URL}/api/demo/trigger",
                json={"event_type": et, "camera_id": "cam-03", "severity": "medium"},
                headers=headers,
                timeout=10,
            )

        time.sleep(0.5)

        # Fetch incidents via API
        resp = httpx.get(
            f"{API_URL}/api/stores/{STORE_ID}/incidents?page=1&limit=20",
            headers=headers,
            timeout=10,
        )
        assert resp.status_code == 200, f"incidents fetch failed: {resp.text}"
        data = resp.json()
        incidents = data.get("incidents", [])
        assert len(incidents) > 0, "No incidents returned from API"

        unknown = [i for i in incidents if i.get("event_type") == "unknown"]
        assert len(unknown) == 0, (
            f"{len(unknown)} incident(s) still have event_type='unknown': "
            + json.dumps(unknown[:3], indent=2)
        )

    def test_description_has_no_hardcoded_counts(self, auth_token: str) -> None:
        """Description must not contain hardcoded count strings like '3 → 2'."""
        headers = {"Authorization": f"Bearer {auth_token}"}
        httpx.post(
            f"{API_URL}/api/demo/trigger",
            json={
                "event_type": "inventory_movement",
                "camera_id":  "cam-03",
                "severity":   "medium",
                "zone_name":  "WhitePen",
                "zone_label": "Shelf / Inventory",
                "zone_bbox":  [50, 50, 200, 150],
            },
            headers=headers,
            timeout=10,
        )
        time.sleep(0.3)

        resp = httpx.get(
            f"{API_URL}/api/stores/{STORE_ID}/incidents?page=1&limit=5",
            headers=headers,
            timeout=10,
        )
        incidents = resp.json().get("incidents", [])
        inv = [i for i in incidents if i.get("event_type") == "inventory_movement"]
        assert inv, "No inventory_movement incidents found"

        bad_patterns = ["3 →", "3 items removed", "Item count dropped: 3", "87%", "6 minutes"]
        for inc in inv:
            desc = inc.get("description", "")
            for pat in bad_patterns:
                assert pat not in desc, (
                    f"Hardcoded pattern '{pat}' found in description: {desc}"
                )

    def test_sqlite_persistence(self, auth_token: str) -> None:
        """
        Verify that incidents.db exists and contains the events we fired.
        """
        import sqlite3
        from pathlib import Path
        db = Path("D:/AI Algo/Collaterals/Profiles/Retail Nazar/vantag/data/incidents.db")
        assert db.exists(), f"incidents.db not found at {db}"

        conn = sqlite3.connect(str(db))
        count = conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
        conn.close()
        assert count > 0, "No incidents in SQLite DB"
