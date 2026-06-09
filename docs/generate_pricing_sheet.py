"""
Generate Vantag Pricing Sheet PDF — all regions (India, Malaysia, Singapore)
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether, PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from datetime import datetime
import os

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "Vantag_Pricing_Sheet_All_Regions.pdf")

# ── Palette ────────────────────────────────────────────────────────────────────
DARK_NAVY   = colors.HexColor("#0D1B2A")
ACCENT_BLUE = colors.HexColor("#1E90FF")
INDIA_COLOR = colors.HexColor("#FF6B35")
MY_COLOR    = colors.HexColor("#00A86B")
SG_COLOR    = colors.HexColor("#E63946")
LIGHT_BG    = colors.HexColor("#F5F7FA")
MID_GRAY    = colors.HexColor("#DDDDDD")
TEXT_DARK   = colors.HexColor("#1A1A2E")
TEXT_MUTED  = colors.HexColor("#666666")
GOLD        = colors.HexColor("#FFC107")
WHITE       = colors.white

def S(name, **kw):
    styles = getSampleStyleSheet()
    return ParagraphStyle(name, parent=styles["Normal"], **kw)

def hr(c=MID_GRAY, w=0.4):
    return HRFlowable(width="100%", thickness=w, color=c, spaceAfter=6, spaceBefore=6)

# ── Hero banner ────────────────────────────────────────────────────────────────
def hero_banner():
    rows = [
        [Paragraph("VANTAG", S("H", fontSize=30, fontName="Helvetica-Bold",
                                textColor=ACCENT_BLUE, alignment=TA_CENTER))],
        [Paragraph("Retail Intelligence Platform", S("S", fontSize=12, fontName="Helvetica",
                                                       textColor=colors.HexColor("#B0C4DE"),
                                                       alignment=TA_CENTER))],
        [Paragraph("PRICING SHEET", S("T", fontSize=18, fontName="Helvetica-Bold",
                                       textColor=WHITE, alignment=TA_CENTER))],
        [Paragraph("India  &#183;  Malaysia  &#183;  Singapore  |  Effective 2026",
                   S("R", fontSize=9, fontName="Helvetica", textColor=colors.HexColor("#8899AA"),
                     alignment=TA_CENTER))],
    ]
    t = Table(rows, colWidths=["100%"])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), DARK_NAVY),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 20),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 20),
    ]))
    return t

# ── What is Vantag ─────────────────────────────────────────────────────────────
def what_is_vantag():
    story = []
    story.append(Spacer(1, 0.4*cm))
    story.append(Paragraph("What is Vantag?",
                            S("WH", fontSize=13, fontName="Helvetica-Bold",
                              textColor=DARK_NAVY, spaceBefore=6, spaceAfter=4)))
    story.append(Paragraph(
        "Vantag is an <b>AI-powered retail security and inventory intelligence platform</b> that turns your "
        "existing CCTV cameras into smart business tools. It detects shelf theft, inventory movement, "
        "footfall analytics, and zone intrusions in real time — <b>no cloud AI cost</b>, runs on your own "
        "store PC.",
        S("B", fontSize=9.5, fontName="Helvetica", textColor=TEXT_DARK,
          leading=15, alignment=TA_LEFT, spaceAfter=4)))

    features = [
        ("AI Shelf Monitoring", "Detects product pick-up, removal, and theft in real time"),
        ("Auto Camera Discovery", "Scans your LAN, finds Hikvision/Dahua/CP Plus cameras automatically"),
        ("Zone Intelligence", "Define custom zones, get instant alerts on intrusion or movement"),
        ("Footfall Analytics", "People counting, dwell time, heat maps"),
        ("Edge AI Processing", "AI runs on store PC — no per-frame cloud cost"),
        ("Multi-Store Dashboard", "Manage all branches from one web dashboard"),
        ("Mobile Alerts", "Real-time push notifications and incident reports"),
        ("30-Day Incident History", "Full audit trail with video evidence thumbnails"),
    ]
    feat_data = [[
        Paragraph(f"&#10003;  <b>{name}</b>", S("FN", fontSize=8.5, fontName="Helvetica",
                                                   textColor=TEXT_DARK, leading=13)),
        Paragraph(desc, S("FD", fontSize=8.5, fontName="Helvetica",
                          textColor=TEXT_MUTED, leading=13))
    ] for name, desc in features]

    t = Table(feat_data, colWidths=[5.5*cm, 11.5*cm])
    t.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, LIGHT_BG]),
        ("GRID",          (0, 0), (-1, -1), 0.3, MID_GRAY),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
    ]))
    story.append(t)
    return story

# ── Plan card ──────────────────────────────────────────────────────────────────
def plan_table(region_label, region_color, currency, plans, note=""):
    """
    plans = [(plan_name, badge, monthly_price, annual_price, cameras, features), ...]
    col widths sum to 17 cm (A4 - 2cm margins each side)
    """
    def ph(text):
        return Paragraph(text, S("PH", fontSize=9, fontName="Helvetica-Bold",
                                  textColor=WHITE, alignment=TA_CENTER))
    header_row = [ph("Plan"), ph("Monthly"), ph("Annual (save 17%)"),
                  ph("Cameras"), ph("Key Inclusions")]
    all_rows = [header_row]
    for name, badge, mo, ann, cams, inclusions in plans:
        badge_text = f" [{badge}]" if badge else ""
        all_rows.append([
            Paragraph(f"<b>{name}</b>{badge_text}", S("PN", fontSize=9, fontName="Helvetica-Bold",
                                                       textColor=TEXT_DARK, alignment=TA_CENTER)),
            Paragraph(f"<b>{currency} {mo}</b>", S("MP", fontSize=10, fontName="Helvetica-Bold",
                                                     textColor=region_color, alignment=TA_CENTER)),
            Paragraph(f"{currency} {ann}/yr", S("AP", fontSize=9, fontName="Helvetica",
                                                  textColor=TEXT_MUTED, alignment=TA_CENTER)),
            Paragraph(str(cams), S("CP", fontSize=9, fontName="Helvetica",
                                   alignment=TA_CENTER)),
            Paragraph(inclusions, S("INC", fontSize=8, fontName="Helvetica",
                                    textColor=TEXT_DARK, leading=12)),
        ])

    # Total = 3.4+3.2+4.0+2.4+4.0 = 17.0 cm
    col_widths = [3.4*cm, 3.2*cm, 4.0*cm, 2.4*cm, 4.0*cm]
    t = Table(all_rows, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  region_color),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, LIGHT_BG]),
        ("GRID",          (0, 0), (-1, -1), 0.3, MID_GRAY),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))

    items = [t]
    if note:
        items.append(Paragraph(f"<i>* {note}</i>",
                               S("Note", fontSize=7.5, fontName="Helvetica",
                                 textColor=TEXT_MUTED, spaceBefore=2)))
    return items

# ── Feature comparison matrix ─────────────────────────────────────────────────
def comparison_table():
    Y = "&#10003;"
    N = "&#8212;"
    features = [
        ("Feature",                          "Starter", "Growth",  "Pro"),
        ("AI Shelf Monitoring",               Y, Y, Y),
        ("Zone Intrusion Alerts",             Y, Y, Y),
        ("Footfall Counting (basic)",         Y, Y, Y),
        ("Mobile Push Notifications",         Y, Y, Y),
        ("Incident History",                  "7 days", "30 days", "90 days"),
        ("Cameras supported",                 "Up to 4", "Up to 8", "Up to 16"),
        ("Edge AI Agent",                     Y, Y, Y),
        ("Auto Camera Discovery (LAN)",       N, Y, Y),
        ("ONVIF Protocol Support",            N, Y, Y),
        ("Heatmap Analytics",                 N, Y, Y),
        ("Multi-Store / Branch Support",      N, "2 stores", "Unlimited"),
        ("Custom Alert Rules",                N, Y, Y),
        ("Video Evidence Thumbnails",         N, Y, Y),
        ("CSV/PDF Report Export",             N, Y, Y),
        ("API Access",                        N, N, Y),
        ("White-label Dashboard (dealers)",   N, N, Y),
        ("SLA Uptime Guarantee",              "99%", "99.5%", "99.9%"),
        ("Support",                           "Email", "Email+Chat", "Priority"),
    ]

    def cell(text, is_header=False, is_feature=False):
        st = "Helvetica-Bold" if is_header else "Helvetica"
        color = WHITE if is_header else (TEXT_DARK if is_feature else TEXT_MUTED)
        return Paragraph(text, S("CT", fontSize=8, fontName=st,
                                  textColor=color, alignment=TA_LEFT if is_feature else TA_CENTER))

    rows = []
    for i, row in enumerate(features):
        if i == 0:
            rows.append([cell(c, is_header=True) for c in row])
        else:
            rows.append([cell(row[0], is_feature=True)] +
                        [cell(c) for c in row[1:]])

    t = Table(rows, colWidths=[6.2*cm, 3.0*cm, 3.0*cm, 3.0*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  DARK_NAVY),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, LIGHT_BG]),
        ("GRID",          (0, 0), (-1, -1), 0.3, MID_GRAY),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
    ]))
    return t

# ── Add-ons ────────────────────────────────────────────────────────────────────
def addons_table():
    addons = [
        ("Add-On", "India (INR/mo)", "Malaysia (MYR/mo)", "Singapore (SGD/mo)"),
        ("Extra Camera (+4 pack)",     "499",  "39",  "14"),
        ("Extra Store Branch",         "699",  "55",  "19"),
        ("Extended History (180 days)","299",  "24",   "9"),
        ("Advanced AI Model Upgrade",  "999",  "79",  "29"),
        ("Dedicated Support SLA",     "1,499","119",  "45"),
    ]
    rows = [[Paragraph(c, S("AC", fontSize=8.5,
                             fontName="Helvetica-Bold" if i == 0 else "Helvetica",
                             textColor=WHITE if i == 0 else TEXT_DARK,
                             alignment=TA_CENTER))
             for c in row]
            for i, row in enumerate(addons)]
    t = Table(rows, colWidths=[5.8*cm, 3.7*cm, 3.7*cm, 3.7*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  ACCENT_BLUE),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, LIGHT_BG]),
        ("GRID",          (0, 0), (-1, -1), 0.3, MID_GRAY),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
    ]))
    return t

# ── ROI box ────────────────────────────────────────────────────────────────────
def roi_box():
    data = [[Paragraph(
        "<b>RETURN ON INVESTMENT (ROI) EXAMPLE</b><br/>"
        "A small pharmacy with 4 cameras on the Growth plan (INR 2,499/month) "
        "typically prevents 2–4 shoplifting incidents per week. At an average product "
        "value of INR 300 per incident, that is <b>INR 2,400–4,800 saved per week</b> — "
        "paying for the entire annual subscription in the first 2 weeks.",
        S("ROI", fontSize=9, fontName="Helvetica", textColor=DARK_NAVY,
          leading=14, alignment=TA_LEFT))]]
    t = Table(data, colWidths=["100%"])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#FFF8E1")),
        ("BOX",           (0, 0), (-1, -1), 1.2, GOLD),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
    ]))
    return t

# ── Contact + footer ───────────────────────────────────────────────────────────
def contact_footer():
    contact_data = [
        [Paragraph("<b>CONTACT &amp; SALES</b>", S("CH", fontSize=10, fontName="Helvetica-Bold",
                                                     textColor=WHITE)),
         Paragraph("", S("_"))],
        [Paragraph("India", S("CR", fontSize=9, fontName="Helvetica-Bold", textColor=GOLD)),
         Paragraph("retailnazar.com | retailnazar.in | support@retail-vantag.com", S("CV", fontSize=9, fontName="Helvetica", textColor=WHITE))],
        [Paragraph("Malaysia", S("CR", fontSize=9, fontName="Helvetica-Bold", textColor=GOLD)),
         Paragraph("jagajaga.my | support@retail-vantag.com", S("CV", fontSize=9, fontName="Helvetica", textColor=WHITE))],
        [Paragraph("Singapore", S("CR", fontSize=9, fontName="Helvetica-Bold", textColor=GOLD)),
         Paragraph("retail-vantag.com | support@retail-vantag.com", S("CV", fontSize=9, fontName="Helvetica", textColor=WHITE))],
        [Paragraph("Dealer Enquiries", S("CR", fontSize=9, fontName="Helvetica-Bold", textColor=GOLD)),
         Paragraph("Email subject: 'Dealer Partnership – [Your Region]' to support@retail-vantag.com", S("CV", fontSize=9, fontName="Helvetica", textColor=WHITE))],
    ]
    t = Table(contact_data, colWidths=[3.5*cm, 13.5*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), DARK_NAVY),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
    ]))
    return t


def section_title(text, color=DARK_NAVY):
    data = [[Paragraph(text, S("ST", fontSize=11, fontName="Helvetica-Bold",
                                textColor=WHITE, alignment=TA_LEFT))]]
    t = Table(data, colWidths=["100%"])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), color),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
    ]))
    return t


# ── Build story ────────────────────────────────────────────────────────────────
def build_story():
    story = []

    story.append(hero_banner())
    story += what_is_vantag()
    story.append(Spacer(1, 0.5*cm))

    # ─ India ─
    story.append(section_title("  INDIA PRICING  (INR — Indian Rupees)", INDIA_COLOR))
    story.append(Spacer(1, 0.2*cm))
    india_plans = [
        ("Starter", "",       "999",   "9,990",  "Up to 4",
         "AI monitoring, zone alerts, 7-day history, email support"),
        ("Growth",  "Popular","2,499","24,990", "Up to 8",
         "All Starter + auto discovery, heatmaps, 30-day history, chat support, multi-store (2)"),
        ("Pro",     "Best",   "4,999","49,990", "Up to 16",
         "All Growth + 90-day history, API, unlimited stores, priority support, white-label"),
    ]
    story += plan_table("India", INDIA_COLOR, "INR", india_plans,
                        note="GST applicable as per Indian tax law. Annual plan = 10 months price.")
    story.append(Spacer(1, 0.4*cm))

    # ─ Malaysia ─
    story.append(section_title("  MALAYSIA PRICING  (MYR — Malaysian Ringgit)", MY_COLOR))
    story.append(Spacer(1, 0.2*cm))
    my_plans = [
        ("Starter", "",       "79",   "790",   "Up to 4",
         "AI monitoring, zone alerts, 7-day history, email support"),
        ("Growth",  "Popular","149",  "1,490", "Up to 8",
         "All Starter + auto discovery, heatmaps, 30-day history, chat support, multi-store (2)"),
        ("Pro",     "Best",   "299",  "2,990", "Up to 16",
         "All Growth + 90-day history, API, unlimited stores, priority support, white-label"),
    ]
    story += plan_table("Malaysia", MY_COLOR, "MYR", my_plans,
                        note="SST applicable as per Malaysian tax law. Annual plan = 10 months price.")
    story.append(Spacer(1, 0.4*cm))

    # ─ Singapore ─
    story.append(section_title("  SINGAPORE PRICING  (SGD — Singapore Dollar)", SG_COLOR))
    story.append(Spacer(1, 0.2*cm))
    sg_plans = [
        ("Starter", "",      "29",  "290",  "Up to 4",
         "AI monitoring, zone alerts, 7-day history, email support"),
        ("Growth",  "Popular","59", "590",  "Up to 8",
         "All Starter + auto discovery, heatmaps, 30-day history, chat support, multi-store (2)"),
        ("Pro",     "Best",  "99",  "990",  "Up to 16",
         "All Growth + 90-day history, API, unlimited stores, priority support, white-label"),
    ]
    story += plan_table("Singapore", SG_COLOR, "SGD", sg_plans,
                        note="GST applicable as per Singapore tax law. Annual plan = 10 months price.")

    story.append(Spacer(1, 0.5*cm))
    story.append(hr(ACCENT_BLUE, 1))
    story.append(Spacer(1, 0.3*cm))

    # Feature comparison
    story.append(section_title("  PLAN FEATURES AT A GLANCE", DARK_NAVY))
    story.append(Spacer(1, 0.2*cm))
    story.append(comparison_table())
    story.append(Spacer(1, 0.4*cm))

    # Add-ons
    story.append(section_title("  ADD-ONS & UPGRADES", ACCENT_BLUE))
    story.append(Spacer(1, 0.2*cm))
    story.append(addons_table())
    story.append(Spacer(1, 0.4*cm))

    # ROI
    story.append(roi_box())
    story.append(Spacer(1, 0.4*cm))

    # Dealer margin reminder
    margin_data = [[
        Paragraph("<b>Dealer / Partner Margin</b>",
                  S("DM", fontSize=9, fontName="Helvetica-Bold", textColor=DARK_NAVY)),
        Paragraph("Authorised Dealer (installing): <b>15% of subscription</b>  |  "
                  "Referral Partner (non-installing): <b>10% of subscription</b>  |  "
                  "Paid monthly, 30 days after customer payment clears.",
                  S("DV", fontSize=8.5, fontName="Helvetica", textColor=TEXT_DARK, leading=13)),
    ]]
    mt = Table(margin_data, colWidths=[4.5*cm, 12.5*cm])
    mt.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#E8F4FD")),
        ("BOX",           (0, 0), (-1, -1), 1, ACCENT_BLUE),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(mt)
    story.append(Spacer(1, 0.5*cm))

    # Terms
    story.append(Paragraph("Terms & Conditions",
                            S("TCH", fontSize=10, fontName="Helvetica-Bold",
                              textColor=DARK_NAVY, spaceBefore=4, spaceAfter=3)))
    terms = [
        "All prices are exclusive of applicable taxes (GST/SST) unless stated otherwise.",
        "Annual plans are billed upfront. Monthly plans are billed on the subscription renewal date.",
        "Subscriptions auto-renew unless cancelled 7 days before renewal date.",
        "14-day money-back guarantee for new customers (first subscription only).",
        "Hardware (cameras, NVR/DVR) is NOT included — customers use their existing cameras.",
        "Free onboarding support (1 session) included with Growth and Pro plans.",
        "Prices may be revised with 30 days advance notice to existing subscribers.",
        "Dealer pricing and margins are governed by the Dealer Agreement separately executed.",
    ]
    for t in terms:
        story.append(Paragraph(
            f"&#8226;&#160; {t}",
            S("TI", fontSize=8.5, fontName="Helvetica", textColor=TEXT_DARK,
              leading=13, leftIndent=10, spaceBefore=2)))

    story.append(Spacer(1, 0.5*cm))
    story.append(contact_footer())
    story.append(Spacer(1, 0.3*cm))
    story.append(HRFlowable(width="100%", thickness=0.3, color=MID_GRAY))
    story.append(Paragraph(
        f"Vantag Retail Intelligence Platform  |  Pricing Sheet v1.0  |  "
        f"Generated: {datetime.now().strftime('%d %B %Y')}  |  "
        "Subject to change without notice.",
        S("F", fontSize=7.5, fontName="Helvetica", textColor=TEXT_MUTED,
          alignment=TA_CENTER, spaceBefore=4)))

    return story


def build_pdf():
    doc = SimpleDocTemplate(
        OUTPUT_PATH, pagesize=A4,
        topMargin=1.5*cm, bottomMargin=1.5*cm,
        leftMargin=2.0*cm, rightMargin=2.0*cm,
        title="Vantag Pricing Sheet",
        author="Retail Nazar Technologies",
        subject="Vantag Platform — Pricing for India, Malaysia, Singapore",
    )
    doc.build(build_story())
    print(f"[OK] Saved: {OUTPUT_PATH}")


if __name__ == "__main__":
    build_pdf()
