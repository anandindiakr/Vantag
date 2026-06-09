"""
Vantag — One-Page Dealer Sales Flyer / Leave-Behind
A4 portrait, two-sided (front + back) → saved as 2-page PDF
Print at any copy shop, hand to store owners after a demo visit.
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame,
    Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether,
)
from reportlab.platypus.flowables import Flowable
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
import os

# ─── Colours ────────────────────────────────────────────────
CYAN    = colors.HexColor("#06b6d4")
VIOLET  = colors.HexColor("#6366f1")
PURPLE  = colors.HexColor("#a855f7")
GOLD    = colors.HexColor("#f59e0b")
RED     = colors.HexColor("#ef4444")
GREEN   = colors.HexColor("#22c55e")
DGRAY   = colors.HexColor("#1e293b")   # dark slate bg
LGRAY   = colors.HexColor("#334155")   # card bg
WHITE   = colors.white
OFFWHT  = colors.HexColor("#f1f5f9")
SUBDUED = colors.HexColor("#94a3b8")

W, H = A4   # 595.28 × 841.89 pt


# ─── Helper: paragraph shorthand ────────────────────────────
def P(text, **kw):
    fs   = kw.pop("fontSize", 9)
    font = kw.pop("fontName", "Helvetica")
    tc   = kw.pop("textColor", OFFWHT)
    aln  = kw.pop("alignment", TA_LEFT)
    lb   = kw.pop("leading", fs * 1.4)
    sb   = kw.pop("spaceBefore", 0)
    sa   = kw.pop("spaceAfter", 0)
    li   = kw.pop("leftIndent", 0)
    return Paragraph(text, ParagraphStyle(
        "x", fontSize=fs, fontName=font, textColor=tc,
        alignment=aln, leading=lb, spaceBefore=sb, spaceAfter=sa,
        leftIndent=li,
    ))


# ─── Custom Flowables ────────────────────────────────────────
class ColorBlock(Flowable):
    """Full-width coloured rectangle used as section background."""
    def __init__(self, width, height, color):
        super().__init__()
        self.width  = width
        self.height = height
        self._color = color

    def draw(self):
        self.canv.setFillColor(self._color)
        self.canv.rect(0, 0, self.width, self.height, fill=1, stroke=0)


class HeroBlock(Flowable):
    """Front-page hero: dark gradient header with headline."""
    def __init__(self, width, height):
        super().__init__()
        self.width  = width
        self.height = height

    def draw(self):
        c = self.canv
        # dark bg
        c.setFillColor(DGRAY)
        c.rect(0, 0, self.width, self.height, fill=1, stroke=0)
        # cyan accent bar top
        c.setFillColor(CYAN)
        c.rect(0, self.height - 4, self.width, 4, fill=1, stroke=0)
        # logo pill
        c.setFillColor(colors.HexColor("#0f172a"))
        c.roundRect(12, self.height - 48, 90, 28, 6, fill=1, stroke=0)
        c.setFillColor(CYAN)
        c.setFont("Helvetica-Bold", 15)
        c.drawString(20, self.height - 37, "VANTAG")
        # tagline
        c.setFillColor(SUBDUED)
        c.setFont("Helvetica", 8)
        c.drawString(20, self.height - 52, "AI-Powered Retail Security")
        # big headline
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 26)
        c.drawString(20, self.height - 100, "Stop Theft.")
        c.setFillColor(CYAN)
        c.drawString(20, self.height - 132, "See Everything.")
        c.setFillColor(WHITE)
        c.drawString(20, self.height - 164, "Protect Your Store.")
        # sub-headline
        c.setFillColor(SUBDUED)
        c.setFont("Helvetica", 9.5)
        c.drawString(20, self.height - 185,
                     "11 AI detection models · Works with any CCTV · No IT team needed")
        # divider
        c.setStrokeColor(colors.HexColor("#1e3a5f"))
        c.setLineWidth(0.5)
        c.line(20, self.height - 196, self.width - 20, self.height - 196)


class StatBox(Flowable):
    """Small coloured stat card."""
    def __init__(self, value, label, accent):
        super().__init__()
        self.width  = 3.8 * cm
        self.height = 2.0 * cm
        self._value  = value
        self._label  = label
        self._accent = accent

    def draw(self):
        c = self.canv
        c.setFillColor(LGRAY)
        c.roundRect(0, 0, self.width, self.height, 5, fill=1, stroke=0)
        c.setFillColor(self._accent)
        c.rect(0, self.height - 3, self.width, 3, fill=1, stroke=0)
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 18)
        c.drawCentredString(self.width / 2, self.height - 30, self._value)
        c.setFillColor(SUBDUED)
        c.setFont("Helvetica", 7)
        c.drawCentredString(self.width / 2, self.height - 42, self._label.upper())


class CheckRow(Flowable):
    """Cyan tick + label row."""
    def __init__(self, text, width, color=CYAN):
        super().__init__()
        self.width  = width
        self.height = 18
        self._text  = text
        self._color = color

    def draw(self):
        c = self.canv
        c.setFillColor(self._color)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(0, 2, "✓")
        c.setFillColor(OFFWHT)
        c.setFont("Helvetica", 9)
        c.drawString(16, 2, self._text)


# ─── PAGE 1 — FRONT ─────────────────────────────────────────
def front_story(frame_w):
    story = []

    # Hero
    story.append(HeroBlock(frame_w, 5.5 * cm))
    story.append(Spacer(1, 0.4 * cm))

    # ── STATS ROW ──
    stats = [
        StatBox("11",    "AI Models",       CYAN),
        StatBox("24/7",  "Monitoring",      VIOLET),
        StatBox("< 1s",  "Alert Speed",     GREEN),
        StatBox("0",     "IT Staff Needed", GOLD),
    ]
    stat_table = Table(
        [stats],
        colWidths=[3.8 * cm] * 4,
        hAlign="LEFT",
    )
    story.append(stat_table)
    story.append(Spacer(1, 0.45 * cm))

    # ── HOW IT WORKS ──
    story.append(P("<b>HOW IT WORKS</b>",
                   fontSize=8, fontName="Helvetica-Bold",
                   textColor=SUBDUED))
    story.append(Spacer(1, 0.15 * cm))

    steps = [
        ("1", CYAN,   "Connect your existing CCTV cameras — any brand"),
        ("2", VIOLET, "AI analyses video in real time on-site (Edge Agent)"),
        ("3", PURPLE, "Instant alerts on mobile, email or Slack"),
        ("4", GREEN,  "Review evidence clips & incident history anytime"),
    ]
    for num, col, txt in steps:
        row_tbl = Table(
            [[P(f"<b>{num}</b>", fontSize=12, textColor=col, fontName="Helvetica-Bold"),
              P(txt, fontSize=9, textColor=OFFWHT)]],
            colWidths=[0.7 * cm, frame_w - 0.7 * cm],
        )
        row_tbl.setStyle(TableStyle([
            ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ]))
        story.append(row_tbl)

    story.append(Spacer(1, 0.4 * cm))

    # ── AI DETECTION GRID ──
    story.append(P("<b>WHAT THE AI DETECTS</b>",
                   fontSize=8, fontName="Helvetica-Bold",
                   textColor=SUBDUED))
    story.append(Spacer(1, 0.15 * cm))

    detections = [
        ("Shoplifting",        RED,    "CRITICAL"),
        ("Fall Detection",     PURPLE, "CRITICAL"),
        ("Restricted Zone",    RED,    "CRITICAL"),
        ("Inventory Movement", GOLD,   "HIGH"),
        ("Camera Tamper",      GOLD,   "HIGH"),
        ("Loitering",          CYAN,   "MEDIUM"),
        ("Queue Length",       CYAN,   "MEDIUM"),
        ("Abandoned Object",   VIOLET, "MEDIUM"),
        ("Fire & Smoke",       RED,    "CRITICAL"),
        ("Crowd Density",      CYAN,   "MEDIUM"),
        ("Night Intruder",     VIOLET, "HIGH"),
    ]
    # 3-column grid
    cells = []
    for label, col, badge in detections:
        cell = Table(
            [[P(f"<b>{label}</b>", fontSize=7.5, textColor=WHITE, fontName="Helvetica-Bold"),
              P(badge, fontSize=6, textColor=col, fontName="Helvetica-Bold", alignment=TA_RIGHT)]],
            colWidths=[3.2 * cm, 1.7 * cm],
        )
        cell.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), LGRAY),
            ("ROUNDEDCORNERS", [4]),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING",   (0, 0), (0, -1), 6),
            ("RIGHTPADDING",  (-1, 0), (-1, -1), 6),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ]))
        cells.append(cell)

    # pad to multiple of 3
    while len(cells) % 3:
        cells.append(Spacer(1, 1))

    grid_data = [cells[i:i+3] for i in range(0, len(cells), 3)]
    grid_tbl  = Table(grid_data, colWidths=[(frame_w / 3)] * 3,
                      spaceBefore=0, spaceAfter=0)
    grid_tbl.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 2),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 2),
    ]))
    story.append(grid_tbl)
    story.append(Spacer(1, 0.4 * cm))

    # ── PRICING TEASER ──
    story.append(HRFlowable(width=frame_w, color=LGRAY, thickness=0.5))
    story.append(Spacer(1, 0.2 * cm))
    pricing_tbl = Table(
        [[P("Plans from", fontSize=8, textColor=SUBDUED),
          P("<b>₹999/mo</b>", fontSize=11, textColor=CYAN, fontName="Helvetica-Bold"),
          P("MYR 79/mo", fontSize=8.5, textColor=OFFWHT, fontName="Helvetica-Bold"),
          P("SGD 29/mo", fontSize=8.5, textColor=OFFWHT, fontName="Helvetica-Bold"),
          P("<b>14-day free trial</b>", fontSize=8, textColor=GREEN, fontName="Helvetica-Bold")]],
        colWidths=[2.2 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm, 4.0 * cm],
        hAlign="LEFT",
    )
    pricing_tbl.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(pricing_tbl)

    return story


# ─── PAGE 2 — BACK ──────────────────────────────────────────
def back_story(frame_w):
    story = []

    # Header bar
    hdr = Table(
        [[P("<b>DEALER INFORMATION</b>",
            fontSize=10, fontName="Helvetica-Bold", textColor=WHITE),
          P("Earn 15% recurring commission on every subscription",
            fontSize=8.5, textColor=SUBDUED, alignment=TA_RIGHT)]],
        colWidths=[frame_w * 0.5, frame_w * 0.5],
    )
    hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), DGRAY),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (0, 0), 8),
        ("RIGHTPADDING",  (-1, 0), (-1, -1), 8),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 0.5 * cm))

    # ── WHY DEALERS LOVE VANTAG ──
    story.append(P("<b>WHY DEALERS LOVE VANTAG</b>",
                   fontSize=8, fontName="Helvetica-Bold", textColor=SUBDUED))
    story.append(Spacer(1, 0.15 * cm))

    dealer_points = [
        "No hardware to stock — pure SaaS subscription",
        "Works with cameras the client ALREADY owns",
        "15% recurring monthly commission (paid forever)",
        "10% referral bonus when you bring other dealers",
        "Free demo account + demo kit supplied",
        "Technical support line for your installations",
        "Onboarding fee refunded against year-1 commissions",
    ]
    for pt in dealer_points:
        story.append(CheckRow(pt, frame_w, GOLD))

    story.append(Spacer(1, 0.45 * cm))

    # ── COMMISSION TABLE ──
    story.append(P("<b>WHAT YOU EARN (India INR)</b>",
                   fontSize=8, fontName="Helvetica-Bold", textColor=SUBDUED))
    story.append(Spacer(1, 0.15 * cm))

    comm_data = [
        [P("<b>Plan</b>", fontSize=8, fontName="Helvetica-Bold", textColor=WHITE),
         P("<b>Monthly Price</b>", fontSize=8, fontName="Helvetica-Bold", textColor=WHITE),
         P("<b>Your 15%</b>", fontSize=8, fontName="Helvetica-Bold", textColor=CYAN),
         P("<b>10 Clients/mo</b>", fontSize=8, fontName="Helvetica-Bold", textColor=GOLD)],
        [P("Starter",  fontSize=8, textColor=OFFWHT),
         P("₹999",     fontSize=8, textColor=OFFWHT),
         P("₹150",     fontSize=8, textColor=CYAN),
         P("₹1,500",   fontSize=8, textColor=GOLD)],
        [P("Growth",   fontSize=8, textColor=OFFWHT),
         P("₹2,499",   fontSize=8, textColor=OFFWHT),
         P("₹375",     fontSize=8, textColor=CYAN),
         P("₹3,750",   fontSize=8, textColor=GOLD)],
        [P("Pro",      fontSize=8, textColor=OFFWHT),
         P("₹4,999",   fontSize=8, textColor=OFFWHT),
         P("₹750",     fontSize=8, textColor=CYAN),
         P("₹7,500",   fontSize=8, textColor=GOLD)],
    ]
    comm_tbl = Table(comm_data,
                     colWidths=[3.2 * cm, 3.8 * cm, 3.2 * cm, 3.6 * cm])
    comm_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), DGRAY),
        ("BACKGROUND",    (0, 1), (-1, 1), LGRAY),
        ("BACKGROUND",    (0, 2), (-1, 2), colors.HexColor("#1e293b")),
        ("BACKGROUND",    (0, 3), (-1, 3), LGRAY),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW",     (0, 0), (-1, 0), 1.5, CYAN),
        ("LINEBELOW",     (0, 1), (-1, -2), 0.3, LGRAY),
    ]))
    story.append(comm_tbl)
    story.append(Spacer(1, 0.35 * cm))
    story.append(P("*Malaysia: MYR 79/149/299 · Singapore: SGD 29/59/99 — same 15% commission structure",
                   fontSize=7, textColor=SUBDUED))
    story.append(Spacer(1, 0.45 * cm))

    # ── HOW TO SIGN UP A CLIENT ──
    story.append(P("<b>HOW TO SIGN UP A CLIENT IN 4 STEPS</b>",
                   fontSize=8, fontName="Helvetica-Bold", textColor=SUBDUED))
    story.append(Spacer(1, 0.15 * cm))

    signup_steps = [
        ("STEP 1", CYAN,   "Visit client's store — show live AI demo on your laptop"),
        ("STEP 2", VIOLET, "Help them register at retailnazar.com / retail-vantag.com"),
        ("STEP 3", PURPLE, "Download Edge Agent on their Windows PC — 5-min setup"),
        ("STEP 4", GOLD,   "Configure 1–2 cameras in Zone Editor — demo is live!"),
    ]
    step_rows = []
    for label, col, text in signup_steps:
        step_rows.append([
            P(f"<b>{label}</b>", fontSize=7, fontName="Helvetica-Bold",
              textColor=col, alignment=TA_CENTER),
            P(text, fontSize=8.5, textColor=OFFWHT),
        ])
    step_tbl = Table(step_rows, colWidths=[1.8 * cm, frame_w - 1.8 * cm])
    step_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, -1), LGRAY),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (0, -1), 4),
        ("LEFTPADDING",   (1, 0), (1, -1), 10),
        ("LINEBELOW",     (0, 0), (-1, -2), 0.3, DGRAY),
    ]))
    story.append(step_tbl)
    story.append(Spacer(1, 0.45 * cm))

    # ── CONTACT / CTA footer ──
    cta_tbl = Table(
        [[P("<b>Ready to become a Vantag Dealer?</b>",
            fontSize=10, fontName="Helvetica-Bold", textColor=WHITE),
          P("dealer@retail-vantag.com\n+91 XXXXX XXXXX",
            fontSize=9, textColor=CYAN, alignment=TA_RIGHT)]],
        colWidths=[frame_w * 0.58, frame_w * 0.42],
    )
    cta_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), DGRAY),
        ("TOPPADDING",    (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING",   (0, 0), (0, 0), 10),
        ("RIGHTPADDING",  (-1, 0), (-1, -1), 10),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LINEABOVE",     (0, 0), (-1, 0), 1.5, CYAN),
    ]))
    story.append(cta_tbl)
    story.append(Spacer(1, 0.2 * cm))

    # Region URLs row
    url_tbl = Table(
        [[P("🇮🇳  retailnazar.com", fontSize=8, textColor=SUBDUED, alignment=TA_CENTER),
          P("🇸🇬  retail-vantag.com", fontSize=8, textColor=SUBDUED, alignment=TA_CENTER),
          P("🇲🇾  jagajaga.my", fontSize=8, textColor=SUBDUED, alignment=TA_CENTER)]],
        colWidths=[frame_w / 3] * 3,
    )
    url_tbl.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEABOVE",     (0, 0), (-1, 0), 0.3, LGRAY),
    ]))
    story.append(url_tbl)

    return story


# ─── BUILD PDF ──────────────────────────────────────────────
def build_pdf():
    OUT = os.path.join(os.path.dirname(__file__), "Vantag_Dealer_Flyer.pdf")

    margin = 1.2 * cm
    frame_w = W - 2 * margin
    frame_h = H - 2 * margin

    frame = Frame(margin, margin, frame_w, frame_h,
                  leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0)

    doc = BaseDocTemplate(
        OUT, pagesize=A4,
        leftMargin=margin, rightMargin=margin,
        topMargin=margin, bottomMargin=margin,
    )

    def _bg(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor("#0f172a"))
        canvas.rect(0, 0, W, H, fill=1, stroke=0)
        canvas.restoreState()

    pt = PageTemplate(id="main", frames=[frame], onPage=_bg)
    doc.addPageTemplates([pt])

    full_story = front_story(frame_w) + [
        # force page break
        Paragraph("<br/>", ParagraphStyle("pb", fontSize=1)),
    ]
    # inject a manual page break flowable
    from reportlab.platypus import PageBreak
    full_story.append(PageBreak())
    full_story += back_story(frame_w)

    doc.build(full_story)
    print(f"[OK] Saved: {OUT}")


if __name__ == "__main__":
    build_pdf()
