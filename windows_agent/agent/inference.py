"""
YOLO26n (with automatic YOLOv8n fallback) inference via ONNX Runtime.
Handles model loading, preprocessing, and result parsing.

v1.5.0: upgraded from YOLOv8n to YOLO26n — Ultralytics' 2026 nano model.
YOLO26n is end-to-end / NMS-free: the exported ONNX graph performs its own
duplicate-suppression internally and returns a fixed-size, already-filtered
detection list. This is not just a speed upgrade — the OLD YOLOv8n path
below applied NO NMS at all (see `_postprocess_legacy`), so a single real
person standing near several overlapping anchor cells could legitimately
produce more than one detection box, quietly inflating counts. YOLO26n's
end-to-end head removes that failure mode entirely, on top of being
~2x faster on CPU, which is what makes the 5fps ByteTrack pipeline
affordable on a normal shop laptop.
"""
import logging
import time
from pathlib import Path
from typing import List, Tuple, Optional

import numpy as np

log = logging.getLogger("vantag.inference")

YOLO_CLASSES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
    "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep",
    "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
    "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard",
    "sports ball", "kite", "baseball bat", "baseball glove", "skateboard",
    "surfboard", "tennis racket", "bottle", "wine glass", "cup", "fork",
    "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
    "couch", "potted plant", "bed", "dining table", "toilet", "tv",
    "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave",
    "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase",
    "scissors", "teddy bear", "hair drier", "toothbrush",
]

# Vantag-specific class mappings for retail events
RETAIL_CLASSES = {
    "person": "person",
    "backpack": "high_value_item",
    "handbag": "high_value_item",
    "suitcase": "high_value_item",
    "bottle": "shelf_item",
    "cup": "shelf_item",
    "bowl": "shelf_item",
}


class BoundingBox:
    def __init__(self, x: float, y: float, w: float, h: float, label: str, confidence: float):
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.label = label
        self.confidence = confidence

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h, "label": self.label}


class YoloInference:
    # Ultralytics does NOT ship a prebuilt .onnx in its release assets (that URL
    # 404s). The reliable path is to let the bundled `ultralytics` package fetch
    # the .pt weights and export ONNX locally. These mirrors are only a fallback
    # for environments where ultralytics export is unavailable (and only exist
    # for YOLOv8n — there is no public YOLO26 mirror, so that path always goes
    # through ultralytics or falls all the way back to YOLOv8n).
    MODEL_URLS = [
        "https://huggingface.co/Xenova/yolov8n/resolve/main/onnx/model.onnx",
    ]

    def __init__(self, model_path: Optional[str] = None, device: str = "cpu"):
        self._session = None
        self._input_name = None
        self._img_size = 640
        self.device = device
        self._load_model(model_path)

    def _load_model(self, model_path: Optional[str]):
        try:
            import onnxruntime as ort

            # Auto-download if model not found
            if model_path is None:
                cache_dir = Path.home() / ".vantag" / "models"
                cache_dir.mkdir(parents=True, exist_ok=True)
                model_path = str(cache_dir / "yolo26n.onnx")

                if not Path(model_path).exists():
                    self._acquire_model(model_path)

            providers = ["CPUExecutionProvider"]
            if self.device == "cuda":
                providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            elif self.device == "dml":
                providers = ["DmlExecutionProvider", "CPUExecutionProvider"]

            opts = ort.SessionOptions()
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            opts.intra_op_num_threads = 4
            self._session = ort.InferenceSession(model_path, sess_options=opts, providers=providers)
            self._input_name = self._session.get_inputs()[0].name
            log.info(f"ONNX model loaded: {model_path} providers={providers}")

        except ImportError:
            log.warning("onnxruntime not installed — inference disabled (install: pip install onnxruntime)")
        except Exception as e:
            log.error(f"Failed to load ONNX model: {e}")

    def _acquire_model(self, model_path: str):
        """Obtain a detection ONNX model at ``model_path``.

        Preferred: YOLO26n (v1.5.0+, faster + NMS-free). Automatically falls
        back to YOLOv8n if the installed ``ultralytics`` version predates
        YOLO26 support, so older/offline environments keep working.
        """
        # 1) Preferred — YOLO26n via ultralytics (handles weight download too).
        try:
            from ultralytics import YOLO
            import shutil
            log.info("Preparing YOLO26n ONNX via ultralytics (first run only, ~30s)…")
            m = YOLO("yolo26n.pt")
            exported = m.export(format="onnx", imgsz=self._img_size, opset=12)
            shutil.copyfile(str(exported), model_path)
            log.info(f"YOLO26n model ready at {model_path}")
            return
        except Exception as e:  # noqa: BLE001
            log.warning(f"YOLO26n unavailable ({e}); falling back to YOLOv8n…")

        # 2) Fallback — YOLOv8n via ultralytics (older ultralytics installs).
        try:
            from ultralytics import YOLO
            import shutil
            log.info("Preparing YOLOv8n ONNX via ultralytics (first run only, ~30s)…")
            m = YOLO("yolov8n.pt")
            exported = m.export(format="onnx", imgsz=self._img_size, opset=12)
            shutil.copyfile(str(exported), model_path)
            log.info(f"Fallback YOLOv8n model ready at {model_path}")
            return
        except Exception as e:  # noqa: BLE001
            log.warning(f"ultralytics export unavailable ({e}); trying mirror download…")

        # 3) Last resort — direct download of a prebuilt YOLOv8n ONNX mirror.
        import urllib.request
        for url in self.MODEL_URLS:
            try:
                log.info(f"Downloading YOLOv8n model from {url}…")
                urllib.request.urlretrieve(url, model_path)
                log.info("Model downloaded successfully")
                return
            except Exception as e:  # noqa: BLE001
                log.warning(f"Download failed from {url}: {e}")

        raise RuntimeError("Could not obtain a detection model from ultralytics or mirrors")

    def detect(self, frame_bgr: np.ndarray, conf_threshold: float = 0.5) -> List[BoundingBox]:
        """Run inference on a BGR OpenCV frame. Returns list of BoundingBox."""
        if self._session is None:
            return []

        t0 = time.time()
        try:
            h, w = frame_bgr.shape[:2]
            blob = self._preprocess(frame_bgr)
            outputs = self._session.run(None, {self._input_name: blob})
            boxes = self._postprocess(outputs[0], w, h, conf_threshold)
            elapsed = (time.time() - t0) * 1000
            if boxes:
                log.debug(f"Inference: {len(boxes)} detections in {elapsed:.1f}ms")
            return boxes
        except Exception as e:
            log.error(f"Inference error: {e}")
            return []

    def _preprocess(self, frame_bgr: np.ndarray) -> np.ndarray:
        import cv2
        img = cv2.resize(frame_bgr, (self._img_size, self._img_size))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))
        img = np.expand_dims(img, axis=0)
        return img

    def _postprocess(self, output: np.ndarray, orig_w: int, orig_h: int, conf: float) -> List[BoundingBox]:
        """Parse a detector output tensor into a BoundingBox list.

        Auto-detects which model produced ``output`` so this works with
        either the current YOLO26n (end-to-end/NMS-free) or a YOLOv8n
        fallback, without needing to know which one loaded at runtime:

          - YOLO26n end-to-end: squeezed shape (<=300, 6) = already-final
            ``[x1, y1, x2, y2, confidence, class_id]`` rows, no NMS needed.
          - YOLOv8n legacy: squeezed shape (84, 8400) = raw per-anchor grid
            requiring an argmax over classes + manual score filtering (see
            `_postprocess_legacy`). This path has 8400 rows/anchors, which
            can never collide with the end-to-end shape's <=300 rows.
        """
        output = np.squeeze(output)
        if output.ndim != 2:
            return []
        if output.shape[-1] == 6 and output.shape[0] <= 300:
            return self._postprocess_end2end(output, conf)
        return self._postprocess_legacy(output, conf)

    def _postprocess_end2end(self, dets: np.ndarray, conf: float) -> List[BoundingBox]:
        """YOLO26 end-to-end rows: [x1, y1, x2, y2, confidence, class_id],
        already de-duplicated by the model — just filter by confidence."""
        s = float(self._img_size)
        results = []
        for x1, y1, x2, y2, score, cls_id in dets:
            if score < conf:
                continue
            cls_id = int(cls_id)
            label = YOLO_CLASSES[cls_id] if 0 <= cls_id < len(YOLO_CLASSES) else "unknown"
            results.append(BoundingBox(
                x=max(0.0, float(x1) / s), y=max(0.0, float(y1) / s),
                w=min(1.0, float(x2 - x1) / s), h=min(1.0, float(y2 - y1) / s),
                label=label, confidence=float(score),
            ))
        return results[:50]

    def _postprocess_legacy(self, output: np.ndarray, conf: float) -> List[BoundingBox]:
        """Parse a YOLOv8-style raw output tensor [84, 8400] → BoundingBox list.

        No NMS is applied here (fallback-only path) — the current model is
        YOLO26n, which needs none. If a YOLOv8n fallback is ever active this
        can produce duplicate boxes for one object, a known limitation of
        this fallback path only.
        """
        boxes = output[:4].T       # [8400, 4] — cx, cy, w, h (normalized)
        scores = output[4:].T      # [8400, 80]

        max_scores = scores.max(axis=1)
        class_ids = scores.argmax(axis=1)

        results = []
        for i, (score, cls_id) in enumerate(zip(max_scores, class_ids)):
            if score < conf:
                continue
            cx, cy, bw, bh = boxes[i]
            label = YOLO_CLASSES[cls_id] if cls_id < len(YOLO_CLASSES) else "unknown"
            # Normalize to 0-1 relative to original frame
            x = float(cx - bw / 2) / self._img_size
            y = float(cy - bh / 2) / self._img_size
            nw = float(bw) / self._img_size
            nh = float(bh) / self._img_size
            results.append(BoundingBox(
                x=max(0.0, x), y=max(0.0, y),
                w=min(1.0, nw), h=min(1.0, nh),
                label=label, confidence=float(score)
            ))

        return results[:50]  # cap at 50 boxes


# ---------------------------------------------------------------------------
# Pose estimation (YOLOv8n-pose) — used for concealment-gesture shoplifting
# detection. 17 COCO keypoints per person.
# ---------------------------------------------------------------------------

COCO_KEYPOINTS = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
]

# Keypoint indices used by the concealment heuristic
KP_L_SHOULDER, KP_R_SHOULDER = 5, 6
KP_L_WRIST, KP_R_WRIST = 9, 10
KP_L_HIP, KP_R_HIP = 11, 12


class PersonPose:
    """A detected person with 17 COCO keypoints.

    ``keypoints`` is an ndarray [17, 3] of (x, y, conf) with x/y normalized
    to 0-1 relative to the original frame.
    """

    def __init__(self, box: BoundingBox, keypoints: np.ndarray):
        self.box = box
        self.keypoints = keypoints

    def kp(self, idx: int, min_conf: float = 0.3):
        """Return (x, y) for keypoint ``idx`` or None if below confidence."""
        x, y, c = self.keypoints[idx]
        if c < min_conf:
            return None
        return float(x), float(y)

    def to_dict(self) -> dict:
        return {
            "box": self.box.to_dict(),
            "keypoints": {
                COCO_KEYPOINTS[i]: [round(float(x), 4), round(float(y), 4), round(float(c), 3)]
                for i, (x, y, c) in enumerate(self.keypoints)
            },
        }


class YoloPoseInference(YoloInference):
    """YOLOv8n-pose via ONNX Runtime.

    Output tensor is [1, 56, 8400]: 4 box coords + 1 person conf +
    17 keypoints x (x, y, conf). Coordinates are in 640-input pixel space.
    """

    MODEL_URLS = []  # no reliable prebuilt pose ONNX mirror — export locally

    def _load_model(self, model_path: Optional[str]):
        try:
            import onnxruntime as ort

            if model_path is None:
                cache_dir = Path.home() / ".vantag" / "models"
                cache_dir.mkdir(parents=True, exist_ok=True)
                model_path = str(cache_dir / "yolov8n-pose.onnx")

                if not Path(model_path).exists():
                    self._acquire_model(model_path)

            providers = ["CPUExecutionProvider"]
            if self.device == "cuda":
                providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            elif self.device == "dml":
                providers = ["DmlExecutionProvider", "CPUExecutionProvider"]

            opts = ort.SessionOptions()
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            opts.intra_op_num_threads = 4
            self._session = ort.InferenceSession(model_path, sess_options=opts, providers=providers)
            self._input_name = self._session.get_inputs()[0].name
            log.info(f"ONNX pose model loaded: {model_path} providers={providers}")

        except ImportError:
            log.warning("onnxruntime not installed — pose inference disabled")
        except Exception as e:
            log.error(f"Failed to load ONNX pose model: {e}")

    def _acquire_model(self, model_path: str):
        try:
            from ultralytics import YOLO
            import shutil
            log.info("Preparing YOLOv8n-pose ONNX via ultralytics (first run only, ~30s)…")
            m = YOLO("yolov8n-pose.pt")
            exported = m.export(format="onnx", imgsz=self._img_size, opset=12)
            shutil.copyfile(str(exported), model_path)
            log.info(f"Pose model ready at {model_path}")
            return
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"Could not obtain YOLOv8n-pose model: {e}")

    def detect_poses(self, frame_bgr: np.ndarray, conf_threshold: float = 0.4) -> List["PersonPose"]:
        """Run pose inference on a BGR frame. Returns list of PersonPose."""
        if self._session is None:
            return []
        try:
            blob = self._preprocess(frame_bgr)
            outputs = self._session.run(None, {self._input_name: blob})
            return self._postprocess_pose(outputs[0], conf_threshold)
        except Exception as e:
            log.error(f"Pose inference error: {e}")
            return []

    def _postprocess_pose(self, output: np.ndarray, conf: float) -> List["PersonPose"]:
        output = np.squeeze(output)  # [56, 8400]
        if output.ndim != 2 or output.shape[0] != 56:
            return []

        boxes = output[:4].T          # [8400, 4] cx, cy, w, h (640-px space)
        scores = output[4]            # [8400] person confidence
        kps = output[5:].T            # [8400, 51] → 17 x (x, y, conf)

        keep = np.where(scores >= conf)[0]
        if keep.size == 0:
            return []

        # Greedy NMS on the kept candidates (pose head has no class NMS baked in)
        order = keep[np.argsort(-scores[keep])]
        selected = []
        for i in order:
            cx, cy, bw, bh = boxes[i]
            dup = False
            for j in selected:
                cx2, cy2, bw2, bh2 = boxes[j]
                # IoU approximation via center distance vs half-extent
                if abs(cx - cx2) < (bw + bw2) * 0.3 and abs(cy - cy2) < (bh + bh2) * 0.3:
                    dup = True
                    break
            if not dup:
                selected.append(i)
            if len(selected) >= 20:
                break

        results = []
        s = float(self._img_size)
        for i in selected:
            cx, cy, bw, bh = boxes[i]
            box = BoundingBox(
                x=max(0.0, float(cx - bw / 2) / s),
                y=max(0.0, float(cy - bh / 2) / s),
                w=min(1.0, float(bw) / s),
                h=min(1.0, float(bh) / s),
                label="person",
                confidence=float(scores[i]),
            )
            pts = kps[i].reshape(17, 3).astype(np.float64).copy()
            pts[:, 0] /= s
            pts[:, 1] /= s
            results.append(PersonPose(box, pts))
        return results
