# High-Value Counter Setup Guide

**Applies to:** Jewellery, watches, luxury goods, electronics showcases, and any
counter where staff hand merchandise across a display case instead of stocking
shelves.

The High-Value Counter module is **vision-only** — it needs **no POS integration
and no shelf zones**. It watches the three physical moments that matter at a
counter:

1. A **hand reaches into** the display case/tray and withdraws.
2. The **tray contents change** while a person is at the counter.
3. A person moves **case → exit unusually fast** (grab-and-run).

---

## 1. What the detectors need

| Detector | Event type | What it watches | Zones required |
|---|---|---|---|
| Case Hand Reach | `jewelry_handover` | A tracked person's hand enters the tray and withdraws | `counter_polygon` + `tray_polygon` |
| Tray Change | `jewelry_tray` | Foreground fill in the tray region drops while a person is present | `counter_polygon` + `trays[]` |
| Grab & Run | `grab_and_run` | Fast traversal from the case to the exit within a short window | `case_polygon` + `exit_polygon` (+ optional `approach_polygon`) |
| Item Count Drop | `inventory_movement` | Item count falls in the monitored display-case zone | `inventory_movement.zones[]` (bbox) |

> All detectors are **OFF until their polygons are configured** — a missing
> zone never silently means "the whole frame". This keeps unconfigured cameras
> quiet instead of noisy.

---

## 2. Camera placement

- **Counter camera (main)** — place directly above or at a high oblique angle
  over the serving counter so the full case/tray is in frame. This is the camera
  for **Case Hand Reach** and **Tray Change**.
- **Exit camera (or same camera if the door is in frame)** — must see the
  customer's path from the counter to the door. This powers **Grab & Run**.
  A single wide camera that frames both the case and the exit works if the
  polygons are drawn correctly; otherwise use two cameras and keep
  `grab_and_run` on the one that sees both zones.

Polygon coordinates are in the **camera's reference resolution**
(default 1920×1080), i.e. the same coordinate space used by the Zone Editor.

---

## 3. Which polygon to draw, on which camera

### On the counter camera

| Polygon | Draw it around… | Used by |
|---|---|---|
| `counter_polygon` | The serving counter / customer-side surface where a person stands to view items | hand reach-in (person-at-counter gate) + tray change (person-presence gate) |
| `tray_polygon` | The display case or velvet tray a hand actually reaches into | Case Hand Reach |
| `trays[]` | Each individual display tray/case you want monitored (one ROI per tray) | Tray Change |
| `case_polygon` | The display case area the suspect must enter before fleeing | Grab & Run |

### On the exit (or combined) camera

| Polygon | Draw it around… | Used by |
|---|---|---|
| `exit_polygon` | The door / exit of the room | Grab & Run |
| `approach_polygon` *(optional)* | The approach corridor toward the counter — if set, the person must pass through it first | Grab & Run (extra gate) |

Keep polygons **tight** — a hand-sized tray polygon is far more accurate than a
loose box around the whole counter.

---

## 4. Worked example (1920×1080)

```yaml
# Counter camera (e.g. cam-01) — cameras.yaml
analyzer_config:
  jewelry_handover:
    counter_polygon: [[400,300],[1500,300],[1500,900],[400,900]]   # serving counter
    tray_polygon:    [[700,320],[1200,320],[1200,620],[700,620]]   # display tray
    min_hand_inside_frames: 2
    cooldown_seconds: 30
    require_person_at_counter: true
  jewelry_tray:
    counter_polygon: [[400,300],[1500,300],[1500,900],[400,900]]
    trays:
      - label: Main display case
        polygon: [[700,320],[1200,320],[1200,620],[700,620]]
    drop_ratio_threshold: 0.25
    check_interval_seconds: 3.0
    cooldown_seconds: 30
    person_required: true
  grab_and_run:
    case_polygon:  [[700,300],[1200,300],[1200,620],[700,620]]
    exit_polygon:  [[1600,400],[1920,400],[1920,1080],[1600,1080]]
    approach_polygon: []          # optional
    max_window_seconds: 8.0
    min_exit_speed_px_s: 120.0
    cooldown_seconds: 30
```

> `counter_polygon`, `tray_polygon`, `case_polygon`, `exit_polygon` and
> `approach_polygon` are 4+ point polygons `[[x,y], ...]`. `trays[]` is a list
> of `{label, polygon}` objects.

---

## 5. Enabling the module

- **SaaS dashboard (recommended)** — open **High-Value Counter** in the
  sidebar, pick the camera, and draw the five polygons point-and-click on the
  live snapshot (Serving Counter, Display Tray, Display Case, Exit Door,
  optional Approach Corridor), then **Save**. The polygons are written to the
  camera's `analyzer_config` (`jewelry_handover` / `jewelry_tray` /
  `grab_and_run`), exactly as in the YAML below.
- **Self-hosted / single-tenant pipeline** — add the same blocks directly to
  the camera's `analyzer_config` in `backend/config/cameras.yaml`, then
  restart the pipeline.

> **Edge Agent:** the three detectors also run **on-box** in the Windows/Linux
> Edge Agent (v1.7.0+). The backend delivers the normalized polygons to the
> agent automatically — no extra config. Existing stores must update their
> agent from the dashboard (Download page) to pick up the new detectors.

All three detectors are wired into the live pipeline and risk scorer — drawing
the zones is what turns them on. See **Help Center → FAQ → High-Value Counter**
for a diagram of where each shape goes.

---

## 6. Testing

1. Open **Demo Center** in the dashboard.
2. Use **Fire High-Value Counter Demo** to run the full four-signal story
   (hand reach-in → tray change → item count drop → grab-and-run) in order.
3. Or fire each detector individually from its card (Case Hand Reach, Tray
   Change, Grab & Run).
4. Confirm events appear in **Incidents** and move the **Dashboard** risk score.

For a real (non-demo) test: enable the zones above, then have a staff member
reach into the tray and withdraw, shift an item on the tray, and finally walk
briskly from the case to the exit.
