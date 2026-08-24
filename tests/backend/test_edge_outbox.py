from __future__ import annotations

import time

from windows_agent.agent.outbox import IncidentOutbox


def test_outbox_retries_until_acknowledged(tmp_path):
    outbox = IncidentOutbox(tmp_path / "incident.db", max_items=50)
    payload = {"event_id": "evt-1", "event_type": "shoplifting"}
    outbox.enqueue(payload)

    attempts = []

    def sender(item: dict) -> bool:
        attempts.append(item)
        return len(attempts) == 2

    # First delivery fails and remains queued; make it due again without
    # sleeping through the production backoff window.
    assert outbox.flush(sender) == 0
    assert outbox.pending_count() == 1
    with outbox._connect() as conn:  # test-only clock control
        conn.execute("UPDATE incident_outbox SET next_attempt_at = ?", (time.time() - 1,))

    assert outbox.flush(sender) == 1
    assert outbox.pending_count() == 0
    assert len(attempts) == 2


def test_outbox_is_bounded(tmp_path):
    outbox = IncidentOutbox(tmp_path / "incident.db", max_items=50)
    for index in range(80):
        outbox.enqueue({"event_id": f"evt-{index}"})
    assert outbox.pending_count() == 50
