# -*- coding: utf-8 -*-
"""Build polished, print-friendly PDFs for the High-Value Counter launch.

Produces:
  1. high_value_counter_feature.pdf   (from the .md feature doc)
  2. high_value_counter_sales_pitch.pdf (from the .md sales pitch)
  3. high_value_counter_handout.pdf   (single-page leave-behind)

Fonts: Noto Sans Devanagari (covers Latin + Devanagari + the rupee sign),
bundled under Marketing/.fonts/ so the build is reproducible offline.
"""
import os
import re

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.fonts import addMapping
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether,
)

BASE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(BASE, ".fonts")
REG = os.path.join(FONT_DIR, "NotoSansDevanagari-Regular.ttf")
BOLD = os.path.join(FONT_DIR, "NotoSansDevanagari-Bold.ttf")

pdfmetrics.registerFont(TTFont("Noto", REG))
pdfmetrics.registerFont(TTFont("Noto-Bold", BOLD))
addMapping("Noto", 0, 0, "Noto")
addMapping("Noto", 1, 0, "Noto-Bold")
addMapping("Noto", 0, 1, "Noto")
addMapping("Noto", 1, 1, "Noto-Bold")

# ---- palette (matches the existing build_architecture_pdf.py theme) ----
INK    = colors.HexColor("#0F172A")
MUTED  = colors.HexColor("#475569")
SOFT   = colors.HexColor("#64748B")
CYAN   = colors.HexColor("#0E7490")
VIOLET = colors.HexColor("#6D28D9")
GREEN  = colors.HexColor("#047857")
RED    = colors.HexColor("#DC2626")
AMBER  = colors.HexColor("#B45309")
PANEL  = colors.HexColor("#F8FAFC")
PANEL2 = colors.HexColor("#F1F5F9")
LINE   = colors.HexColor("#CBD5E1")

INK_H, AMBER_H, CYAN_H = "#0F172A", "#B45309", "#0E7490"
VIOLET_H, GREEN_H, RED_H = "#6D28D9", "#047857", "#DC2626"

W, H = A4
M = 14 * mm
CW = W - 2 * M  # content width

# ----------------------------------------------------------------------
# text sanitising (strip emoji, keep what the bundled font can render)
# ----------------------------------------------------------------------
EMOJI = {
    "💎": "", "🎯": "", "▶️": "", "🖐️": "", "💍": "", "🏃": "",
    "☕": "", "🌅": "", "📌": "", "🔒": "",
    "🥇": "1", "🥈": "2", "🥉": "3",
    "✅": "", "❌": "", "✔": "", "⚠️": "",
    "⌚": "•", "👜": "•", "📱": "•", "👓": "•", "🏦": "•",
    "→": "›", "➡️": "›",
}


def _keep_char(ch):
    o = ord(ch)
    if 0x20 <= o <= 0x7E:
        return True
    if 0xA0 <= o <= 0xFF:
        return True
    if 0x0900 <= o <= 0x097F:  # Devanagari
        return True
    return o in (0x20B9, 0x203A, 0x00AB, 0x00BB)  # ₹ › « »


def clean(text):
    for k, v in EMOJI.items():
        text = text.replace(k, v)
    text = text.replace("\u00a0", " ")
    return "".join(ch for ch in text if _keep_char(ch))


def inline(text):
    text = clean(text)
    text = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)\*(?!\*)", r"<i>\1</i>", text)
    return text


# ----------------------------------------------------------------------
# styles
# ----------------------------------------------------------------------
def _style(name, **kw):
    base = dict(fontName="Noto", fontSize=9.5, leading=14,
                textColor=INK, alignment=TA_LEFT)
    base.update(kw)
    return ParagraphStyle(name, **base)


S_TITLE    = _style("title", fontName="Noto-Bold", fontSize=20, leading=25, textColor=colors.white)
S_SUBTITLE = _style("subtitle", fontSize=11, leading=16, textColor=colors.HexColor("#CBD5E1"))
S_META     = _style("meta", fontSize=7.5, leading=11, textColor=colors.HexColor("#94A3B8"))
S_H2       = _style("h2", fontName="Noto-Bold", fontSize=12.5, leading=16, spaceBefore=12, spaceAfter=3)
S_BODY     = _style("body", spaceAfter=5)
S_BULLET   = _style("bullet", leftIndent=12, firstLineIndent=-12, spaceAfter=3)
S_QUOTE    = _style("quote", fontSize=10, leading=15, textColor=INK)
S_CELL     = _style("cell", fontSize=8.6, leading=12)
S_CELL_B   = _style("cellb", fontName="Noto-Bold", fontSize=8.6, leading=12)
S_CELL_H   = _style("cellh", fontName="Noto-Bold", fontSize=8.8, leading=12, textColor=colors.white)


def h2(text):
    m = re.match(r"^(\d+\.)\s*(.*)$", text)
    if m:
        return Paragraph(
            f'<font color="{AMBER_H}">{m.group(1)}</font> {inline(m.group(2))}', S_H2)
    return Paragraph(inline(text), S_H2)


# ----------------------------------------------------------------------
# markdown -> flowables
# ----------------------------------------------------------------------
def parse_markdown(path):
    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")

    flow = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
            continue

        # headings
        if line.startswith("# "):
            flow.append(Paragraph(inline(line[2:]), S_TITLE))
            i += 1
        elif line.startswith("### "):
            flow.append(Paragraph(inline(line[4:]), S_SUBTITLE))
            flow.append(Spacer(1, 3 * mm))
            i += 1
        elif line.startswith("## "):
            flow.append(h2(line[3:]))
            flow.append(HRFlowable(width="100%", thickness=1.2,
                                   color=CYAN, spaceAfter=4))
            i += 1

        # horizontal rule
        elif line.strip() == "---":
            flow.append(Spacer(1, 3 * mm))
            flow.append(HRFlowable(width="100%", thickness=0.6,
                                   color=LINE, spaceBefore=2, spaceAfter=4))
            i += 1

        # blockquote
        elif line.startswith("> "):
            buf = []
            while i < n and lines[i].startswith("> "):
                buf.append(inline(lines[i][2:].strip()))
                i += 1
            body = " ".join(buf)
            quote = Paragraph(body, S_QUOTE)
            panel = Table([[quote]], colWidths=[CW])
            panel.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), PANEL),
                ("LINEBEFORE", (0, 0), (0, -1), 3, AMBER),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]))
            flow.append(panel)
            flow.append(Spacer(1, 3 * mm))

        # table
        elif line.lstrip().startswith("|"):
            rows = []
            while i < n and lines[i].lstrip().startswith("|"):
                raw = lines[i].strip()
                if set(raw.replace("|", "").replace("-", "").replace(":", "").strip()):
                    cells = [c.strip() for c in raw.strip("|").split("|")]
                    rows.append(cells)
                i += 1
            flow.append(render_table(rows))
            flow.append(Spacer(1, 3 * mm))

        # lists
        elif re.match(r"^\s*[-*] ", line) or re.match(r"^\s*\d+\.\s+", line):
            items = []
            while i < n:
                l = lines[i].rstrip()
                m_b = re.match(r"^\s*[-*] (.*)$", l)
                m_n = re.match(r"^\s*(\d+)\.\s+(.*)$", l)
                if m_b:
                    items.append(("b", m_b.group(1)))
                    i += 1
                elif m_n:
                    items.append(("n", l.strip()))
                    i += 1
                else:
                    break
            for kind, content in items:
                if kind == "b":
                    flow.append(Paragraph(
                        f'<font color="{AMBER_H}">•</font>&nbsp;&nbsp;{inline(content)}', S_BULLET))
                else:
                    flow.append(Paragraph(inline(content), S_BULLET))
            flow.append(Spacer(1, 1 * mm))

        # paragraph (join hard-wrapped lines)
        else:
            buf = [line]
            i += 1
            while i < n and lines[i].strip() and \
                    not lines[i].lstrip().startswith(("|", ">", "- ", "* ", "#")) and \
                    not re.match(r"^\s*\d+\.\s+", lines[i]) and \
                    lines[i].strip() != "---":
                buf.append(lines[i].rstrip())
                i += 1
            flow.append(Paragraph(inline(" ".join(buf)), S_BODY))

    return flow


def render_table(rows):
    header = [Paragraph(f"<b>{inline(c)}</b>" if c else " ", S_CELL_H) for c in rows[0]]
    body = []
    for r in rows[1:]:
        body.append([Paragraph(inline(c) if c else " ", S_CELL) for c in r])

    n = len(rows[0])
    lens = [0] * n
    for r in rows:
        for j, c in enumerate(r):
            lens[j] = max(lens[j], len(clean(c)))
    total = sum(lens) or n
    header_min = [stringWidth(clean(c), "Noto-Bold", 8.8) + 18 for c in rows[0]]
    widths = [max(CW * l / total, h) for l, h in zip(lens, header_min)]
    widths = [w * CW / sum(widths) for w in widths]

    data = [header] + body
    t = Table(data, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
        ("LINEAFTER", (0, 0), (-1, -2), 0.5, LINE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PANEL]),
    ]
    t.setStyle(TableStyle(style))
    return t


# ----------------------------------------------------------------------
# page chrome
# ----------------------------------------------------------------------
def cover(title, subtitle, meta):
    """Dark cover band rendered as a full-width table."""
    inner = [
        [Paragraph('<font color="#22D3EE">RETAIL NAZAR · HIGH-VALUE COUNTER</font>', S_META)],
        [Paragraph(inline(title), S_TITLE)],
        [Paragraph(inline(subtitle), S_SUBTITLE)],
        [Paragraph(inline(meta), S_META)],
    ]
    t = Table(inner, colWidths=[CW])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), INK),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))
    return t


def build_doc(out_path, doc_title, footer, flow):
    doc = SimpleDocTemplate(
        out_path, pagesize=A4,
        leftMargin=M, rightMargin=M, topMargin=13 * mm, bottomMargin=14 * mm,
        title=doc_title, author="BrainGuardX AI Technologies Pvt. Ltd.",
    )

    def _footer(canv, d):
        canv.saveState()
        canv.setFont("Noto", 7.5)
        canv.setFillColor(SOFT)
        canv.drawString(M, 9 * mm, footer)
        canv.drawRightString(W - M, 9 * mm, f"Page {d.page}")
        if d.page > 1:
            canv.setStrokeColor(LINE)
            canv.setLineWidth(0.5)
            canv.line(M, H - 10 * mm, W - M, H - 10 * mm)
        canv.restoreState()

    doc.build(flow, onFirstPage=_footer, onLaterPages=_footer)


# ----------------------------------------------------------------------
# one-page handout (self-contained flyer)
# ----------------------------------------------------------------------
def build_handout(out_path):
    S_TITLE2 = _style("ht", fontName="Noto-Bold", fontSize=19, leading=23, textColor=colors.white)
    S_TAG = _style("htag", fontSize=10.5, leading=15, textColor=colors.HexColor("#CBD5E1"))
    S_H3 = _style("h3", fontName="Noto-Bold", fontSize=11, leading=14, spaceBefore=6, spaceAfter=3)
    S_SMALL = _style("small", fontSize=8.4, leading=12, spaceAfter=4)
    S_CARD_T = _style("cardt", fontName="Noto-Bold", fontSize=10, leading=13, textColor=colors.white)
    S_CARD_B = _style("cardb", fontSize=8.3, leading=11.5, textColor=colors.HexColor("#E2E8F0"))

    flow = []
    # header
    flow.append(cover(
        "High-Value Counter",
        "No shelves. No POS. Still caught.",
        "AI theft detection for jewellers, watch boutiques & luxury counters  ·  BrainGuardX AI Technologies Pvt. Ltd.",
    ))
    flow.append(Spacer(1, 4 * mm))

    # four detector cards (2 x 2)
    cards = [
        ("CASE HAND REACH",
         "A hand dips into the display tray, stays, then withdraws. Tracks the actual fingertip — 21-point hand tracking.",
         RED_H),
        ("TRAY CHANGE",
         "The tray contents visibly drop (an item removed) while a person is at the counter.",
         VIOLET_H),
        ("GRAB & RUN",
         "A person moves from the display case to the exit door unusually fast — the highest-weighted signal.",
         AMBER_H),
        ("FULL CHAIN DEMO",
         "One click replays all three signals in story order — demo the flow live with zero real theft.",
         GREEN_H),
    ]
    card_rows = []
    for a, b in (cards[0:2], cards[2:4]):
        cells = []
        for title, body, accent in (a, b):
            inner = [[Paragraph(title, S_CARD_T)],
                     [Paragraph(body, S_CARD_B)]]
            t = Table(inner, colWidths=[(CW / 2) - 4 * mm])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), INK),
                ("LINEBELOW", (0, 0), (-1, 0), 2, colors.HexColor(accent)),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]))
            cells.append(t)
        card_rows.append([cells[0], "", cells[1]])
    ct = Table(card_rows, colWidths=[CW / 2 - 4 * mm, 8 * mm, CW / 2 - 4 * mm])
    ct.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    flow.append(ct)
    flow.append(Spacer(1, 4 * mm))

    # why it's different
    flow.append(h2("Why it's different"))
    flow.append(HRFlowable(width="100%", thickness=1.2, color=CYAN, spaceAfter=3))
    diff = [
        ("One camera, many brains", "hand-reach + tray-change + grab-and-run, plus loitering, fall & queue detection — all at once."),
        ("Per-finger precision", "MediaPipe 21-point hand tracking measures the real fingertip entering the tray."),
        ("No POS, no shelves, no new cameras", "connects to the Hikvision / Dahua / ONVIF cameras the shop already owns."),
        ("Runs on the edge, real-time", "video is analysed on-site; alerts reach the owner's phone in under a second."),
    ]
    for k, v in diff:
        flow.append(Paragraph(
            f'<b><font color="{CYAN_H}">›</font> {k}</b> — {v}', S_SMALL))
    flow.append(Spacer(1, 3 * mm))

    # roi strip
    roi = Paragraph(
        '<b>One prevented theft pays for the year.</b> A single lost chain/watch is ₹50,000–₹3,00,000; '
        'Retail Nazar Starter is ₹1,999/month (~₹24,000/year). If it stops one ₹50,000 piece, you are already ahead — '
        'and it keeps guarding every day after.',
        _style("roi", fontSize=9.2, leading=13.5, textColor=INK))
    panel = Table([[roi]], colWidths=[CW])
    panel.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ECFEFF")),
        ("LINEBEFORE", (0, 0), (0, -1), 3, GREEN),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    flow.append(panel)
    flow.append(Spacer(1, 4 * mm))

    # how to see it
    flow.append(h2("See it live in 2 minutes"))
    flow.append(HRFlowable(width="100%", thickness=1.2, color=CYAN, spaceAfter=3))
    steps = [
        "Open the dashboard → High-Value Counter page.",
        "Draw the Serving Counter, Display Tray, Display Case and Exit Door on the live snapshot.",
        "Save, then go to Demo Center → \"Fire High-Value Counter Demo\" and watch the alerts land in Incidents.",
    ]
    for idx, s in enumerate(steps, 1):
        flow.append(Paragraph(
            f'<font color="{AMBER_H}"><b>{idx}.</b></font>&nbsp;&nbsp;{inline(s)}', S_BULLET))
    flow.append(Spacer(1, 4 * mm))

    # footer contact
    foot = Table([[Paragraph(
        '<font color="#22D3EE"><b>Retail Nazar</b></font>  ·  '
        'support@retailnazar.com  ·  retailnazar.com  ·  '
        'Jewellery · Watches · Luxury Bags · Electronics Showcases · Phones & Accessories', S_META)]],
        colWidths=[CW])
    foot.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), INK),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    flow.append(foot)

    build_doc(out_path, "High-Value Counter — One-Page Handout",
              "Retail Nazar · High-Value Counter", flow)


# ----------------------------------------------------------------------
def main():
    feature = os.path.join(BASE, "high_value_counter_feature.md")
    pitch = os.path.join(BASE, "high_value_counter_sales_pitch.md")

    f = parse_markdown(feature)
    build_doc(os.path.join(BASE, "high_value_counter_feature.pdf"),
              "High-Value Counter — Feature & Go-To-Market Overview",
              "Retail Nazar · High-Value Counter · Feature Overview", f)

    p = parse_markdown(pitch)
    build_doc(os.path.join(BASE, "high_value_counter_sales_pitch.pdf"),
              "High-Value Counter — Retail Sales Pitch Playbook",
              "Retail Nazar · High-Value Counter · Sales Pitch Playbook", p)

    build_handout(os.path.join(BASE, "high_value_counter_handout.pdf"))

    for name in ("high_value_counter_feature.pdf",
                 "high_value_counter_sales_pitch.pdf",
                 "high_value_counter_handout.pdf"):
        path = os.path.join(BASE, name)
        print(f"WROTE {name} ({os.path.getsize(path):,} bytes)")


if __name__ == "__main__":
    main()
