"""
Generate Vantag Dealer Agreement PDF
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether, PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY, TA_RIGHT
from datetime import datetime
import os

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "Vantag_Dealer_Agreement_Template.pdf")

# ── Color palette ──────────────────────────────────────────────────────────────
DARK_NAVY  = colors.HexColor("#0D1B2A")
ACCENT     = colors.HexColor("#1E90FF")
LIGHT_GRAY = colors.HexColor("#F5F7FA")
MID_GRAY   = colors.HexColor("#CCCCCC")
TEXT_DARK  = colors.HexColor("#1A1A2E")
TEXT_MUTED = colors.HexColor("#555555")
WHITE      = colors.white

# ── Styles ─────────────────────────────────────────────────────────────────────
styles = getSampleStyleSheet()

def S(name, **kw):
    return ParagraphStyle(name, parent=styles["Normal"], **kw)

TITLE_STYLE     = S("DocTitle",   fontSize=22, fontName="Helvetica-Bold",
                    textColor=WHITE, alignment=TA_CENTER, spaceAfter=4)
SUBTITLE_STYLE  = S("DocSub",    fontSize=11, fontName="Helvetica",
                    textColor=colors.HexColor("#B0C4DE"), alignment=TA_CENTER, spaceAfter=2)
H1              = S("H1",         fontSize=13, fontName="Helvetica-Bold",
                    textColor=DARK_NAVY, spaceBefore=14, spaceAfter=4,
                    borderPad=4)
H2              = S("H2",         fontSize=11, fontName="Helvetica-Bold",
                    textColor=ACCENT, spaceBefore=10, spaceAfter=3)
BODY            = S("Body",       fontSize=9.5, fontName="Helvetica",
                    textColor=TEXT_DARK, leading=15, alignment=TA_JUSTIFY,
                    spaceBefore=3, spaceAfter=3)
SMALL           = S("Small",      fontSize=8.5, fontName="Helvetica",
                    textColor=TEXT_MUTED, leading=13, alignment=TA_JUSTIFY)
FIELD_LABEL     = S("FL",         fontSize=9, fontName="Helvetica-Bold",
                    textColor=TEXT_DARK, spaceBefore=8)
FIELD_VALUE     = S("FV",         fontSize=9, fontName="Helvetica",
                    textColor=TEXT_MUTED, borderPad=2)
SIG_LABEL       = S("SigLbl",     fontSize=9, fontName="Helvetica-Bold",
                    textColor=TEXT_DARK)
FOOTER_STYLE    = S("Footer",     fontSize=7.5, fontName="Helvetica",
                    textColor=TEXT_MUTED, alignment=TA_CENTER)
CLAUSE_NUM      = S("ClauseNum",  fontSize=9.5, fontName="Helvetica-Bold",
                    textColor=DARK_NAVY)
BULLET          = S("Bullet",     fontSize=9.5, fontName="Helvetica",
                    textColor=TEXT_DARK, leading=15, leftIndent=12,
                    bulletIndent=0, spaceBefore=2)

def hr(color=MID_GRAY, width=0.5):
    return HRFlowable(width="100%", thickness=width, color=color, spaceAfter=6, spaceBefore=6)

def section_header(text):
    """Blue pill-style section header."""
    data = [[Paragraph(text, S("SH", fontSize=11, fontName="Helvetica-Bold",
                                textColor=WHITE, alignment=TA_LEFT))]]
    t = Table(data, colWidths=["100%"])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), DARK_NAVY),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("ROUNDEDCORNERS", [4]),
    ]))
    return t

def field_row(label, value="___________________________________"):
    return [
        Paragraph(f"<b>{label}:</b>", BODY),
        Paragraph(value, BODY),
    ]

def clause(number, title, *paragraphs):
    items = [
        KeepTogether([
            Paragraph(f"{number}. {title}", H1),
            hr(ACCENT, 1),
        ])
    ]
    for p in paragraphs:
        if isinstance(p, str):
            items.append(Paragraph(p, BODY))
        else:
            items.append(p)
    return items

def bullet(text):
    return Paragraph(f"&#8226;&#160; {text}", BULLET)

# ── Header / Cover ─────────────────────────────────────────────────────────────
def cover_table():
    cover_data = [[
        Paragraph("VANTAG", S("Brand", fontSize=28, fontName="Helvetica-Bold",
                               textColor=ACCENT, alignment=TA_CENTER)),
    ], [
        Paragraph("Retail Intelligence Platform", SUBTITLE_STYLE),
    ], [
        Paragraph("AUTHORISED DEALER &amp; RESELLER AGREEMENT", TITLE_STYLE),
    ], [
        Paragraph("Version 1.0  |  Effective upon execution by both parties", SUBTITLE_STYLE),
    ]]
    t = Table(cover_data, colWidths=["100%"])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), DARK_NAVY),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 20),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 20),
    ]))
    return t

# ── Party table ────────────────────────────────────────────────────────────────
def parties_table():
    rows = [
        [Paragraph("<b>PARTY</b>", BODY), Paragraph("<b>DETAILS</b>", BODY)],
        [Paragraph("Company (Vantag)", BODY),
         Paragraph("Retail Nazar Technologies | retail-vantag.com / retailnazar.com / jagajaga.my", BODY)],
        [Paragraph("Authorised Signatory", BODY),
         Paragraph("[Owner Name] · [Designation]", BODY)],
        [Paragraph("Dealer / Reseller", BODY),
         Paragraph("[Dealer Company Name]", BODY)],
        [Paragraph("Dealer Address", BODY),
         Paragraph("[Full registered address]", BODY)],
        [Paragraph("Dealer Contact", BODY),
         Paragraph("[Name · Phone · Email]", BODY)],
        [Paragraph("Dealer Region", BODY),
         Paragraph("[India / Malaysia / Singapore]", BODY)],
        [Paragraph("Agreement Date", BODY),
         Paragraph("[DD-MMM-YYYY]", BODY)],
    ]
    t = Table(rows, colWidths=[5.5*cm, 11.5*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  DARK_NAVY),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  WHITE),
        ("BACKGROUND",    (0, 1), (-1, -1), LIGHT_GRAY),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
        ("GRID",          (0, 0), (-1, -1), 0.4, MID_GRAY),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
    ]))
    return t

# ── Commission table ───────────────────────────────────────────────────────────
def commission_table():
    rows = [
        ["Region", "Plan", "Monthly Price", "Dealer Commission (15%)", "Payout Trigger"],
        ["India",   "Starter", "INR 999",  "INR 150",  "30 days after customer payment"],
        ["India",   "Growth",  "INR 2,499","INR 375",  "30 days after customer payment"],
        ["India",   "Pro",     "INR 4,999","INR 750",  "30 days after customer payment"],
        ["Malaysia","Starter", "MYR 79",   "MYR 12",   "30 days after customer payment"],
        ["Malaysia","Growth",  "MYR 149",  "MYR 22",   "30 days after customer payment"],
        ["Malaysia","Pro",     "MYR 299",  "MYR 45",   "30 days after customer payment"],
        ["Singapore","Starter","SGD 29",   "SGD 4.35", "30 days after customer payment"],
        ["Singapore","Growth", "SGD 59",   "SGD 8.85", "30 days after customer payment"],
        ["Singapore","Pro",    "SGD 99",   "SGD 14.85","30 days after customer payment"],
    ]
    style_rows = [[Paragraph(c, S("TC", fontSize=8, fontName="Helvetica-Bold" if i == 0 else "Helvetica",
                                   textColor=WHITE if i == 0 else TEXT_DARK,
                                   alignment=TA_CENTER)) for c in row]
                  for i, row in enumerate(rows)]
    t = Table(style_rows, colWidths=[2.8*cm, 2.4*cm, 3.0*cm, 4.0*cm, 4.8*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  ACCENT),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
        ("GRID",          (0, 0), (-1, -1), 0.4, MID_GRAY),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
    ]))
    return t

# ── Signature block ────────────────────────────────────────────────────────────
def signature_block():
    def sig_col(party):
        return [
            Paragraph(f"<b>FOR {party.upper()}</b>", SIG_LABEL),
            Spacer(1, 1.2*cm),
            HRFlowable(width="80%", thickness=0.5, color=TEXT_DARK),
            Paragraph("Signature", SMALL),
            Spacer(1, 0.3*cm),
            Paragraph("Name: ___________________________", SMALL),
            Paragraph("Designation: ____________________", SMALL),
            Paragraph("Date: ___________________________", SMALL),
            Paragraph("Stamp / Seal:", SMALL),
            Spacer(1, 1.5*cm),
            HRFlowable(width="80%", thickness=0.3, color=MID_GRAY),
        ]
    rows = [[sig_col("Vantag / Retail Nazar Technologies"), sig_col("Authorised Dealer")]]
    t = Table(rows, colWidths=[8.5*cm, 8.5*cm])
    t.setStyle(TableStyle([
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t

# ── Build story ────────────────────────────────────────────────────────────────
def build_story():
    story = []

    # Cover
    story.append(cover_table())
    story.append(Spacer(1, 0.6*cm))

    # Preamble
    story.append(Paragraph(
        "This Authorised Dealer &amp; Reseller Agreement (\"Agreement\") is entered into between "
        "<b>Retail Nazar Technologies</b> operating the Vantag platform (\"Company\") and the dealer "
        "entity named above (\"Dealer\"). By signing below, both parties agree to the terms set out herein.",
        BODY))
    story.append(Spacer(1, 0.3*cm))

    # Parties
    story.append(section_header("PARTIES TO THIS AGREEMENT"))
    story.append(Spacer(1, 0.2*cm))
    story.append(parties_table())
    story.append(Spacer(1, 0.4*cm))

    # Clause 1
    story += clause("1", "APPOINTMENT & TERRITORY",
        "The Company hereby appoints the Dealer as a <b>non-exclusive</b> authorised reseller of "
        "the Vantag Retail Intelligence Platform in the territory/region specified above. "
        "This appointment does not restrict the Company from appointing other resellers in the same territory.",
        bullet("Dealer may not sub-appoint resellers without prior written consent of the Company."),
        bullet("Territory is limited to the region specified in the parties table above."),
        bullet("Dealer shall not actively solicit customers outside the assigned territory."),
    )

    # Clause 2
    story += clause("2", "DEALER OBLIGATIONS",
        "The Dealer agrees to:",
        bullet("Actively promote and sell Vantag subscriptions to retail businesses, shops, malls, hospitals, offices, and other commercial establishments within the assigned territory."),
        bullet("Complete a one-time Dealer Onboarding with the Company's sales team before commencing sales."),
        bullet("Provide first-line installation support: install the Vantag Edge Agent on customer premises, ensure cameras are configured, and verify the dashboard is operational."),
        bullet("Maintain accurate records of all customers onboarded through this agreement."),
        bullet("Not misrepresent the features, pricing, or capabilities of the Vantag platform."),
        bullet("Report any customer complaints or technical issues to support@retail-vantag.com within 24 hours."),
        bullet("Comply with applicable data protection and privacy laws in the Dealer's region."),
    )

    # Clause 3
    story += clause("3", "COMPANY OBLIGATIONS",
        "The Company agrees to:",
        bullet("Provide Dealer with access to marketing materials, product documentation, and demo accounts."),
        bullet("Pay commission as per the schedule in Clause 5, within 30 days of customer payment clearing."),
        bullet("Provide Tier-2 technical support for issues escalated by the Dealer."),
        bullet("Notify Dealer of material changes to product pricing with at least 30 days advance notice."),
        bullet("Maintain the Vantag platform and SLA uptime of 99.5% monthly."),
    )

    # Clause 4
    story += clause("4", "SUBSCRIPTION PLANS & PRICING",
        "The Dealer shall sell Vantag subscriptions at the <b>official published prices</b> listed below. "
        "The Dealer is strictly prohibited from discounting below the minimum floor price without written "
        "approval from the Company. Annual plans may be offered with a maximum 17% discount (2 months free).",
    )
    story.append(Spacer(1, 0.2*cm))
    story.append(commission_table())
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        "<i>* Prices subject to revision with 30 days advance notice. Commission % remains constant unless renegotiated in writing.</i>",
        SMALL))

    # Clause 5
    story += clause("5", "COMMISSION & PAYMENT TERMS",
        bullet("Dealer commission rate: <b>15% of the net subscription amount</b> actually received by the Company from customers introduced by the Dealer."),
        bullet("Commission is paid monthly in arrears, within 30 days of the customer's successful payment being received and cleared."),
        bullet("Payment method: Bank transfer to Dealer's registered bank account. Dealer to provide banking details separately."),
        bullet("Minimum payout threshold: INR 500 / MYR 20 / SGD 10. Amounts below this threshold roll over to the next month."),
        bullet("Commission is forfeited if the customer receives a full refund within the first 30 days."),
        bullet("No commission is payable on customers the Company has already been in direct contact with prior to Dealer's introduction."),
        Paragraph(
            "<b>Referral Partner Rate (Non-Installing Introducer):</b> A flat 10% commission applies to "
            "introductions made by non-installing partners. This lower rate applies when the Company's team "
            "performs the installation directly.",
            BODY),
    )

    # Clause 6
    story += clause("6", "ONBOARDING FEE",
        "A one-time, refundable Dealer Onboarding Fee of <b>INR 5,000 / MYR 200 / SGD 80</b> "
        "(as applicable to the Dealer's region) is payable upon signing this agreement. "
        "This fee is fully recoverable against commissions earned within the first 12 months. "
        "The fee serves to identify committed dealers and offset onboarding costs.",
    )

    # Clause 7
    story += clause("7", "INTELLECTUAL PROPERTY",
        "All intellectual property in the Vantag platform, including software, AI models, branding, "
        "logos, documentation, and marketing materials, remains the exclusive property of the Company. "
        "The Dealer receives a limited, non-transferable, non-exclusive licence to use Vantag branding "
        "solely for the purpose of promoting and selling Vantag subscriptions under this Agreement.",
        bullet("Dealer shall not modify, reverse-engineer, or white-label the Vantag platform."),
        bullet("Dealer shall not register domain names, trademarks, or social handles incorporating the name 'Vantag' without written consent."),
    )

    # Clause 8
    story += clause("8", "CONFIDENTIALITY",
        "Both parties agree to keep confidential all non-public information received from the other party, "
        "including pricing structures, customer lists, technical architecture, and business strategies. "
        "This obligation survives termination of this Agreement for a period of <b>3 years</b>.",
    )

    # Clause 9
    story += clause("9", "TERM & TERMINATION",
        bullet("This Agreement is valid for <b>12 months</b> from the execution date and auto-renews annually unless either party gives 30 days written notice of non-renewal."),
        bullet("Either party may terminate for cause (material breach) with 14 days written notice if the breach is not remedied within that period."),
        bullet("The Company may terminate immediately if the Dealer engages in misrepresentation, fraud, or any act that damages the Company's reputation."),
        bullet("Upon termination, commissions earned but not yet paid for completed customer months shall still be paid."),
        bullet("Dealer shall immediately cease using all Vantag branding and marketing materials upon termination."),
    )

    # Clause 10
    story += clause("10", "LIMITATION OF LIABILITY",
        "The Company's total liability under this Agreement shall not exceed the total commission paid to "
        "the Dealer in the 3 months preceding the event giving rise to the claim. "
        "The Company is not liable for indirect, incidental, or consequential damages.",
    )

    # Clause 11
    story += clause("11", "GOVERNING LAW & DISPUTE RESOLUTION",
        bullet("<b>India region:</b> This Agreement is governed by the laws of India. Disputes shall be resolved by arbitration under the Arbitration and Conciliation Act 1996, seated in Bengaluru, India."),
        bullet("<b>Malaysia region:</b> Governed by Malaysian law. Disputes resolved by the Kuala Lumpur Regional Centre for Arbitration (KLRCA)."),
        bullet("<b>Singapore region:</b> Governed by Singapore law. Disputes resolved by the Singapore International Arbitration Centre (SIAC)."),
    )

    # Clause 12
    story += clause("12", "ENTIRE AGREEMENT",
        "This Agreement, together with any Schedule or Addendum signed by both parties, constitutes the "
        "entire agreement between the parties with respect to the subject matter herein and supersedes all "
        "prior discussions, representations, and agreements. Amendments must be in writing and signed by "
        "authorised representatives of both parties.",
    )

    story.append(PageBreak())

    # Signature
    story.append(section_header("SIGNATURES"))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(
        "Both parties confirm they have read, understood, and agree to be bound by this Agreement.",
        BODY))
    story.append(Spacer(1, 0.5*cm))
    story.append(signature_block())
    story.append(Spacer(1, 0.8*cm))
    story.append(hr())

    # Witness
    story.append(Paragraph("<b>WITNESS</b>", H2))
    witness_data = [
        ["Witness Name:", "___________________________", "Witness Name:", "___________________________"],
        ["Signature:",    "___________________________", "Signature:",    "___________________________"],
        ["Date:",         "___________________________", "Date:",         "___________________________"],
    ]
    wt = Table([[Paragraph(c, SMALL) for c in r] for r in witness_data],
               colWidths=[2.8*cm, 5.0*cm, 2.8*cm, 5.0*cm])
    wt.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(wt)
    story.append(Spacer(1, 0.4*cm))
    story.append(hr())
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(
        "Vantag Retail Intelligence Platform  |  support@retail-vantag.com  |  "
        "www.retail-vantag.com  |  www.retailnazar.com  |  www.jagajaga.my<br/>"
        f"Document generated: {datetime.now().strftime('%d %B %Y')}  |  Template v1.0  |  "
        "This is a template — insert actual party details before execution.",
        FOOTER_STYLE))

    return story


def build_pdf():
    doc = SimpleDocTemplate(
        OUTPUT_PATH, pagesize=A4,
        topMargin=1.8*cm, bottomMargin=1.8*cm,
        leftMargin=2.2*cm, rightMargin=2.2*cm,
        title="Vantag Dealer Agreement",
        author="Retail Nazar Technologies",
        subject="Authorised Dealer & Reseller Agreement",
    )
    doc.build(build_story())
    print(f"[OK] Saved: {OUTPUT_PATH}")


if __name__ == "__main__":
    build_pdf()
