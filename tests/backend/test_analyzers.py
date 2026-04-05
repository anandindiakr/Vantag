"""
tests/backend/test_analyzers.py
================================
pytest test suite for key Vantag analyser modules and integrations.

Test groups
-----------
1. DwellTimeAnalyzer — mock detections crossing dwell threshold
2. QueueDetector     — queue depth counting within a zone
3. RiskScorer        — weighted scoring math and severity thresholds
4. WebhookEngine     — dispatch with mocked HTTP calls
5. POSIntegration    — sweethearting detection (normal & anomalous)

Dependencies: pytest, pytest-asyncio, unittest.mock
"""

from __future__ import annotations

import asyncio
import sys
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─── Path setup ───────────────────────────────────────────────────────────────
# Ensure the repo root is on sys.path so backend packages import cleanly.

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ─── Optional-dependency stubs ───────────────────────────────────────────────
# numpy and shapely may not be installed in the test environment.
# Provide lightweight stubs so that analyser modules can still be imported.

try:
    import numpy  # noqa: F401
except ModuleNotFoundError:
    import types

    _np_stub = types.ModuleType("numpy")

    # Minimal numpy surface used by dwell_time / queue_detector
    def _mean(arr, *a, **kw):
        items = list(arr)
        return sum(items) / len(items) if items else 0.0

    _np_stub.mean = _mean
    _np_stub.zeros = lambda *a, **kw: []
    _np_stub.ndarray = list
    # pytest.approx uses np.isscalar and np.bool_
    _np_stub.isscalar = lambda x: isinstance(x, (int, float, complex, bool))
    _np_stub.bool_ = bool
    sys.modules["numpy"] = _np_stub

try:
    import shapely  # noqa: F401
except ModuleNotFoundError:
    import types

    _shapely_stub = types.ModuleType("shapely")
    _shapely_geo = types.ModuleType("shapely.geometry")

    class _Point:
        def __init__(self, x, y):
            self.x, self.y = x, y

    class _Polygon:
        """Minimal polygon stub using point-in-bounding-box containment."""
        def __init__(self, pts):
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            self.minx, self.maxx = min(xs), max(xs)
            self.miny, self.maxy = min(ys), max(ys)

        def contains(self, point: _Point) -> bool:
            return (
                self.minx <= point.x <= self.maxx
                and self.miny <= point.y <= self.maxy
            )

    _shapely_geo.Point = _Point
    _shapely_geo.Polygon = _Polygon
    _shapely_stub.geometry = _shapely_geo
    sys.modules["shapely"] = _shapely_stub
    sys.modules["shapely.geometry"] = _shapely_geo

# ─── Stub heavy optional modules that some analysers import ──────────────────
# cv2 (OpenCV) and torch may be absent in the CI/test environment.

for _mod_name in [
    "cv2",
    "torch",
    "torchvision",
    "torchvision.transforms",
    "ultralytics",
    "PIL",
    "PIL.Image",
]:
    if _mod_name not in sys.modules:
        try:
            import importlib as _importlib
            _importlib.import_module(_mod_name)
        except ImportError:
            import types as _types
            _stub = _types.ModuleType(_mod_name)
            _stub.__spec__ = None  # type: ignore[assignment]
            sys.modules[_mod_name] = _stub


# ─── Shared detection stub ────────────────────────────────────────────────────

@dataclass
class _Detection:
    track_id: int
    class_id: int
    class_name: str
    confidence: float
    bbox: Tuple[int, int, int, int]
    keypoints: Optional[list] = None


def _person(track_id: int, bbox: Tuple[int, int, int, int]) -> _Detection:
    return _Detection(
        track_id=track_id,
        class_id=0,
        class_name="person",
        confidence=0.92,
        bbox=bbox,
    )


# ─────────────────────────────────────────────────────────────────────────────
# TEST GROUP 1: DwellTimeAnalyzer
# ─────────────────────────────────────────────────────────────────────────────

class TestDwellTimeAnalyzer:
    """
    Tests for DwellTimeAnalyzer: event emission, cooldown, and zone logic.
    """

    def _make_analyzer(
        self,
        dwell_threshold: float = 0.1,
        cooldown: float = 0.2,
        with_polygon: bool = True,
    ):
        from backend.analyzers.dwell_time import DwellTimeAnalyzer

        zones = []
        if with_polygon:
            # Polygon covering entire 640×480 frame
            zones = [
                {
                    "label": "test_zone",
                    "polygon": [[0, 0], [640, 0], [640, 480], [0, 480]],
                }
            ]
        else:
            zones = [{"label": "test_zone", "polygon": []}]

        config = {
            "zones": zones,
            "dwell_threshold_seconds": dwell_threshold,
            "cooldown_seconds": cooldown,
        }
        return DwellTimeAnalyzer(camera_id="test-cam", config=config)

    def test_no_event_below_threshold(self):
        """Events must NOT be emitted before the dwell threshold is reached."""
        analyzer = self._make_analyzer(dwell_threshold=10.0)
        det = [_person(1, (100, 100, 200, 200))]
        start = time.monotonic()
        events = analyzer.analyze(det, timestamp=start)
        assert events == [], "No event expected before threshold"

    def test_event_emitted_after_threshold(self):
        """A DwellEvent must be emitted once the threshold is crossed."""
        from backend.analyzers.dwell_time import DwellEvent

        analyzer = self._make_analyzer(dwell_threshold=0.05, cooldown=999.0)
        det = [_person(1, (100, 100, 200, 200))]
        t0 = time.monotonic()

        events = analyzer.analyze(det, timestamp=t0)
        assert events == []

        # Advance time past threshold
        t1 = t0 + 0.1
        events = analyzer.analyze(det, timestamp=t1)

        assert len(events) == 1
        assert isinstance(events[0], DwellEvent)
        assert events[0].track_id == 1
        assert events[0].zone_label == "test_zone"
        assert events[0].dwell_seconds >= 0.05

    def test_only_one_event_per_cooldown(self):
        """A second event for the same track must be suppressed during cooldown."""
        analyzer = self._make_analyzer(dwell_threshold=0.05, cooldown=999.0)
        det = [_person(1, (100, 100, 200, 200))]
        t0 = time.monotonic()

        analyzer.analyze(det, timestamp=t0)          # enters zone
        e1 = analyzer.analyze(det, timestamp=t0 + 0.1)  # crosses threshold → event
        e2 = analyzer.analyze(det, timestamp=t0 + 0.2)  # still in zone → suppressed

        assert len(e1) == 1
        assert len(e2) == 0, "Second event must be suppressed within cooldown"

    def test_zone_exit_resets_entry_time(self):
        """
        When a person leaves and re-enters a zone, the dwell clock resets.
        """
        analyzer = self._make_analyzer(dwell_threshold=0.05, cooldown=999.0)
        det = [_person(1, (100, 100, 200, 200))]
        outside = [_person(1, (9999, 9999, 9999, 9999))]  # well outside polygon

        t0 = time.monotonic()
        analyzer.analyze(det, timestamp=t0)
        # Person leaves
        analyzer.analyze(outside, timestamp=t0 + 0.03)
        # Person re-enters — clock should reset
        analyzer.analyze(det, timestamp=t0 + 0.04)
        # Not enough time since re-entry
        events = analyzer.analyze(det, timestamp=t0 + 0.06)

        # 0.06 - 0.04 = 0.02 s since re-entry; threshold = 0.05 s → no event
        assert events == [], "No event — not enough dwell since re-entry"

    def test_multiple_tracks_independent(self):
        """Multiple track IDs must be tracked independently."""
        from backend.analyzers.dwell_time import DwellEvent

        analyzer = self._make_analyzer(dwell_threshold=0.05, cooldown=999.0)
        d1 = [_person(1, (10, 10, 50, 50))]
        d2 = [_person(2, (200, 200, 300, 300))]
        t0 = time.monotonic()

        # Both tracks enter zone simultaneously at t0
        analyzer.analyze(d1 + d2, timestamp=t0)

        # Advance past threshold — both should fire
        events = analyzer.analyze(d1 + d2, timestamp=t0 + 0.1)

        assert len(events) == 2, (
            f"Expected 2 events (one per track), got {len(events)}: {events}"
        )
        track_ids = {e.track_id for e in events}
        assert track_ids == {1, 2}


# ─────────────────────────────────────────────────────────────────────────────
# TEST GROUP 2: QueueDetector
# ─────────────────────────────────────────────────────────────────────────────

class TestQueueDetector:
    """
    Tests for QueueDetector: depth counting, severity levels, and wait times.
    """

    def _make_detector(
        self,
        depth_threshold: int = 3,
        with_polygon: bool = True,
    ):
        from backend.analyzers.queue_detector import QueueDetector

        zones = []
        if with_polygon:
            zones = [
                {
                    "label": "checkout_1",
                    "polygon": [[0, 0], [640, 0], [640, 480], [0, 480]],
                }
            ]
        else:
            zones = [{"label": "checkout_1", "polygon": []}]

        config = {
            "lane_zones": zones,
            "depth_threshold": depth_threshold,
            "rolling_window_seconds": 300.0,
        }
        return QueueDetector(camera_id="test-cam", config=config)

    def test_no_event_below_threshold(self):
        """Queue depth below threshold must not emit events."""
        detector = self._make_detector(depth_threshold=4)
        persons = [_person(i, (i * 50, 10, i * 50 + 40, 80)) for i in range(3)]
        t0 = time.monotonic()
        events = detector.analyze(persons, timestamp=t0)
        assert events == []

    def test_event_emitted_at_threshold(self):
        """Exactly at depth_threshold, a QueueEvent must be emitted."""
        from backend.analyzers.queue_detector import QueueEvent

        detector = self._make_detector(depth_threshold=3)
        persons = [_person(i, (i * 50, 10, i * 50 + 40, 80)) for i in range(3)]
        t0 = time.monotonic()
        events = detector.analyze(persons, timestamp=t0)
        assert len(events) == 1
        assert isinstance(events[0], QueueEvent)
        assert events[0].depth == 3
        assert events[0].lane_id == "checkout_1"

    def test_depth_counts_persons_in_zone(self):
        """Depth should equal the number of persons detected in the zone."""
        from backend.analyzers.queue_detector import QueueEvent

        detector = self._make_detector(depth_threshold=2)
        persons = [_person(i, (i * 30, 20, i * 30 + 25, 60)) for i in range(5)]
        events = detector.analyze(persons, timestamp=time.monotonic())
        assert len(events) == 1
        assert events[0].depth == 5

    def test_severity_low(self):
        """Depth just at threshold → LOW severity."""
        detector = self._make_detector(depth_threshold=4)
        persons = [_person(i, (i * 40, 10, i * 40 + 35, 80)) for i in range(4)]
        events = detector.analyze(persons, timestamp=time.monotonic())
        assert events[0].severity == "LOW"

    def test_severity_medium(self):
        """Depth > threshold × 1.5 → MEDIUM severity."""
        # threshold=4, depth=7 → 7 > 6.0 (=4×1.5) → MEDIUM
        detector = self._make_detector(depth_threshold=4)
        persons = [_person(i, (i * 40, 10, i * 40 + 35, 80)) for i in range(7)]
        events = detector.analyze(persons, timestamp=time.monotonic())
        assert events[0].severity == "MEDIUM"

    def test_severity_high(self):
        """Depth > threshold × 2.5 → HIGH severity."""
        # threshold=4, depth=11 → 11 > 10.0 (=4×2.5) → HIGH
        detector = self._make_detector(depth_threshold=4)
        persons = [_person(i, (i * 40, 10, i * 40 + 35, 80)) for i in range(11)]
        events = detector.analyze(persons, timestamp=time.monotonic())
        assert events[0].severity == "HIGH"

    def test_empty_lane_no_event(self):
        """Zero persons → no event."""
        detector = self._make_detector(depth_threshold=2)
        events = detector.analyze([], timestamp=time.monotonic())
        assert events == []

    def test_non_person_detections_ignored(self):
        """Non-person detections must not count toward queue depth."""
        detector = self._make_detector(depth_threshold=2)
        dets = [
            _Detection(0, 1, "car", 0.9, (0, 0, 100, 100)),
            _Detection(1, 2, "bag", 0.85, (50, 50, 150, 150)),
            _Detection(2, 3, "umbrella", 0.88, (100, 100, 200, 200)),
        ]
        events = detector.analyze(dets, timestamp=time.monotonic())
        assert events == []


# ─────────────────────────────────────────────────────────────────────────────
# TEST GROUP 3: RiskScorer
# ─────────────────────────────────────────────────────────────────────────────

class TestRiskScorer:
    """
    Tests for RiskScorer: weighted scoring math and severity classification.
    """

    def _make_scorer(self, window_seconds: float = 300.0):
        from backend.scoring.risk_scorer import RiskScorer
        return RiskScorer(store_id="test-store", config={"window_seconds": window_seconds})

    def test_empty_store_score_is_zero(self):
        """A scorer with no events must return score=0 and severity='LOW'."""
        scorer = self._make_scorer()
        rs = scorer.get_score()
        assert rs.score == 0.0
        assert rs.severity == "LOW"
        assert rs.store_id == "test-store"

    def test_single_event_increases_score(self):
        """Ingesting one tamper event (weight=35) must produce score > 0."""
        scorer = self._make_scorer()
        event = {"event_type": "tamper"}
        scorer.ingest_event(event)
        rs = scorer.get_score()
        assert rs.score > 0.0

    def test_high_weight_events_push_score_above_medium(self):
        """
        Multiple high-weight events should push score into MEDIUM or HIGH band.
        Weight for 'tamper'=35.  Two tamper events = 70 raw weight.
        Normalised = 70/200*100 = 35.0 → MEDIUM.
        """
        scorer = self._make_scorer()
        for _ in range(2):
            scorer.ingest_event({"event_type": "tamper"})
        rs = scorer.get_score()
        assert rs.score >= 30.0
        assert rs.severity in ("MEDIUM", "HIGH")

    def test_severity_thresholds(self):
        """Verify exact boundary conditions for severity classification."""
        from backend.scoring.risk_scorer import RiskScorer

        scorer = RiskScorer(store_id="boundary-test", config={})

        # Manually override score computation via mock
        with patch.object(scorer, "_compute_score_and_counts", return_value=(0.0, {})):
            assert scorer.get_score().severity == "LOW"

        with patch.object(scorer, "_compute_score_and_counts", return_value=(29.9, {})):
            assert scorer.get_score().severity == "LOW"

        with patch.object(scorer, "_compute_score_and_counts", return_value=(30.0, {})):
            assert scorer.get_score().severity == "MEDIUM"

        with patch.object(scorer, "_compute_score_and_counts", return_value=(69.9, {})):
            assert scorer.get_score().severity == "MEDIUM"

        with patch.object(scorer, "_compute_score_and_counts", return_value=(70.0, {})):
            assert scorer.get_score().severity == "HIGH"

        with patch.object(scorer, "_compute_score_and_counts", return_value=(100.0, {})):
            assert scorer.get_score().severity == "HIGH"

    def test_event_counts_tracked_correctly(self):
        """Event type counts in get_score() must reflect ingested events."""
        scorer = self._make_scorer()
        scorer.ingest_event({"event_type": "sweeping"})
        scorer.ingest_event({"event_type": "sweeping"})
        scorer.ingest_event({"event_type": "tamper"})
        rs = scorer.get_score()
        assert rs.event_counts.get("sweeping") == 2
        assert rs.event_counts.get("tamper") == 1

    def test_unknown_event_type_does_not_raise(self):
        """
        Unknown event types must not raise an exception.
        The RiskScorer applies a fallback weight (5.0) for unrecognised types
        when passed as plain dicts, so the score will be > 0 but that is
        acceptable behaviour — the important invariant is no exception raised.
        """
        scorer = self._make_scorer()
        # Must not raise
        scorer.ingest_event({"event_type": "unknown_event_xyz"})
        rs = scorer.get_score()
        # Score is non-negative (fallback weight applied) and ≤ 100
        assert 0.0 <= rs.score <= 100.0

    def test_rolling_window_prunes_old_events(self):
        """Events older than the window must not contribute to the score."""
        scorer = self._make_scorer(window_seconds=0.05)
        scorer.ingest_event({"event_type": "tamper"})
        # Wait for the window to expire
        time.sleep(0.1)
        rs = scorer.get_score()
        # Window has expired — score should be 0 (or very close)
        assert rs.score == 0.0

    def test_score_clamped_to_100(self):
        """Score must not exceed 100 even with many events."""
        scorer = self._make_scorer()
        for _ in range(100):
            scorer.ingest_event({"event_type": "tamper"})
        rs = scorer.get_score()
        assert rs.score <= 100.0

    def test_history_appended(self):
        """Each call to get_score() must append to internal history."""
        scorer = self._make_scorer()
        scorer.get_score()
        scorer.get_score()
        scorer.get_score()
        history = scorer.get_history()
        assert len(history) == 3

    def test_get_history_returns_oldest_first(self):
        """History is returned oldest-first with correct ordering."""
        scorer = self._make_scorer()
        # Ingest events to differentiate scores
        scorer.get_score()  # score=0
        scorer.ingest_event({"event_type": "tamper"})
        scorer.get_score()  # score>0
        history = scorer.get_history(n=2)
        assert history[0].score <= history[1].score


# ─────────────────────────────────────────────────────────────────────────────
# TEST GROUP 4: WebhookEngine.dispatch()
# ─────────────────────────────────────────────────────────────────────────────

class TestWebhookEngineDispatch:
    """
    Tests for WebhookEngine.dispatch() using mocked HTTP calls.
    """

    def _make_engine(self, subscriptions: list):
        from backend.webhooks.webhook_engine import WebhookEngine

        engine = WebhookEngine.__new__(WebhookEngine)
        engine._subscriptions = subscriptions
        return engine

    def _slack_sub(self, event_types=None, severity="LOW"):
        return {
            "id": "test-slack",
            "name": "Test Slack",
            "connector": "slack",
            "url": "https://hooks.slack.com/test",
            "event_types": event_types or ["*"],
            "severity_threshold": severity,
        }

    def _generic_sub(self, event_types=None, severity="LOW"):
        return {
            "id": "test-generic",
            "name": "Test Generic",
            "connector": "generic",
            "url": "https://example.com/webhook",
            "event_types": event_types or ["*"],
            "severity_threshold": severity,
            "headers": {},
        }

    def _make_event(self, event_type="tamper", severity="HIGH"):
        return {
            "id": "evt-001",
            "type": event_type,
            "severity": severity,
            "store_id": "store-01",
            "camera_id": "cam-01",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "description": "Test event",
        }

    @pytest.mark.asyncio
    async def test_dispatch_calls_connector_send(self):
        """dispatch() must call the connector's send method for matching subs."""
        engine = self._make_engine([self._slack_sub()])
        event = self._make_event()

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch(
            "backend.webhooks.webhook_engine.SlackConnector.send",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_send:
            await engine.dispatch(event)

        mock_send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dispatch_skips_non_matching_event_type(self):
        """Subscriptions filtering specific event types must not fire on others."""
        engine = self._make_engine([self._slack_sub(event_types=["sweeping"])])
        event = self._make_event(event_type="tamper")

        with patch(
            "backend.webhooks.webhook_engine.SlackConnector.send",
            new_callable=AsyncMock,
        ) as mock_send:
            await engine.dispatch(event)

        mock_send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dispatch_skips_below_severity_threshold(self):
        """Events below the severity threshold must not be dispatched."""
        engine = self._make_engine(
            [self._generic_sub(severity="HIGH")]
        )
        event = self._make_event(severity="LOW")

        with patch(
            "backend.webhooks.webhook_engine.GenericWebhookConnector.send",
            new_callable=AsyncMock,
        ) as mock_send:
            await engine.dispatch(event)

        mock_send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dispatch_fires_for_matching_severity(self):
        """Events at or above the threshold must be dispatched."""
        engine = self._make_engine([self._generic_sub(severity="MEDIUM")])
        event = self._make_event(severity="HIGH")

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch(
            "backend.webhooks.webhook_engine.GenericWebhookConnector.send",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_send:
            await engine.dispatch(event)

        mock_send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dispatch_wildcard_event_type_matches_all(self):
        """A subscription with event_types=['*'] must match any event type."""
        engine = self._make_engine([self._generic_sub(event_types=["*"])])

        mock_response = MagicMock()
        mock_response.status_code = 200

        for et in ["tamper", "sweeping", "queue", "accident", "dwell"]:
            with patch(
                "backend.webhooks.webhook_engine.GenericWebhookConnector.send",
                new_callable=AsyncMock,
                return_value=mock_response,
            ) as mock_send:
                await engine.dispatch(self._make_event(event_type=et))
            mock_send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_retry_on_http_error(self):
        """Failed HTTP calls must be retried up to 3 times."""
        engine = self._make_engine([self._generic_sub()])

        fail_response = MagicMock()
        fail_response.status_code = 503

        call_count = 0

        async def failing_send(event, client):
            nonlocal call_count
            call_count += 1
            return fail_response

        with patch(
            "backend.webhooks.webhook_engine.GenericWebhookConnector.send",
            side_effect=failing_send,
        ):
            # Patch sleep to avoid actually waiting
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await engine.dispatch(self._make_event())

        assert call_count == 3, f"Expected 3 attempts, got {call_count}"

    @pytest.mark.asyncio
    async def test_no_subscriptions_no_crash(self):
        """dispatch() with no subscriptions must complete without error."""
        engine = self._make_engine([])
        await engine.dispatch(self._make_event())  # Must not raise

    @pytest.mark.asyncio
    async def test_multiple_subscriptions_dispatched_concurrently(self):
        """Multiple matching subscriptions must all receive the event."""
        subs = [self._generic_sub(), self._slack_sub()]
        engine = self._make_engine(subs)
        event = self._make_event()

        mock_response = MagicMock()
        mock_response.status_code = 200

        generic_send = AsyncMock(return_value=mock_response)
        slack_send = AsyncMock(return_value=mock_response)

        with patch(
            "backend.webhooks.webhook_engine.GenericWebhookConnector.send",
            generic_send,
        ), patch(
            "backend.webhooks.webhook_engine.SlackConnector.send",
            slack_send,
        ):
            await engine.dispatch(event)

        generic_send.assert_awaited_once()
        slack_send.assert_awaited_once()


# ─────────────────────────────────────────────────────────────────────────────
# TEST GROUP 5: POSIntegration.detect_sweethearting()
# ─────────────────────────────────────────────────────────────────────────────

class TestPOSIntegration:
    """
    Tests for POSIntegration: sweethearting detection and escalation logic.
    """

    def _make_integration(self, ratio_threshold: float = 0.5):
        from backend.pos.pos_integration import POSIntegration
        return POSIntegration(sweetheating_ratio_threshold=ratio_threshold)

    def _make_tx(
        self,
        transaction_id: str = "TX001",
        cashier_id: str = "C001",
        camera_id: str = "cam-01",
        pos_items: int = 10,
        camera_estimate: float = 10.0,
        store_id: str = "store-01",
    ) -> dict:
        return {
            "transaction_id": transaction_id,
            "cashier_id": cashier_id,
            "camera_id": camera_id,
            "store_id": store_id,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "items": [{"sku": f"SKU{i}", "qty": 1, "price": 1.99} for i in range(pos_items)],
            "total_amount": pos_items * 1.99,
            "basket_size_camera_estimate": camera_estimate,
        }

    def test_normal_transaction_no_anomaly(self):
        """A transaction where vision estimate ≈ POS count must not flag."""
        pos = self._make_integration()
        tx = self._make_tx(pos_items=10, camera_estimate=10.0)
        result = pos.ingest_transaction(tx)
        assert result is None

    def test_exactly_at_threshold_no_anomaly(self):
        """Ratio exactly equal to threshold must NOT be flagged (non-strict <)."""
        pos = self._make_integration(ratio_threshold=0.5)
        # ratio = 5/10 = 0.5 → exactly at threshold → not flagged
        tx = self._make_tx(pos_items=10, camera_estimate=5.0)
        result = pos.ingest_transaction(tx)
        assert result is None

    def test_below_threshold_flagged_as_sweethearting(self):
        """Ratio below threshold must produce a sweethearting anomaly."""
        from backend.pos.pos_integration import POSAnomalyEvent

        pos = self._make_integration(ratio_threshold=0.5)
        # ratio = 3/10 = 0.3 < 0.5 → sweethearting
        tx = self._make_tx(pos_items=10, camera_estimate=3.0)
        result = pos.ingest_transaction(tx)

        assert result is not None
        assert isinstance(result, POSAnomalyEvent)
        assert result.anomaly_type == "sweethearting"
        assert result.risk_score == 60.0
        assert result.cashier_id == "C001"
        assert result.ratio == pytest.approx(0.3, abs=0.001)

    def test_zero_vision_estimate_not_flagged(self):
        """Zero camera estimate must not flag (camera may have malfunctioned)."""
        pos = self._make_integration()
        tx = self._make_tx(pos_items=10, camera_estimate=0.0)
        result = pos.ingest_transaction(tx)
        assert result is None

    def test_zero_pos_items_not_flagged(self):
        """Zero POS items cannot produce a meaningful ratio — must not flag."""
        pos = self._make_integration()
        tx = self._make_tx(pos_items=0, camera_estimate=5.0)
        # Items list is empty → pos_item_count = 0 → guard in detect_sweethearting
        result = pos.ingest_transaction(tx)
        assert result is None

    def test_escalated_pattern_after_multiple_anomalies(self):
        """
        When a cashier accumulates ≥ escalation_threshold anomalies within the
        window, subsequent anomalies must be typed 'escalated_pattern' with
        risk_score ≥ 80.
        """
        from backend.pos.pos_integration import POSIntegration

        pos = POSIntegration(
            sweetheating_ratio_threshold=0.5,
            escalation_window_minutes=60,
            escalation_threshold=3,
        )

        # Trigger 3 anomalies for the same cashier within the window
        results = []
        for i in range(5):
            tx = self._make_tx(
                transaction_id=f"TX{i:03d}",
                cashier_id="BADCASHIER",
                pos_items=10,
                camera_estimate=2.0,  # ratio=0.2 → sweethearting
            )
            result = pos.ingest_transaction(tx)
            if result is not None:
                results.append(result)

        assert len(results) >= 1, "Expected at least one anomaly"

        # After 3+ anomalies, the last result should be escalated
        last = results[-1]
        assert last.anomaly_type == "escalated_pattern"
        assert last.risk_score >= 80.0

    def test_missing_required_field_returns_none(self):
        """A transaction with a missing required field must return None gracefully."""
        pos = self._make_integration()
        bad_tx = {
            "cashier_id": "C001",
            "camera_id": "cam-01",
            # Missing: transaction_id, items, total_amount, basket_size_camera_estimate
        }
        result = pos.ingest_transaction(bad_tx)
        assert result is None

    def test_get_anomalies_returns_newest_first(self):
        """get_anomalies() must return events with newest first."""
        from backend.pos.pos_integration import POSIntegration

        pos = POSIntegration()
        for i in range(3):
            tx = self._make_tx(
                transaction_id=f"TX{i}",
                cashier_id="BAD",
                pos_items=10,
                camera_estimate=1.0,
            )
            pos.ingest_transaction(tx)

        anomalies = pos.get_anomalies(limit=10)
        assert len(anomalies) == 3
        # Newest first — timestamps should be non-ascending
        for j in range(len(anomalies) - 1):
            assert anomalies[j].timestamp >= anomalies[j + 1].timestamp

    def test_get_stats_reflects_ingested_data(self):
        """get_stats() must reflect actual transaction and anomaly counts."""
        pos = self._make_integration()

        # 2 normal + 2 anomalous
        for i in range(2):
            pos.ingest_transaction(self._make_tx(f"N{i}", pos_items=10, camera_estimate=10.0))
        for i in range(2):
            pos.ingest_transaction(
                self._make_tx(f"A{i}", cashier_id="BAD", pos_items=10, camera_estimate=1.0)
            )

        stats = pos.get_stats()
        assert stats["total_transactions"] == 4
        assert stats["total_anomalies"] == 2
        assert stats["anomaly_rate"] == pytest.approx(0.5, abs=0.01)
        assert "BAD" in [c["cashier_id"] for c in stats["top_flagged_cashiers"]]

    def test_ingest_from_csv_bad_path_does_not_raise(self):
        """ingest_from_csv with a non-existent file must return (0, 0) gracefully."""
        pos = self._make_integration()
        total, anomalies = pos.ingest_from_csv("/nonexistent/path/transactions.csv")
        assert total == 0
        assert anomalies == 0
