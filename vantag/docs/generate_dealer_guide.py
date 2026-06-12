"""
Vantag Dealer Onboarding & Training Guide PDF
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY, TA_RIGHT
from datetime import datetime
import os

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "Vantag_Dealer_Onboarding_Guide.pdf")

NAVY  = colors.HexColor("#0D1B2A")
BLUE  = colors.HexColor("#1E90FF")
TEAL  = colors.HexColor("#00C9A7")
ORG   = colors.HexColor("#FF6B35")
GOLD  = colors.HexColor("#FFC107")
LGRAY = colors.HexColor("#F5F7FA")
MGRAY = colors.HexColor("#CCCCCC")
DGRAY = colors.HexColor("#444444")
WHITE = colors.white
GREEN = colors.HexColor("#28A745")
RED   = colors.HexColor("#DC3545")

def S(name, **kw):
    return ParagraphStyle(name, parent=getSampleStyleSheet()["Normal"], **kw)

def hr(c=MGRAY, w=0.5):
    return HRFlowable(width="100%", thickness=w, color=c, spaceAfter=5, spaceBefore=5)

def section_banner(text, color=NAVY, sub=""):
    rows = [[Paragraph(text, S("SBT", fontSize=14, fontName="Helvetica-Bold",
                                textColor=WHITE, alignment=TA_LEFT))]]
    if sub:
        rows.append([Paragraph(sub, S("SBS", fontSize=9, fontName="Helvetica",
                                       textColor=colors.HexColor("#AABBCC"),
                                       alignment=TA_LEFT))])
    t = Table(rows, colWidths=["100%"])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), color),
        ("TOPPADDING",    (0,0),(-1,-1), 8),
        ("BOTTOMPADDING", (0,0),(-1,-1), 8),
        ("LEFTPADDING",   (0,0),(-1,-1), 12),
        ("RIGHTPADDING",  (0,0),(-1,-1), 12),
    ]))
    return t

def num_bullet(num, text, sub=""):
    rows = [[
        Paragraph(f"<b>{num}</b>",
                  S("NB", fontSize=14, fontName="Helvetica-Bold", textColor=BLUE,
                    alignment=TA_CENTER)),
        Paragraph(f"<b>{text}</b>" + (f"<br/><font color='#888888' size='8.5'>{sub}</font>" if sub else ""),
                  S("NT", fontSize=10, fontName="Helvetica-Bold", textColor=DGRAY,
                    leading=14)),
    ]]
    t = Table(rows, colWidths=[1.0*cm, 15.5*cm])
    t.setStyle(TableStyle([
        ("VALIGN",       (0,0),(-1,-1), "MIDDLE"),
        ("LEFTPADDING",  (0,0),(-1,-1), 0),
        ("RIGHTPADDING", (0,0),(-1,-1), 0),
        ("TOPPADDING",   (0,0),(-1,-1), 3),
        ("BOTTOMPADDING",(0,0),(-1,-1), 3),
    ]))
    return t

def check(text, done=True):
    sym = "&#9745;" if done else "&#9744;"
    c   = GREEN if done else MGRAY
    return Paragraph(
        f"<font color='#{c.hexval()[2:]}'>{sym}</font>  {text}",
        S("CH", fontSize=9.5, fontName="Helvetica", textColor=DGRAY,
          leading=14, leftIndent=4, spaceBefore=2))

def tip_box(text, color=GOLD):
    data = [[Paragraph(f"<b>TIP:</b>  {text}",
                       S("TB", fontSize=9, fontName="Helvetica",
                         textColor=DGRAY, leading=13, alignment=TA_LEFT))]]
    t = Table(data, colWidths=["100%"])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), colors.HexColor("#FFF8E1")),
        ("BOX",           (0,0),(-1,-1), 1.2, color),
        ("TOPPADDING",    (0,0),(-1,-1), 6),
        ("BOTTOMPADDING", (0,0),(-1,-1), 6),
        ("LEFTPADDING",   (0,0),(-1,-1), 10),
        ("RIGHTPADDING",  (0,0),(-1,-1), 10),
    ]))
    return t

def warn_box(text):
    data = [[Paragraph(f"<b>IMPORTANT:</b>  {text}",
                       S("WB", fontSize=9, fontName="Helvetica",
                         textColor=DGRAY, leading=13))]]
    t = Table(data, colWidths=["100%"])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), colors.HexColor("#FFF3CD")),
        ("BOX",           (0,0),(-1,-1), 1.2, ORG),
        ("TOPPADDING",    (0,0),(-1,-1), 6),
        ("BOTTOMPADDING", (0,0),(-1,-1), 6),
        ("LEFTPADDING",   (0,0),(-1,-1), 10),
    ]))
    return t

def faq_table(items):
    rows = []
    for q, a in items:
        rows.append([
            Paragraph(f"<b>Q: {q}</b>", S("FQ", fontSize=9.5, fontName="Helvetica-Bold",
                                            textColor=NAVY)),
            Paragraph(f"A: {a}", S("FA", fontSize=9, fontName="Helvetica",
                                    textColor=DGRAY, leading=13)),
        ])
    t = Table(rows, colWidths=[6*cm, 11*cm])
    t.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0,0),(-1,-1), [WHITE, LGRAY]),
        ("GRID",           (0,0),(-1,-1), 0.3, MGRAY),
        ("TOPPADDING",     (0,0),(-1,-1), 6),
        ("BOTTOMPADDING",  (0,0),(-1,-1), 6),
        ("LEFTPADDING",    (0,0),(-1,-1), 8),
        ("RIGHTPADDING",   (0,0),(-1,-1), 8),
        ("VALIGN",         (0,0),(-1,-1), "TOP"),
    ]))
    return t

def objection_table(items):
    rows = [[
        Paragraph("Customer Objection", S("OH", fontSize=9, fontName="Helvetica-Bold",
                                           textColor=WHITE, alignment=TA_CENTER)),
        Paragraph("Your Response", S("OH", fontSize=9, fontName="Helvetica-Bold",
                                      textColor=WHITE, alignment=TA_CENTER)),
    ]]
    for obj, resp in items:
        rows.append([
            Paragraph(f"<i>\"{obj}\"</i>", S("OQ", fontSize=9, fontName="Helvetica",
                                               textColor=RED, leading=13)),
            Paragraph(resp, S("OR", fontSize=9, fontName="Helvetica",
                               textColor=DGRAY, leading=13)),
        ])
    t = Table(rows, colWidths=[7*cm, 10*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0),  NAVY),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [WHITE, LGRAY]),
        ("GRID",          (0,0),(-1,-1), 0.3, MGRAY),
        ("TOPPADDING",    (0,0),(-1,-1), 7),
        ("BOTTOMPADDING", (0,0),(-1,-1), 7),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
        ("VALIGN",        (0,0),(-1,-1), "TOP"),
    ]))
    return t

# ── Cover ──────────────────────────────────────────────────────────────────────
def cover():
    story = []
    data = [[
        Paragraph("VANTAG", S("CV", fontSize=34, fontName="Helvetica-Bold",
                               textColor=BLUE, alignment=TA_CENTER)),
    ],[
        Paragraph("Dealer Onboarding &amp; Training Guide",
                  S("CT", fontSize=16, fontName="Helvetica-Bold",
                    textColor=WHITE, alignment=TA_CENTER)),
    ],[
        Paragraph("Everything you need to sell, install, and support Vantag",
                  S("CS", fontSize=10, fontName="Helvetica",
                    textColor=colors.HexColor("#AABBCC"), alignment=TA_CENTER)),
    ],[
        Paragraph(f"Version 1.0  |  {datetime.now().strftime('%B %Y')}  |  Confidential — Authorised Dealers Only",
                  S("CD", fontSize=8.5, fontName="Helvetica",
                    textColor=colors.HexColor("#666677"), alignment=TA_CENTER)),
    ]]
    t = Table(data, colWidths=["100%"])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), NAVY),
        ("TOPPADDING",    (0,0),(-1,-1), 14),
        ("BOTTOMPADDING", (0,0),(-1,-1), 14),
        ("LEFTPADDING",   (0,0),(-1,-1), 20),
        ("RIGHTPADDING",  (0,0),(-1,-1), 20),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.5*cm))

    toc_items = [
        ("Part 1", "Welcome & Programme Overview", BLUE),
        ("Part 2", "What is Vantag — Product Knowledge", TEAL),
        ("Part 3", "How to Qualify & Approach Customers", ORG),
        ("Part 4", "Installation Step-by-Step", GOLD),
        ("Part 5", "Handling Objections & Closing Sales", GREEN),
        ("Part 6", "Commission, Payments & Reporting", NAVY),
        ("Part 7", "FAQ & Escalation Contacts", BLUE),
    ]
    rows = [[Paragraph(f"<b><font color='#{c.hexval()[2:]}'>{p}</font></b>",
                       S("TP", fontSize=10, fontName="Helvetica-Bold")),
             Paragraph(t, S("TT", fontSize=10, fontName="Helvetica", textColor=DGRAY))]
            for p, t, c in toc_items]

    toc = Table(rows, colWidths=[3*cm, 14*cm])
    toc.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0,0),(-1,-1), [WHITE, LGRAY]),
        ("TOPPADDING",     (0,0),(-1,-1), 6),
        ("BOTTOMPADDING",  (0,0),(-1,-1), 6),
        ("LEFTPADDING",    (0,0),(-1,-1), 10),
        ("BOX",            (0,0),(-1,-1), 1, BLUE),
    ]))
    story.append(Paragraph("Table of Contents",
                            S("TOC", fontSize=12, fontName="Helvetica-Bold",
                              textColor=NAVY, spaceBefore=6, spaceAfter=6)))
    story.append(toc)
    return story


def part1():
    story = [PageBreak()]
    story.append(section_banner("PART 1 — WELCOME TO THE VANTAG DEALER PROGRAMME", NAVY,
                                 "Your guide to building a successful reseller business"))
    story.append(Spacer(1, 0.4*cm))
    story.append(Paragraph(
        "Welcome to the Vantag Authorised Dealer Programme. As a Vantag dealer, "
        "you are joining a growing network of professionals helping retail businesses "
        "across India, Malaysia, and Singapore protect their stores and grow their profits "
        "with AI-powered security — at a price that every shop owner can afford.",
        S("B", fontSize=9.5, fontName="Helvetica", textColor=DGRAY, leading=15,
          alignment=TA_JUSTIFY, spaceAfter=6)))

    story.append(Paragraph("Your Earning Potential",
                            S("H2", fontSize=11, fontName="Helvetica-Bold",
                              textColor=NAVY, spaceBefore=8, spaceAfter=4)))
    earn = [
        ["Customers\nOnboarded", "Average Plan\n(INR Growth)", "Monthly\nCommission", "Annual\nIncome"],
        ["5 customers",  "INR 2,499/mo", "INR 1,875",   "INR 22,500"],
        ["10 customers", "INR 2,499/mo", "INR 3,750",   "INR 45,000"],
        ["20 customers", "INR 2,499/mo", "INR 7,500",   "INR 90,000"],
        ["50 customers", "INR 2,499/mo", "INR 18,750",  "INR 2,25,000"],
    ]
    rows = [[Paragraph(c, S("EH", fontSize=9, fontName="Helvetica-Bold",
                             textColor=WHITE if i == 0 else DGRAY, alignment=TA_CENTER))
             for c in row]
            for i, row in enumerate(earn)]
    et = Table(rows, colWidths=[4.25*cm]*4)
    et.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0),  BLUE),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [WHITE, LGRAY]),
        ("GRID",          (0,0),(-1,-1), 0.3, MGRAY),
        ("TOPPADDING",    (0,0),(-1,-1), 6),
        ("BOTTOMPADDING", (0,0),(-1,-1), 6),
        ("ALIGN",         (0,0),(-1,-1), "CENTER"),
    ]))
    story.append(et)
    story.append(Spacer(1, 0.3*cm))
    story.append(tip_box("Commission is RECURRING — every month the customer pays, you earn. "
                          "A single customer earning INR 375/month for 3 years = INR 13,500 from one sale."))
    story.append(Spacer(1, 0.3*cm))

    story.append(Paragraph("What the Programme Provides You",
                            S("H2", fontSize=11, fontName="Helvetica-Bold",
                              textColor=NAVY, spaceBefore=4, spaceAfter=4)))
    provides = [
        "Authorised Dealer Certificate (physical + digital)",
        "Demo account with full platform access for demonstrations",
        "This Dealer Training Guide (PDF)",
        "Pricing Sheet (customisable with your contact details)",
        "Pitch Deck for customer presentations",
        "Dedicated support contact at Vantag for escalations",
        "Commission tracking via dealer portal (in development)",
        "Marketing materials: banners, brochures, social media assets",
    ]
    for p in provides:
        story.append(check(p))
    return story


def part2():
    story = [PageBreak()]
    story.append(section_banner("PART 2 — PRODUCT KNOWLEDGE", TEAL,
                                 "Know the product inside out before selling it"))
    story.append(Spacer(1, 0.3*cm))

    story.append(Paragraph("The Vantag Platform — In Simple Terms",
                            S("H2", fontSize=11, fontName="Helvetica-Bold", textColor=NAVY,
                              spaceAfter=4)))
    story.append(Paragraph(
        "Vantag is a software subscription that adds AI intelligence to existing CCTV cameras. "
        "It consists of two parts: (1) a small <b>Edge Agent</b> — a Windows app installed on any PC "
        "at the store — and (2) a <b>cloud dashboard</b> the owner accesses from any browser or phone. "
        "The AI runs on the store's own PC, so there are no expensive cloud AI bills.",
        S("B", fontSize=9.5, fontName="Helvetica", textColor=DGRAY, leading=15,
          alignment=TA_JUSTIFY, spaceAfter=6)))

    features = [
        ("AI Shelf Monitoring",
         "The camera watches the shelf 24/7. When a product is picked up, removed, "
         "or unusual activity is detected, an alert fires within seconds.",
         "Pharmacies, electronics shops, cosmetics stores, supermarkets"),
        ("Auto Camera Discovery",
         "When the Edge Agent is installed, it scans the store's Wi-Fi/LAN and finds "
         "all connected cameras automatically. The owner never needs to know an IP address or RTSP path.",
         "All store types — especially non-technical owners"),
        ("Zone Intelligence",
         "The owner draws a box on the camera view (e.g., 'Cash Counter', 'Entrance', 'Stockroom Door'). "
         "Any person entering or object moving in that zone triggers an alert.",
         "Convenience stores, banks, pharmacies, jewellery shops"),
        ("Footfall Analytics",
         "Counts how many people enter the store per hour, per day, per week. "
         "Shows peak times so staff can be allocated efficiently.",
         "Malls, food courts, franchise chains"),
        ("30-Day Incident History",
         "All incidents are stored with a thumbnail snapshot for 30 days (Growth/Pro). "
         "Useful for insurance claims, police reports, staff disputes.",
         "All store types"),
        ("Multi-Language Dashboard",
         "Available in English, Hindi, Tamil, Telugu, Kannada, Malayalam, Marathi, Gujarati, Bengali, Punjabi, Malay.",
         "India multi-state dealers, Malaysian dealers"),
    ]

    for fname, fdesc, fwho in features:
        data = [[
            Paragraph(f"<b>{fname}</b>",
                      S("FN", fontSize=10, fontName="Helvetica-Bold", textColor=BLUE)),
            Paragraph(f"<b>Best for:</b> {fwho}",
                      S("FW", fontSize=8.5, fontName="Helvetica", textColor=TEAL,
                        alignment=TA_RIGHT)),
        ],[
            Paragraph(fdesc, S("FD", fontSize=9, fontName="Helvetica", textColor=DGRAY,
                                leading=13)),
            Paragraph("", S("_")),
        ]]
        ft = Table(data, colWidths=[11*cm, 6*cm])
        ft.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), LGRAY),
            ("BOX",           (0,0),(-1,-1), 0.5, BLUE),
            ("TOPPADDING",    (0,0),(-1,-1), 6),
            ("BOTTOMPADDING", (0,0),(-1,-1), 6),
            ("LEFTPADDING",   (0,0),(-1,-1), 8),
            ("RIGHTPADDING",  (0,0),(-1,-1), 8),
            ("SPAN",          (0,1),(1,1)),
        ]))
        story.append(ft)
        story.append(Spacer(1, 0.2*cm))

    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph("Supported Camera Brands",
                            S("H2", fontSize=11, fontName="Helvetica-Bold", textColor=NAVY,
                              spaceAfter=4)))
    brands = ["Hikvision", "Dahua", "CP Plus", "TP-Link (Tapo)", "Reolink",
              "Uniview", "Axis (ONVIF)", "Any RTSP/ONVIF camera"]
    brand_data = [[Paragraph(b, S("BR", fontSize=9.5, fontName="Helvetica",
                                   textColor=DGRAY, alignment=TA_CENTER))
                   for b in brands]]
    bt = Table(brand_data, colWidths=[2.125*cm]*8)
    bt.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0,0),(-1,-1), [LGRAY]),
        ("GRID",           (0,0),(-1,-1), 0.3, MGRAY),
        ("TOPPADDING",     (0,0),(-1,-1), 6),
        ("BOTTOMPADDING",  (0,0),(-1,-1), 6),
        ("ALIGN",          (0,0),(-1,-1), "CENTER"),
    ]))
    story.append(bt)
    return story


def part3():
    story = [PageBreak()]
    story.append(section_banner("PART 3 — QUALIFYING & APPROACHING CUSTOMERS", ORG,
                                 "Who to target and what to say"))
    story.append(Spacer(1, 0.3*cm))

    story.append(Paragraph("Ideal Customer Profile",
                            S("H2", fontSize=11, fontName="Helvetica-Bold", textColor=NAVY, spaceAfter=4)))
    profiles = [
        ("HIGH PRIORITY", BLUE, [
            "Pharmacies & medical stores (1–10 staff)",
            "Electronics & mobile phone shops",
            "Jewellery & watch stores",
            "Cosmetics & beauty stores",
            "Supermarkets & grocery chains",
            "Convenience stores / mini-marts",
        ]),
        ("MEDIUM PRIORITY", TEAL, [
            "Clothing & garment stores",
            "Restaurants with multiple entry/exit points",
            "Hostels, PGs, service apartments",
            "Small offices & co-working spaces",
            "Post offices, government counters",
        ]),
        ("EXPANSION TARGETS", ORG, [
            "Franchise chains (multi-store discount)",
            "Shopping malls (multi-camera, Pro plan)",
            "Hospitals & clinics (security + compliance)",
            "School canteens & bookshops",
            "Petrol stations & convenience forecourts",
        ]),
    ]
    prows = []
    for tier, col, items in profiles:
        prows.append([
            Paragraph(f"<b>{tier}</b>",
                      S("PT", fontSize=10, fontName="Helvetica-Bold", textColor=col,
                        alignment=TA_CENTER)),
            Paragraph("<br/>".join([f"&#9654; {i}" for i in items]),
                      S("PI", fontSize=9, fontName="Helvetica", textColor=DGRAY, leading=14)),
        ])
    pt = Table(prows, colWidths=[3.5*cm, 13.5*cm])
    pt.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0,0),(-1,-1), [WHITE, LGRAY]),
        ("GRID",           (0,0),(-1,-1), 0.3, MGRAY),
        ("TOPPADDING",     (0,0),(-1,-1), 8),
        ("BOTTOMPADDING",  (0,0),(-1,-1), 8),
        ("LEFTPADDING",    (0,0),(-1,-1), 8),
        ("VALIGN",         (0,0),(-1,-1), "TOP"),
    ]))
    story.append(pt)
    story.append(Spacer(1, 0.3*cm))

    story.append(Paragraph("The 3-Minute Opening Script",
                            S("H2", fontSize=11, fontName="Helvetica-Bold", textColor=NAVY, spaceAfter=4)))
    script_data = [[Paragraph(
        "<i>\"Hi, my name is [Your Name]. I help shop owners like yourself use AI to stop theft "
        "and protect your inventory — using the cameras you already have installed.<br/><br/>"
        "Most CCTV systems just record. Nobody watches them until after something goes missing. "
        "Vantag makes your existing cameras smart — it alerts you the moment something unusual happens, "
        "right on your phone.<br/><br/>"
        "The cost is less than INR 100 per day. And most shop owners recover that cost from prevented "
        "theft in the first week. Can I show you a 3-minute demo?\"</i>",
        S("SC", fontSize=9.5, fontName="Helvetica", textColor=DGRAY,
          leading=16, alignment=TA_LEFT))]]
    st = Table(script_data, colWidths=["100%"])
    st.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), colors.HexColor("#E8F4FD")),
        ("BOX",           (0,0),(-1,-1), 1.5, BLUE),
        ("TOPPADDING",    (0,0),(-1,-1), 10),
        ("BOTTOMPADDING", (0,0),(-1,-1), 10),
        ("LEFTPADDING",   (0,0),(-1,-1), 14),
        ("RIGHTPADDING",  (0,0),(-1,-1), 14),
    ]))
    story.append(st)
    story.append(Spacer(1, 0.3*cm))

    story.append(Paragraph("Handling Objections",
                            S("H2", fontSize=11, fontName="Helvetica-Bold", textColor=NAVY, spaceAfter=4)))
    objections = [
        ("I already have CCTV",
         "Exactly! Vantag works with your existing cameras. You don't replace anything. "
         "We just make your current cameras intelligent. It's like upgrading from a basic phone to a smartphone — "
         "same hardware, 10x smarter."),
        ("It's too expensive",
         "The Starter plan is INR 999/month — that's INR 33/day, less than a chai and snack. "
         "Most shops recover this cost from just 3–4 prevented thefts in the first month."),
        ("I need to think about it",
         "Absolutely. In the meantime, we offer a 14-day money-back guarantee, so you risk nothing. "
         "Why not start today and cancel if it doesn't work? Most customers never cancel."),
        ("I'm not technical",
         "You don't need to be. Installation takes 30 minutes and we handle it for you. "
         "After that, you just see alerts on your phone — no technical knowledge needed."),
        ("I'll wait for someone else to try first",
         "Several shops in [city/area] are already using it. Would you like me to connect you "
         "with one of them so you can hear directly from them?"),
        ("My internet is slow / unreliable",
         "The AI processing happens on your own store PC — not the internet. "
         "You only need basic internet for the dashboard and alerts. "
         "Even a 4G dongle is sufficient."),
    ]
    story.append(objection_table(objections))
    return story


def part4():
    story = [PageBreak()]
    story.append(section_banner("PART 4 — INSTALLATION GUIDE", GOLD,
                                 "Step-by-step: from unboxing to live AI in 30 minutes"))
    story.append(Spacer(1, 0.3*cm))

    story.append(Paragraph("What You Need Before You Start",
                            S("H2", fontSize=11, fontName="Helvetica-Bold", textColor=NAVY, spaceAfter=4)))
    prereqs = [
        "A Windows PC or laptop at the store (Windows 10/11, any age)",
        "The store's Wi-Fi password or LAN access",
        "Cameras connected to the same network (CCTV, NVR, or IP cameras)",
        "The customer's Vantag account login (from their registration email)",
        "Your phone/laptop to access the Vantag web dashboard",
    ]
    for p in prereqs:
        story.append(check(p, done=False))
    story.append(Spacer(1, 0.3*cm))

    steps = [
        ("Register the Customer", [
            "Go to retail-vantag.com (or retailnazar.com for India)",
            "Click 'Register' — fill in store name, email, country, language",
            "Select a plan (recommend Growth for most stores)",
            "Complete payment via Razorpay / credit card",
            "Customer receives login credentials via email",
        ]),
        ("Download & Install the Edge Agent", [
            "Log in to the dashboard at retail-vantag.com/dashboard",
            "Go to Settings → Download Agent → Click 'Windows'",
            "Run the installer on the store's PC",
            "Enter the API Key shown in the dashboard when prompted",
            "Click 'Start Monitoring' in the system tray",
        ]),
        ("Auto-Discover Cameras", [
            "In the dashboard, go to Cameras → Click 'Auto-Scan'",
            "Wait 30–60 seconds — cameras appear automatically",
            "If cameras don't appear, check they are on the same Wi-Fi/LAN as the PC",
            "For each camera: click 'Confirm & Add', give it a name (e.g. 'Entrance Cam')",
            "Test the camera feed — you should see live video within 5 seconds",
        ]),
        ("Configure Zones", [
            "Go to Zones → Click 'Add Zone' on any camera",
            "Drag a rectangle over the area to monitor (shelf, entrance, counter)",
            "Name the zone clearly: e.g. 'Shelf A - Medicines', 'Main Entrance'",
            "Select alert type: Movement, Intrusion, Product Removal",
            "Save the zone — monitoring starts immediately",
        ]),
        ("Test & Hand Over", [
            "Ask the customer to physically walk through the zone / move a product",
            "Confirm the incident appears in the dashboard and on their phone",
            "Show the customer how to view incidents, filter by date/type",
            "Give them the support email: support@retail-vantag.com",
            "Collect their signature on the Dealer Agreement copy",
        ]),
    ]
    for i, (title, substeps) in enumerate(steps):
        story.append(num_bullet(str(i+1), title))
        for s in substeps:
            story.append(Paragraph(f"&#160;&#160;&#160;&#9702;  {s}",
                                    S("IS", fontSize=9, fontName="Helvetica", textColor=DGRAY,
                                      leading=14, leftIndent=16, spaceBefore=1)))
        story.append(Spacer(1, 0.15*cm))

    story.append(Spacer(1, 0.1*cm))
    story.append(warn_box(
        "If the camera is behind a separate NVR network (not the store's main LAN), "
        "you may need to connect the store PC to the NVR's VLAN. Ask the customer for the NVR manual "
        "or call Vantag support for remote assistance."))
    story.append(Spacer(1, 0.3*cm))

    story.append(Paragraph("Common Issues & Quick Fixes",
                            S("H2", fontSize=11, fontName="Helvetica-Bold", textColor=NAVY, spaceAfter=4)))
    issues = [
        ("Camera not found after Auto-Scan",
         "Ensure camera and PC are on same Wi-Fi/LAN. Try turning camera off and on. "
         "Use 'Manual Add' in the dashboard if camera brand is known."),
        ("Video feed shows but is very slow",
         "Change the camera stream to Sub-stream (lower resolution) in the camera settings. "
         "Vantag works fine on sub-stream — saves bandwidth and reduces latency."),
        ("Agent not connecting to dashboard",
         "Check the API Key is entered correctly. Check PC internet connection. "
         "Restart the Vantag Agent from the system tray."),
        ("Alerts not reaching phone",
         "Ensure the customer has installed the Vantag mobile app and enabled push notifications. "
         "Check notification settings in the Vantag dashboard under Alerts."),
    ]
    story.append(faq_table(issues))
    return story


def part5_6_7():
    story = [PageBreak()]
    story.append(section_banner("PART 5 — COMMISSION & PAYMENTS", GREEN,
                                 "How you earn, how it's tracked, how it's paid"))
    story.append(Spacer(1, 0.3*cm))

    comm = [
        ["Item", "Detail"],
        ["Commission Rate (Installing Dealer)", "15% of net subscription"],
        ["Commission Rate (Referral Partner, non-installing)", "10% of net subscription"],
        ["Payment Frequency", "Monthly, within 30 days of customer payment clearing"],
        ["Minimum Payout Threshold", "INR 500 / MYR 20 / SGD 10"],
        ["Payment Method", "Bank transfer to dealer's registered account"],
        ["Chargeback / Refund", "Commission forfeited if customer refunded within 30 days"],
        ["Annual Plan Commission", "Full 15% on annual amount received (paid as lump sum)"],
        ["Tracking", "Dealer portal (in development) — monthly statement via email until live"],
    ]
    rows = [[Paragraph(c, S("CL", fontSize=9, fontName="Helvetica-Bold" if i == 0 else "Helvetica",
                             textColor=WHITE if i == 0 else DGRAY,
                             alignment=TA_LEFT))
             for c in row]
            for i, row in enumerate(comm)]
    ct = Table(rows, colWidths=[7*cm, 10*cm])
    ct.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0),  GREEN),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [WHITE, LGRAY]),
        ("GRID",          (0,0),(-1,-1), 0.3, MGRAY),
        ("TOPPADDING",    (0,0),(-1,-1), 6),
        ("BOTTOMPADDING", (0,0),(-1,-1), 6),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
    ]))
    story.append(ct)
    story.append(Spacer(1, 0.3*cm))
    story.append(tip_box("Always use the same email when introducing a customer — "
                          "this is how we track your commissions. "
                          "Send customer name + email + phone to support@retail-vantag.com "
                          "with subject 'New Customer — [Dealer Name]' before or immediately after sign-up."))

    story.append(PageBreak())
    story.append(section_banner("PART 6 — FAQ FOR DEALERS", BLUE,
                                 "Answers to the most common dealer questions"))
    story.append(Spacer(1, 0.3*cm))
    faqs = [
        ("Do I need technical knowledge to install?",
         "Basic familiarity with Windows and Wi-Fi is enough. You don't need to be a CCTV technician. "
         "Full support is available from Vantag for the first 3 installations."),
        ("Can I offer a free trial to customers?",
         "Yes — use your demo account to show a live demonstration. "
         "The 14-day money-back guarantee effectively acts as a trial for new customers."),
        ("What if the customer's cameras are old?",
         "As long as the camera supports RTSP (most IP cameras from 2015 onwards do), Vantag works. "
         "If the camera is very old (analog, no IP), a hybrid DVR with RTSP output is needed."),
        ("Can I resell across regions (e.g. India + Malaysia)?",
         "Your agreement covers a specific region. To sell in multiple regions, "
         "request a multi-region addendum from support@retail-vantag.com."),
        ("What if a customer wants to cancel?",
         "Direct them to support@retail-vantag.com. Cancellations processed within 24 hours. "
         "Pro-rated refunds as per the T&C. Your commission is retained for months already paid."),
        ("Can I set my own installation fee?",
         "Yes — your installation or onboarding fee to the customer is entirely your own charge "
         "and separate from the Vantag subscription. Many dealers charge INR 500–2,000 for installation."),
        ("How do I escalate a technical issue I can't solve?",
         "Email support@retail-vantag.com with subject 'DEALER ESCALATION — [Customer Name] — [Issue]'. "
         "Include the customer's registered email and a description. Response within 4 hours."),
    ]
    story.append(faq_table(faqs))

    story.append(Spacer(1, 0.4*cm))
    story.append(section_banner("PART 7 — CONTACTS & SUPPORT", NAVY,
                                 "Reach the right person, every time"))
    story.append(Spacer(1, 0.3*cm))
    contacts = [
        ("General Support & Escalations", "support@retail-vantag.com", "Within 4 hours (business days)"),
        ("Dealer Commission Queries", "support@retail-vantag.com\nSubject: Commission Query", "Within 2 business days"),
        ("New Customer Registration", "support@retail-vantag.com\nSubject: New Customer — [Dealer Name]", "Same day"),
        ("Technical Installation Help", "support@retail-vantag.com\nSubject: DEALER ESCALATION", "Within 4 hours"),
        ("Dealer Agreement & Legal", "support@retail-vantag.com\nSubject: Agreement Query", "Within 3 business days"),
    ]
    crows = [[Paragraph("<b>Contact Type</b>", S("_", fontSize=9, fontName="Helvetica-Bold",
                                                   textColor=WHITE)),
              Paragraph("<b>Contact</b>", S("_", fontSize=9, fontName="Helvetica-Bold",
                                             textColor=WHITE)),
              Paragraph("<b>Response Time</b>", S("_", fontSize=9, fontName="Helvetica-Bold",
                                                    textColor=WHITE))]]
    for ctype, email, resp in contacts:
        crows.append([
            Paragraph(ctype, S("CT", fontSize=9, fontName="Helvetica", textColor=DGRAY)),
            Paragraph(email, S("CE", fontSize=9, fontName="Helvetica", textColor=BLUE)),
            Paragraph(resp,  S("CR", fontSize=9, fontName="Helvetica", textColor=DGRAY)),
        ])
    ctable = Table(crows, colWidths=[5.5*cm, 7.0*cm, 4.5*cm])
    ctable.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0),  NAVY),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [WHITE, LGRAY]),
        ("GRID",          (0,0),(-1,-1), 0.3, MGRAY),
        ("TOPPADDING",    (0,0),(-1,-1), 6),
        ("BOTTOMPADDING", (0,0),(-1,-1), 6),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
        ("VALIGN",        (0,0),(-1,-1), "TOP"),
    ]))
    story.append(ctable)
    story.append(Spacer(1, 0.4*cm))
    story.append(hr(BLUE, 1))
    story.append(Paragraph(
        f"Vantag Dealer Onboarding Guide v1.0  |  {datetime.now().strftime('%B %Y')}  |  "
        "Confidential — Authorised Dealers Only  |  support@retail-vantag.com",
        S("FT", fontSize=7.5, fontName="Helvetica",
          textColor=MGRAY, alignment=TA_CENTER, spaceBefore=4)))
    return story


def build_pdf():
    doc = SimpleDocTemplate(
        OUTPUT_PATH, pagesize=A4,
        topMargin=1.8*cm, bottomMargin=1.8*cm,
        leftMargin=2.2*cm, rightMargin=2.2*cm,
        title="Vantag Dealer Onboarding Guide",
        author="Retail Nazar Technologies",
    )
    story = cover() + part1() + part2() + part3() + part4() + part5_6_7()
    doc.build(story)
    print(f"[OK] Saved: {OUTPUT_PATH}")


if __name__ == "__main__":
    build_pdf()
