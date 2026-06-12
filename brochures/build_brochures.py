"""
Generate 3 region-specific Vantag brochures as PDFs.
Outputs to: ./brochures/Vantag_Brochure_{IN,SG,MY}.pdf
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm, cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Flowable, KeepTogether
)
from reportlab.pdfgen import canvas
import os

OUT_DIR = os.path.join(os.path.dirname(__file__))
os.makedirs(OUT_DIR, exist_ok=True)

PAGE_W, PAGE_H = A4
MARGIN = 15 * mm

# ── Region configurations ──────────────────────────────────────────────────
REGIONS = {
    "IN": {
        "brand": "Vantag — Retail Nazar",
        "short": "Retail Nazar",
        "tagline": "आपकी दुकान की तीसरी आँख  •  India's AI Eye for Retail",
        "country": "India",
        "symbol": "Rs.",
        "plans": [
            ("Starter", 5,  "Rs. 1,999/mo",  "Rs. 1,666/mo"),
            ("Growth",  15, "Rs. 4,499/mo",  "Rs. 3,749/mo"),
            ("Pro",     30, "Rs. 8,999/mo",  "Rs. 7,499/mo"),
        ],
        "domains": ["retailnazar.com", "retailnazar.in", "retailnazar.info"],
        "support_phone": "+91-XXX-XXX-XXXX",
        "primary": colors.HexColor("#F97316"),   # saffron
        "primary_dark": colors.HexColor("#C2410C"),
        "accent": colors.HexColor("#1E3A8A"),    # navy
        "gst_line": "All prices exclude 18% GST. Billed monthly or annually.",
    },
    "SG": {
        "brand": "Vantag — Retail Intelligence",
        "short": "Vantag",
        "tagline": "AI-Powered Retail Security & Predictive Analytics",
        "country": "Singapore",
        "symbol": "S$",
        "plans": [
            ("Starter", 5,  "S$ 39/mo",  "S$ 32/mo"),
            ("Growth",  15, "S$ 99/mo",  "S$ 82/mo"),
            ("Pro",     30, "S$ 189/mo", "S$ 157/mo"),
        ],
        "domains": ["retail-vantag.com"],
        "support_phone": "+65-XXXX-XXXX",
        "primary": colors.HexColor("#8B5CF6"),   # violet
        "primary_dark": colors.HexColor("#5B21B6"),
        "accent": colors.HexColor("#10B981"),    # emerald
        "gst_line": "Prices exclude 9% GST. Billed monthly or annually.",
    },
    "MY": {
        "brand": "Vantag — JagaJaga",
        "short": "JagaJaga",
        "tagline": "Pengawal AI untuk Kedai Anda  •  AI Guardian for Your Shop",
        "country": "Malaysia",
        "symbol": "RM",
        "plans": [
            ("Starter", 5,  "RM 59/mo",  "RM 49/mo"),
            ("Growth",  15, "RM 149/mo", "RM 124/mo"),
            ("Pro",     30, "RM 299/mo", "RM 249/mo"),
        ],
        "domains": ["jagajaga.my", "retailjagajaga.com"],
        "support_phone": "+60-XX-XXX-XXXX",
        "primary": colors.HexColor("#10B981"),   # emerald
        "primary_dark": colors.HexColor("#047857"),
        "accent": colors.HexColor("#FCD34D"),    # gold
        "gst_line": "Prices exclude 8% SST. Billed monthly or annually.",
    },
}

# ── Shared feature list (12 detection types) ───────────────────────────────
FEATURES = [
    ("Product Sweeping Detection",    "Catches shoplifters grabbing multiple items in seconds."),
    ("Anomalous Dwell Time",          "Flags loiterers lingering near high-value shelves."),
    ("Empty Shelf Detection",         "Tells staff exactly when to restock — before customers leave."),
    ("Theft & Concealment",           "Spots items slipped into bags, pockets, or clothing."),
    ("Inventory Movement Tracking",   "Knows which SKU moved, how many, and when."),
    ("Fall Detection",                "Alerts you instantly if a staff member or customer falls."),
    ("Zone Entry Violations",         "Stops unauthorized entry to stock-rooms & back offices."),
    ("Crowd / Queue Analytics",       "Sees long queues — open another counter automatically."),
    ("Camera Tamper Detection",       "Knows the moment a lens is blocked, sprayed, or rotated."),
    ("Staff Behavior Monitoring",     "Till fraud, phone use, prolonged absence — all logged."),
    ("After-Hours Intrusion",         "Zero tolerance for movement when the shop is closed."),
    ("License Plate Capture",         "Capture every car at drive-through lanes or car parks."),
]

WHY_BULLETS = [
    "Plug-and-play: set up in under 30 minutes from a phone.",
    "Works with ANY IP camera — no vendor lock-in, no new hardware cost.",
    "AI runs on a local Edge device — your video never leaves the shop.",
    "One-tap door lock via MQTT the instant a threat is detected.",
    "Real-time alerts on mobile + web, with video evidence attached.",
    "Built-in POS & email integrations — no coding required.",
    "Bilingual UI — English + your local language, switchable anytime.",
    "Starts at just one monthly subscription — no long contracts.",
]

# ── Custom flowables ───────────────────────────────────────────────────────

class HeroBanner(Flowable):
    """Full-width gradient banner with brand, tagline."""
    def __init__(self, brand, tagline, primary, primary_dark, height=110*mm):
        Flowable.__init__(self)
        self.brand = brand
        self.tagline = tagline
        self.primary = primary
        self.primary_dark = primary_dark
        self.width = PAGE_W - 2 * MARGIN
        self.height = height

    def draw(self):
        c = self.canv
        # gradient rectangle (simulate via many strips)
        steps = 60
        for i in range(steps):
            t = i / (steps - 1)
            r = self.primary.red * (1 - t) + self.primary_dark.red * t
            g = self.primary.green * (1 - t) + self.primary_dark.green * t
            b = self.primary.blue * (1 - t) + self.primary_dark.blue * t
            c.setFillColorRGB(r, g, b)
            c.rect(0, self.height * (1 - (i + 1) / steps), self.width, self.height / steps + 0.5, stroke=0, fill=1)

        # Decorative circles
        c.setFillColor(colors.Color(1, 1, 1, alpha=0.12))
        c.circle(self.width - 40*mm, self.height - 20*mm, 30*mm, stroke=0, fill=1)
        c.setFillColor(colors.Color(1, 1, 1, alpha=0.08))
        c.circle(self.width - 70*mm, self.height - 50*mm, 18*mm, stroke=0, fill=1)

        # Brand text
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 28)
        c.drawString(10*mm, self.height - 35*mm, self.brand)
        c.setFont("Helvetica", 13)
        c.drawString(10*mm, self.height - 47*mm, self.tagline)

        # "AI-Powered" pill
        c.setFillColor(colors.Color(1, 1, 1, alpha=0.2))
        c.roundRect(10*mm, self.height - 65*mm, 56*mm, 10*mm, 5*mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(14*mm, self.height - 62*mm, "AI-POWERED  •  EDGE-FIRST  •  PLUG & PLAY")

        # Bottom tagline bar
        c.setFillColor(colors.Color(0, 0, 0, alpha=0.25))
        c.rect(0, 0, self.width, 14*mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica", 10)
        c.drawString(10*mm, 5*mm, "12 AI detection types  |  works with ANY IP camera  |  setup in 30 min")


class ColoredDivider(Flowable):
    def __init__(self, color, width=None, height=3):
        Flowable.__init__(self)
        self.color = color
        self.w = width or (PAGE_W - 2 * MARGIN)
        self.height = height

    def draw(self):
        self.canv.setFillColor(self.color)
        self.canv.rect(0, 0, self.w, self.height, stroke=0, fill=1)


def footer_canvas(primary, brand, domain):
    def _draw(c, doc):
        c.saveState()
        # Footer bar
        c.setFillColor(primary)
        c.rect(0, 0, PAGE_W, 12*mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(MARGIN, 5*mm, brand)
        c.setFont("Helvetica", 9)
        c.drawRightString(PAGE_W - MARGIN, 5*mm, f"{domain}  |  Page {doc.page}")
        c.restoreState()
    return _draw


# ── Main PDF builder ───────────────────────────────────────────────────────

def build_pdf(region_code, cfg):
    out_path = os.path.join(OUT_DIR, f"Vantag_Brochure_{region_code}.pdf")

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle('H1', parent=styles['Heading1'],
                        fontName='Helvetica-Bold', fontSize=22,
                        textColor=cfg['primary_dark'], spaceAfter=8, spaceBefore=4)
    h2 = ParagraphStyle('H2', parent=styles['Heading2'],
                        fontName='Helvetica-Bold', fontSize=14,
                        textColor=cfg['primary_dark'], spaceAfter=6, spaceBefore=10)
    body = ParagraphStyle('Body', parent=styles['BodyText'],
                          fontName='Helvetica', fontSize=10.5,
                          textColor=colors.HexColor("#1F2937"), leading=15, spaceAfter=4)
    lead = ParagraphStyle('Lead', parent=body, fontSize=11.5,
                          textColor=colors.HexColor("#374151"), leading=17)
    muted = ParagraphStyle('Muted', parent=body, fontSize=9,
                           textColor=colors.HexColor("#6B7280"))
    cta = ParagraphStyle('CTA', parent=body, alignment=TA_CENTER,
                         fontSize=11, textColor=colors.white,
                         fontName='Helvetica-Bold')

    doc = SimpleDocTemplate(
        out_path, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=18*mm,
    )

    story = []

    # ─── PAGE 1: HERO + WHY VANTAG ────────────────────────────────────────
    story.append(HeroBanner(cfg['brand'], cfg['tagline'],
                            cfg['primary'], cfg['primary_dark']))
    story.append(Spacer(1, 8*mm))

    story.append(Paragraph("The Retail Problem — Solved", h1))
    story.append(Paragraph(
        f"Retail shrinkage costs {cfg['country']}'s shopkeepers "
        "a staggering 1.5–3% of revenue every year. Traditional CCTV only "
        "records — it doesn't alert, doesn't prevent, and nobody watches it. "
        f"<b>{cfg['short']}</b> turns your existing cameras into a 24/7 AI guardian "
        "that catches theft, fall-hazards, empty shelves and staff fraud — "
        "<i>before</i> they cost you money.", lead))
    story.append(Spacer(1, 4*mm))

    story.append(Paragraph("Why shopkeepers choose us", h2))
    bullet_rows = []
    for b in WHY_BULLETS:
        bullet_rows.append([
            Paragraph(f'<font color="{cfg["primary"].hexval()}"><b>▸</b></font>', body),
            Paragraph(b, body),
        ])
    t = Table(bullet_rows, colWidths=[7*mm, None])
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(t)

    story.append(PageBreak())

    # ─── PAGE 2: 12 AI DETECTIONS ─────────────────────────────────────────
    story.append(Paragraph("12 AI Detections Running Simultaneously", h1))
    story.append(ColoredDivider(cfg['primary']))
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph(
        "Every camera in your shop is analyzed 24/7 by 12 specialized AI models "
        "running on-site. No cloud upload. No video leaves your premises.", body))
    story.append(Spacer(1, 5*mm))

    # 2-column grid of features
    cell_style = ParagraphStyle('Cell', parent=body, fontSize=9.5, leading=13)
    title_style = ParagraphStyle('CellTitle', parent=body, fontSize=10.5,
                                 fontName='Helvetica-Bold',
                                 textColor=cfg['primary_dark'], leading=13)
    rows = []
    for i in range(0, len(FEATURES), 2):
        left = FEATURES[i]
        right = FEATURES[i + 1] if i + 1 < len(FEATURES) else ("", "")
        left_cell = [Paragraph(f"● {left[0]}", title_style),
                     Paragraph(left[1], cell_style)]
        right_cell = [Paragraph(f"● {right[0]}", title_style),
                      Paragraph(right[1], cell_style)] if right[0] else []
        rows.append([left_cell, right_cell])

    feat_tbl = Table(rows, colWidths=[(PAGE_W - 2*MARGIN) / 2 - 2*mm] * 2)
    feat_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F9FAFB")),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(feat_tbl)
    story.append(Spacer(1, 6*mm))

    story.append(Paragraph("How It Works — 3 Steps", h2))
    flow_rows = [[
        Paragraph(
            f'<font color="{cfg["primary"].hexval()}"><b>STEP 1</b></font><br/>'
            '<b>Register & Pay</b><br/>'
            '<font size="9">Enter shop details, pick a plan, '
            'pay securely via Razorpay. 3 minutes.</font>', body),
        Paragraph(
            f'<font color="{cfg["primary"].hexval()}"><b>STEP 2</b></font><br/>'
            '<b>Scan QR → Install Agent</b><br/>'
            '<font size="9">Install the Edge Agent on any Android '
            'phone, tablet, or Windows PC. Scan the QR to pair.</font>', body),
        Paragraph(
            f'<font color="{cfg["primary"].hexval()}"><b>STEP 3</b></font><br/>'
            '<b>Cameras auto-detected</b><br/>'
            '<font size="9">System scans your LAN, finds every IP '
            'camera, and starts AI in under 30 minutes.</font>', body),
    ]]
    flow = Table(flow_rows, colWidths=[(PAGE_W - 2*MARGIN) / 3 - 2*mm] * 3)
    flow.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#FFF7ED") if region_code == "IN"
                                         else colors.HexColor("#ECFDF5") if region_code == "MY"
                                         else colors.HexColor("#F5F3FF")),
        ('BOX', (0, 0), (-1, -1), 0, colors.white),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(flow)

    story.append(PageBreak())

    # ─── PAGE 3: PRICING + CONTACT ────────────────────────────────────────
    story.append(Paragraph(f"Pricing — {cfg['country']}", h1))
    story.append(ColoredDivider(cfg['primary']))
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph(
        "Simple, transparent pricing. No setup fees. No long contracts. "
        "Cancel anytime.", body))
    story.append(Spacer(1, 5*mm))

    price_header = [
        Paragraph('<b>Plan</b>', body),
        Paragraph('<b>Cameras</b>', body),
        Paragraph('<b>Monthly</b>', body),
        Paragraph('<b>Annual (save ~17%)</b>', body),
    ]
    price_rows = [price_header]
    for i, p in enumerate(cfg['plans']):
        row = [
            Paragraph(f'<b>{p[0]}</b>' + (' ★' if p[0] == 'Growth' else ''), body),
            Paragraph(f"up to {p[1]}", body),
            Paragraph(p[2], body),
            Paragraph(p[3], body),
        ]
        price_rows.append(row)

    price_tbl = Table(price_rows, colWidths=[35*mm, 30*mm, 45*mm, 55*mm])
    price_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), cfg['primary']),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor("#FEF3C7")),  # highlight Growth
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(price_tbl)
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph(
        f"★ Growth is our most popular plan.  {cfg['gst_line']}", muted))
    story.append(Spacer(1, 8*mm))

    # What's included
    story.append(Paragraph("Every plan includes", h2))
    includes = [
        "All 12 AI detection types",
        "Real-time mobile + web dashboard",
        "One-Tap Door Lock via MQTT",
        "Unlimited users per shop",
        "Email + in-app alerts with video evidence",
        "30-day incident history (longer on Pro)",
        "Multi-language UI (English + local)",
        "Edge Agent for Android / Windows / Jetson",
        "POS integration (Square, Shopify, custom)",
        "Email support  &  24/7 AI Support Chat",
    ]
    inc_rows = []
    for i in range(0, len(includes), 2):
        left = includes[i]
        right = includes[i + 1] if i + 1 < len(includes) else ""
        inc_rows.append([
            Paragraph(f'<font color="{cfg["accent"].hexval()}"><b>✓</b></font>  {left}', body),
            Paragraph(f'<font color="{cfg["accent"].hexval()}"><b>✓</b></font>  {right}', body) if right else "",
        ])
    inc_tbl = Table(inc_rows, colWidths=[(PAGE_W - 2*MARGIN) / 2] * 2)
    inc_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(inc_tbl)

    story.append(Spacer(1, 10*mm))

    # ── CTA box
    domain = cfg['domains'][0]
    cta_data = [[Paragraph(
        f'<font size="18" color="white"><b>Ready to protect your shop?</b></font><br/>'
        f'<font size="11" color="white">Start free trial at <b>{domain}</b> '
        f'— set up in 30 minutes, first 14 days free.</font><br/><br/>'
        f'<font size="12" color="white">📧 support@retail-vantag.com   &nbsp;&nbsp;&nbsp;   '
        f'📞 {cfg["support_phone"]}</font>',
        ParagraphStyle('CtaBig', fontName='Helvetica', fontSize=11,
                       textColor=colors.white, alignment=TA_CENTER, leading=17))]]
    cta_tbl = Table(cta_data, colWidths=[PAGE_W - 2*MARGIN])
    cta_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), cfg['primary_dark']),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 20),
        ('RIGHTPADDING', (0, 0), (-1, -1), 20),
        ('TOPPADDING', (0, 0), (-1, -1), 20),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 20),
    ]))
    story.append(cta_tbl)

    story.append(Spacer(1, 6*mm))
    story.append(Paragraph(
        f"<i>Websites: {' • '.join(cfg['domains'])}</i>", muted))
    story.append(Paragraph(
        f"<i>© 2026 Vantag Retail Intelligence Platform. All rights reserved.</i>", muted))

    footer = footer_canvas(cfg['primary'], cfg['brand'], cfg['domains'][0])
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"Built: {out_path}")


if __name__ == "__main__":
    for code, cfg in REGIONS.items():
        build_pdf(code, cfg)
    print("\nAll 3 brochures generated.")
