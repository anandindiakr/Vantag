"""
zero_dce.py
===========
Low-light image enhancement for the Vantag platform.

Two enhancement methods are supported:

* **clahe** (default) – Contrast Limited Adaptive Histogram Equalization
  applied to the L channel of the CIE LAB colour space.  Lightweight,
  runs entirely in OpenCV with no additional model files.

* **zero_dce** – Zero-Reference Deep Curve Estimation enhancement via an
  ONNX model (``models/weights/zero_dce.onnx``).  Falls back gracefully to
  CLAHE when the ONNX model file is absent or ``onnxruntime`` is not
  installed.
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Path to the optional Zero-DCE ONNX weight file, relative to the repo root.
_ZERO_DCE_ONNX_PATH = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "models", "weights", "zero_dce.onnx",
)


class LowLightEnhancer:
    """
    Enhances dark / low-light video frames before they reach the detection
    pipeline.

    Parameters
    ----------
    method:
        ``'clahe'`` (default) or ``'zero_dce'``.
    clip_limit:
        CLAHE clip limit controlling contrast enhancement intensity.
        Higher values → stronger contrast, more noise amplification.
    tile_grid_size:
        CLAHE tile grid size as ``(width, height)`` tuple.
    brightness_threshold:
        Mean pixel value (0–255) below which a frame is considered
        low-light by :meth:`is_low_light`.
    """

    def __init__(
        self,
        method: str = "clahe",
        clip_limit: float = 3.0,
        tile_grid_size: Tuple[int, int] = (8, 8),
        brightness_threshold: float = 80.0,
    ) -> None:
        if method not in ("clahe", "zero_dce"):
            raise ValueError(f"Unknown method '{method}'. Choose 'clahe' or 'zero_dce'.")

        self._method = method
        self._brightness_threshold = brightness_threshold

        # Build CLAHE object (used as primary path and as Zero-DCE fallback).
        self._clahe = cv2.createCLAHE(
            clipLimit=clip_limit,
            tileGridSize=tile_grid_size,
        )

        # Zero-DCE ONNX session (lazy-loaded on first enhance() call when
        # method == 'zero_dce').
        self._ort_session: Optional[object] = None
        self._onnx_loaded: bool = False  # True = successfully loaded
        self._onnx_attempted: bool = False  # True = load already tried once

        logger.info(
            "LowLightEnhancer: method='%s', brightness_threshold=%.1f",
            method,
            brightness_threshold,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_low_light(self, frame: np.ndarray) -> bool:
        """
        Return ``True`` when the mean pixel brightness of *frame* is below
        the configured threshold.

        Parameters
        ----------
        frame:
            BGR or grayscale ``numpy.ndarray``.
        """
        if frame is None or frame.size == 0:
            return False
        gray = (
            cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if frame.ndim == 3
            else frame
        )
        return float(np.mean(gray)) < self._brightness_threshold

    def enhance(self, frame: np.ndarray) -> np.ndarray:
        """
        Enhance the brightness/contrast of *frame*.

        Parameters
        ----------
        frame:
            BGR ``numpy.ndarray`` (H×W×3, uint8).

        Returns
        -------
        Enhanced BGR ``numpy.ndarray`` of the same shape and dtype.
        """
        if frame is None or frame.size == 0:
            return frame

        if self._method == "zero_dce":
            return self._enhance_zero_dce(frame)
        return self._enhance_clahe(frame)

    # ------------------------------------------------------------------
    # CLAHE enhancement
    # ------------------------------------------------------------------

    def _enhance_clahe(self, frame: np.ndarray) -> np.ndarray:
        """Apply CLAHE to the L channel of the LAB representation."""
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)
        l_enhanced = self._clahe.apply(l_ch)
        lab_enhanced = cv2.merge((l_enhanced, a_ch, b_ch))
        return cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2BGR)

    # ------------------------------------------------------------------
    # Zero-DCE ONNX enhancement
    # ------------------------------------------------------------------

    def _load_onnx(self) -> bool:
        """
        Attempt to load the Zero-DCE ONNX model.

        Returns ``True`` if the session is ready, ``False`` otherwise.
        The load is attempted only once; subsequent calls return the
        cached result immediately.
        """
        if self._onnx_attempted:
            return self._onnx_loaded

        self._onnx_attempted = True
        onnx_path = os.path.abspath(_ZERO_DCE_ONNX_PATH)

        if not os.path.isfile(onnx_path):
            logger.warning(
                "LowLightEnhancer: Zero-DCE ONNX model not found at '%s'. "
                "Falling back to CLAHE.",
                onnx_path,
            )
            return False

        try:
            import onnxruntime as ort  # type: ignore[import]

            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            self._ort_session = ort.InferenceSession(onnx_path, providers=providers)
            self._onnx_loaded = True
            logger.info(
                "LowLightEnhancer: Zero-DCE ONNX session created from '%s'.",
                onnx_path,
            )
        except ImportError:
            logger.warning(
                "LowLightEnhancer: 'onnxruntime' is not installed. "
                "Install it with: pip install onnxruntime. "
                "Falling back to CLAHE."
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "LowLightEnhancer: failed to create ONNX session: %s. "
                "Falling back to CLAHE.",
                exc,
            )

        return self._onnx_loaded

    def _enhance_zero_dce(self, frame: np.ndarray) -> np.ndarray:
        """
        Run the Zero-DCE ONNX model on *frame*.

        The model expects a float32 NCHW tensor normalised to [0, 1].
        Output is assumed to be in the same format.  Falls back to CLAHE
        if the model is unavailable.
        """
        if not self._load_onnx():
            return self._enhance_clahe(frame)

        try:
            session = self._ort_session  # type: ignore[assignment]
            # Retrieve input metadata from the session.
            input_meta = session.get_inputs()[0]  # type: ignore[union-attr]
            input_name: str = input_meta.name

            # Determine target spatial size from model's expected shape.
            # Shape is typically [1, 3, H, W]; some models use dynamic dims.
            model_shape = input_meta.shape
            if (
                isinstance(model_shape, (list, tuple))
                and len(model_shape) == 4
                and isinstance(model_shape[2], int)
                and isinstance(model_shape[3], int)
            ):
                target_h, target_w = int(model_shape[2]), int(model_shape[3])
            else:
                # Default safe resolution for Zero-DCE.
                target_h, target_w = 512, 512

            orig_h, orig_w = frame.shape[:2]
            resized = cv2.resize(frame, (target_w, target_h))

            # BGR → RGB, HWC → NCHW, uint8 → float32 [0,1].
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
            nchw = np.transpose(rgb, (2, 0, 1))[np.newaxis, ...]  # (1, 3, H, W)

            outputs = session.run(None, {input_name: nchw})  # type: ignore[union-attr]
            out_nchw: np.ndarray = outputs[0]  # (1, 3, H, W)

            # NCHW → HWC → RGB uint8.
            out_hwc = np.transpose(out_nchw[0], (1, 2, 0))
            out_hwc = np.clip(out_hwc, 0.0, 1.0)
            out_rgb = (out_hwc * 255.0).astype(np.uint8)
            out_bgr = cv2.cvtColor(out_rgb, cv2.COLOR_RGB2BGR)

            # Restore original resolution if we had to resize.
            if (orig_h, orig_w) != (target_h, target_w):
                out_bgr = cv2.resize(out_bgr, (orig_w, orig_h))

            return out_bgr

        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "LowLightEnhancer._enhance_zero_dce: inference error (%s). "
                "Falling back to CLAHE.",
                exc,
            )
            return self._enhance_clahe(frame)
