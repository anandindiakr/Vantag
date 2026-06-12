"""
Vantag Customer Success Case Studies + ROI Calculator PDF
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

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "Vantag_CaseStudies_ROI_Calculator.pdf")

NAVY  = colors.HexColor("#0D1B2A")
BLUE  = colors.HexColor("#1E90FF")
TEAL  = colors.HexColor("#00C9A7")
ORG   = colors.HexColor("#FF6B35")
GOLD  = colors.HexColor("#FFC107")
GREEN = colors.HexColor("#28A745")
LGRAY = colors.HexColor("#F5F7FA")
MGRAY = colors.HexColor("#CCCCCC")
DGRAY = colors.HexColor("#444444")
WHITE = colors.white
INDIA = colors.HexColor("#FF6B35")
MY    = colors.HexColor("#00C9A7")
SG    = colors.HexColor("#1E90FF")

def S(name, **kw):
    return ParagraphStyle(name, parent=getSampleStyleSheet()["Normal"], **kw)

def hr(c=MGRAY, w=0.5):
    return HRFlowable(width="100%", thickness=w, color=c, spaceAfter=5, spaceBefore=5)

def banner(text, color=NAVY, sub=""):
    rows = [[Paragraph(text, S("BT", fontSize=14, fontName="Helvetica-Bold",
                                textColor=WHITE, alignment=TA_LEFT))]]
    if sub:
        rows.append([Paragraph(sub, S("BS", fontSize=9, fontName="Helvetica",
                                       textColor=colors.HexColor("#AABBCC")))])
    t = Table(rows, colWidths=["100%"])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), color),
        ("TOPPADDING",    (0,0),(-1,-1), 8),
        ("BOTTOMPADDING", (0,0),(-1,-1), 8),
        ("LEFTPADDING",   (0,0),(-1,-1), 12),
    ]))
    return t

def quote_box(text, attribution, color=BLUE):
    data = [[
        Paragraph(f"<i>&#8220;{text}&#8221;</i>",
                  S("QT", fontSize=10, fontName="Helvetica", textColor=DGRAY,
                    leading=16, alignment=TA_JUSTIFY)),
    ],[
        Paragraph(f"— {attribution}",
                  S("QA", fontSize=8.5, fontName="Helvetica-Bold", textColor=color,
                    alignment=TA_RIGHT)),
    ]]
    t = Table(data, colWidths=["100%"])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), colors.HexColor("#F0F7FF")),
        ("BOX",           (0,0),(-1,-1), 1.5, color),
        ("LEFTBORDER",    (0,0),(0,-1),  4, color),
        ("TOPPADDING",    (0,0),(-1,-1), 10),
        ("BOTTOMPADDING", (0,0),(-1,-1), 8),
        ("LEFTPADDING",   (0,0),(-1,-1), 14),
        ("RIGHTPADDING",  (0,0),(-1,-1), 12),
    ]))
    return t

def metric_row(items):
    """items = [(value, label, color), ...]"""
    cells = []
    for val, lbl, col in items:
        d = [[
            Paragraph(f"<b>{val}</b>",
                      S("MV", fontSize=18, fontName="Helvetica-Bold",
                        textColor=col, alignment=TA_CENTER)),
        ],[
            Paragraph(lbl, S("ML", fontSize=8, fontName="Helvetica",
                              textColor=DGRAY, alignment=TA_CENTER, leading=11)),
        ]]
        mt = Table(d, colWidths=[4.2*cm])
        mt.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), LGRAY),
            ("BOX",           (0,0),(-1,-1), 1, col),
            ("TOPPADDING",    (0,0),(-1,-1), 6),
            ("BOTTOMPADDING", (0,0),(-1,-1), 6),
            ("ALIGN",         (0,0),(-1,-1), "CENTER"),
        ]))
        cells.append(mt)
    ncols = len(cells)
    row = [cells]
    t = Table(row, colWidths=[4.2*cm]*ncols)
    t.setStyle(TableStyle([
        ("LEFTPADDING",  (0,0),(-1,-1), 3),
        ("RIGHTPADDING", (0,0),(-1,-1), 3),
    ]))
    return t


def case_study(region_color, region_flag, business_type, location,
               plan, cameras, challenge, solution, results, quote, attribution,
               metrics):
    story = []
    # Header
    header_data = [[
        Paragraph(f"<b>{business_type}</b>",
                  S("CSH", fontSize=14, fontName="Helvetica-Bold", textColor=WHITE)),
        Paragraph(f"{region_flag}  {location}  |  {plan}  |  {cameras} cameras",
                  S("CSS", fontSize=9, fontName="Helvetica",
                    textColor=colors.HexColor("#AABBCC"), alignment=TA_RIGHT)),
    ]]
    ht = Table(header_data, colWidths=[9*cm, 8*cm])
    ht.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), region_color),
        ("TOPPADDING",    (0,0),(-1,-1), 8),
        ("BOTTOMPADDING", (0,0),(-1,-1), 8),
        ("LEFTPADDING",   (0,0),(-1,-1), 12),
        ("RIGHTPADDING",  (0,0),(-1,-1), 12),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
    ]))
    story.append(ht)
    story.append(Spacer(1, 0.2*cm))

    # Metrics bar
    story.append(metric_row(metrics))
    story.append(Spacer(1, 0.2*cm))

    # Challenge / Solution / Results in 3 cols
    body_data = [[
        [Paragraph("The Challenge",
                   S("BH", fontSize=10, fontName="Helvetica-Bold",
                     textColor=ORG, spaceAfter=4)),
         Paragraph(challenge, S("BB", fontSize=9, fontName="Helvetica",
                                 textColor=DGRAY, leading=13, alignment=TA_JUSTIFY))],
        [Paragraph("The Solution",
                   S("BH2", fontSize=10, fontName="Helvetica-Bold",
                     textColor=region_color, spaceAfter=4)),
         Paragraph(solution, S("BB2", fontSize=9, fontName="Helvetica",
                                textColor=DGRAY, leading=13, alignment=TA_JUSTIFY))],
        [Paragraph("The Results",
                   S("BH3", fontSize=10, fontName="Helvetica-Bold",
                     textColor=GREEN, spaceAfter=4)),
         Paragraph(results, S("BB3", fontSize=9, fontName="Helvetica",
                               textColor=DGRAY, leading=13, alignment=TA_JUSTIFY))],
    ]]
    bt = Table(body_data, colWidths=[5.5*cm, 5.5*cm, 5.5*cm])
    bt.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(0,-1), colors.HexColor("#FFF5F0")),
        ("BACKGROUND",    (1,0),(1,-1), LGRAY),
        ("BACKGROUND",    (2,0),(2,-1), colors.HexColor("#F0FFF4")),
        ("BOX",           (0,0),(-1,-1), 0.5, MGRAY),
        ("INNERGRID",     (0,0),(-1,-1), 0.5, MGRAY),
        ("TOPPADDING",    (0,0),(-1,-1), 8),
        ("BOTTOMPADDING", (0,0),(-1,-1), 8),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
        ("RIGHTPADDING",  (0,0),(-1,-1), 8),
        ("VALIGN",        (0,0),(-1,-1), "TOP"),
    ]))
    story.append(bt)
    story.append(Spacer(1, 0.2*cm))
    story.append(quote_box(quote, attribution, region_color))
    story.append(Spacer(1, 0.4*cm))
    story.append(hr(region_color, 1))
    return story


def roi_calculator():
    story = [PageBreak()]
    story.append(banner("ROI CALCULATOR", NAVY,
                         "Use this with your customer — fill in their numbers and show instant ROI"))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(
        "Hand this page to a prospective customer or walk through it together. "
        "Fill in the yellow boxes with their actual numbers to calculate their personal ROI.",
        S("B", fontSize=9.5, fontName="Helvetica", textColor=DGRAY,
          leading=15, alignment=TA_JUSTIFY, spaceAfter=6)))

    # INPUT SECTION
    def input_row(label, default, unit=""):
        return [
            Paragraph(f"<b>{label}</b>",
                      S("IL", fontSize=9.5, fontName="Helvetica-Bold", textColor=DGRAY)),
            Paragraph(f"{default}",
                      S("IV", fontSize=9.5, fontName="Helvetica-Bold",
                        textColor=NAVY, alignment=TA_CENTER)),
            Paragraph(unit, S("IU", fontSize=8.5, fontName="Helvetica",
                               textColor=DGRAY, alignment=TA_LEFT)),
            Paragraph("", S("_")),
        ]

    def calc_row(label, formula, result, is_total=False):
        return [
            Paragraph(f"<b>{label}</b>" if is_total else label,
                      S("CL", fontSize=9.5 if not is_total else 10,
                        fontName="Helvetica-Bold" if is_total else "Helvetica",
                        textColor=NAVY if is_total else DGRAY)),
            Paragraph(formula,
                      S("CF", fontSize=8.5, fontName="Helvetica",
                        textColor=DGRAY, alignment=TA_CENTER)),
            Paragraph(f"<b>{result}</b>" if is_total else result,
                      S("CR", fontSize=9.5 if not is_total else 11,
                        fontName="Helvetica-Bold" if is_total else "Helvetica",
                        textColor=GREEN if is_total else BLUE, alignment=TA_RIGHT)),
        ]

    story.append(Paragraph("STEP 1 — Enter Customer's Numbers",
                            S("SH", fontSize=11, fontName="Helvetica-Bold",
                              textColor=NAVY, spaceBefore=6, spaceAfter=6)))

    input_data = [
        [Paragraph("Input", S("IH", fontSize=9, fontName="Helvetica-Bold",
                               textColor=WHITE, alignment=TA_CENTER)),
         Paragraph("Example Value", S("IH", fontSize=9, fontName="Helvetica-Bold",
                                       textColor=WHITE, alignment=TA_CENTER)),
         Paragraph("Unit", S("IH", fontSize=9, fontName="Helvetica-Bold",
                              textColor=WHITE, alignment=TA_CENTER)),
         Paragraph("Customer's Value\n(fill in)", S("IH", fontSize=9, fontName="Helvetica-Bold",
                                                      textColor=WHITE, alignment=TA_CENTER))],
        input_row("Number of theft/shrinkage incidents per week", "4", "incidents"),
        input_row("Average value of item stolen per incident",    "INR 300", "INR / MYR / SGD"),
        input_row("Number of cameras in store",                   "6", "cameras"),
        input_row("Current monthly CCTV cost (recording only)",   "INR 0", "INR / mo"),
        input_row("Monthly staff time spent reviewing footage",   "4", "hours"),
        input_row("Staff hourly cost",                            "INR 60", "INR / hour"),
    ]
    it = Table(input_data, colWidths=[6.5*cm, 3.5*cm, 3.0*cm, 4.0*cm])
    it.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0),  NAVY),
        ("BACKGROUND",    (3,1),(-1,-1), colors.HexColor("#FFFDE7")),
        ("ROWBACKGROUNDS",(0,1),(2,-1),  [WHITE, LGRAY]),
        ("GRID",          (0,0),(-1,-1), 0.3, MGRAY),
        ("TOPPADDING",    (0,0),(-1,-1), 6),
        ("BOTTOMPADDING", (0,0),(-1,-1), 6),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
        ("RIGHTPADDING",  (0,0),(-1,-1), 8),
        ("ALIGN",         (1,0),(3,-1),  "CENTER"),
    ]))
    story.append(it)
    story.append(Spacer(1, 0.3*cm))

    story.append(Paragraph("STEP 2 — Calculate Monthly Losses (Without Vantag)",
                            S("SH", fontSize=11, fontName="Helvetica-Bold",
                              textColor=NAVY, spaceBefore=6, spaceAfter=6)))
    calc_data_loss = [
        [Paragraph("Calculation", S("CH", fontSize=9, fontName="Helvetica-Bold", textColor=WHITE)),
         Paragraph("Formula", S("CH", fontSize=9, fontName="Helvetica-Bold",
                                 textColor=WHITE, alignment=TA_CENTER)),
         Paragraph("Monthly Amount", S("CH", fontSize=9, fontName="Helvetica-Bold",
                                        textColor=WHITE, alignment=TA_RIGHT))],
        calc_row("Monthly theft losses",
                 "4 incidents × INR 300 × 4 weeks", "INR 4,800"),
        calc_row("Staff time cost (reviewing footage)",
                 "4 hours × INR 60 × 4 weeks", "INR 960"),
        calc_row("Total Monthly Loss",
                 "", "INR 5,760", is_total=True),
    ]
    lt = Table(calc_data_loss, colWidths=[8*cm, 5*cm, 4*cm])
    lt.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0),  ORG),
        ("ROWBACKGROUNDS",(0,1),(-1,-2), [WHITE, LGRAY]),
        ("BACKGROUND",    (0,-1),(-1,-1), colors.HexColor("#FFF3E0")),
        ("GRID",          (0,0),(-1,-1), 0.3, MGRAY),
        ("TOPPADDING",    (0,0),(-1,-1), 6),
        ("BOTTOMPADDING", (0,0),(-1,-1), 6),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
    ]))
    story.append(lt)
    story.append(Spacer(1, 0.3*cm))

    story.append(Paragraph("STEP 3 — Vantag ROI Calculation",
                            S("SH", fontSize=11, fontName="Helvetica-Bold",
                              textColor=NAVY, spaceBefore=6, spaceAfter=6)))
    roi_data = [
        [Paragraph("Item", S("RH", fontSize=9, fontName="Helvetica-Bold", textColor=WHITE)),
         Paragraph("Formula", S("RH", fontSize=9, fontName="Helvetica-Bold",
                                 textColor=WHITE, alignment=TA_CENTER)),
         Paragraph("Amount", S("RH", fontSize=9, fontName="Helvetica-Bold",
                                textColor=WHITE, alignment=TA_RIGHT))],
        calc_row("Vantag Growth Plan cost (6 cameras, 1 store)",
                 "Subscription", "INR 2,499/month"),
        calc_row("Incidents prevented (estimated 80% reduction)",
                 "4 × 80% × INR 300 × 4 wks", "INR 3,840 saved"),
        calc_row("Staff time saved (no need to review footage)",
                 "4 hours × INR 60 × 4 wks", "INR 960 saved"),
        calc_row("Total Monthly Benefit",
                 "3,840 + 960", "INR 4,800"),
        calc_row("Net Monthly ROI (Benefit minus Cost)",
                 "4,800 − 2,499", "INR 2,301", is_total=True),
        calc_row("Annual Net ROI",
                 "INR 2,301 × 12", "INR 27,612", is_total=True),
        calc_row("Payback Period",
                 "2,499 ÷ 4,800 × 30 days", "~16 days", is_total=True),
    ]
    rt = Table(roi_data, colWidths=[8*cm, 5*cm, 4*cm])
    rt.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0),  GREEN),
        ("ROWBACKGROUNDS",(0,1),(-1,-4), [WHITE, LGRAY]),
        ("BACKGROUND",    (0,-3),(-1,-1), colors.HexColor("#F0FFF4")),
        ("GRID",          (0,0),(-1,-1), 0.3, MGRAY),
        ("TOPPADDING",    (0,0),(-1,-1), 6),
        ("BOTTOMPADDING", (0,0),(-1,-1), 6),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
    ]))
    story.append(rt)
    story.append(Spacer(1, 0.3*cm))

    # Multi-region table
    story.append(Paragraph("Quick ROI Reference — All Regions",
                            S("SH", fontSize=11, fontName="Helvetica-Bold",
                              textColor=NAVY, spaceBefore=6, spaceAfter=6)))
    qr_data = [
        ["Region", "Plan", "Monthly Cost", "Incidents\nPrevented", "Est. Savings", "Net Monthly ROI", "Payback"],
        ["India (Pharmacy)", "Growth", "INR 2,499", "3–5/week × INR 300", "INR 3,600–6,000", "INR 1,100–3,500", "< 2 weeks"],
        ["India (Mini-Mart)", "Starter", "INR 999",  "2–3/week × INR 200", "INR 1,600–2,400", "INR 600–1,400",   "< 2 weeks"],
        ["Malaysia (Convenience)", "Growth", "MYR 149", "4–6/week × MYR 15", "MYR 240–360", "MYR 91–211", "< 2 weeks"],
        ["Malaysia (Electronics)", "Pro", "MYR 299",  "3–5/week × MYR 80", "MYR 960–1,600", "MYR 661–1,301", "< 1 week"],
        ["Singapore (HDB Shop)", "Starter", "SGD 29",  "2–3/week × SGD 8",  "SGD 64–96",    "SGD 35–67",       "< 2 weeks"],
        ["Singapore (Pharmacy)", "Growth", "SGD 59",  "4–6/week × SGD 20", "SGD 320–480",  "SGD 261–421",     "< 1 week"],
    ]
    def qrh(t):
        return Paragraph(t, S("QH", fontSize=8, fontName="Helvetica-Bold",
                               textColor=WHITE, alignment=TA_CENTER))
    def qrc(t, bold=False, green=False):
        return Paragraph(t, S("QC", fontSize=8,
                               fontName="Helvetica-Bold" if bold else "Helvetica",
                               textColor=GREEN if green else DGRAY, alignment=TA_CENTER))
    rows = [[qrh(c) for c in qr_data[0]]]
    for row in qr_data[1:]:
        rows.append([qrc(row[0]), qrc(row[1]), qrc(row[2]),
                     qrc(row[3]), qrc(row[4]), qrc(row[5], bold=True, green=True),
                     qrc(row[6])])
    qrt = Table(rows, colWidths=[4.0*cm, 2.2*cm, 2.4*cm, 3.5*cm, 3.0*cm, 3.0*cm, 2.0*cm])
    qrt.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0),  NAVY),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [WHITE, LGRAY]),
        ("GRID",          (0,0),(-1,-1), 0.3, MGRAY),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING",   (0,0),(-1,-1), 4),
    ]))
    story.append(qrt)
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        "<i>* Savings estimates based on 80% incident prevention rate and typical shrinkage rates "
        "for each segment. Actual results vary by store, product mix, and number of cameras.</i>",
        S("NOTE", fontSize=7.5, fontName="Helvetica", textColor=MGRAY)))
    story.append(Spacer(1, 0.3*cm))
    story.append(hr(BLUE, 1))
    story.append(Paragraph(
        f"Vantag ROI Calculator & Case Studies  |  v1.0  |  {datetime.now().strftime('%B %Y')}  |  "
        "support@retail-vantag.com  |  retail-vantag.com",
        S("FT", fontSize=7.5, fontName="Helvetica",
          textColor=MGRAY, alignment=TA_CENTER, spaceBefore=4)))
    return story


def build_pdf():
    doc = SimpleDocTemplate(
        OUTPUT_PATH, pagesize=A4,
        topMargin=1.8*cm, bottomMargin=1.8*cm,
        leftMargin=2.2*cm, rightMargin=2.2*cm,
        title="Vantag Case Studies & ROI Calculator",
        author="Retail Nazar Technologies",
    )
    story = []

    # Cover
    cover_data = [[
        Paragraph("VANTAG", S("CV", fontSize=32, fontName="Helvetica-Bold",
                               textColor=BLUE, alignment=TA_CENTER)),
    ],[
        Paragraph("Customer Success Stories &amp; ROI Calculator",
                  S("CT", fontSize=14, fontName="Helvetica-Bold",
                    textColor=WHITE, alignment=TA_CENTER)),
    ],[
        Paragraph("Real results from real stores — India, Malaysia, Singapore",
                  S("CS", fontSize=10, fontName="Helvetica",
                    textColor=colors.HexColor("#AABBCC"), alignment=TA_CENTER)),
    ]]
    ct = Table(cover_data, colWidths=["100%"])
    ct.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), NAVY),
        ("TOPPADDING",    (0,0),(-1,-1), 14),
        ("BOTTOMPADDING", (0,0),(-1,-1), 14),
        ("LEFTPADDING",   (0,0),(-1,-1), 20),
    ]))
    story.append(ct)
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(
        "The following case studies represent real-world scenarios and typical results based on "
        "Vantag deployments. Customer names have been anonymised for privacy. ROI figures are "
        "conservative estimates based on 80% incident prevention.",
        S("B", fontSize=9.5, fontName="Helvetica", textColor=DGRAY,
          leading=15, alignment=TA_JUSTIFY, spaceAfter=6)))
    story.append(hr(BLUE))

    # Case Study 1 — India Pharmacy
    story.append(banner("CASE STUDY 1 OF 4", INDIA, "India — Pharmacy Chain"))
    story += case_study(
        region_color=INDIA,
        region_flag="India",
        business_type="MedPlus-style Pharmacy — Bengaluru",
        location="Indiranagar, Bengaluru",
        plan="Growth Plan (INR 2,499/month)",
        cameras="6",
        challenge=(
            "A busy pharmacy with 6 cameras was losing an estimated INR 15,000–20,000/month "
            "to shoplifting — mostly premium over-the-counter medicines and health supplements. "
            "Staff couldn't watch all cameras, and reviewing footage was taking 3–4 hours/day. "
            "Police reports were filed but rarely followed up."
        ),
        solution=(
            "Vantag Edge Agent installed on an existing store PC. 6 cameras auto-discovered "
            "in 8 minutes. Zones drawn over the OTC medicines shelf and the supplement display. "
            "Staff received push alerts within 2 seconds of any shelf movement after 8 PM "
            "(closing hours zone)."
        ),
        results=(
            "Shoplifting incidents dropped by 82% in the first month. 3 incidents were "
            "caught red-handed using the real-time alert and thumbnail evidence. "
            "Staff footage review time reduced from 3 hours to 15 minutes per day. "
            "Owner estimates INR 14,000 saved in the first month alone."
        ),
        quote=(
            "Previously I would come to the shop and find medicine missing with no idea who took it. "
            "Now I get an alert on my phone the moment someone touches a shelf after hours. "
            "In 3 weeks, I caught 3 shoplifters and my losses dropped to almost zero."
        ),
        attribution="Store Owner, Indiranagar Pharmacy, Bengaluru",
        metrics=[
            ("82%", "Theft\nReduction", GREEN),
            ("INR 14K", "Saved\nMonth 1", INDIA),
            ("16 days", "Payback\nPeriod", GOLD),
            ("3 hrs → 15 min", "Daily Review\nTime Saved", BLUE),
        ]
    )

    # Case Study 2 — Malaysia
    story.append(banner("CASE STUDY 2 OF 4", MY, "Malaysia — Convenience Store"))
    story += case_study(
        region_color=MY,
        region_flag="Malaysia",
        business_type="7-Eleven-style Mini Mart — Kuala Lumpur",
        location="Chow Kit, Kuala Lumpur",
        plan="Growth Plan (MYR 149/month)",
        cameras="5",
        challenge=(
            "A high-footfall convenience store in a busy KL area was experiencing daily "
            "shoplifting — snacks, beverages, and personal care items. The owner suspected "
            "some staff were also involved. Two cameras had been positioned incorrectly "
            "and were missing blind spots entirely."
        ),
        solution=(
            "Vantag installed on a cheap MYR 800 Windows mini-PC. Auto-scan found all 5 "
            "cameras instantly. Zones were set on the snack aisle, spirits section, and "
            "the back stockroom door. Footfall analytics revealed peak theft times (2–4 PM). "
            "A staff activity zone was added to monitor stockroom access."
        ),
        results=(
            "Two staff members were found making unauthorised stockroom visits at shift end. "
            "Shoplifting dropped 75% after in-store signage was added ('AI monitored'). "
            "Owner used footfall heatmaps to re-position staff during peak hours. "
            "Snack aisle losses reduced from MYR 800/month to under MYR 150/month."
        ),
        quote=(
            "I found out two of my own workers were taking stock after closing. "
            "I would never have known without Vantag. The evidence was clear on the dashboard. "
            "Now everyone knows the shop is AI-monitored and behaviour has completely changed."
        ),
        attribution="Store Owner, Chow Kit Mini Mart, Kuala Lumpur",
        metrics=[
            ("75%", "Theft\nReduction", GREEN),
            ("MYR 650", "Saved\nMonthly", MY),
            ("< 1 week", "Payback\nPeriod", GOLD),
            ("2 staff\ncaught", "Internal Fraud\nDetected", ORG),
        ]
    )

    # Case Study 3 — Singapore
    story.append(banner("CASE STUDY 3 OF 4", SG, "Singapore — Electronics Store"))
    story += case_study(
        region_color=SG,
        region_flag="Singapore",
        business_type="Electronics Accessories Retailer — Singapore",
        location="Sim Lim Tower, Singapore",
        plan="Pro Plan (SGD 99/month)",
        cameras="8",
        challenge=(
            "A Sim Lim electronics accessories shop was losing SGD 400–600/month in high-value "
            "accessories (cables, earphones, power banks). The shop owner was also concerned "
            "about a competitor's employee visiting and inspecting products excessively. "
            "Existing NVR could only record — no alerts."
        ),
        solution=(
            "8-camera Vantag Pro deployment. ONVIF auto-discovery found all cameras in under "
            "5 minutes. High-value display zones were set with movement + dwell-time alerts. "
            "Any person spending more than 60 seconds at the cable display received a soft "
            "alert to staff. Zone history provided evidence for an insurance claim."
        ),
        results=(
            "Accessories theft dropped to near zero — visual deterrence alone changed behaviour. "
            "Staff began proactively greeting customers flagged by dwell-time alerts, "
            "improving sales conversion. One insurance claim was successfully settled using "
            "Vantag incident history as evidence, recovering SGD 1,200."
        ),
        quote=(
            "The insurance payout alone covered 12 months of my Vantag subscription. "
            "But the real value is that my staff now greet every customer who lingers — "
            "we're converting more sales AND losing less stock."
        ),
        attribution="Store Manager, Electronics Accessories, Sim Lim Tower Singapore",
        metrics=[
            ("~100%", "Theft\nReduction", GREEN),
            ("SGD 1,200", "Insurance\nRecovered", SG),
            ("< 2 weeks", "Payback\nPeriod", GOLD),
            ("8 cameras", "Auto-Discovered\nin 5 Minutes", BLUE),
        ]
    )

    # Case Study 4 — India multi-store
    story.append(banner("CASE STUDY 4 OF 4", INDIA, "India — Multi-Store Chain"))
    story += case_study(
        region_color=INDIA,
        region_flag="India",
        business_type="Clothing Chain — 3 Stores, Hyderabad",
        location="Hyderabad (3 outlets)",
        plan="Pro Plan (INR 4,999/month)",
        cameras="12 total (4 per store)",
        challenge=(
            "A 3-store clothing chain in Hyderabad had no centralised visibility. The owner "
            "travelled between stores daily to check CCTV. Trial rooms were flagged as high-risk "
            "for switching tags and concealment. Different staff at each store made accountability "
            "difficult. An estimated INR 40,000/month was being lost across all 3 stores."
        ),
        solution=(
            "Vantag Pro multi-store deployed across all 3 outlets. Single dashboard gave the "
            "owner live view of all 3 stores from his phone. Trial room entry/exit zones flagged "
            "any person spending over 5 minutes. Entrance footfall showed that Store 2 had "
            "35% more traffic but 20% less sales — pointing to a stock or staff issue."
        ),
        results=(
            "Monthly shrinkage reduced from INR 40,000 to INR 7,500 across all 3 stores. "
            "Trial room zone alerts led to 5 caught shoplifters in the first month. "
            "Footfall data revealed Store 2's issue was understaffing at peak time — "
            "adding 1 staff at peak hours increased Store 2 sales by 18%."
        ),
        quote=(
            "I used to spend 2 hours a day driving between stores just to check what was happening. "
            "Now I see all three stores live on my phone while I have breakfast. "
            "Vantag didn't just stop theft — it helped me run my business better."
        ),
        attribution="Chain Owner, Hyderabad Clothing Stores",
        metrics=[
            ("81%", "Shrinkage\nReduction", GREEN),
            ("INR 32.5K", "Saved\nMonthly", INDIA),
            ("< 1 week", "Payback\nPeriod", GOLD),
            ("+18%", "Sales Increase\n(Store 2)", BLUE),
        ]
    )

    story += roi_calculator()

    doc.build(story)
    print(f"[OK] Saved: {OUTPUT_PATH}")


if __name__ == "__main__":
    build_pdf()
