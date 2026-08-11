"""
backend/api/reports_router.py
==============================
Incident report management API for the Vantag platform.

Endpoints
---------
GET  /api/reports                         – list all generated reports
GET  /api/reports/{report_id}             – download a PDF report
POST /api/reports/generate/{incident_id}  – trigger manual report generation

Reports are stored as PDF files in the ``snapshots/reports/`` directory.
Metadata is maintained in-memory by the pipeline and persisted to a lightweight
JSON sidecar file on each write.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import FileResponse

from .models import ReportListResponse, ReportResponse
from ..middleware.tenant_middleware import get_current_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["Reports"])

# ---------------------------------------------------------------------------
# Directory configuration
# ---------------------------------------------------------------------------

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_REPORTS_DIR: Path = _BASE_DIR / "snapshots" / "reports"
_META_FILE: Path = _REPORTS_DIR / "reports_meta.json"

# ---------------------------------------------------------------------------
# In-memory report registry (loaded from / flushed to disk JSON sidecar)
# ---------------------------------------------------------------------------

_report_registry: Dict[str, dict] = {}


def _ensure_dir() -> None:
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def _load_registry() -> None:
    """Populate ``_report_registry`` from the JSON sidecar on disk."""
    global _report_registry  # noqa: PLW0603
    _ensure_dir()
    if _META_FILE.exists():
        try:
            with _META_FILE.open("r", encoding="utf-8") as fh:
                _report_registry = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load report registry | error=%s", exc)
            _report_registry = {}
    else:
        _report_registry = {}


def _flush_registry() -> None:
    """Persist the in-memory registry to the JSON sidecar."""
    _ensure_dir()
    try:
        with _META_FILE.open("w", encoding="utf-8") as fh:
            json.dump(_report_registry, fh, indent=2, default=str)
    except OSError as exc:
        logger.error("Failed to flush report registry | error=%s", exc)


def _register_report(
    report_id: str,
    incident_id: str,
    store_id: str,
    file_name: str,
    file_size: int,
    tenant_id: str | None = None,
) -> ReportResponse:
    now = datetime.now(tz=timezone.utc)
    entry = {
        "report_id": report_id,
        "incident_id": incident_id,
        "store_id": store_id,
        "tenant_id": tenant_id,
        "generated_at": now.isoformat(),
        "file_name": file_name,
        "file_size_bytes": file_size,
    }
    _report_registry[report_id] = entry
    _flush_registry()
    return _entry_to_model(entry)


def _entry_to_model(entry: dict) -> ReportResponse:
    return ReportResponse(
        report_id=entry["report_id"],
        incident_id=entry["incident_id"],
        store_id=entry["store_id"],
        generated_at=datetime.fromisoformat(entry["generated_at"]),
        file_name=entry["file_name"],
        file_size_bytes=int(entry["file_size_bytes"]),
    )


# Load registry at module import time.
_load_registry()


# ---------------------------------------------------------------------------
# PDF generation helper
# ---------------------------------------------------------------------------


def _resolve_snapshot_file(snapshot_url: str | None) -> Optional[Path]:
    """Map an ``/api/snapshots/...`` URL to its local file under snapshots/.

    Returns the file path if it exists on disk, else None. Rejects any path
    that escapes the snapshots root (path traversal safety).
    """
    if not snapshot_url:
        return None
    prefix = "/api/snapshots/"
    if not snapshot_url.startswith(prefix):
        return None
    rel = snapshot_url[len(prefix):]
    snapshots_root = (_BASE_DIR / "snapshots").resolve()
    try:
        candidate = (snapshots_root / rel).resolve()
        if candidate != snapshots_root and snapshots_root not in candidate.parents:
            return None
        return candidate if candidate.is_file() else None
    except OSError:
        return None


async def _resolve_occurred_at_local(
    camera_id: str,
    raw_timestamp: str,
    tenant_id: str | None = None,
) -> str:
    """
    Convert a stored UTC incident timestamp into a human-readable string in
    the camera's configured local time (falls back to UTC if the camera or
    its schedule tz_offset can't be resolved).

    The offset reused here (``analyzer_config.detection_schedule.tz_offset_minutes``)
    is the same value the camera's own Schedule tab already saves when a user
    configures active hours — so this uses a timezone that has actually been
    confirmed for that camera, rather than guessing the server's own timezone
    (which is UTC and was previously being shown to users unconverted).
    """
    if not raw_timestamp or raw_timestamp == "N/A":
        return "N/A"
    try:
        dt = datetime.fromisoformat(str(raw_timestamp).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return str(raw_timestamp)

    offset_minutes = 0
    try:
        from sqlalchemy import select

        from ..db.database import get_session
        from ..db.models.camera import CameraConfig

        async for session in get_session():
            stmt = select(CameraConfig).where(CameraConfig.camera_id == camera_id)
            if tenant_id:
                stmt = stmt.where(CameraConfig.tenant_id == tenant_id)
            row = (await session.execute(stmt)).scalars().first()
            if row is not None and row.analyzer_config:
                schedule = row.analyzer_config.get("detection_schedule") or {}
                offset_minutes = int(schedule.get("tz_offset_minutes") or 0)
            break
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Could not resolve camera tz offset for report | camera_id=%s error=%s",
            camera_id, exc,
        )

    from datetime import timedelta

    local_dt = dt.astimezone(timezone.utc) + timedelta(minutes=offset_minutes)
    sign = "+" if offset_minutes >= 0 else "-"
    hh, mm = divmod(abs(offset_minutes), 60)
    return f"{local_dt.strftime('%d %b %Y, %I:%M:%S %p')} (UTC{sign}{hh:02d}:{mm:02d})"


def _generate_pdf_report(
    report_id: str,
    incident_id: str,
    incident_data: dict,
    occurred_at_local: str = "",
) -> Path:
    """
    Generate a minimal PDF incident report.

    Uses ``reportlab`` if available; falls back to a plain-text file with a
    ``.pdf`` extension so the endpoint remains functional without the
    optional dependency.
    """
    _ensure_dir()
    file_name = f"report_{report_id}.pdf"
    file_path = _REPORTS_DIR / file_name

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        doc = SimpleDocTemplate(str(file_path), pagesize=A4)
        styles = getSampleStyleSheet()
        elements = []

        elements.append(Paragraph("Vantag Incident Report", styles["Title"]))
        elements.append(Spacer(1, 0.5 * cm))

        table_data = [
            ["Report ID", report_id],
            ["Incident ID", incident_id],
            ["Store", incident_data.get("store_id", "N/A")],
            ["Camera", incident_data.get("camera_id", "N/A")],
            ["Event Type", incident_data.get("type", "N/A")],
            ["Severity", incident_data.get("severity", "N/A")],
            ["Occurred At", occurred_at_local or str(incident_data.get("timestamp", "N/A"))],
            ["Generated At", datetime.now(tz=timezone.utc).isoformat()],
        ]

        table = Table(table_data, colWidths=[5 * cm, 12 * cm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), "#4A90D9"),
                    ("TEXTCOLOR", (0, 0), (0, -1), "#FFFFFF"),
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("GRID", (0, 0), (-1, -1), 0.5, "#CCCCCC"),
                    ("ROWBACKGROUNDS", (1, 0), (-1, -1), ["#F5F5F5", "#FFFFFF"]),
                ]
            )
        )
        elements.append(table)

        description = str(incident_data.get("description", "No description available."))
        from xml.sax.saxutils import escape
        description = escape(description)
        elements.append(Spacer(1, 0.5 * cm))
        elements.append(Paragraph(f"<b>Description:</b> {description}", styles["Normal"]))

        # Embed the event snapshot image when it exists on disk.
        snapshot_file = _resolve_snapshot_file(incident_data.get("snapshot_url"))
        if snapshot_file is not None:
            try:
                from reportlab.platypus import Image as RLImage

                elements.append(Spacer(1, 0.6 * cm))
                elements.append(Paragraph("<b>Event Snapshot:</b>", styles["Normal"]))
                elements.append(Spacer(1, 0.2 * cm))
                img = RLImage(str(snapshot_file))
                # Scale to fit page width (max 16 cm) keeping aspect ratio.
                max_w = 16 * cm
                if img.drawWidth > max_w:
                    scale = max_w / img.drawWidth
                    img.drawWidth *= scale
                    img.drawHeight *= scale
                elements.append(img)
            except Exception as img_exc:  # noqa: BLE001
                logger.warning(
                    "Could not embed snapshot in report | report_id=%s error=%s",
                    report_id, img_exc,
                )

        doc.build(elements)
        logger.info("PDF report generated | report_id=%s path=%s", report_id, file_path)

    except ImportError:
        # reportlab not installed – write a plain-text placeholder.
        logger.warning(
            "reportlab not installed; generating plain-text report | report_id=%s",
            report_id,
        )
        with file_path.open("w", encoding="utf-8") as fh:
            fh.write(f"VANTAG INCIDENT REPORT\n{'=' * 40}\n")
            fh.write(f"Report ID:   {report_id}\n")
            fh.write(f"Incident ID: {incident_id}\n")
            for key, value in incident_data.items():
                fh.write(f"{key.capitalize()}: {value}\n")
            fh.write(f"\nGenerated At: {datetime.now(tz=timezone.utc).isoformat()}\n")

    return file_path


# ---------------------------------------------------------------------------
# Pipeline reference
# ---------------------------------------------------------------------------

_pipeline = None  # type: ignore[assignment]


def set_pipeline(pipeline: object) -> None:  # noqa: ANN001
    global _pipeline  # noqa: PLW0603
    _pipeline = pipeline


def _find_incident(incident_id: str, tenant_id: str) -> Optional[dict]:
    """Search only the authenticated tenant's incidents."""
    if _pipeline is not None:
        for events in _pipeline.recent_events.values():
            for ev in events:
                if ev.get("incident_id") == incident_id and ev.get("tenant_id") == tenant_id:
                    return ev
    # Fallback: persisted incidents survive backend restarts.
    try:
        from ..db import incident_store as _istore  # lazy import

        return _istore.get_incident(incident_id, tenant_id=tenant_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Incident DB lookup failed | id=%s error=%s", incident_id, exc)
        return None


# ---------------------------------------------------------------------------
# Background report generation task
# ---------------------------------------------------------------------------


async def _bg_generate_report(report_id: str, incident_id: str, incident_data: dict) -> None:
    """Background task that generates the PDF and updates the registry."""
    store_id = incident_data.get("store_id", "unknown")
    try:
        occurred_at_local = await _resolve_occurred_at_local(
            incident_data.get("camera_id", ""),
            incident_data.get("timestamp", ""),
            incident_data.get("tenant_id"),
        )
        file_path = _generate_pdf_report(report_id, incident_id, incident_data, occurred_at_local)
        file_size = file_path.stat().st_size
        _register_report(
            report_id=report_id,
            incident_id=incident_id,
            store_id=store_id,
            file_name=file_path.name,
            file_size=file_size,
            tenant_id=incident_data.get("tenant_id"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Report generation failed | report_id=%s error=%s", report_id, exc
        )


# ---------------------------------------------------------------------------
# GET /api/reports
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=ReportListResponse,
    summary="List all generated reports",
)
async def list_reports(
    user: dict = Depends(get_current_user_id),
) -> ReportListResponse:
    """Return only reports generated for the authenticated tenant."""
    tenant_id = str(user.get("tenant_id"))
    reports = [
        _entry_to_model(e)
        for e in _report_registry.values()
        if e.get("tenant_id") == tenant_id
    ]
    reports.sort(key=lambda r: r.generated_at, reverse=True)
    return ReportListResponse(reports=reports)


# ---------------------------------------------------------------------------
# GET /api/reports/{report_id}
# ---------------------------------------------------------------------------


@router.get(
    "/incident/{incident_id}",
    summary="Generate and download an incident PDF",
    responses={200: {"content": {"application/pdf": {}}}},
)
async def download_incident_report(
    incident_id: str,
    user: dict = Depends(get_current_user_id),
) -> FileResponse:
    """Generate a report synchronously for the authenticated tenant's incident."""
    tenant_id = str(user.get("tenant_id"))
    incident_data = _find_incident(incident_id, tenant_id) or {
        "incident_id": incident_id,
        "store_id": "unknown",
        "tenant_id": tenant_id,
        "camera_id": "unknown",
        "type": "manual",
        "severity": "medium",
        "description": "Incident report.",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }
    report_id = str(uuid.uuid4())
    occurred_at_local = await _resolve_occurred_at_local(
        incident_data.get("camera_id", ""),
        incident_data.get("timestamp", ""),
        incident_data.get("tenant_id"),
    )
    file_path = _generate_pdf_report(report_id, incident_id, incident_data, occurred_at_local)
    _register_report(
        report_id=report_id,
        incident_id=incident_id,
        store_id=incident_data.get("store_id", "unknown"),
        file_name=file_path.name,
        file_size=file_path.stat().st_size,
        tenant_id=tenant_id,
    )
    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        filename=file_path.name,
    )


@router.get(
    "/{report_id}",
    summary="Download a PDF report",
    responses={200: {"content": {"application/pdf": {}}}},
)
async def download_report(
    report_id: str,
    user: dict = Depends(get_current_user_id),
) -> FileResponse:
    """Download a PDF report belonging to the authenticated tenant."""
    entry = _report_registry.get(report_id)
    if not entry or entry.get("tenant_id") != str(user.get("tenant_id")):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report '{report_id}' not found.",
        )

    file_path = _REPORTS_DIR / entry["file_name"]
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"Report file has been deleted from disk: {entry['file_name']}",
        )

    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        filename=entry["file_name"],
    )


# ---------------------------------------------------------------------------
# POST /api/reports/generate/{incident_id}
# ---------------------------------------------------------------------------


@router.post(
    "/generate/{incident_id}",
    response_model=ReportResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger manual report generation",
)
async def generate_report(
    incident_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user_id),
) -> ReportResponse:
    """
    Initiate PDF report generation for an incident.

    The generation runs in the background; the response is returned
    immediately with a ``202 Accepted`` status.  Poll ``GET /api/reports``
    to confirm when the file is ready.
    """
    tenant_id = str(user.get("tenant_id"))
    incident_data = _find_incident(incident_id, tenant_id)
    if incident_data is None:
        # Allow generating a stub report even if the incident is not found
        # (e.g. for incidents from a previous session).
        incident_data = {
            "incident_id": incident_id,
            "store_id": "unknown",
            "tenant_id": tenant_id,
            "camera_id": "unknown",
            "type": "manual",
            "severity": "medium",
            "description": "Manually triggered report.",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }
        logger.warning(
            "Incident '%s' not found in memory; generating stub report.", incident_id
        )

    report_id = str(uuid.uuid4())

    # Register a pending entry immediately so the caller has a report_id.
    placeholder = _register_report(
        report_id=report_id,
        incident_id=incident_id,
        store_id=incident_data.get("store_id", "unknown"),
        file_name=f"report_{report_id}.pdf",
        file_size=0,
        tenant_id=tenant_id,
    )

    background_tasks.add_task(_bg_generate_report, report_id, incident_id, incident_data)

    logger.info(
        "Report generation queued | report_id=%s incident_id=%s",
        report_id,
        incident_id,
    )
    return placeholder
