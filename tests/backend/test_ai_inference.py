"""Focused regression tests for the detector performance/accuracy upgrade."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AGENT_ROOT = _REPO_ROOT / "windows_agent"
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))

from agent.inference import YoloInference, _parse_version  # noqa: E402


def _detector_for_postprocess() -> YoloInference:
    detector = YoloInference.__new__(YoloInference)
    detector._img_size = 640
    return detector


def test_end_to_end_output_filters_confidence_and_normalizes_boxes():
    detector = _detector_for_postprocess()
    output = np.array(
        [[
            [64, 128, 320, 512, 0.91, 0],
            [10, 20, 40, 60, 0.19, 0],
        ]],
        dtype=np.float32,
    )

    boxes = detector._postprocess(output, orig_w=1280, orig_h=720, conf=0.5)

    assert len(boxes) == 1
    assert boxes[0].label == "person"
    assert boxes[0].confidence == pytest.approx(0.91)
    assert (boxes[0].x, boxes[0].y) == (0.1, 0.2)
    assert boxes[0].w == pytest.approx(0.4)
    assert boxes[0].h == pytest.approx(0.6)


def test_legacy_output_applies_per_class_nms():
    detector = _detector_for_postprocess()
    output = np.zeros((1, 84, 3), dtype=np.float32)

    # Two highly-overlapping person candidates: only the stronger survives.
    output[0, :4, 0] = [320, 320, 200, 200]
    output[0, :4, 1] = [325, 325, 200, 200]
    output[0, 4, 0] = 0.90
    output[0, 4, 1] = 0.80
    # A separate class in a separate location must not be suppressed.
    output[0, :4, 2] = [100, 100, 40, 40]
    output[0, 5, 2] = 0.85

    boxes = detector._postprocess(output, orig_w=640, orig_h=640, conf=0.5)

    assert len(boxes) == 2
    assert sorted(box.label for box in boxes) == ["bicycle", "person"]
    assert max(box.confidence for box in boxes) == pytest.approx(0.90)


def test_version_parser_is_conservative_for_unknown_versions():
    assert _parse_version("8.4.1") == (8, 4, 1)
    assert _parse_version("8.3.100+cpu") == (8, 3, 100)
    assert _parse_version("not-installed") == (0, 0, 0)
