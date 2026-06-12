"""
backend/inference/trt_engine.py
================================
TensorRT inference engine for the Vantag platform.

``TRTEngine`` is a drop-in replacement for ``YOLOEngine``.  It exposes
identical ``detect()`` and ``detect_pose()`` methods but executes inference
via TensorRT on NVIDIA Jetson hardware for maximum throughput.

Graceful fallback
-----------------
If TensorRT or PyCUDA are unavailable (e.g. on a developer x86 machine
without an NVIDIA GPU), the class transparently delegates all inference
calls to :class:`~backend.inference.yolo_engine.YOLOEngine`.  No code
changes are required in callers.

Design notes
------------
* CUDA buffers (host-pinned + device) are allocated once in ``__init__``;
  each call to ``detect()`` / ``detect_pose()`` avoids Python-level
  allocation on the hot path.
* Input format expected: BGR ``numpy.ndarray`` (H×W×3, uint8), same as
  OpenCV output.
* Post-processing (NMS, confidence filtering, class mapping) is performed
  in NumPy/Python to keep the module dependency-light.
* Keypoint extraction for pose models follows the same 17-keypoint COCO
  layout produced by ``YOLOEngine.detect_pose()``.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from backend.inference.yolo_engine import Detection, YOLOEngine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Attempt TensorRT / PyCUDA imports — non-fatal on non-Jetson hosts
# ---------------------------------------------------------------------------

_TRT_AVAILABLE = False
try:
    import tensorrt as trt  # type: ignore[import]
    import pycuda.autoinit  # type: ignore[import]  # noqa: F401 – side-effect init
    import pycuda.driver as cuda  # type: ignore[import]

    _TRT_AVAILABLE = True
    logger.info("TRTEngine: TensorRT %s + PyCUDA available.", trt.__version__)
except Exception as _trt_import_err:  # noqa: BLE001
    logger.warning(
        "TRTEngine: TensorRT/PyCUDA not available (%s). "
        "Will delegate to YOLOEngine.",
        _trt_import_err,
    )


# ---------------------------------------------------------------------------
# COCO keypoint indices (17 keypoints, YOLOv8-pose output layout)
# ---------------------------------------------------------------------------

_COCO_KP_COUNT = 17

# YOLOv8 detection output layout per box (when ONNX is exported with
# EXPLICIT_BATCH, the output tensor is [1, num_preds, 5+nc] for detection
# and [1, num_preds, 5+nc+17*3] for pose).
_BOX_ATTRS = 4     # cx, cy, w, h
_CONF_ATTRS = 1    # objectness / box confidence

# ---------------------------------------------------------------------------
# Internal NMS helpers
# ---------------------------------------------------------------------------

def _xywh_to_xyxy(boxes_xywh: np.ndarray) -> np.ndarray:
    """Convert center-form boxes to corner-form in-place copy."""
    xy = boxes_xywh[:, :2] - boxes_xywh[:, 2:4] / 2.0
    xy2 = boxes_xywh[:, :2] + boxes_xywh[:, 2:4] / 2.0
    return np.concatenate([xy, xy2], axis=1)


def _iou(box: np.ndarray, boxes: np.ndarray) -> np.ndarray:
    """Compute IoU of one box against an array of boxes (corner form)."""
    x1 = np.maximum(box[0], boxes[:, 0])
    y1 = np.maximum(box[1], boxes[:, 1])
    x2 = np.minimum(box[2], boxes[:, 2])
    y2 = np.minimum(box[3], boxes[:, 3])
    inter = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    area_box = (box[2] - box[0]) * (box[3] - box[1])
    area_boxes = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    union = area_box + area_boxes - inter
    return np.where(union > 0, inter / union, 0.0)


def _nms(
    boxes_xyxy: np.ndarray,
    scores: np.ndarray,
    iou_threshold: float = 0.45,
) -> List[int]:
    """Greedy NMS; returns list of kept indices sorted by score descending."""
    order = scores.argsort()[::-1]
    kept: List[int] = []
    while order.size > 0:
        i = int(order[0])
        kept.append(i)
        if order.size == 1:
            break
        ious = _iou(boxes_xyxy[i], boxes_xyxy[order[1:]])
        mask = ious < iou_threshold
        order = order[1:][mask]
    return kept


# ---------------------------------------------------------------------------
# TRTEngine
# ---------------------------------------------------------------------------

class TRTEngine:
    """
    TensorRT inference engine — drop-in for :class:`YOLOEngine`.

    Parameters
    ----------
    engine_path:
        Path to the serialised ``.engine`` file produced by
        :mod:`models.export.export_tensorrt`.
    input_shape:
        Expected input tensor shape ``(N, C, H, W)``.  Must match the
        shape the engine was built with.  Default: ``(1, 3, 640, 640)``.
    conf_threshold:
        Minimum confidence score to keep a detection.
    iou_threshold:
        IoU threshold used during NMS.
    fallback_model_path:
        Path to a ``.pt`` file used when TRT is unavailable.  Only
        required on non-Jetson hosts.
    device:
        PyTorch/ultralytics device string passed to the fallback
        :class:`YOLOEngine` when TRT is not available.
    """

    # COCO class names indexed 0-79 (YOLO default).
    _COCO_NAMES: Dict[int, str] = {
        0: "person", 1: "bicycle", 2: "car", 3: "motorcycle",
        4: "airplane", 5: "bus", 6: "train", 7: "truck", 8: "boat",
        9: "traffic light", 10: "fire hydrant", 11: "stop sign",
        12: "parking meter", 13: "bench", 14: "bird", 15: "cat",
        16: "dog", 17: "horse", 18: "sheep", 19: "cow", 20: "elephant",
        21: "bear", 22: "zebra", 23: "giraffe", 24: "backpack",
        25: "umbrella", 26: "handbag", 27: "tie", 28: "suitcase",
        29: "frisbee", 30: "skis", 31: "snowboard", 32: "sports ball",
        33: "kite", 34: "baseball bat", 35: "baseball glove",
        36: "skateboard", 37: "surfboard", 38: "tennis racket",
        39: "bottle", 40: "wine glass", 41: "cup", 42: "fork",
        43: "knife", 44: "spoon", 45: "bowl", 46: "banana",
        47: "apple", 48: "sandwich", 49: "orange", 50: "broccoli",
        51: "carrot", 52: "hot dog", 53: "pizza", 54: "donut",
        55: "cake", 56: "chair", 57: "couch", 58: "potted plant",
        59: "bed", 60: "dining table", 61: "toilet", 62: "tv",
        63: "laptop", 64: "mouse", 65: "remote", 66: "keyboard",
        67: "cell phone", 68: "microwave", 69: "oven", 70: "toaster",
        71: "sink", 72: "refrigerator", 73: "book", 74: "clock",
        75: "vase", 76: "scissors", 77: "teddy bear",
        78: "hair drier", 79: "toothbrush",
    }

    def __init__(
        self,
        engine_path: str,
        input_shape: Tuple[int, int, int, int] = (1, 3, 640, 640),
        conf_threshold: float = 0.5,
        iou_threshold: float = 0.45,
        fallback_model_path: Optional[str] = None,
        device: str = "cpu",
    ) -> None:
        self._engine_path = engine_path
        self._input_shape = input_shape
        self._conf_threshold = conf_threshold
        self._iou_threshold = iou_threshold
        self._device = device

        # State flags.
        self._using_trt: bool = False
        self._fallback: Optional[YOLOEngine] = None

        # TRT runtime objects (populated in _init_trt).
        self._engine: Any = None
        self._context: Any = None
        self._stream: Any = None
        self._bindings: List[int] = []
        self._host_inputs: List[np.ndarray] = []
        self._device_inputs: List[Any] = []
        self._host_outputs: List[np.ndarray] = []
        self._device_outputs: List[Any] = []
        self._output_shapes: List[Tuple] = []
        self._input_binding_idx: int = 0

        # Track IDs are not available from raw TRT output (no ByteTrack);
        # we assign sequential per-frame IDs as a best-effort placeholder.
        self._frame_counter: int = 0

        if _TRT_AVAILABLE and os.path.isfile(engine_path):
            self._init_trt()
        else:
            self._init_fallback(fallback_model_path, device)

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------

    def _init_trt(self) -> None:
        """Deserialise the TRT engine and pre-allocate CUDA buffers."""
        logger.info("TRTEngine: loading engine from '%s' …", self._engine_path)
        try:
            TRT_LOGGER = trt.Logger(trt.Logger.WARNING)  # type: ignore[name-defined]
            runtime = trt.Runtime(TRT_LOGGER)  # type: ignore[name-defined]

            with open(self._engine_path, "rb") as f:
                engine_data = f.read()

            self._engine = runtime.deserialize_cuda_engine(engine_data)
            self._context = self._engine.create_execution_context()
            self._stream = cuda.Stream()  # type: ignore[name-defined]

            # Allocate buffers for each binding.
            for i in range(self._engine.num_bindings):
                name = self._engine.get_binding_name(i)
                dtype = trt.nptype(self._engine.get_binding_dtype(i))  # type: ignore[name-defined]

                if self._engine.binding_is_input(i):
                    shape = self._input_shape
                    self._input_binding_idx = i
                else:
                    shape = tuple(self._engine.get_binding_shape(i))
                    self._output_shapes.append(shape)

                size = int(np.prod(shape))
                host_mem = cuda.pagelocked_empty(size, dtype)  # type: ignore[name-defined]
                device_mem = cuda.mem_alloc(host_mem.nbytes)  # type: ignore[name-defined]

                self._bindings.append(int(device_mem))

                if self._engine.binding_is_input(i):
                    self._host_inputs.append(host_mem)
                    self._device_inputs.append(device_mem)
                else:
                    self._host_outputs.append(host_mem)
                    self._device_outputs.append(device_mem)

                logger.debug(
                    "TRTEngine binding[%d] '%s': shape=%s dtype=%s",
                    i, name, shape, dtype,
                )

            self._using_trt = True
            logger.info(
                "TRTEngine: engine loaded — %d input(s), %d output(s).",
                len(self._host_inputs),
                len(self._host_outputs),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "TRTEngine: failed to initialise TRT engine: %s. "
                "Falling back to YOLOEngine.",
                exc,
            )
            self._using_trt = False
            self._init_fallback(None, self._device)

    def _init_fallback(
        self,
        fallback_model_path: Optional[str],
        device: str,
    ) -> None:
        """Initialise a YOLOEngine as fallback, auto-downloading yolov8n if needed."""
        # Try supplied path first
        candidate = fallback_model_path if fallback_model_path and os.path.isfile(fallback_model_path) else None

        # Auto-discover any .pt file in models/weights/
        if candidate is None:
            weights_dir = os.path.join(os.path.dirname(__file__), "..", "..", "models", "weights")
            weights_dir = os.path.normpath(weights_dir)
            if os.path.isdir(weights_dir):
                pts = [os.path.join(weights_dir, f) for f in os.listdir(weights_dir) if f.endswith(".pt")]
                if pts:
                    candidate = pts[0]

        # Last resort: let ultralytics auto-download yolov8n.pt
        if candidate is None:
            candidate = "yolov8n.pt"
            logger.info("TRTEngine: no local .pt found — ultralytics will download yolov8n.pt on first use.")

        logger.info("TRTEngine: using YOLOEngine fallback ('%s').", candidate)
        try:
            self._fallback = YOLOEngine(
                model_path=candidate,
                device=device,
                conf_threshold=self._conf_threshold,
            )
            self._backend = "YOLOEngine-delegate"
        except Exception as exc:  # noqa: BLE001
            logger.warning("TRTEngine: YOLOEngine fallback also failed (%s) — inference disabled.", exc)
            self._fallback = None
            self._backend = "disabled"

    # ------------------------------------------------------------------
    # Pre/post-processing
    # ------------------------------------------------------------------

    def _preprocess(self, frame: np.ndarray) -> np.ndarray:
        """
        Resize, normalise, and transpose a BGR frame for TRT input.

        Returns a contiguous float32 array of shape ``(1, 3, H, W)``
        with values in [0, 1].
        """
        import cv2  # type: ignore[import]

        _, _, h, w = self._input_shape
        resized = cv2.resize(frame, (w, h), interpolation=cv2.INTER_LINEAR)
        # BGR → RGB, then HWC → CHW.
        rgb = resized[:, :, ::-1].astype(np.float32) / 255.0
        chw = np.ascontiguousarray(np.transpose(rgb, (2, 0, 1)))
        return chw[np.newaxis, :]  # (1, 3, H, W)

    def _run_trt(self, input_arr: np.ndarray) -> List[np.ndarray]:
        """Copy input to GPU, execute, copy outputs back to host."""
        np.copyto(self._host_inputs[0], input_arr.ravel())
        cuda.memcpy_htod_async(  # type: ignore[name-defined]
            self._device_inputs[0],
            self._host_inputs[0],
            self._stream,
        )
        self._context.execute_async_v2(
            bindings=self._bindings,
            stream_handle=self._stream.handle,
        )
        for h_out, d_out in zip(self._host_outputs, self._device_outputs):
            cuda.memcpy_dtoh_async(h_out, d_out, self._stream)  # type: ignore[name-defined]

        self._stream.synchronize()

        outputs = []
        for h_out, shape in zip(self._host_outputs, self._output_shapes):
            outputs.append(h_out.reshape(shape).copy())
        return outputs

    def _postprocess_detect(
        self,
        raw_outputs: List[np.ndarray],
        orig_h: int,
        orig_w: int,
    ) -> List[Detection]:
        """
        Parse raw TRT detection output → list of :class:`Detection`.

        Expected output tensor shape: ``(1, num_preds, 5 + num_classes)``
        where the first 4 columns are cx,cy,w,h and column 4 is the
        objectness score.  Remaining columns are per-class probabilities.
        """
        if not raw_outputs:
            return []

        preds = raw_outputs[0]  # shape (1, num_preds, 5+nc) or (1, 6, num_preds)

        # Handle transposed output from some exporters: (1, 6, N) → (1, N, 6)
        if preds.ndim == 3 and preds.shape[1] < preds.shape[2]:
            preds = preds.transpose(0, 2, 1)

        preds = preds[0]  # (num_preds, 5+nc)

        if preds.shape[0] == 0:
            return []

        # Objectness confidence.
        obj_conf = preds[:, 4]
        # Class probabilities → best class + confidence.
        cls_probs = preds[:, 5:]
        if cls_probs.shape[1] == 0:
            return []

        cls_ids = cls_probs.argmax(axis=1)
        cls_confs = cls_probs[np.arange(len(cls_ids)), cls_ids]
        scores = obj_conf * cls_confs

        # Confidence filter.
        mask = scores >= self._conf_threshold
        if not mask.any():
            return []

        preds_f = preds[mask]
        scores_f = scores[mask]
        cls_ids_f = cls_ids[mask]

        # Convert boxes: cx,cy,w,h (normalised) → pixel xyxy
        _, _, in_h, in_w = self._input_shape
        scale_x = orig_w / in_w
        scale_y = orig_h / in_h

        boxes_xywh = preds_f[:, :4].copy()
        boxes_xywh[:, 0] *= in_w * scale_x
        boxes_xywh[:, 1] *= in_h * scale_y
        boxes_xywh[:, 2] *= in_w * scale_x
        boxes_xywh[:, 3] *= in_h * scale_y
        boxes_xyxy = _xywh_to_xyxy(boxes_xywh)

        # NMS.
        keep = _nms(boxes_xyxy, scores_f, self._iou_threshold)

        detections: List[Detection] = []
        self._frame_counter += 1
        for rank, idx in enumerate(keep):
            x1, y1, x2, y2 = boxes_xyxy[idx].clip(0).astype(int).tolist()
            cid = int(cls_ids_f[idx])
            cname = self._COCO_NAMES.get(cid, str(cid))
            detections.append(
                Detection(
                    track_id=rank,  # best-effort; no ByteTrack in TRT path
                    class_id=cid,
                    class_name=cname,
                    confidence=float(scores_f[idx]),
                    bbox=(x1, y1, x2, y2),
                    keypoints=None,
                )
            )
        return detections

    def _postprocess_pose(
        self,
        raw_outputs: List[np.ndarray],
        orig_h: int,
        orig_w: int,
    ) -> List[Detection]:
        """
        Parse raw TRT pose output → list of :class:`Detection` with keypoints.

        Expected output shape: ``(1, num_preds, 5 + nc + 17*3)``
        where the trailing ``17*3`` columns are (kp_x, kp_y, kp_conf) × 17.
        """
        if not raw_outputs:
            return []

        preds = raw_outputs[0]

        if preds.ndim == 3 and preds.shape[1] < preds.shape[2]:
            preds = preds.transpose(0, 2, 1)

        preds = preds[0]  # (num_preds, 5 + nc + 51)

        if preds.shape[0] == 0:
            return []

        obj_conf = preds[:, 4]
        n_classes = preds.shape[1] - 5 - _COCO_KP_COUNT * 3
        n_classes = max(n_classes, 1)

        cls_probs = preds[:, 5: 5 + n_classes]
        kp_data = preds[:, 5 + n_classes:]  # (num_preds, 51)

        cls_ids = cls_probs.argmax(axis=1) if cls_probs.shape[1] > 0 else np.zeros(len(preds), dtype=int)
        cls_confs = cls_probs[np.arange(len(cls_ids)), cls_ids] if cls_probs.shape[1] > 0 else obj_conf
        scores = obj_conf * cls_confs

        mask = scores >= self._conf_threshold
        if not mask.any():
            return []

        preds_f = preds[mask]
        scores_f = scores[mask]
        cls_ids_f = cls_ids[mask]
        kp_data_f = kp_data[mask]

        _, _, in_h, in_w = self._input_shape
        scale_x = orig_w / in_w
        scale_y = orig_h / in_h

        boxes_xywh = preds_f[:, :4].copy()
        boxes_xywh[:, 0] *= in_w * scale_x
        boxes_xywh[:, 1] *= in_h * scale_y
        boxes_xywh[:, 2] *= in_w * scale_x
        boxes_xywh[:, 3] *= in_h * scale_y
        boxes_xyxy = _xywh_to_xyxy(boxes_xywh)

        keep = _nms(boxes_xyxy, scores_f, self._iou_threshold)

        detections: List[Detection] = []
        for rank, idx in enumerate(keep):
            x1, y1, x2, y2 = boxes_xyxy[idx].clip(0).astype(int).tolist()
            cid = int(cls_ids_f[idx])
            cname = self._COCO_NAMES.get(cid, str(cid))

            # Parse keypoints: reshape (51,) → (17, 3) and scale to pixels.
            raw_kp = kp_data_f[idx].reshape(_COCO_KP_COUNT, 3)
            keypoints: List[Tuple[float, float, float]] = []
            for kp in raw_kp:
                kx = float(kp[0]) * in_w * scale_x
                ky = float(kp[1]) * in_h * scale_y
                kc = float(kp[2])
                keypoints.append((kx, ky, kc))

            detections.append(
                Detection(
                    track_id=rank,
                    class_id=cid,
                    class_name=cname,
                    confidence=float(scores_f[idx]),
                    bbox=(x1, y1, x2, y2),
                    keypoints=keypoints,
                )
            )
        return detections

    # ------------------------------------------------------------------
    # Public API — identical signature to YOLOEngine
    # ------------------------------------------------------------------

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        Run object detection on *frame*.

        Parameters
        ----------
        frame:
            BGR ``numpy.ndarray`` (H×W×3, uint8).

        Returns
        -------
        List of :class:`Detection` objects (empty list on error or no detections).
        """
        if frame is None or frame.size == 0:
            return []

        if not self._using_trt:
            if self._fallback is not None:
                return self._fallback.detect(frame)
            return []

        try:
            orig_h, orig_w = frame.shape[:2]
            inp = self._preprocess(frame)
            raw_outputs = self._run_trt(inp)
            return self._postprocess_detect(raw_outputs, orig_h, orig_w)
        except Exception as exc:  # noqa: BLE001
            logger.error("TRTEngine.detect: inference error: %s", exc)
            return []

    def detect_pose(self, frame: np.ndarray) -> List[Detection]:
        """
        Run pose estimation on *frame*.

        The loaded engine must have been exported from a YOLOv8-pose model.

        Parameters
        ----------
        frame:
            BGR ``numpy.ndarray`` (H×W×3, uint8).

        Returns
        -------
        List of :class:`Detection` with the ``keypoints`` field populated.
        """
        if frame is None or frame.size == 0:
            return []

        if not self._using_trt:
            if self._fallback is not None:
                return self._fallback.detect_pose(frame)
            return []

        try:
            orig_h, orig_w = frame.shape[:2]
            inp = self._preprocess(frame)
            raw_outputs = self._run_trt(inp)
            return self._postprocess_pose(raw_outputs, orig_h, orig_w)
        except Exception as exc:  # noqa: BLE001
            logger.error("TRTEngine.detect_pose: inference error: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def __del__(self) -> None:
        """Release CUDA resources."""
        if self._using_trt:
            try:
                del self._context
                del self._engine
                for d in self._device_inputs + self._device_outputs:
                    d.free()  # type: ignore[union-attr]
            except Exception:  # noqa: BLE001
                pass
