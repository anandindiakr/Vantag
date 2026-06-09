"""
Vantag Sales Pitch Deck — slide-style A4 landscape PDF
Each page = one "slide"
"""
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus.flowables import Flowable
from datetime import datetime
import os

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "Vantag_Sales_Pitch_Deck.pdf")

W, H = landscape(A4)   # 297 x 210 mm

# ── Palette ────────────────────────────────────────────────────────────────────
NAVY    = colors.HexColor("#0D1B2A")
BLUE    = colors.HexColor("#1E90FF")
TEAL    = colors.HexColor("#00C9A7")
ORANGE  = colors.HexColor("#FF6B35")
GOLD    = colors.HexColor("#FFC107")
LGRAY   = colors.HexColor("#F5F7FA")
MGRAY   = colors.HexColor("#CCCCCC")
DGRAY   = colors.HexColor("#444444")
WHITE   = colors.white

styles = getSampleStyleSheet()
def S(name, **kw):
    return ParagraphStyle(name, parent=styles["Normal"], **kw)

def hr(c=MGRAY, w=0.5):
    return HRFlowable(width="100%", thickness=w, color=c, spaceAfter=4, spaceBefore=4)

# ── Slide wrapper ──────────────────────────────────────────────────────────────
class SlideHeader(Flowable):
    """Full-width navy top bar with slide title + subtitle."""
    def __init__(self, title, subtitle="", accent=BLUE):
        super().__init__()
        self.title = title
        self.subtitle = subtitle
        self.accent = accent
        self.width = W - 2.4*cm
        self.height = 2.2*cm

    def draw(self):
        c = self.canv
        # background bar
        c.setFillColor(NAVY)
        c.rect(0, 0, self.width, self.height, fill=1, stroke=0)
        # accent left stripe
        c.setFillColor(self.accent)
        c.rect(0, 0, 0.35*cm, self.height, fill=1, stroke=0)
        # title
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 18)
        c.drawString(0.6*cm, self.height - 0.75*cm, self.title)
        # subtitle
        if self.subtitle:
            c.setFillColor(colors.HexColor("#8899AA"))
            c.setFont("Helvetica", 10)
            c.drawString(0.6*cm, 0.4*cm, self.subtitle)


class SlideNumber(Flowable):
    """Bottom-right slide number + logo."""
    def __init__(self, num, total):
        super().__init__()
        self.num = num
        self.total = total
        self.width = W - 2.4*cm
        self.height = 0.5*cm

    def draw(self):
        c = self.canv
        c.setFillColor(MGRAY)
        c.setFont("Helvetica", 8)
        c.drawRightString(self.width, 0.1*cm,
                          f"VANTAG  |  retail-vantag.com  |  Slide {self.num}/{self.total}")


def stat_box(value, label, color=BLUE):
    data = [[
        Paragraph(f"<b>{value}</b>", S("SV", fontSize=22, fontName="Helvetica-Bold",
                                        textColor=color, alignment=TA_CENTER)),
    ], [
        Paragraph(label, S("SL", fontSize=8, fontName="Helvetica",
                            textColor=DGRAY, alignment=TA_CENTER, leading=11)),
    ]]
    t = Table(data, colWidths=[4.5*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), LGRAY),
        ("BOX",           (0, 0), (-1, -1), 1.5, color),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
    ]))
    return t


def two_col(left_items, right_items, left_w=12*cm, right_w=12*cm):
    row = [[left_items, right_items]]
    t = Table(row, colWidths=[left_w, right_w])
    t.setStyle(TableStyle([
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, -1),  12),
        ("RIGHTPADDING", (1, 0), (1, -1),  0),
    ]))
    return t


def bullet(text, color=BLUE, indent=0):
    return Paragraph(
        f"<font color='#{color.hexval()[2:] if hasattr(color,'hexval') else '1E90FF'}'><b>&#9654;</b></font>  {text}",
        S("BL", fontSize=9.5, fontName="Helvetica", textColor=DGRAY,
          leading=15, leftIndent=indent, spaceBefore=2))


def blue_bullet(text):
    return Paragraph(
        f"<font color='#1E90FF'><b>&#9654;</b></font>  {text}",
        S("BB", fontSize=9.5, fontName="Helvetica", textColor=DGRAY,
          leading=15, leftIndent=4, spaceBefore=2))


def section_pill(text, color=BLUE):
    data = [[Paragraph(text, S("SP", fontSize=9, fontName="Helvetica-Bold",
                                textColor=WHITE, alignment=TA_CENTER))]]
    t = Table(data, colWidths=[5*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), color),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
    ]))
    return t

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE BUILDERS
# ══════════════════════════════════════════════════════════════════════════════
TOTAL_SLIDES = 10

def slide_cover():
    story = []
    # Full-width cover block
    data = [[
        Paragraph("VANTAG", S("CV", fontSize=48, fontName="Helvetica-Bold",
                               textColor=BLUE, alignment=TA_CENTER)),
    ],[
        Paragraph("Retail Intelligence Platform", S("CS", fontSize=16, fontName="Helvetica",
                                                      textColor=colors.HexColor("#B0C4DE"),
                                                      alignment=TA_CENTER)),
    ],[
        Paragraph("AI-Powered Security &amp; Inventory Analytics for Every Shop, Mall &amp; Store",
                  S("CT", fontSize=11, fontName="Helvetica", textColor=WHITE,
                    alignment=TA_CENTER, leading=17)),
    ],[
        Paragraph("India  &#183;  Malaysia  &#183;  Singapore",
                  S("CR", fontSize=10, fontName="Helvetica", textColor=GOLD, alignment=TA_CENTER)),
    ],[
        Paragraph("retail-vantag.com  |  retailnazar.com  |  jagajaga.my",
                  S("CL", fontSize=9, fontName="Helvetica",
                    textColor=colors.HexColor("#8899AA"), alignment=TA_CENTER)),
    ]]
    t = Table(data, colWidths=["100%"])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), NAVY),
        ("TOPPADDING",    (0, 0), (-1, -1), 16),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
        ("LEFTPADDING",   (0, 0), (-1, -1), 30),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 30),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.4*cm))
    # Three tag pills
    pills_data = [[
        section_pill("AI Shelf Monitoring", BLUE),
        section_pill("Auto Camera Discovery", TEAL),
        section_pill("Zone Intelligence", ORANGE),
        section_pill("No Cloud AI Cost", GOLD),
    ]]
    pt = Table(pills_data, colWidths=[5.5*cm, 5.5*cm, 5.5*cm, 5.5*cm])
    pt.setStyle(TableStyle([("ALIGN", (0,0),(-1,-1), "CENTER"),
                             ("LEFTPADDING",(0,0),(-1,-1),4),
                             ("RIGHTPADDING",(0,0),(-1,-1),4)]))
    story.append(pt)
    story.append(Spacer(1, 0.3*cm))
    story.append(SlideNumber(1, TOTAL_SLIDES))
    return story


def slide_problem():
    story = []
    story.append(SlideHeader("The Problem", "What keeps retail store owners awake at night", ORANGE))
    story.append(Spacer(1, 0.3*cm))

    problems = [
        ("Retail Theft & Shrinkage",
         "Global retail shrinkage is $112B/year. Small stores lose 1.5–3% of revenue to theft, "
         "mostly undetected by existing 'record-only' CCTV."),
        ("Dumb CCTV Systems",
         "90% of retail cameras only record. Nobody watches the footage until after the incident. "
         "By then, the product — and the thief — are gone."),
        ("Expensive Enterprise Solutions",
         "AI security from Axis, Genetec, Verkada costs $500–$2,000/camera/year. "
         "Totally out of reach for SME retailers, pharmacies, convenience stores."),
        ("No Inventory Visibility",
         "Store managers don't know when shelves go empty, when products are misplaced, "
         "or when high-value items are moved without a sale."),
        ("Complex Setup",
         "Existing AI systems require specialist integrators, NVR replacements, "
         "dedicated servers. SMEs simply can't afford the downtime or the bill."),
    ]

    rows = []
    for title, body in problems:
        rows.append([
            Paragraph(f"<b>{title}</b>",
                      S("PT", fontSize=10, fontName="Helvetica-Bold", textColor=ORANGE)),
            Paragraph(body, S("PB", fontSize=9, fontName="Helvetica", textColor=DGRAY,
                               leading=13)),
        ])

    t = Table(rows, colWidths=[5.5*cm, 16.5*cm])
    t.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, LGRAY]),
        ("GRID",           (0, 0), (-1, -1), 0.3, MGRAY),
        ("TOPPADDING",     (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 7),
        ("LEFTPADDING",    (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 8),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.2*cm))
    story.append(SlideNumber(2, TOTAL_SLIDES))
    return story


def slide_solution():
    story = []
    story.append(SlideHeader("The Solution", "Vantag — Turn any existing camera into an AI analyst", TEAL))
    story.append(Spacer(1, 0.3*cm))

    left = [
        Paragraph("What is Vantag?",
                  S("SH", fontSize=12, fontName="Helvetica-Bold", textColor=NAVY, spaceAfter=6)),
        Paragraph(
            "Vantag is a <b>plug-in AI layer</b> that sits on top of your existing CCTV cameras. "
            "A small Windows/Linux agent runs on any store PC, connects to your cameras over the local network, "
            "and streams real-time AI analysis to your cloud dashboard — with <b>zero per-frame cloud AI cost.</b>",
            S("SB", fontSize=9.5, fontName="Helvetica", textColor=DGRAY, leading=15, spaceAfter=8)),
        Paragraph("How it works:",
                  S("SH2", fontSize=10, fontName="Helvetica-Bold", textColor=NAVY, spaceAfter=4)),
        blue_bullet("Install the Edge Agent on any Windows store PC (2 min setup)"),
        blue_bullet("Agent auto-discovers Hikvision, Dahua, CP Plus cameras on your LAN"),
        blue_bullet("Draw zones on your camera view in the web dashboard"),
        blue_bullet("AI starts detecting theft, movement, footfall in real time"),
        blue_bullet("Incidents push to your phone & dashboard instantly"),
        Spacer(1, 0.3*cm),
        Paragraph("<b>Works with cameras you already own.</b> No hardware replacement needed.",
                  S("HL", fontSize=9.5, fontName="Helvetica-Bold", textColor=TEAL, leading=14)),
    ]

    right = [
        Paragraph("Key Features",
                  S("KH", fontSize=12, fontName="Helvetica-Bold", textColor=NAVY, spaceAfter=6)),
    ]
    features = [
        (BLUE,   "AI Shelf Monitoring — detects pick-up, removal, theft"),
        (TEAL,   "Auto Camera Discovery — scans LAN, no IP needed"),
        (ORANGE, "Zone Intrusion Alerts — custom zones, instant push alerts"),
        (GOLD,   "Footfall Analytics — people counting, heat maps"),
        (BLUE,   "30-Day Incident History with video thumbnail evidence"),
        (TEAL,   "Multi-Store Dashboard — manage all branches in one view"),
        (ORANGE, "Mobile Notifications — iOS & Android push alerts"),
        (GOLD,   "No Cloud AI Cost — AI runs locally on your store PC"),
    ]
    for col, text in features:
        right.append(blue_bullet(text))
        right.append(Spacer(1, 2))

    story.append(two_col(left, right, left_w=12.5*cm, right_w=10*cm))
    story.append(Spacer(1, 0.15*cm))
    story.append(SlideNumber(3, TOTAL_SLIDES))
    return story


def slide_market():
    story = []
    story.append(SlideHeader("Market Opportunity", "A massive, underserved SME retail market", GOLD))
    story.append(Spacer(1, 0.3*cm))

    stats = [
        ("$112B", "Global retail\nshrinkage/year", ORANGE),
        ("65M+",  "SME retail stores\nin India alone", BLUE),
        ("90%",   "Cameras with NO\nAI — record only", TEAL),
        ("<$10",  "Vantag cost per\nstore per month", GOLD),
        ("3–5x",  "ROI in the\nfirst month", NAVY),
    ]
    stat_cells = [[stat_box(v, l, c) for v, l, c in stats]]
    st = Table(stat_cells, colWidths=[4.8*cm]*5)
    st.setStyle(TableStyle([
        ("ALIGN",        (0,0),(-1,-1), "CENTER"),
        ("LEFTPADDING",  (0,0),(-1,-1), 4),
        ("RIGHTPADDING", (0,0),(-1,-1), 4),
    ]))
    story.append(st)
    story.append(Spacer(1, 0.3*cm))

    markets = [
        ("India", ORANGE, "INR 999–4,999/mo",
         "65M+ SME stores. Pharmacies, kirana, malls, hospitals, hostels, post offices. "
         "Massive untapped market with near-zero existing AI security penetration."),
        ("Malaysia", TEAL, "MYR 79–299/mo",
         "500,000+ SME retail outlets. Growing CCTV adoption post-COVID. "
         "jagajaga.my targets Bahasa Malaysia-speaking store owners."),
        ("Singapore", BLUE, "SGD 29–99/mo",
         "Highly tech-savvy market. Strong SME density in HDB shophouses, food courts, "
         "mini-marts. retail-vantag.com positions as premium AI solution."),
    ]
    rows = []
    for region, col, price, desc in markets:
        rows.append([
            Paragraph(f"<b>{region}</b>",
                      S("RT", fontSize=12, fontName="Helvetica-Bold", textColor=col, alignment=TA_CENTER)),
            Paragraph(f"<b>{price}</b>",
                      S("RP", fontSize=10, fontName="Helvetica-Bold", textColor=col, alignment=TA_CENTER)),
            Paragraph(desc, S("RD", fontSize=9, fontName="Helvetica", textColor=DGRAY, leading=13)),
        ])
    mt = Table(rows, colWidths=[3.5*cm, 4.5*cm, 14.5*cm])
    mt.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, LGRAY]),
        ("GRID",           (0, 0), (-1, -1), 0.3, MGRAY),
        ("TOPPADDING",     (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 7),
        ("LEFTPADDING",    (0, 0), (-1, -1), 8),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(mt)
    story.append(Spacer(1, 0.15*cm))
    story.append(SlideNumber(4, TOTAL_SLIDES))
    return story


def slide_competitive():
    story = []
    story.append(SlideHeader("Competitive Advantage", "Why Vantag wins against alternatives", BLUE))
    story.append(Spacer(1, 0.3*cm))

    Y = Paragraph("<b>YES</b>", S("Y", fontSize=9, fontName="Helvetica-Bold",
                                   textColor=TEAL, alignment=TA_CENTER))
    N = Paragraph("<b>NO</b>",  S("N", fontSize=9, fontName="Helvetica-Bold",
                                   textColor=ORANGE, alignment=TA_CENTER))
    P = Paragraph("<b>PARTIAL</b>", S("P", fontSize=9, fontName="Helvetica-Bold",
                                       textColor=GOLD, alignment=TA_CENTER))

    def hdr(t):
        return Paragraph(t, S("CH", fontSize=8.5, fontName="Helvetica-Bold",
                               textColor=WHITE, alignment=TA_CENTER))
    def feat(t):
        return Paragraph(t, S("CF", fontSize=8.5, fontName="Helvetica",
                               textColor=DGRAY))

    rows = [
        [hdr("Feature"), hdr("Vantag"), hdr("Traditional\nCCTV"), hdr("Verkada /\nAxis (Enterprise)"),
         hdr("Generic AI\nSaaS"), hdr("Manual\nReview")],
        [feat("AI shelf theft detection"),  Y, N, Y, P, N],
        [feat("Works with existing cameras"),Y,Y, N, P, Y],
        [feat("Edge processing (no cloud AI cost)"), Y, N, N, N, N],
        [feat("Auto camera discovery (LAN)"), Y, N, N, N, N],
        [feat("Zone-based alerts"),          Y, N, Y, P, N],
        [feat("Price under $30/mo"),         Y, Y, N, P, Y],
        [feat("30-min setup"),               Y, N, N, P, N],
        [feat("Multi-language support"),     Y, N, P, N, N],
        [feat("Mobile push alerts"),         Y, N, Y, Y, N],
    ]
    ct = Table(rows, colWidths=[5.5*cm, 2.5*cm, 2.5*cm, 4.0*cm, 3.5*cm, 2.5*cm])
    ct.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  NAVY),
        ("BACKGROUND",    (0, 1), (1, -1),  colors.HexColor("#E8F8F5")),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, LGRAY]),
        ("GRID",          (0, 0), (-1, -1), 0.3, MGRAY),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("ALIGN",         (1, 0), (-1, -1), "CENTER"),
    ]))
    story.append(ct)
    story.append(Spacer(1, 0.15*cm))
    story.append(SlideNumber(5, TOTAL_SLIDES))
    return story


def slide_pricing_summary():
    story = []
    story.append(SlideHeader("Pricing", "Simple, transparent, affordable for every store", TEAL))
    story.append(Spacer(1, 0.3*cm))

    def region_mini_table(region, currency, color, plans):
        header = [Paragraph(f"<b>{region}</b>", S("RH", fontSize=10, fontName="Helvetica-Bold",
                                                    textColor=WHITE, alignment=TA_CENTER)),
                  Paragraph("Monthly", S("PH", fontSize=8.5, fontName="Helvetica-Bold",
                                          textColor=WHITE, alignment=TA_CENTER)),
                  Paragraph("Annual", S("PH", fontSize=8.5, fontName="Helvetica-Bold",
                                         textColor=WHITE, alignment=TA_CENTER))]
        rows = [header]
        for plan, mo, ann in plans:
            rows.append([
                Paragraph(plan, S("PN", fontSize=9, fontName="Helvetica",
                                   textColor=DGRAY, alignment=TA_CENTER)),
                Paragraph(f"<b>{currency} {mo}</b>", S("PM", fontSize=9.5, fontName="Helvetica-Bold",
                                                         textColor=color, alignment=TA_CENTER)),
                Paragraph(f"{currency} {ann}/yr", S("PA", fontSize=8.5, fontName="Helvetica",
                                                      textColor=DGRAY, alignment=TA_CENTER)),
            ])
        t = Table(rows, colWidths=[2.5*cm, 2.5*cm, 3.0*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0),  color),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, LGRAY]),
            ("GRID",          (0, 0), (-1, -1), 0.3, MGRAY),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ]))
        return t

    india  = region_mini_table("India (INR)",     "INR", ORANGE,
                               [("Starter","999","9,990"),("Growth","2,499","24,990"),("Pro","4,999","49,990")])
    my     = region_mini_table("Malaysia (MYR)",  "MYR", TEAL,
                               [("Starter","79","790"),("Growth","149","1,490"),("Pro","299","2,990")])
    sg     = region_mini_table("Singapore (SGD)", "SGD", BLUE,
                               [("Starter","29","290"),("Growth","59","590"),("Pro","99","990")])

    tables_row = [[india, my, sg]]
    tt = Table(tables_row, colWidths=[8.5*cm, 8.5*cm, 8.5*cm])
    tt.setStyle(TableStyle([
        ("VALIGN",       (0,0),(-1,-1), "TOP"),
        ("LEFTPADDING",  (0,0),(-1,-1), 4),
        ("RIGHTPADDING", (0,0),(-1,-1), 4),
    ]))
    story.append(tt)
    story.append(Spacer(1, 0.3*cm))

    highlights = [
        "14-day money-back guarantee for new customers",
        "Annual plan = 10 months price (2 months FREE)",
        "Hardware NOT required — use your existing cameras",
        "Dealer commission: 15% | Referral partner: 10%",
        "Scales from 1 store to unlimited stores seamlessly",
    ]
    hl_data = [[Paragraph(f"&#10003;  {h}", S("HL", fontSize=9, fontName="Helvetica",
                                               textColor=DGRAY, leading=13))
                for h in highlights]]
    ht = Table(hl_data, colWidths=[5.2*cm]*5)
    ht.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0,0),(-1,-1), [colors.HexColor("#E8F8F5")]),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING",   (0,0),(-1,-1), 6),
        ("BOX",           (0,0),(-1,-1), 1, TEAL),
    ]))
    story.append(ht)
    story.append(Spacer(1, 0.15*cm))
    story.append(SlideNumber(6, TOTAL_SLIDES))
    return story


def slide_roi():
    story = []
    story.append(SlideHeader("ROI for Your Customer", "Real numbers that close the sale", GOLD))
    story.append(Spacer(1, 0.3*cm))

    scenarios = [
        ("Pharmacy — Mumbai", "4 cameras, Growth Plan (INR 2,499/mo)",
         ORANGE, [
             ("Weekly shoplifting incidents prevented", "3–5"),
             ("Average product value saved per incident", "INR 300"),
             ("Weekly savings", "INR 900–1,500"),
             ("Monthly savings", "INR 3,600–6,000"),
             ("Monthly plan cost", "INR 2,499"),
             ("NET MONTHLY BENEFIT", "INR 1,100–3,500"),
             ("Payback period", "< 2 weeks"),
         ]),
        ("Convenience Store — KL", "6 cameras, Growth Plan (MYR 149/mo)",
         TEAL, [
             ("Weekly shrinkage prevented", "5–8 items"),
             ("Average item value saved", "MYR 15"),
             ("Monthly savings", "MYR 300–480"),
             ("Monthly plan cost", "MYR 149"),
             ("NET MONTHLY BENEFIT", "MYR 151–331"),
             ("Payback period", "< 2 weeks"),
         ]),
        ("HDB Mini-Mart — Singapore", "4 cameras, Starter Plan (SGD 29/mo)",
         BLUE, [
             ("Theft incidents prevented/week", "2–3"),
             ("Average item value", "SGD 8"),
             ("Monthly savings", "SGD 64–96"),
             ("Monthly plan cost", "SGD 29"),
             ("NET MONTHLY BENEFIT", "SGD 35–67"),
             ("Payback period", "< 2 weeks"),
         ]),
    ]

    def scenario_table(title, sub, col, items):
        rows = [[Paragraph(f"<b>{title}</b>",
                            S("ST", fontSize=10, fontName="Helvetica-Bold",
                              textColor=WHITE, alignment=TA_CENTER)),
                 Paragraph(sub, S("SS", fontSize=8.5, fontName="Helvetica",
                                   textColor=colors.HexColor("#DDDDDD"), alignment=TA_CENTER))]]
        for label, val in items:
            is_net = "NET" in label
            rows.append([
                Paragraph(f"<b>{label}</b>" if is_net else label,
                           S("IL", fontSize=8.5 if not is_net else 9,
                             fontName="Helvetica-Bold" if is_net else "Helvetica",
                             textColor=GOLD if is_net else DGRAY)),
                Paragraph(f"<b>{val}</b>" if is_net else val,
                           S("IV", fontSize=8.5 if not is_net else 9.5,
                             fontName="Helvetica-Bold" if is_net else "Helvetica",
                             textColor=GOLD if is_net else col, alignment=TA_RIGHT)),
            ])
        t = Table(rows, colWidths=[6.0*cm, 2.8*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0),  col),
            ("SPAN",          (0, 0), (-1, 0)),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, LGRAY]),
            ("BACKGROUND",    (0, -1), (-1, -1), colors.HexColor("#FFFDE7")),
            ("GRID",          (0, 0), (-1, -1), 0.3, MGRAY),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ]))
        return t

    tables_row = [[scenario_table(*s) for s in scenarios]]
    tt = Table(tables_row, colWidths=[9.0*cm, 9.0*cm, 9.0*cm])
    tt.setStyle(TableStyle([
        ("VALIGN", (0,0),(-1,-1), "TOP"),
        ("LEFTPADDING",  (0,0),(-1,-1), 4),
        ("RIGHTPADDING", (0,0),(-1,-1), 4),
    ]))
    story.append(tt)
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(
        "<b>Key message to customers:</b> \"Vantag pays for itself in 2 weeks. "
        "After that, every prevented theft is pure profit.\"",
        S("KM", fontSize=9.5, fontName="Helvetica-Bold", textColor=NAVY,
          alignment=TA_CENTER, leading=14)))
    story.append(Spacer(1, 0.15*cm))
    story.append(SlideNumber(7, TOTAL_SLIDES))
    return story


def slide_how_it_works():
    story = []
    story.append(SlideHeader("How It Works", "From sign-up to live AI monitoring in under 30 minutes", BLUE))
    story.append(Spacer(1, 0.3*cm))

    steps = [
        ("1", "Register Online", BLUE,
         "Customer visits retail-vantag.com, selects a plan, and registers in 2 minutes. "
         "Receives login credentials instantly."),
        ("2", "Download Edge Agent", TEAL,
         "Download the Vantag Windows Agent (free download, ~80MB). "
         "Install on any store PC — even an old laptop works."),
        ("3", "Auto-Scan Cameras", ORANGE,
         "Click 'Auto-Scan' in the dashboard. The agent finds all cameras on the store LAN "
         "automatically — Hikvision, Dahua, CP Plus, and more."),
        ("4", "Draw Your Zones", GOLD,
         "In the web dashboard, drag a box over your shelf, entrance, or cash counter. "
         "Name it (e.g. 'Shelf A – Chocolates'). Done."),
        ("5", "Go Live — Get Alerts", NAVY,
         "AI starts monitoring in real time. Any detected movement, removal, or intrusion "
         "sends a push notification to your phone within seconds."),
    ]

    def step_box(num, title, col, body):
        data = [[
            Paragraph(f"<b>{num}</b>",
                      S("SN", fontSize=20, fontName="Helvetica-Bold",
                        textColor=WHITE, alignment=TA_CENTER)),
            Paragraph(f"<b>{title}</b>",
                      S("STI", fontSize=10, fontName="Helvetica-Bold", textColor=WHITE)),
        ],[
            Paragraph("", S("_")),
            Paragraph(body, S("SBO", fontSize=8.5, fontName="Helvetica",
                               textColor=colors.HexColor("#CCCCCC"), leading=13)),
        ]]
        t = Table(data, colWidths=[1.2*cm, 3.9*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), col),
            ("TOPPADDING",    (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ]))
        return t

    boxes = [[step_box(n, t, c, b) for n, t, c, b in steps]]
    bt = Table(boxes, colWidths=[5.1*cm]*5)
    bt.setStyle(TableStyle([
        ("LEFTPADDING",  (0,0),(-1,-1), 3),
        ("RIGHTPADDING", (0,0),(-1,-1), 3),
    ]))
    story.append(bt)
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(
        "Compatible camera brands:  Hikvision  &#183;  Dahua  &#183;  CP Plus  &#183;  "
        "TP-Link  &#183;  Reolink  &#183;  Uniview  &#183;  Any RTSP/ONVIF camera",
        S("CB", fontSize=9, fontName="Helvetica", textColor=TEXT_MUTED if False else DGRAY,
          alignment=TA_CENTER, leading=13)))
    story.append(Spacer(1, 0.15*cm))
    story.append(SlideNumber(8, TOTAL_SLIDES))
    return story


def slide_traction():
    story = []
    story.append(SlideHeader("Traction & Roadmap", "Where we are and where we are going", TEAL))
    story.append(Spacer(1, 0.3*cm))

    left = [
        Paragraph("Current Status", S("TH", fontSize=12, fontName="Helvetica-Bold",
                                       textColor=NAVY, spaceAfter=6)),
        blue_bullet("Platform fully built and deployed on live VPS (Hostinger, Singapore)"),
        blue_bullet("3 domains live: retail-vantag.com · retailnazar.com · jagajaga.my"),
        blue_bullet("Edge Agent for Windows complete — auto camera discovery working"),
        blue_bullet("AI shelf monitoring, zone detection, footfall analytics functional"),
        blue_bullet("Multi-language support: EN, HI, TA, TE, KN, ML, MR, GU, BN, PA, MS"),
        blue_bullet("Razorpay payment integration (India & Singapore) live"),
        blue_bullet("AI Smart Support Chat (GPT-4o) deployed on all 3 sites"),
        Spacer(1, 0.3*cm),
        Paragraph("Active Dealer Programme", S("TH2", fontSize=10, fontName="Helvetica-Bold",
                                                textColor=NAVY, spaceAfter=4)),
        blue_bullet("Dealer onboarding fee: INR 5,000 / MYR 200 / SGD 80 (refundable)"),
        blue_bullet("15% dealer commission on all subscriptions"),
        blue_bullet("Marketing kit, training guide, and demo account provided"),
    ]

    right = [
        Paragraph("Near-Term Roadmap", S("RH", fontSize=12, fontName="Helvetica-Bold",
                                          textColor=NAVY, spaceAfter=6)),
    ]
    roadmap = [
        (ORANGE, "Q3 2026", "Android & iOS mobile app launch"),
        (BLUE,   "Q3 2026", "Linux Edge Agent for Raspberry Pi"),
        (TEAL,   "Q3 2026", "Stripe payment for Malaysia / SGD"),
        (GOLD,   "Q4 2026", "NVR/DVR direct integration (no PC needed)"),
        (ORANGE, "Q4 2026", "Facial recognition optional add-on"),
        (BLUE,   "Q1 2027", "POS integration — link sales to theft events"),
        (TEAL,   "Q1 2027", "Franchise / chain management dashboard"),
        (GOLD,   "Q2 2027", "White-label OEM for security integrators"),
    ]
    for col, quarter, item in roadmap:
        right.append(Paragraph(
            f"<b><font color='#{col.hexval()[2:]}'>{quarter}</font></b>  {item}",
            S("RI", fontSize=9, fontName="Helvetica", textColor=DGRAY,
              leading=14, spaceBefore=2)))

    story.append(two_col(left, right, left_w=13*cm, right_w=10*cm))
    story.append(Spacer(1, 0.15*cm))
    story.append(SlideNumber(9, TOTAL_SLIDES))
    return story


def slide_cta():
    story = []
    data = [[
        Paragraph("Ready to Get Started?", S("CTA1", fontSize=26, fontName="Helvetica-Bold",
                                               textColor=BLUE, alignment=TA_CENTER)),
    ],[
        Paragraph("Join the Vantag dealer network or start your free trial today.",
                  S("CTA2", fontSize=12, fontName="Helvetica",
                    textColor=colors.HexColor("#B0C4DE"), alignment=TA_CENTER)),
    ]]
    ct = Table(data, colWidths=["100%"])
    ct.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), NAVY),
        ("TOPPADDING",    (0, 0), (-1, -1), 20),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 20),
        ("LEFTPADDING",   (0, 0), (-1, -1), 30),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 30),
    ]))
    story.append(ct)
    story.append(Spacer(1, 0.3*cm))

    contacts = [
        ("India", ORANGE, "retailnazar.com\nretailnazar.in", "support@retail-vantag.com"),
        ("Malaysia", TEAL, "jagajaga.my", "support@retail-vantag.com"),
        ("Singapore", BLUE, "retail-vantag.com", "support@retail-vantag.com"),
        ("Dealer Enquiry", GOLD, "Email subject:\n'Dealer – [Region]'", "support@retail-vantag.com"),
    ]
    def contact_card(region, col, web, email):
        data = [[
            Paragraph(f"<b>{region}</b>",
                      S("CCR", fontSize=11, fontName="Helvetica-Bold", textColor=col, alignment=TA_CENTER)),
        ],[
            Paragraph(web, S("CCW", fontSize=8.5, fontName="Helvetica",
                              textColor=DGRAY, alignment=TA_CENTER, leading=13)),
        ],[
            Paragraph(email, S("CCE", fontSize=8, fontName="Helvetica",
                                textColor=BLUE, alignment=TA_CENTER)),
        ]]
        t = Table(data, colWidths=[5.8*cm])
        t.setStyle(TableStyle([
            ("BOX",           (0,0),(-1,-1), 1.5, col),
            ("TOPPADDING",    (0,0),(-1,-1), 6),
            ("BOTTOMPADDING", (0,0),(-1,-1), 6),
            ("BACKGROUND",    (0,0),(-1,-1), LGRAY),
        ]))
        return t

    cards = [[contact_card(*c) for c in contacts]]
    cct = Table(cards, colWidths=[5.8*cm]*4)
    cct.setStyle(TableStyle([
        ("LEFTPADDING",  (0,0),(-1,-1), 4),
        ("RIGHTPADDING", (0,0),(-1,-1), 4),
    ]))
    story.append(cct)
    story.append(Spacer(1, 0.3*cm))

    story.append(Paragraph(
        "&#9474;  14-day money-back guarantee  &#9474;  No hardware replacement needed  "
        "&#9474;  30-minute setup  &#9474;  Works with cameras you already own  &#9474;",
        S("GB", fontSize=9, fontName="Helvetica-Bold", textColor=TEAL, alignment=TA_CENTER)))
    story.append(Spacer(1, 0.15*cm))
    story.append(SlideNumber(10, TOTAL_SLIDES))
    return story


TEXT_MUTED = colors.HexColor("#888888")

def build_story():
    story = []
    slides = [
        slide_cover,
        slide_problem,
        slide_solution,
        slide_market,
        slide_competitive,
        slide_pricing_summary,
        slide_roi,
        slide_how_it_works,
        slide_traction,
        slide_cta,
    ]
    for i, fn in enumerate(slides):
        story += fn()
        if i < len(slides) - 1:
            story.append(PageBreak())
    return story


def build_pdf():
    doc = SimpleDocTemplate(
        OUTPUT_PATH, pagesize=landscape(A4),
        topMargin=1.2*cm, bottomMargin=1.2*cm,
        leftMargin=1.2*cm, rightMargin=1.2*cm,
        title="Vantag Sales Pitch Deck",
        author="Retail Nazar Technologies",
        subject="Vantag Platform — Investor & Sales Pitch Deck",
    )
    doc.build(build_story())
    print(f"[OK] Saved: {OUTPUT_PATH}")


if __name__ == "__main__":
    build_pdf()
