from __future__ import annotations

import os
import time

from backend.services.snapshot_retention import cleanup_snapshot_files


def test_cleanup_uses_plan_retention_and_preserves_latest(tmp_path):
    tenant = tmp_path / "tenant-1"
    tenant.mkdir()
    old_event = tenant / "event.jpg"
    old_report = tenant / "report.pdf"
    protected = tenant / "people_count_latest.jpg"
    for path in (old_event, old_report, protected):
        path.write_bytes(b"evidence")
        old = time.time() - 10 * 86400
        os.utime(path, (old, old))

    result = cleanup_snapshot_files(tmp_path, {"tenant-1": "starter"})
    assert result["deleted"] == 2
    assert not old_event.exists()
    assert not old_report.exists()
    assert protected.exists()
