"""
Generate: Retail Nazar VPS Configuration Guide (PDF)
Covers: Live API Keys, Razorpay Webhooks, Plan IDs
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

OUTPUT = os.path.join(os.path.dirname(__file__), "Retail_Nazar_VPS_Config_Guide.pdf")

# ── Colour palette ───────────────────────────────────────────────
NAVY   = colors.HexColor("#1a1a2e")
BLUE   = colors.HexColor("#0f3460")
ACCENT = colors.HexColor("#e94560")
GOLD   = colors.HexColor("#f5a623")
GREEN  = colors.HexColor("#27ae60")
LGREY  = colors.HexColor("#f4f4f4")
DGREY  = colors.HexColor("#555555")
WHITE  = colors.white
BLACK  = colors.black
CMD_BG = colors.HexColor("#1e1e2e")
CMD_FG = colors.HexColor("#a9dc76")

# ── Styles ───────────────────────────────────────────────────────
styles = getSampleStyleSheet()

def S(name, **kw):
    return ParagraphStyle(name, **kw)

Cover_Title   = S("CoverTitle",   fontSize=32, textColor=WHITE,   alignment=TA_CENTER, fontName="Helvetica-Bold",  spaceAfter=8)
Cover_Sub     = S("CoverSub",     fontSize=14, textColor=GOLD,    alignment=TA_CENTER, fontName="Helvetica",       spaceAfter=6)
Cover_Body    = S("CoverBody",    fontSize=11, textColor=WHITE,   alignment=TA_CENTER, fontName="Helvetica",       spaceAfter=4)

H1            = S("H1",           fontSize=18, textColor=NAVY,    fontName="Helvetica-Bold", spaceBefore=14, spaceAfter=6,
                                  borderPad=4)
H2            = S("H2",           fontSize=13, textColor=BLUE,    fontName="Helvetica-Bold", spaceBefore=10, spaceAfter=4)
H3            = S("H3",           fontSize=11, textColor=ACCENT,  fontName="Helvetica-Bold", spaceBefore=8,  spaceAfter=3)
Body          = S("Body",         fontSize=10, textColor=BLACK,   fontName="Helvetica",       spaceAfter=4, leading=15)
BodyJ         = S("BodyJ",        fontSize=10, textColor=DGREY,   fontName="Helvetica",       spaceAfter=4, leading=15, alignment=TA_JUSTIFY)
Note          = S("Note",         fontSize=9,  textColor=colors.HexColor("#7f5af0"), fontName="Helvetica-Oblique", spaceAfter=4, leading=13)
Warn          = S("Warn",         fontSize=9,  textColor=ACCENT,  fontName="Helvetica-Bold",  spaceAfter=4)
StepNum       = S("StepNum",      fontSize=20, textColor=ACCENT,  fontName="Helvetica-Bold",  spaceAfter=0, spaceBefore=6)
StepTitle     = S("StepTitle",    fontSize=12, textColor=NAVY,    fontName="Helvetica-Bold",  spaceAfter=4)
Code          = S("Code",         fontSize=8.5,textColor=CMD_FG,  fontName="Courier-Bold",    spaceAfter=2, leading=13, backColor=CMD_BG, leftIndent=8, rightIndent=8)
BulletStyle   = S("BulletStyle",  fontSize=10, textColor=BLACK,   fontName="Helvetica",       spaceAfter=3, leftIndent=12, bulletIndent=2, leading=14)

# ── Helper flowables ─────────────────────────────────────────────
def hr(color=BLUE, thickness=1):
    return HRFlowable(width="100%", thickness=thickness, color=color, spaceAfter=6)

def section_header(text):
    tbl = Table([[Paragraph(text, H1)]], colWidths=[16.5*cm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), LGREY),
        ("LEFTPADDING", (0,0), (-1,-1), 10),
        ("RIGHTPADDING", (0,0), (-1,-1), 10),
        ("TOPPADDING", (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("LINEBELOW", (0,0), (-1,-1), 2, ACCENT),
    ]))
    return tbl

def step_box(num, title, content_items):
    """A numbered step card."""
    inner = [[Paragraph(f"Step {num}", StepNum), Paragraph(title, StepTitle)]]
    for item in content_items:
        inner.append([Paragraph("", Body), item])
    items = [Spacer(1, 4)]
    items.append(Paragraph(f"<b>Step {num}:</b> {title}", H2))
    return items

def cmd_block(lines):
    """Green-on-dark code block."""
    text = "<br/>".join(lines)
    tbl = Table([[Paragraph(text, Code)]], colWidths=[16.5*cm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), CMD_BG),
        ("LEFTPADDING", (0,0), (-1,-1), 12),
        ("RIGHTPADDING", (0,0), (-1,-1), 12),
        ("TOPPADDING", (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("ROUNDEDCORNERS", [4]),
    ]))
    return tbl

def info_box(title, text, bg=colors.HexColor("#eaf4fb"), border=BLUE):
    tbl = Table([[Paragraph(f"<b>{title}</b>  {text}", Body)]], colWidths=[16.5*cm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), bg),
        ("LEFTPADDING", (0,0), (-1,-1), 10),
        ("RIGHTPADDING", (0,0), (-1,-1), 10),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LINEBEFORE", (0,0), (0,-1), 4, border),
    ]))
    return tbl

def warning_box(text):
    return info_box("WARNING:", text, bg=colors.HexColor("#fff3cd"), border=GOLD)

def success_box(text):
    return info_box("SUCCESS:", text, bg=colors.HexColor("#d4edda"), border=GREEN)

def bullet(text):
    return Paragraph(f"&bull; &nbsp; {text}", BulletStyle)

# ── Document ─────────────────────────────────────────────────────
doc = SimpleDocTemplate(
    OUTPUT,
    pagesize=A4,
    topMargin=2*cm, bottomMargin=2.5*cm,
    leftMargin=2*cm, rightMargin=2*cm,
    title="Retail Nazar VPS Config Guide",
    author="BrainGuardX AI Technologies Pvt. Ltd.",
)

story = []

# ════════════════════════════════════════════════════════════════
# COVER PAGE
# ════════════════════════════════════════════════════════════════
cover_bg = Table(
    [[Paragraph("RETAIL NAZAR", Cover_Title)],
     [Paragraph("VPS Configuration Guide", Cover_Sub)],
     [Spacer(1, 0.3*cm)],
     [Paragraph("Razorpay Live API Keys · Webhooks · Plan IDs", Cover_Body)],
     [Spacer(1, 0.5*cm)],
     [Paragraph("BrainGuardX AI Technologies Pvt. Ltd.", Cover_Body)],
     [Paragraph("Confidential — Internal Use Only", S("small", fontSize=9, textColor=colors.HexColor("#aaaaaa"), alignment=TA_CENTER, fontName="Helvetica-Oblique"))],
    ],
    colWidths=[16.5*cm]
)
cover_bg.setStyle(TableStyle([
    ("BACKGROUND", (0,0), (-1,-1), NAVY),
    ("ALIGN",      (0,0), (-1,-1), "CENTER"),
    ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
    ("LEFTPADDING",(0,0), (-1,-1), 20),
    ("RIGHTPADDING",(0,0),(-1,-1), 20),
    ("TOPPADDING", (0,0), (-1,-1), 50),
    ("BOTTOMPADDING",(0,0),(-1,-1), 50),
    ("LINEBELOW", (0,0), (-1,-1), 4, ACCENT),
]))
story.append(cover_bg)
story.append(Spacer(1, 1*cm))

# Quick info table
info_rows = [
    ["Website", "https://retailnazar.com"],
    ["VPS Path", "/var/www/vantag/"],
    ["Backend Service", "vantag  (systemctl)"],
    ["Webhook URL (India)", "https://retailnazar.com/api/billing/webhook/IN"],
    ["Support Email", "support@retailnazar.com"],
]
info_tbl = Table(info_rows, colWidths=[5*cm, 11.5*cm])
info_tbl.setStyle(TableStyle([
    ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
    ("FONTNAME", (1,0), (1,-1), "Courier"),
    ("FONTSIZE", (0,0), (-1,-1), 9),
    ("TEXTCOLOR", (0,0), (0,-1), NAVY),
    ("TEXTCOLOR", (1,0), (1,-1), BLUE),
    ("ROWBACKGROUNDS", (0,0), (-1,-1), [WHITE, LGREY]),
    ("GRID", (0,0), (-1,-1), 0.3, colors.HexColor("#cccccc")),
    ("LEFTPADDING", (0,0), (-1,-1), 8),
    ("RIGHTPADDING", (0,0), (-1,-1), 8),
    ("TOPPADDING", (0,0), (-1,-1), 5),
    ("BOTTOMPADDING", (0,0), (-1,-1), 5),
]))
story.append(info_tbl)
story.append(PageBreak())

# ════════════════════════════════════════════════════════════════
# SECTION 1 — OVERVIEW
# ════════════════════════════════════════════════════════════════
story.append(section_header("SECTION 1 — Overview"))
story.append(Spacer(1, 0.3*cm))
story.append(Paragraph(
    "This guide explains how to update Razorpay payment credentials on the Retail Nazar production "
    "server (VPS). All changes are made directly on the VPS via SSH — no code files are modified "
    "on your local computer. Follow each section in order.",
    BodyJ))
story.append(Spacer(1, 0.3*cm))

story.append(Paragraph("What This Guide Covers", H2))
items = [
    ("Section 2", "Update Razorpay Live API Keys  (Key ID + Key Secret)"),
    ("Section 3", "Set Up Razorpay Webhooks  (Receive automatic payment notifications)"),
    ("Section 4", "Add Razorpay Subscription Plan IDs  (Link plans to recurring billing)"),
    ("Section 5", "Common VPS Commands Reference"),
    ("Section 6", "Troubleshooting"),
]
rows = [["Section", "Topic"]] + items
tbl = Table(rows, colWidths=[3.5*cm, 13*cm])
tbl.setStyle(TableStyle([
    ("BACKGROUND", (0,0), (-1,0), NAVY),
    ("TEXTCOLOR", (0,0), (-1,0), WHITE),
    ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
    ("FONTSIZE", (0,0), (-1,-1), 9),
    ("ROWBACKGROUNDS", (0,1), (-1,-1), [WHITE, LGREY]),
    ("GRID", (0,0), (-1,-1), 0.3, colors.HexColor("#cccccc")),
    ("LEFTPADDING", (0,0), (-1,-1), 8),
    ("TOPPADDING", (0,0), (-1,-1), 5),
    ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ("FONTNAME", (0,1), (0,-1), "Helvetica-Bold"),
    ("TEXTCOLOR", (0,1), (0,-1), ACCENT),
]))
story.append(tbl)
story.append(Spacer(1, 0.4*cm))

story.append(warning_box(
    "Never paste these commands on your local Windows computer. "
    "All commands MUST be run inside your VPS SSH session (the black terminal connected to Hostinger)."
))
story.append(Spacer(1, 0.3*cm))

story.append(Paragraph("How to Connect to VPS (Quick Reminder)", H2))
story.append(Paragraph("Open your computer's terminal or PuTTY and type:", Body))
story.append(cmd_block(["ssh root@YOUR_VPS_IP"]))
story.append(Paragraph(
    "Replace YOUR_VPS_IP with your Hostinger VPS IP address. "
    "Enter the root password when asked. You are now inside the VPS.",
    Note))
story.append(PageBreak())

# ════════════════════════════════════════════════════════════════
# SECTION 2 — LIVE API KEYS
# ════════════════════════════════════════════════════════════════
story.append(section_header("SECTION 2 — Update Razorpay Live API Keys"))
story.append(Spacer(1, 0.3*cm))
story.append(Paragraph(
    "Razorpay gives you TWO keys: a Key ID (public) and a Key Secret (private). "
    "Both must be updated whenever you rotate or switch from test to live mode. "
    "The backend uses the Key Secret to verify payments securely.",
    BodyJ))
story.append(Spacer(1, 0.4*cm))

story.append(Paragraph("Where to find your Live Keys", H2))
story.append(bullet("Log in to <b>dashboard.razorpay.com</b>"))
story.append(bullet("Click the <b>Test Mode</b> toggle at the top → switch to <b>Live Mode</b>"))
story.append(bullet("Go to <b>Settings → API Keys → Regenerate Key</b>"))
story.append(bullet("Copy the <b>Key ID</b> (starts with rzp_live_...) and <b>Key Secret</b>"))
story.append(Spacer(1, 0.3*cm))

# Steps
story.append(Paragraph("Step 1 — Connect to VPS via SSH", H2))
story.append(cmd_block(["ssh root@YOUR_VPS_IP"]))
story.append(Spacer(1, 0.2*cm))

story.append(Paragraph("Step 2 — Update the Backend .env File", H2))
story.append(Paragraph(
    "Run the two commands below. Replace the values after = with your actual new keys.",
    Body))
story.append(cmd_block([
    "# Replace OLD key ID with new live key ID",
    "sed -i 's|RAZORPAY_KEY_ID_IN=OLD_VALUE|RAZORPAY_KEY_ID_IN=rzp_live_XXXX|g' /var/www/vantag/.env",
    "",
    "# Replace OLD key secret with new live secret",
    "sed -i 's|RAZORPAY_KEY_SECRET_IN=OLD_VALUE|RAZORPAY_KEY_SECRET_IN=YOUR_SECRET|g' /var/www/vantag/.env",
]))
story.append(info_box(
    "TIP:",
    "If you do not know the OLD_VALUE, use this command first to see current values:  "
    "grep RAZORPAY /var/www/vantag/.env",
    bg=colors.HexColor("#eaf4fb"), border=BLUE))
story.append(Spacer(1, 0.2*cm))

story.append(Paragraph("Step 3 — Update the Frontend .env File", H2))
story.append(Paragraph(
    "The frontend (website JavaScript) also needs the Key ID so it can open the Razorpay payment popup. "
    "The Key Secret is NEVER put in the frontend.",
    Body))
story.append(cmd_block([
    "# Update frontend env",
    "sed -i 's|VITE_RAZORPAY_KEY_ID=OLD_VALUE|VITE_RAZORPAY_KEY_ID=rzp_live_XXXX|g' /var/www/vantag/frontend/web/.env",
]))
story.append(Spacer(1, 0.2*cm))

story.append(Paragraph("Step 4 — Rebuild the Frontend", H2))
story.append(Paragraph(
    "The Key ID is baked into the compiled JavaScript at build time. "
    "You MUST rebuild after any frontend .env change.",
    Body))
story.append(cmd_block([
    "cd /var/www/vantag/frontend/web",
    "npm run build",
]))
story.append(Paragraph("Wait for 'built in X.Xs' message before proceeding.", Note))
story.append(Spacer(1, 0.2*cm))

story.append(Paragraph("Step 5 — Restart the Backend Service", H2))
story.append(cmd_block([
    "sudo systemctl restart vantag",
]))
story.append(Spacer(1, 0.2*cm))

story.append(Paragraph("Step 6 — Verify the Update", H2))
story.append(cmd_block([
    "# Check backend env has correct keys",
    "grep 'RAZORPAY_KEY_ID_IN\\|RAZORPAY_KEY_SECRET_IN' /var/www/vantag/.env",
    "",
    "# Check frontend env",
    "grep 'VITE_RAZORPAY_KEY_ID' /var/www/vantag/frontend/web/.env",
    "",
    "# Confirm service is running",
    "sudo systemctl status vantag | head -20",
]))
story.append(success_box(
    "You should see your live key IDs printed (starting with rzp_live_) "
    "and vantag service status as 'active (running)'."))
story.append(PageBreak())

# ════════════════════════════════════════════════════════════════
# SECTION 3 — WEBHOOKS
# ════════════════════════════════════════════════════════════════
story.append(section_header("SECTION 3 — Set Up Razorpay Webhooks"))
story.append(Spacer(1, 0.3*cm))
story.append(Paragraph(
    "A webhook is an automatic notification that Razorpay sends to your server whenever a payment "
    "succeeds, fails, or a subscription is renewed. Without webhooks, your system might not "
    "automatically activate a user's account after payment. Webhooks make the billing fully automatic.",
    BodyJ))
story.append(Spacer(1, 0.3*cm))

story.append(info_box("Your Webhook URL (India):",
    "https://retailnazar.com/api/billing/webhook/IN", border=GREEN,
    bg=colors.HexColor("#d4edda")))
story.append(Spacer(1, 0.3*cm))

story.append(Paragraph("Part A — Configure Webhook in Razorpay Dashboard", H2))
story.append(Spacer(1, 0.1*cm))

steps_razorpay = [
    ("1", "Log in to Razorpay Dashboard", "Go to https://dashboard.razorpay.com and make sure you are in <b>Live Mode</b> (not Test Mode)."),
    ("2", "Open Webhook Settings", "Go to <b>Settings</b> (left sidebar) → <b>Webhooks</b> → click <b>+ Add New Webhook</b>."),
    ("3", "Enter Webhook URL",
     "In the <b>Webhook URL</b> field, paste exactly:<br/>"
     "<font name='Courier' size='9' color='#0f3460'>https://retailnazar.com/api/billing/webhook/IN</font>"),
    ("4", "Create a Webhook Secret",
     "In the <b>Secret</b> field, type a strong password (e.g. a random 32-character string). "
     "<b>Save this secret — you will need it in Part B below.</b>"),
    ("5", "Select Events to Subscribe",
     "Check all of the following events:<br/>"
     "• payment.captured<br/>"
     "• payment.failed<br/>"
     "• subscription.charged<br/>"
     "• subscription.activated<br/>"
     "• subscription.cancelled"),
    ("6", "Save", "Click <b>Save</b>. Razorpay will show a green tick. Your webhook is now active."),
]

for num, title, desc in steps_razorpay:
    row_data = [[Paragraph(num, StepNum), Paragraph(f"<b>{title}</b><br/>{desc}", Body)]]
    row_tbl = Table(row_data, colWidths=[1.2*cm, 15.3*cm])
    row_tbl.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LINEBELOW", (0,0), (-1,-1), 0.3, colors.HexColor("#dddddd")),
    ]))
    story.append(row_tbl)
story.append(Spacer(1, 0.4*cm))

story.append(Paragraph("Part B — Add Webhook Secret to VPS", H2))
story.append(Paragraph(
    "The webhook secret you created in Razorpay (Step 4 above) must also be added to the VPS "
    "so that your server can verify that incoming webhook calls are genuinely from Razorpay "
    "and not from an attacker.",
    Body))
story.append(cmd_block([
    "# Add the webhook secret to backend .env",
    "# Replace YOUR_WEBHOOK_SECRET with the secret you typed in Razorpay dashboard",
    "echo 'RAZORPAY_WEBHOOK_SECRET_IN=YOUR_WEBHOOK_SECRET' >> /var/www/vantag/.env",
    "",
    "# Verify it was added",
    "grep 'RAZORPAY_WEBHOOK_SECRET_IN' /var/www/vantag/.env",
]))
story.append(Spacer(1, 0.2*cm))

story.append(Paragraph("Part C — Restart Backend to Apply Changes", H2))
story.append(cmd_block([
    "sudo systemctl restart vantag",
    "sudo systemctl status vantag | head -5",
]))
story.append(Spacer(1, 0.2*cm))

story.append(Paragraph("Part D — Test the Webhook", H2))
story.append(bullet("In Razorpay Dashboard → Webhooks → click your webhook → <b>Test Webhook</b>"))
story.append(bullet("Select event type <b>payment.captured</b> → Send"))
story.append(bullet("The status should show <b>200 OK</b>. If you see 400, the secret is wrong."))
story.append(Spacer(1, 0.2*cm))

story.append(Paragraph("Part E — Update Webhook Secret (Future Rotation)", H2))
story.append(Paragraph("If you ever change the webhook secret in Razorpay, update the VPS:", Body))
story.append(cmd_block([
    "# Remove old secret and add new one",
    "sed -i '/RAZORPAY_WEBHOOK_SECRET_IN/d' /var/www/vantag/.env",
    "echo 'RAZORPAY_WEBHOOK_SECRET_IN=NEW_SECRET_HERE' >> /var/www/vantag/.env",
    "sudo systemctl restart vantag",
]))
story.append(PageBreak())

# ════════════════════════════════════════════════════════════════
# SECTION 4 — PLAN IDs
# ════════════════════════════════════════════════════════════════
story.append(section_header("SECTION 4 — Add Razorpay Subscription Plan IDs"))
story.append(Spacer(1, 0.3*cm))
story.append(Paragraph(
    "Razorpay Subscription Plans allow customers to be billed automatically every month. "
    "You create a plan once in the Razorpay dashboard, and Razorpay gives you a Plan ID "
    "(format: plan_XXXX...). This ID is then added to your code so the correct plan is selected "
    "when a customer subscribes.",
    BodyJ))
story.append(Spacer(1, 0.3*cm))

story.append(Paragraph("Your 4 Plans at a Glance", H2))
plan_rows = [
    ["Plan Name", "Plan ID (Code)", "Price (INR/month)", "Cameras"],
    ["Starter",   "starter",        "Rs. 1,999",          "Up to 4"],
    ["Growth",    "growth",         "Rs. 4,499",          "Up to 10"],
    ["Pro",       "pro",            "Rs. 9,999",          "Up to 20"],
    ["Pro Plus",  "proplus",        "Rs. 15,000",         "Up to 30"],
]
ptbl = Table(plan_rows, colWidths=[3.5*cm, 3.5*cm, 4.5*cm, 5*cm])
ptbl.setStyle(TableStyle([
    ("BACKGROUND", (0,0), (-1,0), NAVY),
    ("TEXTCOLOR", (0,0), (-1,0), WHITE),
    ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
    ("FONTSIZE", (0,0), (-1,-1), 9),
    ("ROWBACKGROUNDS", (0,1), (-1,-1), [WHITE, LGREY]),
    ("GRID", (0,0), (-1,-1), 0.3, colors.HexColor("#cccccc")),
    ("LEFTPADDING", (0,0), (-1,-1), 8),
    ("TOPPADDING", (0,0), (-1,-1), 5),
    ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ("ALIGN", (2,1), (-1,-1), "CENTER"),
]))
story.append(ptbl)
story.append(Spacer(1, 0.4*cm))

story.append(Paragraph("Part A — Create Plans in Razorpay Dashboard", H2))
plan_steps = [
    ("1", "Go to Razorpay Dashboard → Products → Subscriptions → Plans → + Create Plan"),
    ("2", "For each plan, fill in:<br/>• <b>Plan Name:</b> e.g. 'Retail Nazar Starter'<br/>• <b>Billing Amount:</b> 1999 (in rupees)<br/>• <b>Billing Cycle:</b> Monthly<br/>• <b>Currency:</b> INR"),
    ("3", "Click <b>Create Plan</b>. Copy the <b>Plan ID</b> shown (format: <font name='Courier'>plan_XXXXXXXXXXXXXX</font>)"),
    ("4", "Repeat for all 4 plans: Starter, Growth, Pro, Pro Plus"),
]
for num, desc in plan_steps:
    row_data = [[Paragraph(num, StepNum), Paragraph(desc, Body)]]
    row_tbl = Table(row_data, colWidths=[1.2*cm, 15.3*cm])
    row_tbl.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("TOPPADDING", (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ("LINEBELOW", (0,0), (-1,-1), 0.3, colors.HexColor("#dddddd")),
    ]))
    story.append(row_tbl)
story.append(Spacer(1, 0.4*cm))

story.append(Paragraph("Part B — Add Plan IDs to plans.py on VPS", H2))
story.append(Paragraph(
    "After you have all 4 Plan IDs from Razorpay, edit the plans.py file on the VPS:",
    Body))
story.append(cmd_block([
    "# Open the plans file in nano editor",
    "nano /var/www/vantag/backend/config/plans.py",
]))
story.append(Paragraph("Inside the file, find the section that looks like this:", Body))
story.append(cmd_block([
    '"razorpay_plan_ids": {',
    '    "INR": "",   # <-- replace empty string with your plan ID',
    '    "SGD": "",',
    '    "MYR": "",',
    '},',
]))
story.append(Paragraph("Replace the empty strings with your actual Plan IDs:", Body))
story.append(cmd_block([
    '"razorpay_plan_ids": {',
    '    "INR": "plan_XXXXXXXXXXXXXX",   # <-- paste your Razorpay plan ID here',
    '    "SGD": "",                       # leave blank if not selling in Singapore yet',
    '    "MYR": "",                       # leave blank if not selling in Malaysia yet',
    '},',
]))
story.append(Paragraph("To save in nano: press Ctrl+O then Enter, then Ctrl+X to exit.", Note))
story.append(Spacer(1, 0.2*cm))

story.append(Paragraph("Part C — Restart Backend", H2))
story.append(cmd_block([
    "sudo systemctl restart vantag",
]))
story.append(success_box(
    "Plan IDs are now active. Customers choosing a plan will be linked to the correct "
    "Razorpay subscription, and will be billed automatically every month."
))
story.append(PageBreak())

# ════════════════════════════════════════════════════════════════
# SECTION 5 — QUICK REFERENCE
# ════════════════════════════════════════════════════════════════
story.append(section_header("SECTION 5 — Common VPS Commands Reference"))
story.append(Spacer(1, 0.3*cm))

ref_data = [
    ["Task", "Command"],
    ["See all Razorpay env vars", "grep RAZORPAY /var/www/vantag/.env"],
    ["See all SMTP env vars", "grep SMTP /var/www/vantag/.env"],
    ["Restart backend", "sudo systemctl restart vantag"],
    ["Stop backend", "sudo systemctl stop vantag"],
    ["Start backend", "sudo systemctl start vantag"],
    ["Check backend status", "sudo systemctl status vantag"],
    ["View live logs", "journalctl -u vantag -f"],
    ["View last 100 log lines", "journalctl -u vantag -n 100 --no-pager"],
    ["Rebuild frontend", "cd /var/www/vantag/frontend/web && npm run build"],
    ["Reload nginx (no downtime)", "sudo systemctl reload nginx"],
    ["Restart nginx", "sudo systemctl restart nginx"],
    ["View nginx config", "cat /etc/nginx/sites-available/vantag"],
    ["Test nginx config", "nginx -t"],
    ["View full .env file", "cat /var/www/vantag/.env"],
    ["Edit .env file", "nano /var/www/vantag/.env"],
    ["Pull latest code from GitHub", "cd /var/www/vantag && git pull origin main"],
    ["Force reset to GitHub main", "git fetch origin main && git reset --hard origin/main"],
    ["Check current git commit", "git log --oneline -5"],
    ["Check disk space", "df -h"],
    ["Check memory usage", "free -h"],
]
ref_tbl = Table(ref_data, colWidths=[6*cm, 10.5*cm])
ref_tbl.setStyle(TableStyle([
    ("BACKGROUND", (0,0), (-1,0), NAVY),
    ("TEXTCOLOR", (0,0), (-1,0), WHITE),
    ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
    ("FONTSIZE", (0,0), (-1,-1), 8.5),
    ("ROWBACKGROUNDS", (0,1), (-1,-1), [WHITE, LGREY]),
    ("GRID", (0,0), (-1,-1), 0.3, colors.HexColor("#cccccc")),
    ("LEFTPADDING", (0,0), (-1,-1), 8),
    ("TOPPADDING", (0,0), (-1,-1), 5),
    ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ("FONTNAME", (1,1), (1,-1), "Courier"),
    ("TEXTCOLOR", (1,1), (1,-1), BLUE),
    ("FONTNAME", (0,1), (0,-1), "Helvetica-Bold"),
]))
story.append(ref_tbl)
story.append(PageBreak())

# ════════════════════════════════════════════════════════════════
# SECTION 6 — TROUBLESHOOTING
# ════════════════════════════════════════════════════════════════
story.append(section_header("SECTION 6 — Troubleshooting"))
story.append(Spacer(1, 0.3*cm))

troubles = [
    ("Payment popup shows 'International cards not supported'",
     "You are using a non-Indian test card (e.g. 4111 1111 1111 1111). "
     "This is blocked by Razorpay India. Use Netbanking for testing, or enable "
     "International Payments in Razorpay Dashboard → Settings → International Payments.",
     "Use Netbanking or enable International Cards in Razorpay dashboard settings."),

    ("Website still shows old prices after rebuild",
     "The browser is serving a cached version of the JavaScript files. "
     "The cache is either in the browser or in nginx.",
     "1. Hard refresh: Ctrl+Shift+R (Windows)\n"
     "2. Open incognito/private window and test\n"
     "3. Run: sudo systemctl reload nginx"),

    ("Webhook returns 400 error",
     "The webhook secret in your VPS .env does not match the secret you entered in Razorpay dashboard.",
     "Check the secret: grep RAZORPAY_WEBHOOK_SECRET_IN /var/www/vantag/.env\n"
     "Then compare with what is shown in Razorpay Dashboard → Settings → Webhooks."),

    ("Backend service not starting (systemctl start fails)",
     "There may be a syntax error in the .env file or Python code. Check the logs.",
     "Run: journalctl -u vantag -n 50 --no-pager\nLook for ERROR or Traceback lines."),

    ("OTP email not being received",
     "Gmail app password may have been revoked or SMTP settings are wrong.",
     "Run: grep SMTP /var/www/vantag/.env\n"
     "Ensure SMTP_FROM matches SMTP_USER exactly (both should be support@retailnazar.com).\n"
     "Check Gmail: myaccount.google.com/apppasswords"),

    ("Frontend shows blank page or error after rebuild",
     "The npm build failed with an error. Check the build output.",
     "Run: cd /var/www/vantag/frontend/web && npm run build 2>&1 | tail -30\n"
     "Fix any TypeScript/import errors shown, then rebuild."),

    ("git pull fails: 'divergent branches' error",
     "The VPS has local uncommitted changes that conflict with GitHub.",
     "Run: cd /var/www/vantag && git fetch origin main && git reset --hard origin/main\n"
     "WARNING: This discards any local VPS changes. Only use .env for local config."),
]

for problem, cause, solution in troubles:
    tbl_data = [
        [Paragraph(f"Problem: {problem}", H3)],
        [Paragraph(f"<b>Cause:</b> {cause}", Body)],
        [Paragraph(f"<b>Solution:</b><br/>{solution.replace(chr(10), '<br/>')}", Body)],
    ]
    t = Table(tbl_data, colWidths=[16.5*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,0), colors.HexColor("#fff0f0")),
        ("BACKGROUND", (0,1), (0,1), WHITE),
        ("BACKGROUND", (0,2), (0,2), colors.HexColor("#f0fff0")),
        ("LEFTPADDING", (0,0), (-1,-1), 10),
        ("RIGHTPADDING", (0,0), (-1,-1), 10),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LINEBEFORE", (0,0), (0,0), 4, ACCENT),
        ("LINEBEFORE", (0,2), (0,2), 4, GREEN),
        ("LINEBELOW", (0,-1), (-1,-1), 0.5, colors.HexColor("#cccccc")),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.3*cm))

story.append(Spacer(1, 0.5*cm))
story.append(hr(NAVY, 2))
story.append(Paragraph(
    "For further support contact support@retailnazar.com  |  BrainGuardX AI Technologies Pvt. Ltd.",
    S("footer", fontSize=8, textColor=DGREY, alignment=TA_CENTER, fontName="Helvetica-Oblique")))

# ── Build PDF ────────────────────────────────────────────────────
doc.build(story)
print(f"PDF created: {OUTPUT}")
