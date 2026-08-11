"""Plan-aware snapshot/report retention for the VPS filesystem."""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path

log = logging.getLogger("vantag.retention")

# Keep evidence long enough for normal incident review while bounding disk use.
RETENTION_DAYS = {
    "starter": 7,
    "growth": 30,
    "pro": 90,
    "proplus": 180,
}
DEFAULT_RETENTION_DAYS = 30
_PROTECTED_NAMES = {"people_count_latest.jpg", "watchlist_meta.json", "reports_meta.json"}


def _age_seconds(days: int) -> float:
    return max(1, int(days)) * 86400.0


def cleanup_snapshot_files(
    root: Path,
    tenant_retention: dict[str, str] | None = None,
    default_days: int = DEFAULT_RETENTION_DAYS,
) -> dict[str, int]:
    """Delete expired JPEG/PDF evidence without following symlinks.

    ``tenant_retention`` maps tenant id to plan id. When unavailable, the
    conservative default is used. The operation is idempotent and returns
    counts for operational logs/metrics.
    """
    now = time.time()
    deleted = 0
    skipped = 0
    if not root.exists():
        return {"deleted": 0, "skipped": 0}

    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink() or path.name in _PROTECTED_NAMES:
            continue
        if path.suffix.lower() not in {".jpg", ".jpeg", ".pdf"}:
            continue
        try:
            relative = path.relative_to(root)
            tenant_id = relative.parts[0] if relative.parts else ""
            plan = (tenant_retention or {}).get(tenant_id)
            days = RETENTION_DAYS.get(plan or "", default_days)
            if now - path.stat().st_mtime <= _age_seconds(days):
                continue
            path.unlink()
            deleted += 1
        except (OSError, ValueError) as exc:
            skipped += 1
            log.warning("Could not clean evidence file %s: %s", path, exc)

    if deleted:
        log.info("Snapshot retention removed %d expired evidence file(s)", deleted)
    return {"deleted": deleted, "skipped": skipped}
