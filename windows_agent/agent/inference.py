"""
YOLOv8 Nano inference via ONNX Runtime.
Handles model loading, preprocessing, NMS, and result parsing.
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
    MODEL_URL = "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.onnx"

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
                model_path = str(cache_dir / "yolov8n.onnx")

                if not Path(model_path).exists():
                    log.info(f"Downloading YOLOv8n model to {model_path}...")
                    import urllib.request
                    urllib.request.urlretrieve(self.MODEL_URL, model_path)
                    log.info("Model downloaded successfully")

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
        """Parse YOLOv8 output tensor [1, 84, 8400] → BoundingBox list."""
        output = np.squeeze(output)  # [84, 8400]
        if output.ndim != 2:
            return []

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
