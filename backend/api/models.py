"""
backend/api/models.py
=====================
Pydantic v2 models for all Vantag API request and response bodies.

All models are used by the REST routers and WebSocket event payloads.
Descriptions are included on every field so auto-generated OpenAPI docs
remain useful without additional annotation.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class SeverityLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CameraStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"


class DoorAction(str, Enum):
    LOCK = "lock"
    UNLOCK = "unlock"


class DoorState(str, Enum):
    LOCKED = "locked"
    UNLOCKED = "unlocked"
    UNKNOWN = "unknown"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Shared / nested models
# ---------------------------------------------------------------------------


class ZonePolygon(BaseModel):
    """Named region-of-interest polygon within a camera frame."""

    name: str = Field(..., description="Unique zone name within this camera.")
    points: List[Tuple[int, int]] = Field(
        ..., description="Ordered list of (x, y) pixel vertices defining the polygon."
    )


class PaginationMeta(BaseModel):
    """Pagination metadata attached to list responses."""

    page: int = Field(..., description="Current page number (1-based).")
    limit: int = Field(..., description="Maximum items per page.")
    total: int = Field(..., description="Total number of items across all pages.")
    pages: int = Field(..., description="Total number of pages.")


# ---------------------------------------------------------------------------
# Store models
# ---------------------------------------------------------------------------


class StoreResponse(BaseModel):
    """Summary of a single retail store."""

    store_id: str = Field(..., description="Unique store identifier.")
    name: str = Field(..., description="Human-readable store name.")
    location: str = Field(..., description="Physical address or location label.")
    camera_count: int = Field(..., description="Total number of cameras in this store.")
    active_cameras: int = Field(..., description="Currently online cameras.")
    risk_score: float = Field(..., ge=0.0, le=100.0, description="Current composite risk score (0–100).")
    risk_severity: SeverityLevel = Field(..., description="Severity band derived from risk_score.")
    last_event_at: Optional[datetime] = Field(None, description="Timestamp of the most recent behavioral event.")


class RiskScoreResponse(BaseModel):
    """Snapshot risk score for a store at a point in time."""

    store_id: str = Field(..., description="Store this score belongs to.")
    score: float = Field(..., ge=0.0, le=100.0, description="Composite risk score (0–100).")
    severity: SeverityLevel = Field(..., description="Severity band.")
    event_counts: Dict[str, int] = Field(
        ...,
        description=(
            "Map of event-type label to count within the current scoring window. "
            "E.g. {'loitering': 3, 'queue_breach': 1}."
        ),
    )
    window_seconds: int = Field(..., description="Rolling window duration used for scoring.")
    computed_at: datetime = Field(..., description="UTC timestamp when this score was computed.")


class HeatmapCell(BaseModel):
    """Single cell in a 2-D heatmap grid."""

    row: int = Field(..., description="Zero-based row index.")
    col: int = Field(..., description="Zero-based column index.")
    value: float = Field(..., ge=0.0, description="Normalised activity value for this cell.")


class HeatmapResponse(BaseModel):
    """Aggregated heatmap data for a store over a given time window."""

    store_id: str
    window: str = Field(..., description="Aggregation window label, e.g. 'hourly', 'daily'.")
    grid_rows: int = Field(..., description="Number of rows in the grid.")
    grid_cols: int = Field(..., description="Number of columns in the grid.")
    cells: List[HeatmapCell] = Field(..., description="Non-zero heatmap cells.")
    generated_at: datetime


class IncidentResponse(BaseModel):
    """A single logged incident record."""

    incident_id: str = Field(..., description="Unique incident identifier (UUID).")
    store_id: str
    camera_id: str
    event_type: str = Field(..., description="Behavioral event label, e.g. 'loitering', 'tamper'.")
    severity: SeverityLevel
    description: str = Field(..., description="Human-readable description of the incident.")
    occurred_at: datetime
    snapshot_url: Optional[str] = Field(None, description="URL to the associated JPEG snapshot, if any.")
    acknowledged: bool = Field(False, description="Whether an operator has acknowledged this incident.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary event-specific metadata.")


class IncidentListResponse(BaseModel):
    """Paginated list of incidents."""

    incidents: List[IncidentResponse]
    pagination: PaginationMeta


class LaneQueueStatus(BaseModel):
    """Queue depth at a single checkout lane."""

    lane_id: str = Field(..., description="Unique lane identifier.")
    camera_id: str
    store_id: str
    queue_depth: int = Field(..., ge=0, description="Number of customers currently in the queue.")
    avg_wait_seconds: float = Field(..., ge=0.0, description="Estimated average wait time in seconds.")
    status: str = Field(..., description="Queue status label: 'normal', 'busy', 'critical'.")
    updated_at: datetime


class QueueStatusResponse(BaseModel):
    """Live queue depths across all lanes in all stores."""

    lanes: List[LaneQueueStatus]
    retrieved_at: datetime


# ---------------------------------------------------------------------------
# Camera models
# ---------------------------------------------------------------------------


class CameraResponse(BaseModel):
    """Camera record with operational metadata."""

    camera_id: str = Field(..., description="Unique camera identifier.")
    name: str
    location: str
    store_id: str
    rtsp_url: str = Field(..., description="RTSP stream URL (masked in production).")
    resolution_width: int
    resolution_height: int
    fps_target: int
    enabled: bool
    low_light_mode: bool
    status: CameraStatus
    consecutive_failures: int = Field(0, description="Number of consecutive health-check failures.")
    last_checked_at: Optional[datetime] = None
    zones: List[ZonePolygon] = Field(default_factory=list)


class ZoneUpdateRequest(BaseModel):
    """Payload for updating camera zone polygons."""

    zones: List[ZonePolygon] = Field(..., min_length=1, description="Replacement zone list.")


# ---------------------------------------------------------------------------
# Report models
# ---------------------------------------------------------------------------


class ReportResponse(BaseModel):
    """Metadata for a generated incident report."""

    report_id: str = Field(..., description="Unique report identifier (UUID).")
    incident_id: str
    store_id: str
    generated_at: datetime
    file_name: str = Field(..., description="PDF file name on disk.")
    file_size_bytes: int = Field(..., ge=0)


class ReportListResponse(BaseModel):
    reports: List[ReportResponse]


# ---------------------------------------------------------------------------
# Watchlist models
# ---------------------------------------------------------------------------


class WatchlistEntryResponse(BaseModel):
    """Public-facing watchlist entry (embeddings are never returned)."""

    entry_id: str = Field(..., description="Unique watchlist entry identifier (UUID).")
    name: str = Field(..., description="Display name of the individual.")
    alert_level: AlertLevel
    notes: Optional[str] = Field(None, description="Operator notes.")
    created_at: datetime
    image_url: Optional[str] = Field(None, description="URL to the reference face image.")


class WatchlistListResponse(BaseModel):
    entries: List[WatchlistEntryResponse]
    total: int


class WatchlistMatchEvent(BaseModel):
    """A face-match event against the watchlist."""

    match_id: str = Field(..., description="Unique match event identifier.")
    entry_id: str = Field(..., description="Matched watchlist entry ID.")
    entry_name: str
    alert_level: AlertLevel
    camera_id: str
    store_id: str
    confidence: float = Field(..., ge=0.0, le=1.0, description="Match confidence (0–1).")
    matched_at: datetime
    snapshot_url: Optional[str] = None


class WatchlistMatchesResponse(BaseModel):
    matches: List[WatchlistMatchEvent]
    total: int


# ---------------------------------------------------------------------------
# Door / access control models
# ---------------------------------------------------------------------------


class DoorCommandRequest(BaseModel):
    """Payload to issue a lock or unlock command to a door."""

    action: DoorAction = Field(..., description="'lock' or 'unlock'.")
    issued_by: str = Field("dashboard", description="Identifier of the operator issuing the command.")
    reason: Optional[str] = Field(None, description="Optional free-text reason for audit trail.")


class DoorStatusResponse(BaseModel):
    """Current state of a single door."""

    store_id: str
    door_id: str
    state: DoorState
    last_command: Optional[DoorAction] = None
    last_command_by: Optional[str] = None
    last_command_at: Optional[datetime] = None
    correlation_id: Optional[str] = None


# ---------------------------------------------------------------------------
# WebSocket event envelope
# ---------------------------------------------------------------------------


class WebSocketEvent(BaseModel):
    """Envelope for all real-time WebSocket event messages."""

    type: str = Field(..., description="Event type label, e.g. 'tamper', 'loitering', 'watchlist_match'.")
    camera_id: str
    store_id: str
    timestamp: datetime
    severity: SeverityLevel
    payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary event-specific data (detections, bboxes, confidence, etc.).",
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    uptime_seconds: float
