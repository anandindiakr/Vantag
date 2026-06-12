"""
backend/reporting/report_generator.py
=======================================
Automated incident PDF report generator for the Vantag platform.

``ReportGenerator`` produces a professional, multi-section PDF from an
incident payload dict.  The generated file is saved to
``snapshots/reports/<report_id>.pdf`` and the absolute path is returned.

PDF structure
-------------
1. **Header** — Vantag logo (text), store name, report ID.
2. **Incident Summary** — timestamp, camera, behaviour type, risk score.
3. **Frame Snapshots** — up to 4 annotated JPEG frames embedded as images.
4. **Predictive Score** — risk score at the time of the incident.
5. **Event Timeline** — table of the last 10 events before the incident.
6. **Footer** — page number, generation timestamp, confidentiality notice.

Usage
-----
::

    from backend.reporting import ReportGenerator

    rg = ReportGenerator(output_dir="snapshots/reports")
    path = rg.generate(incident, output_path="snapshots/reports/abc123.pdf")
    print(path)  # absolute path to the PDF
"""

from __future__ import annotations

import base64
import io
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ReportLab imports — deferred at module level so the rest of the platform
# can import this module even on environments where reportlab isn't yet
# installed (the error surfaces only when generate() is called).
# ---------------------------------------------------------------------------
try:
    from reportlab.lib import colors  # type: ignore[import]
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT  # type: ignore[import]
    from reportlab.lib.pagesizes import A4  # type: ignore[import]
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle  # type: ignore[import]
    from reportlab.lib.units import cm, mm  # type: ignore[import]
    from reportlab.lib.utils import ImageReader  # type: ignore[import]
    from reportlab.platypus import (  # type: ignore[import]
        BaseDocTemplate,
        Frame,
        Image,
        NextPageTemplate,
        PageBreak,
        PageTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )
    from reportlab.platypus.flowables import HRFlowable  # type: ignore[import]

    _REPORTLAB_AVAILABLE = True
except ImportError as _rl_err:  # noqa: BLE001
    _REPORTLAB_AVAILABLE = False
    logger.warning(
        "ReportGenerator: reportlab is not installed (%s). "
        "PDF generation will be unavailable.",
        _rl_err,
    )


# ---------------------------------------------------------------------------
# Colour palette (Vantag brand colours)
# ---------------------------------------------------------------------------
_BRAND_DARK = colors.HexColor("#0F1923")      # near-black
_BRAND_ACCENT = colors.HexColor("#00C2FF")    # electric blue
_BRAND_HIGH = colors.HexColor("#FF3B30")      # high-severity red
_BRAND_MED = colors.HexColor("#FF9500")       # medium-severity amber
_BRAND_LOW = colors.HexColor("#34C759")       # low-severity green
_GREY_BG = colors.HexColor("#F5F6F8")         # light grey table background
_GREY_LINE = colors.HexColor("#D1D5DB")       # table border grey


def _severity_colour(severity: str) -> Any:
    s = str(severity).upper()
    if s in ("HIGH", "CRITICAL"):
        return _BRAND_HIGH
    if s == "MEDIUM":
        return _BRAND_MED
    return _BRAND_LOW


# ---------------------------------------------------------------------------
# Page template helpers
# ---------------------------------------------------------------------------

class _ReportCanvas:
    """Mixin applied via onPage callback to draw headers and footers."""

    def __init__(self, report_id: str, store_name: str, generated_at: str) -> None:
        self.report_id = report_id
        self.store_name = store_name
        self.generated_at = generated_at

    def draw(self, canvas: Any, doc: Any) -> None:
        canvas.saveState()
        page_w, page_h = A4

        # ---------- Header bar ----------
        canvas.setFillColor(_BRAND_DARK)
        canvas.rect(0, page_h - 2.2 * cm, page_w, 2.2 * cm, fill=1, stroke=0)

        canvas.setFillColor(_BRAND_ACCENT)
        canvas.setFont("Helvetica-Bold", 14)
        canvas.drawString(1.5 * cm, page_h - 1.4 * cm, "VANTAG")
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica", 9)
        canvas.drawString(4.0 * cm, page_h - 1.4 * cm, "Retail AI Surveillance Platform")

        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(
            page_w - 1.5 * cm,
            page_h - 1.0 * cm,
            f"Store: {self.store_name}",
        )
        canvas.drawRightString(
            page_w - 1.5 * cm,
            page_h - 1.6 * cm,
            f"Report: {self.report_id}",
        )

        # ---------- Footer bar ----------
        canvas.setFillColor(_BRAND_DARK)
        canvas.rect(0, 0, page_w, 1.5 * cm, fill=1, stroke=0)

        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(
            1.5 * cm,
            0.6 * cm,
            f"Generated: {self.generated_at} UTC  |  "
            "CONFIDENTIAL — For authorised personnel only",
        )
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawRightString(
            page_w - 1.5 * cm,
            0.6 * cm,
            f"Page {doc.page}",
        )

        canvas.restoreState()


# ---------------------------------------------------------------------------
# ReportGenerator
# ---------------------------------------------------------------------------

class ReportGenerator:
    """
    Automated incident PDF report generator.

    Parameters
    ----------
    output_dir:
        Directory where generated PDFs are saved.  Created automatically if
        it does not exist.  Defaults to ``"snapshots/reports"``.
    """

    def __init__(self, output_dir: str = "snapshots/reports") -> None:
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, incident: Dict[str, Any], output_path: Optional[str] = None) -> str:
        """
        Generate a PDF incident report.

        Parameters
        ----------
        incident:
            Incident payload dict.  Expected keys (all optional except
            ``report_id``):

            * ``report_id`` (str) — unique report / incident ID.
            * ``store_name`` (str) — store display name.
            * ``camera_id`` (str) — originating camera identifier.
            * ``behavior_type`` (str) — e.g. ``'loitering'``, ``'tamper'``.
            * ``timestamp`` (str | datetime) — ISO-8601 or datetime object.
            * ``risk_score`` (float) — risk score at the time of incident.
            * ``severity`` (str) — ``'LOW'``, ``'MEDIUM'``, ``'HIGH'``, or
              ``'CRITICAL'``.
            * ``description`` (str) — free-text description.
            * ``snapshots`` (list[str]) — list of base64-encoded JPEG
              strings (up to 4 shown in the report).
            * ``predictive_score`` (float) — model-predicted future risk.
            * ``predictive_label`` (str) — human label for the prediction.
            * ``timeline`` (list[dict]) — last 10 events before incident.
              Each dict should have ``timestamp``, ``event_type``,
              ``camera_id``, and ``severity``.

        output_path:
            Absolute or relative path for the output ``.pdf`` file.  If
            ``None``, the file is created at
            ``<output_dir>/<report_id>.pdf``.

        Returns
        -------
        str
            Absolute path to the generated PDF file.

        Raises
        ------
        RuntimeError
            If ``reportlab`` is not installed.
        """
        if not _REPORTLAB_AVAILABLE:
            raise RuntimeError(
                "ReportGenerator.generate() requires 'reportlab'. "
                "Install it with: pip install reportlab"
            )

        report_id = str(incident.get("report_id", "unknown"))
        store_name = str(incident.get("store_name", "Unknown Store"))
        camera_id = str(incident.get("camera_id", "—"))
        behavior_type = str(incident.get("behavior_type", "—"))
        severity = str(incident.get("severity", "LOW"))
        description = str(incident.get("description", "No description provided."))
        risk_score = float(incident.get("risk_score", 0.0))
        predictive_score = incident.get("predictive_score")
        predictive_label = str(incident.get("predictive_label", "—"))
        snapshots: List[str] = incident.get("snapshots", [])
        timeline: List[Dict] = incident.get("timeline", [])

        # Normalise timestamp.
        raw_ts = incident.get("timestamp", datetime.now(tz=timezone.utc))
        if isinstance(raw_ts, datetime):
            ts_str = raw_ts.strftime("%Y-%m-%d %H:%M:%S")
        else:
            ts_str = str(raw_ts)

        generated_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # Determine output path.
        if output_path:
            pdf_path = Path(output_path)
        else:
            pdf_path = self._output_dir / f"{report_id}.pdf"

        pdf_path.parent.mkdir(parents=True, exist_ok=True)

        # Build the PDF.
        self._build_pdf(
            pdf_path=pdf_path,
            report_id=report_id,
            store_name=store_name,
            camera_id=camera_id,
            behavior_type=behavior_type,
            severity=severity,
            description=description,
            ts_str=ts_str,
            risk_score=risk_score,
            predictive_score=predictive_score,
            predictive_label=predictive_label,
            snapshots=snapshots,
            timeline=timeline,
            generated_at=generated_at,
        )

        abs_path = str(pdf_path.resolve())
        logger.info("ReportGenerator: PDF written to '%s'.", abs_path)
        return abs_path

    # ------------------------------------------------------------------
    # Private build helpers
    # ------------------------------------------------------------------

    def _build_pdf(
        self,
        pdf_path: Path,
        report_id: str,
        store_name: str,
        camera_id: str,
        behavior_type: str,
        severity: str,
        description: str,
        ts_str: str,
        risk_score: float,
        predictive_score: Optional[float],
        predictive_label: str,
        snapshots: List[str],
        timeline: List[Dict],
        generated_at: str,
    ) -> None:
        """Assemble all PDF flowables and build the document."""

        styles = getSampleStyleSheet()
        style_normal = styles["Normal"]

        # Custom styles.
        heading1 = ParagraphStyle(
            "VantagH1",
            parent=styles["Heading1"],
            fontSize=16,
            textColor=_BRAND_DARK,
            spaceAfter=6,
            spaceBefore=12,
        )
        heading2 = ParagraphStyle(
            "VantagH2",
            parent=styles["Heading2"],
            fontSize=12,
            textColor=_BRAND_DARK,
            spaceAfter=4,
            spaceBefore=10,
            borderPad=(0, 0, 2, 0),
        )
        body = ParagraphStyle(
            "VantagBody",
            parent=styles["Normal"],
            fontSize=9,
            leading=14,
            textColor=colors.HexColor("#2D3748"),
        )
        label_style = ParagraphStyle(
            "VantagLabel",
            parent=body,
            fontSize=8,
            textColor=colors.HexColor("#718096"),
        )
        value_style = ParagraphStyle(
            "VantagValue",
            parent=body,
            fontSize=10,
            fontName="Helvetica-Bold",
            textColor=_BRAND_DARK,
        )
        caption_style = ParagraphStyle(
            "VantagCaption",
            parent=body,
            fontSize=7,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#718096"),
        )
        sev_colour = _severity_colour(severity)

        # ---------- Canvas callback ----------
        canvas_helper = _ReportCanvas(report_id, store_name, generated_at)

        # ---------- Document ----------
        page_w, page_h = A4
        margin_h = 1.5 * cm
        margin_v = 2.8 * cm   # top/bottom reserves space for header/footer
        content_w = page_w - 2 * margin_h

        doc = BaseDocTemplate(
            str(pdf_path),
            pagesize=A4,
            leftMargin=margin_h,
            rightMargin=margin_h,
            topMargin=margin_v,
            bottomMargin=margin_v,
        )
        frame = Frame(
            margin_h,
            margin_v,
            content_w,
            page_h - 2 * margin_v,
            id="main",
        )
        template = PageTemplate(
            id="main",
            frames=[frame],
            onPage=canvas_helper.draw,
        )
        doc.addPageTemplates([template])

        # ---------- Flowables ----------
        story = []

        # --- Report title ---
        story.append(Spacer(1, 0.3 * cm))
        story.append(Paragraph("Incident Report", heading1))
        story.append(
            HRFlowable(
                width="100%",
                thickness=2,
                color=_BRAND_ACCENT,
                spaceAfter=8,
            )
        )

        # --- Section 1: Incident Summary ---
        story.append(Paragraph("1. Incident Summary", heading2))
        story.append(
            HRFlowable(width="100%", thickness=0.5, color=_GREY_LINE, spaceAfter=6)
        )

        summary_data = [
            ["Report ID", report_id],
            ["Store", store_name],
            ["Camera", camera_id],
            ["Timestamp", ts_str],
            ["Behaviour Type", behavior_type],
            ["Severity", severity.upper()],
            ["Risk Score", f"{risk_score:.1f} / 100"],
            ["Description", description],
        ]
        summary_col_widths = [4.5 * cm, content_w - 4.5 * cm]
        summary_table = Table(summary_data, colWidths=summary_col_widths)
        summary_table.setStyle(
            TableStyle(
                [
                    # Header column styling.
                    ("BACKGROUND", (0, 0), (0, -1), _GREY_BG),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (0, -1), 8),
                    ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#4A5568")),
                    # Value column.
                    ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                    ("FONTSIZE", (1, 0), (1, -1), 9),
                    ("TEXTCOLOR", (1, 0), (1, -1), _BRAND_DARK),
                    # Severity row — coloured text.
                    ("TEXTCOLOR", (1, 5), (1, 5), sev_colour),
                    ("FONTNAME", (1, 5), (1, 5), "Helvetica-Bold"),
                    # Grid.
                    ("GRID", (0, 0), (-1, -1), 0.4, _GREY_LINE),
                    ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, _GREY_BG]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(summary_table)
        story.append(Spacer(1, 0.4 * cm))

        # --- Section 2: Frame Snapshots ---
        story.append(Paragraph("2. Frame Snapshots", heading2))
        story.append(
            HRFlowable(width="100%", thickness=0.5, color=_GREY_LINE, spaceAfter=6)
        )

        if snapshots:
            # Show up to 4 images in a 2-column grid.
            images_to_show = snapshots[:4]
            img_w = (content_w - 0.5 * cm) / 2   # 2 columns with gap
            img_h = img_w * (9 / 16)               # 16:9 aspect ratio

            img_rows = []
            for i in range(0, len(images_to_show), 2):
                row = []
                for j in range(2):
                    idx = i + j
                    if idx < len(images_to_show):
                        img_flowable = self._base64_to_image(
                            images_to_show[idx], img_w, img_h
                        )
                        cap = Paragraph(
                            f"Frame {idx + 1}", caption_style
                        )
                        cell = [img_flowable, cap] if img_flowable else [
                            Paragraph(f"[Snapshot {idx + 1} unavailable]", body)
                        ]
                    else:
                        cell = [Paragraph("", body)]
                    row.append(cell)
                img_rows.append(row)

            snapshot_table = Table(
                img_rows,
                colWidths=[img_w, img_w],
                hAlign="LEFT",
            )
            snapshot_table.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 3),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ]
                )
            )
            story.append(snapshot_table)
        else:
            story.append(
                Paragraph("No frame snapshots were captured for this incident.", body)
            )
        story.append(Spacer(1, 0.4 * cm))

        # --- Section 3: Predictive Score ---
        story.append(Paragraph("3. Predictive Risk Score at Incident", heading2))
        story.append(
            HRFlowable(width="100%", thickness=0.5, color=_GREY_LINE, spaceAfter=6)
        )

        if predictive_score is not None:
            pred_colour = _severity_colour(
                "HIGH" if predictive_score >= 70 else "MEDIUM" if predictive_score >= 30 else "LOW"
            )
            pred_data = [
                ["Predictive Score", f"{predictive_score:.1f} / 100"],
                ["Label", predictive_label],
            ]
            pred_table = Table(pred_data, colWidths=[4.5 * cm, content_w - 4.5 * cm])
            pred_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (0, -1), _GREY_BG),
                        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (0, -1), 8),
                        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#4A5568")),
                        ("FONTNAME", (1, 0), (1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (1, 0), (1, 0), 11),
                        ("TEXTCOLOR", (1, 0), (1, 0), pred_colour),
                        ("FONTNAME", (1, 1), (1, 1), "Helvetica"),
                        ("FONTSIZE", (1, 1), (1, 1), 9),
                        ("GRID", (0, 0), (-1, -1), 0.4, _GREY_LINE),
                        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, _GREY_BG]),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )
            story.append(pred_table)
        else:
            story.append(
                Paragraph(
                    "Predictive score was not available at the time of this incident.",
                    body,
                )
            )
        story.append(Spacer(1, 0.4 * cm))

        # --- Section 4: Event Timeline ---
        story.append(Paragraph("4. Event Timeline (Last 10 Events Before Incident)", heading2))
        story.append(
            HRFlowable(width="100%", thickness=0.5, color=_GREY_LINE, spaceAfter=6)
        )

        if timeline:
            events = timeline[-10:]  # safety cap
            tl_header = [
                Paragraph("<b>#</b>", label_style),
                Paragraph("<b>Timestamp</b>", label_style),
                Paragraph("<b>Event Type</b>", label_style),
                Paragraph("<b>Camera</b>", label_style),
                Paragraph("<b>Severity</b>", label_style),
            ]
            tl_col_widths = [
                1.2 * cm,
                4.5 * cm,
                content_w - 1.2 * cm - 4.5 * cm - 3.5 * cm - 2.5 * cm,
                3.5 * cm,
                2.5 * cm,
            ]
            tl_data = [tl_header]
            for n, ev in enumerate(events, start=1):
                ev_ts = str(ev.get("timestamp", "—"))
                ev_type = str(ev.get("event_type", "—"))
                ev_cam = str(ev.get("camera_id", "—"))
                ev_sev = str(ev.get("severity", "—")).upper()
                sev_col = _severity_colour(ev_sev)
                tl_data.append(
                    [
                        Paragraph(str(n), body),
                        Paragraph(ev_ts, body),
                        Paragraph(ev_type, body),
                        Paragraph(ev_cam, body),
                        Paragraph(
                            f'<font color="#{sev_col.hexval()[1:]}">{ev_sev}</font>',
                            body,
                        ),
                    ]
                )

            tl_table = Table(tl_data, colWidths=tl_col_widths, repeatRows=1)
            tl_table.setStyle(
                TableStyle(
                    [
                        # Header row.
                        ("BACKGROUND", (0, 0), (-1, 0), _BRAND_DARK),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, 0), 8),
                        # Data rows.
                        ("FONTSIZE", (0, 1), (-1, -1), 8),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _GREY_BG]),
                        # Grid.
                        ("GRID", (0, 0), (-1, -1), 0.3, _GREY_LINE),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ("LEFTPADDING", (0, 0), (-1, -1), 5),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ]
                )
            )
            story.append(tl_table)
        else:
            story.append(
                Paragraph("No prior events were recorded within the timeline window.", body)
            )

        story.append(Spacer(1, 0.5 * cm))

        # Build PDF.
        doc.build(story)

    # ------------------------------------------------------------------
    # Image helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _base64_to_image(
        b64_str: str,
        max_width: float,
        max_height: float,
    ) -> Optional[Any]:
        """
        Decode a base64-encoded JPEG/PNG string and return a ReportLab
        ``Image`` flowable scaled to fit within *max_width* × *max_height*.

        Returns ``None`` on decode failure.
        """
        try:
            # Strip data-URI prefix if present: "data:image/jpeg;base64,..."
            if "," in b64_str:
                b64_str = b64_str.split(",", 1)[1]

            raw = base64.b64decode(b64_str)
            buf = io.BytesIO(raw)

            from PIL import Image as PILImage  # type: ignore[import]

            pil_img = PILImage.open(buf)
            orig_w, orig_h = pil_img.size

            # Scale to fit within bounding box while preserving aspect ratio.
            scale = min(max_width / orig_w, max_height / orig_h)
            draw_w = orig_w * scale
            draw_h = orig_h * scale

            buf.seek(0)
            return Image(buf, width=draw_w, height=draw_h)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ReportGenerator: could not decode snapshot image: %s", exc
            )
            return None
