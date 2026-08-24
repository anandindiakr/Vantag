# 💎 Retail Nazar — High-Value Counter
### AI theft detection built for jewellers, watch shops, and luxury retailers

**Company:** BrainGuardX AI Technologies Pvt. Ltd.
**Product:** Retail Nazar (Vantag platform)
**Document:** High-Value Counter — Feature & Go-To-Market Overview
**Version:** 1.0
**Prepared:** August 2026
**Contact:** support@retailnazar.com | retailnazar.com

---

## 1. The one-line pitch

> **"No shelves. No POS. Still caught."**

Most theft-detection AI assumes a supermarket: shelves, product barcodes, a POS
terminal. That assumption fails the moment you walk into a jewellery shop, a
watch boutique, or a luxury handbag counter — where the goods sit *inside a
glass case* and the salesperson *hands them across the counter* to the
customer. **High-Value Counter** is the first Retail Nazar detector built for
that world: it watches the *counter, the tray, and the hand*, not the shelf.

---

## 2. The problem it solves

In a high-value retail environment, the theft moment is not a shelf sweep. It is
a *hand*. Specifically:

| The act | What it looks like on camera |
|---|---|
| **Reach-in** | A customer (or staff member) dips a hand into the open display tray while the salesperson is distracted |
| **Tray change** | One moment the tray is full; a moment later an item is gone |
| **Grab & run** | The person takes the item and moves fast toward the exit |

Traditional CCTV records all of this — for review *the next morning*, after the
item is already on a resale site. Retail Nazar alerts the owner **in real time**,
while the item is still in the building.

**Why existing systems miss it:**
- ❌ No shelves → shelf-based AI has nothing to track
- ❌ No POS → "item vs sale" reconciliation is impossible
- ❌ Counter service is normal → motion detectors fire on every legitimate handover
- ❌ High staff involvement → you cannot simply alarm every person near the case

High-Value Counter is designed for exactly these conditions.

---

## 3. What "High-Value Counter" is

It is a dedicated detection mode that turns an ordinary counter camera into a
**theft-watch station**. The retailer (or installer) draws a few simple shapes
on the live camera view once — *Serving Counter, Display Tray, Display Case,
Exit Door, Approach Corridor* — and Retail Nazar runs **four coordinated AI
signals** on that single camera, continuously.

No extra hardware. No new cameras. No POS integration. It works on the IP
cameras the shop already owns.

---

## 4. The four detectors (in plain language)

| # | Detector | What it watches for | Alert |
|---|---|---|---|
| 1 | **Case Hand Reach** | A hand crosses into the display tray, stays, then withdraws | 🖐️ "Case Hand Reach — hand reached into display case and withdrew" |
| 2 | **Tray Change** | The contents of the display tray visibly drop (an item removed) while a person is at the counter | 💍 "Tray Change — tray contents removed" |
| 3 | **Grab & Run** | A person moves from the display case to the exit door unusually fast | 🏃 "Grab & Run — fast case→exit movement" |
| 4 | **Full Chain Demo** | A one-click simulation that fires all three signals in story order, so a salesperson can *show* the flow live without a real theft | ▶️ "Fire High-Value Counter Demo" |

Together they answer the question every jeweller asks: **"when did the hand go
in, and did something leave?"**

---

## 5. What makes it different

| Differentiator | Why it matters |
|---|---|
| **No shelves required** | The geometry is a *counter, tray, case and exit* — not shelf rows |
| **No POS required** | Detection is purely visual; nothing to integrate, nothing to reconcile |
| **One camera, many brains** | The same counter camera simultaneously runs hand-reach, tray-change, grab-and-run **plus** the other Retail Nazar models (loitering, restricted zone, fall, queue, etc.) |
| **Per-finger precision** | 21-point hand tracking measures the *actual fingertip* entering the tray — not a rough "a person is nearby" guess |
| **Works on existing cameras** | Connects to the Hikvision / Dahua / ONVIF cameras the shop already installed |
| **Runs on the edge** | Video is analysed on-site; it does not need to leave the store |
| **Real-time, not next-morning** | Alerts reach the owner's phone in under a second |

---

## 6. Who it is for (target verticals)

- 💍 **Jewellery & gold stores** — trays, cases, counter handovers
- ⌚ **Luxury watches** — showcase counters and try-on areas
- 👜 **Premium bags & leather goods** — display tables, boutique counters
- 📱 **Mobile & electronics showcases** — demo units handed across the counter
- 👓 **Premium eyewear / accessories** — high-value, small-footprint items
- 🏦 **Pawn shops & money counters** — high-value items across a service counter

Any business where **the item is small, expensive, and handed over a counter**
is a High-Value Counter customer.

---

## 7. Features & functions (what the retailer gets)

- **Point-and-click polygon editor** — draw the zones on the live camera
  snapshot in the dashboard; no YAML, no technician.
- **Three individually-fireable test cards** in the Demo Center (Case Hand
  Reach, Tray Change, Grab & Run) so the team can practise and demo.
- **One-click full demo** that replays the whole theft story in order.
- **Live Incidents** with severity, camera, time, and thumbnail — "Case Hand
  Reach", "Tray Change", "Grab & Run" appear with clear labels and colors.
- **Risk scoring** — the events feed the store's live risk score (Grab & Run is
  the highest-weighted signal).
- **Help Center content** — a High-Value Counter FAQ category, a setup guide,
  a diagram, and an animated "How it works / How to configure" story for
  training.

---

## 8. The tech under the hood (for the technically curious)

- **Detection:** Ultralytics **YOLO26** (NMS-free, DFL-free) — roughly 2× faster
  on CPU than the previous generation with better small-object accuracy.
- **Pose:** YOLO26-pose for wrist/elbow geometry.
- **Hands:** **MediaPipe HandLandmarker** — **21 landmark points per hand**
  (five fingertips, palm, wrist), so "the hand entered the tray" is a measured
  geometric fact, not a bounding-box estimate.
- **Orchestration:** a GPU/CPU scheduler runs the heavy models at different
  frame rates so one slow model never blocks the others.

*Sales translation: "It now tracks the fingertips, not just the body."*

---

## 9. How to see it live (2 minutes)

1. Open the dashboard → **High-Value Counter** page.
2. Pick the counter camera and draw the **Serving Counter**, **Display Tray**,
   **Display Case** and **Exit Door** polygons on the live snapshot.
3. Save.
4. Go to **Demo Center** → **"Fire High-Value Counter Demo"** → watch the three
   alerts appear in **Incidents**.

No theft required to demo it.

---

## 10. Honest boundaries (say this clearly)

Retail Nazar's High-Value Counter is a **real-time review candidate**, not a
legal verdict:

- It flags the *behaviour* (hand reach, tray change, fast exit) for an operator
  to confirm.
- A staff member servicing the case can trigger the same "hand reach" signal —
  that is why the alerts are designed for **immediate human confirmation**, not
  automatic arrest.
- It is a **deterrent + fastest-response** tool: the alert fires *during* the
  act, so the owner can intervene before the item leaves the premises.

This honest framing *increases* trust with serious retailers — and it is the
correct one.

---

## 11. Message for the sales team

> "Stop pitching shelves. Pitch the counter. Jewellers don't lose stock off a
> shelf — they lose it the moment a hand dips into an open tray. We now watch
> that hand, finger by finger, and alert before the customer reaches the door."

Use this document as the **what/why**, and the companion
`high_value_counter_sales_pitch.md` as the **how** (scripts, objections, demo
flow, ROI math).
