# -*- coding: utf-8 -*-
"""Generate a light-themed, print-friendly Tech Architecture PDF for Vantag/Nazar."""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib import colors

OUT = r"D:\AI Algo\Collaterals\Profiles\Retail Nazar\Vantag_Tech_Architecture.pdf"

# ---- palette (light theme, high contrast) ----
INK    = colors.HexColor("#0F172A")
MUTED  = colors.HexColor("#475569")
CYAN   = colors.HexColor("#0E7490")
VIOLET = colors.HexColor("#6D28D9")
GREEN  = colors.HexColor("#047857")
RED    = colors.HexColor("#DC2626")
AMBER  = colors.HexColor("#B45309")
PANEL  = colors.HexColor("#F8FAFC")
PANEL2 = colors.HexColor("#F1F5F9")
LINE   = colors.HexColor("#CBD5E1")

W, H = A4
M = 16 * mm  # margin
CW = W - 2 * M  # content width

c = canvas.Canvas(OUT, pagesize=A4)


def rrect(x, y, w, h, fill=PANEL, stroke=LINE, r=8, lw=1):
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.setLineWidth(lw)
    c.roundRect(x, y, w, h, r, stroke=1, fill=1)


def text(x, y, s, size=10, color=INK, font="Helvetica", center=False, right=False):
    c.setFillColor(color)
    c.setFont(font, size)
    if center:
        c.drawCentredString(x, y, s)
    elif right:
        c.drawRightString(x, y, s)
    else:
        c.drawString(x, y, s)


def wrap(s, font, size, maxw):
    words = s.split()
    lines, cur = [], ""
    for w_ in words:
        t = (cur + " " + w_).strip()
        if c.stringWidth(t, font, size) <= maxw:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w_
    if cur:
        lines.append(cur)
    return lines


def bullets(x, y, items, w, size=8.5, gap=12, dotcolor=CYAN, txtcolor=MUTED):
    cy = y
    for it in items:
        c.setFillColor(dotcolor)
        c.circle(x + 2.2, cy + 2.6, 1.4, stroke=0, fill=1)
        lines = wrap(it, "Helvetica", size, w - 10)
        for i, ln in enumerate(lines):
            text(x + 8, cy, ln, size=size, color=txtcolor)
            cy -= gap if i == len(lines) - 1 else (gap - 1.5)
    return cy


def header(subtitle):
    rrect(M, H - M - 30 * mm, CW, 30 * mm, fill=colors.HexColor("#EEF2FF"), stroke=colors.HexColor("#C7D2FE"), r=12)
    text(W / 2, H - M - 9 * mm, "TECHNICAL ARCHITECTURE", size=9, color=CYAN, font="Helvetica-Bold", center=True)
    text(W / 2, H - M - 17 * mm, "How Vantag / Nazar Moves & Protects Your Data", size=16, color=INK, font="Helvetica-Bold", center=True)
    text(W / 2, H - M - 24 * mm, subtitle, size=9.5, color=MUTED, center=True)


def section(y, label, accent=VIOLET):
    text(M, y, label.upper(), size=10, color=accent, font="Helvetica-Bold")
    c.setStrokeColor(LINE)
    c.setLineWidth(1)
    lblw = c.stringWidth(label.upper(), "Helvetica-Bold", 10)
    c.line(M + lblw + 6, y + 3, W - M, y + 3)


# ============== PAGE 1 ==============
header("Edge-first AI surveillance  |  Video stays in your store  |  Only insights reach the cloud")

# ---- Data flow ----
y = H - M - 38 * mm
section(y, "End-to-End Data Flow")
y -= 6 * mm

stages = [
    ("IP Cameras / NVR", "IN-STORE  LAN", CYAN, ["RTSP H.264 / H.265", "Hikvision, Dahua, ONVIF", "On local router"]),
    ("Edge Agent (PC)", "RUNS LOCALLY", GREEN, ["Pulls RTSP frames", "YOLOv8 AI inference", "Encrypted creds", "Local frame buffer"]),
    ("Vantag Cloud (VPS)", "SECURE  HTTPS", VIOLET, ["Event metadata", "Evidence snapshots", "Reports & analytics", "No raw video"]),
    ("Dashboard & Alerts", "WEB  MOBILE", CYAN, ["Live tiles + snapshots", "Incident feed", "Email / push / webhook"]),
]
bw = (CW - 3 * 9 * mm) / 4
bh = 40 * mm
bx = M
boxtop = y
for i, (title, where, accent, items) in enumerate(stages):
    rrect(bx, boxtop - bh, bw, bh, fill=PANEL, stroke=accent, r=8, lw=1.3)
    text(bx + 5, boxtop - 8 * mm, title, size=9.3, color=INK, font="Helvetica-Bold")
    text(bx + 5, boxtop - 12.5 * mm, where, size=6.5, color=accent, font="Helvetica-Bold")
    bullets(bx + 4, boxtop - 17 * mm, items, bw - 6, size=7.6, gap=9.5, dotcolor=accent)
    if i < 3:
        ax = bx + bw + 1.5 * mm
        text(ax + 2.7 * mm, boxtop - bh / 2 - 2, ">", size=18, color=CYAN, font="Helvetica-Bold", center=True)
    bx += bw + 9 * mm

# ---- stays local vs cloud ----
y = boxtop - bh - 12 * mm
section(y, "What Stays Local vs. What Goes to Cloud")
y -= 6 * mm

colw = (CW - 8 * mm) / 2
ch_ = 50 * mm
# local card
rrect(M, y - ch_, colw, ch_, fill=colors.HexColor("#ECFDF5"), stroke=GREEN, r=8, lw=1.3)
c.setFillColor(GREEN); c.rect(M, y - 8 * mm, colw, 8 * mm, stroke=0, fill=1)
text(M + 5, y - 5.6 * mm, "STORED LOCALLY (YOUR STORE)", size=8.5, color=colors.white, font="Helvetica-Bold")
local_items = [
    "Raw video frames & RTSP streams",
    "Live AI processing & detection",
    "Short rolling video buffer (pre/post event)",
    "Encrypted camera usernames & passwords",
    "Raw footage is NEVER uploaded to cloud",
]
ly = bullets(M + 5, y - 13 * mm, local_items, colw - 10, size=9, gap=14, dotcolor=GREEN, txtcolor=INK)
# cloud card
cx = M + colw + 8 * mm
rrect(cx, y - ch_, colw, ch_, fill=colors.HexColor("#F5F3FF"), stroke=VIOLET, r=8, lw=1.3)
c.setFillColor(VIOLET); c.rect(cx, y - 8 * mm, colw, 8 * mm, stroke=0, fill=1)
text(cx + 5, y - 5.6 * mm, "LOGGED TO CLOUD (ENCRYPTED, HTTPS)", size=8.5, color=colors.white, font="Helvetica-Bold")
cloud_items = [
    "Event metadata: type, time, camera, confidence",
    "Single evidence snapshot per incident (JPEG)",
    "Camera online / offline heartbeat",
    "Low-res preview thumbnail for live tile",
    "PDF reports & aggregate analytics",
]
bullets(cx + 5, y - 13 * mm, cloud_items, colw - 10, size=9, gap=14, dotcolor=VIOLET, txtcolor=INK)

# ---- privacy callout ----
y = y - ch_ - 10 * mm
calh = 26 * mm
rrect(M, y - calh, CW, calh, fill=colors.HexColor("#ECFEFF"), stroke=GREEN, r=10, lw=1.3)
text(M + 7, y - 9 * mm, "Privacy by Design", size=11, color=GREEN, font="Helvetica-Bold")
pv = ("Your continuous camera video never leaves the store network. The cloud only ever receives lightweight "
      "insights - a snapshot and a few bytes of metadata when an event is detected. This keeps bandwidth low "
      "(works on 4G) and your footage private.")
cyt = y - 14 * mm
for ln in wrap(pv, "Helvetica", 9.2, CW - 16):
    text(M + 7, cyt, ln, size=9.2, color=INK)
    cyt -= 12

text(W / 2, M - 2 * mm, "Vantag / Nazar  -  Retail AI Surveillance  -  Page 1 of 2", size=7.5, color=MUTED, center=True)
c.showPage()

# ============== PAGE 2 ==============
header("Alert pipeline & security model")

y = H - M - 38 * mm
section(y, "How Alerts Are Sent")
y -= 6 * mm

steps = [
    ("1  Detect", "Edge AI flags sweep, dwell, fall, queue or watchlist match", CYAN),
    ("2  Push Event", "Agent sends event + snapshot to cloud over HTTPS", GREEN),
    ("3  Evaluate", "Cloud applies your zone rules & alert thresholds", VIOLET),
    ("4  Notify", "Email, push & Slack / Teams webhook fired instantly", AMBER),
]
pw = (CW - 3 * 6 * mm) / 4
ph = 34 * mm
px = M
ptop = y
for i, (t, d, accent) in enumerate(steps):
    rrect(px, ptop - ph, pw, ph, fill=PANEL2, stroke=accent, r=8, lw=1.3)
    c.setFillColor(accent); c.circle(px + pw / 2, ptop - 9 * mm, 3.2 * mm, stroke=0, fill=1)
    text(px + pw / 2, ptop - 16 * mm, t, size=9.5, color=INK, font="Helvetica-Bold", center=True)
    dy = ptop - 21 * mm
    for ln in wrap(d, "Helvetica", 7.6, pw - 8):
        text(px + pw / 2, dy, ln, size=7.6, color=MUTED, center=True)
        dy -= 9.5
    px += pw + 6 * mm

# ---- security table ----
y = ptop - ph - 12 * mm
section(y, "Security & Transport")
y -= 6 * mm

rows = [
    ("Camera credentials", "AES-encrypted at rest with a pinned server key; never exposed in plain text"),
    ("Agent <-> Cloud", "HTTPS / TLS; authenticated per-tenant edge token"),
    ("Live preview", "WebSocket channel + authenticated snapshot blobs"),
    ("Data isolation", "Per-tenant separation; each store sees only its own cameras & events"),
    ("Bandwidth", "Only snapshots + metadata leave site - typically under 50 KB per event"),
]
col1 = 45 * mm
rh = 13 * mm
ty = y
# header row
c.setFillColor(CYAN); c.rect(M, ty - 8 * mm, CW, 8 * mm, stroke=0, fill=1)
text(M + 4, ty - 5.6 * mm, "LAYER", size=8, color=colors.white, font="Helvetica-Bold")
text(M + col1 + 4, ty - 5.6 * mm, "MECHANISM", size=8, color=colors.white, font="Helvetica-Bold")
ty -= 8 * mm
for i, (layer, mech) in enumerate(rows):
    bg = colors.white if i % 2 == 0 else PANEL2
    c.setFillColor(bg); c.rect(M, ty - rh, CW, rh, stroke=0, fill=1)
    c.setStrokeColor(LINE); c.setLineWidth(0.6); c.line(M, ty - rh, M + CW, ty - rh)
    text(M + 4, ty - 8 * mm, layer, size=8.7, color=INK, font="Helvetica-Bold")
    mlines = wrap(mech, "Helvetica", 8.7, CW - col1 - 8)
    myy = ty - 8 * mm + (len(mlines) - 1) * 4.5
    for ln in mlines:
        text(M + col1 + 4, myy, ln, size=8.7, color=MUTED)
        myy -= 10
    ty -= rh
c.setStrokeColor(LINE); c.setLineWidth(0.8)
c.rect(M, ty, CW, y - ty, stroke=1, fill=0)

# legend
y = ty - 12 * mm
def sw(x, color, label):
    c.setFillColor(color); c.roundRect(x, y - 3, 9, 9, 2, stroke=0, fill=1)
    text(x + 13, y, label, size=8.5, color=MUTED)
    return x + 13 + c.stringWidth(label, "Helvetica", 8.5) + 18
nx = M + 10
nx = sw(nx, CYAN, "Edge / Access")
nx = sw(nx, GREEN, "Stays Local")
nx = sw(nx, VIOLET, "Cloud Logged")

text(W / 2, M - 2 * mm, "Vantag / Nazar  -  Retail AI Surveillance  -  Page 2 of 2", size=7.5, color=MUTED, center=True)
c.showPage()
c.save()
print("WROTE", OUT)
