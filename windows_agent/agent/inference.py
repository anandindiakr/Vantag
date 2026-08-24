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
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple, Optional

import numpy as np

log = logging.getLogger("vantag.inference")


def _parse_version(v: str) -> tuple:
    """Parse a version string into a comparable integer tuple.

    Tolerant by design: unknown / not-installed / dev suffixes degrade to
    ``(0, 0, 0)`` so a version check can only ever be *conservative* (i.e.
    treat the install as too old and fall back), never optimistic.
    """
    parts = []
    for chunk in str(v).split(".")[:3]:
        digits = ""
        for ch in chunk:
            if ch.isdigit():
                digits += ch
            else:
                break
        if not digits:
            break
        parts.append(int(digits))
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


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

    # The model this build is SUPPOSED to run. Anything else is a fallback and
    # is reported as such rather than passing silently.
    PREFERRED_MODEL = "yolo26n"
    PREFERRED_WEIGHTS = "yolo26n.pt"

    def __init__(self, model_path: Optional[str] = None, device: str = "cpu"):
        self._session = None
        self._input_name = None
        self._img_size = 640
        # The ONNX session is shared by all camera workers. Serializing the
        # short session.run section keeps CPU thread pools bounded and avoids
        # provider-specific races while capture/inference remains per-camera.
        self._inference_lock = threading.RLock()
        self.device = device
        # Machine-readable record of what actually loaded, sent to the backend
        # in the heartbeat and shown on the admin panel. "unknown" until the
        # ONNX graph has been inspected — never optimistically "yolo26".
        self.status: dict = {
            "architecture": "unknown",
            "is_preferred": False,
            "model": None,
            "expected_model": self.PREFERRED_MODEL,
            "ultralytics": self._ultralytics_version(),
            "acquire_error": None,
            "error": None,
            "provider": None,
            "inference_count": 0,
            "last_inference_ms": 0.0,
            "avg_inference_ms": 0.0,
        }
        self._inference_count = 0
        self._total_inference_ms = 0.0
        self._load_model(model_path)

    def _load_model(self, model_path: Optional[str]):
        try:
            import onnxruntime as ort

            # Auto-download if model not found
            if model_path is None:
                cache_dir = Path.home() / ".vantag" / "models"
                cache_dir.mkdir(parents=True, exist_ok=True)
                model_path = str(cache_dir / "yolo26n.onnx")

                # A cache file may have been written by an OLDER agent build
                # that fell back to YOLOv8n — it is still named
                # "yolo26n.onnx", so its NAME proves nothing. The manifest
                # records what actually landed there. If it is missing (old
                # cache) or records a fallback, re-acquire so a one-off
                # network/export failure cannot pin this machine to YOLOv8n
                # permanently.
                manifest = Path(model_path).with_suffix(".json")
                stale = False
                if Path(model_path).exists():
                    try:
                        rec = json.loads(manifest.read_text(encoding="utf-8"))
                        stale = rec.get("model") != self.PREFERRED_MODEL
                        if stale:
                            log.warning(
                                "Cached detector is %s, not %s — re-acquiring.",
                                rec.get("model"), self.PREFERRED_MODEL,
                            )
                    except Exception:  # noqa: BLE001 — missing/corrupt manifest
                        stale = True
                        log.warning(
                            "Cached detector at %s has no manifest (written by an "
                            "older agent) — re-acquiring to confirm YOLO26.",
                            model_path,
                        )

                if stale or not Path(model_path).exists():
                    self._acquire_model(model_path)

            available = set(ort.get_available_providers())
            providers = ["CPUExecutionProvider"]
            if self.device == "cuda" and "CUDAExecutionProvider" in available:
                providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            elif self.device == "dml" and "DmlExecutionProvider" in available:
                providers = ["DmlExecutionProvider", "CPUExecutionProvider"]
            elif self.device in {"cuda", "dml"}:
                log.warning(
                    "Requested %s provider is unavailable (%s); using CPUExecutionProvider.",
                    self.device,
                    sorted(available),
                )

            opts = ort.SessionOptions()
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            # One shared session serves all camera workers. A bounded pool
            # prevents each store camera from multiplying CPU threads.
            env_threads = os.getenv("VANTAG_ORT_INTRA_OP_THREADS")
            try:
                intra_threads = max(1, int(env_threads)) if env_threads else min(
                    4, max(1, (os.cpu_count() or 2) // 2)
                )
            except ValueError:
                intra_threads = min(4, max(1, (os.cpu_count() or 2) // 2))
            opts.intra_op_num_threads = intra_threads
            opts.inter_op_num_threads = 1
            self._session = ort.InferenceSession(model_path, sess_options=opts, providers=providers)
            self._input_name = self._session.get_inputs()[0].name
            self.status["provider"] = self._session.get_providers()[0]
            # Warm up ORT's graph/kernels once at startup. Without this, the
            # first live frame absorbs graph allocation and looks like a
            # dropped/late incident on CPU-only store machines.
            try:
                warmup = np.zeros((1, 3, self._img_size, self._img_size), dtype=np.float32)
                self._session.run(None, {self._input_name: warmup})
            except Exception as warmup_exc:  # noqa: BLE001
                log.debug("ONNX warm-up skipped: %s", warmup_exc)
            self._verify_architecture(model_path)
            log.info(f"ONNX model loaded: {model_path} providers={providers}")

        except ImportError:
            log.warning("onnxruntime not installed — inference disabled (install: pip install onnxruntime)")
            self.status["error"] = "onnxruntime not installed"
        except Exception as e:
            log.error(f"Failed to load ONNX model: {e}")
            self.status["error"] = str(e)[:300]

    def _verify_architecture(self, model_path: str) -> None:
        """Determine from the loaded ONNX graph which architecture is ACTUALLY
        running, and record it in ``self.status``.

        This does not trust the cache filename or the manifest — it reads the
        graph's own output shape, which is unforgeable:

          * YOLO26 end-to-end one-to-one head -> ``(N, 300, 6)``
          * YOLOv8 / one-to-many head         -> ``(N, 84, 8400)``

        The result is surfaced to the backend heartbeat so the dashboard can
        state plainly which model is live instead of assuming the upgrade
        took effect.
        """
        try:
            out = self._session.get_outputs()[0]
            shape = [d if isinstance(d, int) else -1 for d in (out.shape or [])]
            # Drop dynamic/batch dims (-1) so a dynamic batch axis cannot
            # confuse the check. The trailing dim is what distinguishes the
            # two heads: 6 (x1,y1,x2,y2,conf,cls) for YOLO26 end-to-end vs
            # 8400 anchor predictions for the legacy YOLOv8 head.
            dims = [d for d in shape if d and d > 0]
            end2end = bool(dims) and dims[-1] == 6
            self.status.update({
                "onnx_output_shape": shape,
                "architecture": "yolo26-end2end" if end2end else "yolov8-legacy-nms",
                "is_preferred": bool(end2end),
                "model_path": model_path,
            })
            if end2end:
                log.info(
                    "Detector architecture CONFIRMED: YOLO26 end-to-end "
                    "(NMS-free), output shape=%s", shape,
                )
            else:
                log.warning(
                    "Detector architecture is YOLOv8 LEGACY (output shape=%s). "
                    "YOLO26 is NOT active — counts go through the fallback NMS "
                    "path. Reason for fallback: %s",
                    shape, self.status.get("acquire_error") or "unknown",
                )
                # Self-heal: if the manifest claims YOLO26 but the graph is
                # legacy, the export silently produced the wrong head (a known
                # ultralytics failure mode where the training branch is traced
                # instead of the one-to-one inference branch). Left alone, the
                # staleness check reads the manifest, sees "yolo26n", and never
                # re-acquires — pinning the machine to the fallback forever.
                # Rewriting the manifest with what actually loaded makes the
                # next start re-export instead.
                self._correct_manifest(model_path, "yolov8-legacy-nms")
        except Exception as e:  # noqa: BLE001
            log.warning(f"Could not verify detector architecture: {e}")

    @staticmethod
    def _correct_manifest(model_path: str, actual: str) -> None:
        try:
            manifest = Path(model_path).with_suffix(".json")
            rec = {}
            if manifest.exists():
                try:
                    rec = json.loads(manifest.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    rec = {}
            if rec.get("model") == YoloInference.PREFERRED_MODEL:
                rec["model"] = actual
                rec["corrected_by_graph_inspection"] = True
                manifest.write_text(json.dumps(rec), encoding="utf-8")
                log.warning(
                    "Manifest claimed %s but the ONNX graph is %s — manifest "
                    "corrected so the next agent start re-exports.",
                    YoloInference.PREFERRED_MODEL, actual,
                )
        except Exception:  # noqa: BLE001 — manifest is advisory only
            pass


    def _acquire_model(self, model_path: str):
        """Obtain a detection ONNX model at ``model_path``.

        Preferred: YOLO26n (v1.5.0+, faster + NMS-free). Automatically falls
        back to YOLOv8n if the installed ``ultralytics`` version predates
        YOLO26 support, so older/offline environments keep working.

        Every fallback reason is recorded in ``self.status`` and reported to
        the backend, so a silent downgrade is impossible.
        """
        manifest = Path(model_path).with_suffix(".json")

        def _record(model_name: str) -> None:
            try:
                manifest.write_text(json.dumps({
                    "model": model_name,
                    "acquired_at": datetime.now(timezone.utc).isoformat(),
                    "ultralytics": self._ultralytics_version(),
                }), encoding="utf-8")
            except Exception:  # noqa: BLE001 — manifest is advisory only
                pass
            self.status["model"] = model_name

        # 1) Preferred — YOLO26n via ultralytics (handles weight download too).
        try:
            # MUST be set BEFORE `import ultralytics` — ultralytics reads
            # YOLO_AUTOINSTALL once at module import time into a constant, so
            # setting it afterwards is a no-op. This stops ultralytics from
            # trying to pip-install onnxslim over the network mid-export on a
            # customer machine (which fails on any locked-down Python install
            # and silently degrades the export).
            os.environ.setdefault("YOLO_AUTOINSTALL", "false")
            from ultralytics import YOLO
            import shutil

            # YOLO26 does not exist before ultralytics 8.4.0 — on 8.3.x the
            # YOLO() call fails with an opaque error and we silently ran
            # YOLOv8n instead. Check explicitly so the recorded reason names
            # the actual problem (and tells the operator how to fix it).
            _uv = self._ultralytics_version()
            if _parse_version(_uv) < (8, 4, 0):
                raise RuntimeError(
                    f"ultralytics {_uv} is too old for YOLO26 (requires >=8.4.0). "
                    f"Fix: pip install --upgrade 'ultralytics>=8.4.0'"
                )

            log.info(
                "Preparing YOLO26n ONNX via ultralytics "
                "(first run only, ~60s on a typical CPU)…"
            )
            # Never let ultralytics pip-install anything at runtime on a
            # customer machine. Every dependency the export needs (onnxslim
            # for simplify=True) is pinned in requirements.txt; a runtime
            # AutoUpdate attempt just fails noisily on locked-down Python
            # installs and silently degrades the export.
            os.environ.setdefault("YOLO_AUTOINSTALL", "false")
            m = YOLO(self.PREFERRED_WEIGHTS)

            # opset: 12 was pinned here originally and CANNOT represent YOLO26's
            # end-to-end one-to-one head, so the export raised on every machine
            # and the agent fell back to YOLOv8n. 19 is the opset the ONNX
            # Runtime CPU provider handles best for this head; leaving it
            # unpinned made the export non-deterministic across ultralytics
            # releases.
            # nms is deliberately NOT passed: YOLO26 is already NMS-free
            # end-to-end, and asking for NMS applies it twice, which drops
            # overlapping people — exactly the doorway case people counting
            # depends on.
            # dynamic=False keeps a fixed input shape, which both avoids a
            # known fragility in the e2e head export and lets ORT plan memory.
            exported = m.export(
                format="onnx",
                imgsz=self._img_size,
                opset=19,
                dynamic=False,
                simplify=True,
            )
            shutil.copyfile(str(exported), model_path)
            _record(self.PREFERRED_MODEL)
            log.info(f"YOLO26n model ready at {model_path}")
            return
        except Exception as e:  # noqa: BLE001
            self.status["acquire_error"] = f"{type(e).__name__}: {e}"[:300]
            log.warning(f"YOLO26n unavailable ({e}); falling back to YOLOv8n…")


        # 2) Fallback — YOLOv8n via ultralytics (older ultralytics installs).
        try:
            from ultralytics import YOLO
            import shutil
            log.info("Preparing YOLOv8n ONNX via ultralytics (first run only, ~30s)…")
            m = YOLO("yolov8n.pt")
            exported = m.export(format="onnx", imgsz=self._img_size, opset=12)
            shutil.copyfile(str(exported), model_path)
            _record("yolov8n")
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
                _record("yolov8n-mirror")
                log.info("Model downloaded successfully")
                return
            except Exception as e:  # noqa: BLE001
                log.warning(f"Download failed from {url}: {e}")

        raise RuntimeError("Could not obtain a detection model from ultralytics or mirrors")

    @staticmethod
    def _ultralytics_version() -> str:
        try:
            import ultralytics
            return str(getattr(ultralytics, "__version__", "unknown"))
        except Exception:  # noqa: BLE001
            return "not-installed"

    def detect(self, frame_bgr: np.ndarray, conf_threshold: float = 0.5) -> List[BoundingBox]:
        """Run inference on a BGR OpenCV frame. Returns list of BoundingBox."""
        if self._session is None:
            return []

        t0 = time.time()
        try:
            h, w = frame_bgr.shape[:2]
            blob = self._preprocess(frame_bgr)
            with self._inference_lock:
                outputs = self._session.run(None, {self._input_name: blob})
            boxes = self._postprocess(outputs[0], w, h, conf_threshold)
            elapsed = (time.perf_counter() - t0) * 1000.0
            with self._inference_lock:
                self._inference_count += 1
                self._total_inference_ms += elapsed
                self.status.update({
                    "inference_count": self._inference_count,
                    "last_inference_ms": round(elapsed, 2),
                    "avg_inference_ms": round(
                        self._total_inference_ms / self._inference_count, 2
                    ),
                })
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

        NMS **is** applied here. Previously it was not, on the reasoning that
        the fallback "should never" be active — but when it silently was, one
        person produced several overlapping boxes and every person-counting
        and crowding figure derived from them was inflated. A fallback that
        corrupts counts is worse than no fallback, so it now de-duplicates.
        """
        boxes = output[:4].T       # [8400, 4] — cx, cy, w, h (normalized)
        scores = output[4:].T      # [8400, 80]

        max_scores = scores.max(axis=1)
        class_ids = scores.argmax(axis=1)

        keep = max_scores >= conf
        if not np.any(keep):
            return []

        idx = np.nonzero(keep)[0]
        cand = []
        for i in idx:
            cx, cy, bw, bh = boxes[i]
            x1 = float(cx - bw / 2)
            y1 = float(cy - bh / 2)
            cand.append((x1, y1, x1 + float(bw), y1 + float(bh),
                         float(max_scores[i]), int(class_ids[i])))

        kept = self._nms(cand, iou_threshold=0.45)

        s = float(self._img_size)
        results = []
        for x1, y1, x2, y2, score, cls_id in kept[:50]:
            label = YOLO_CLASSES[cls_id] if cls_id < len(YOLO_CLASSES) else "unknown"
            results.append(BoundingBox(
                x=max(0.0, x1 / s), y=max(0.0, y1 / s),
                w=min(1.0, (x2 - x1) / s), h=min(1.0, (y2 - y1) / s),
                label=label, confidence=score,
            ))
        return results

    @staticmethod
    def _nms(dets: list, iou_threshold: float = 0.45) -> list:
        """Greedy per-class non-maximum suppression.

        ``dets`` are ``(x1, y1, x2, y2, score, cls_id)`` tuples in model-input
        pixel space. Suppression is per class so a person standing in front of
        a bottle never suppresses the bottle.
        """
        out: list = []
        by_cls: dict = {}
        for d in dets:
            by_cls.setdefault(d[5], []).append(d)

        for cls_dets in by_cls.values():
            cls_dets.sort(key=lambda d: d[4], reverse=True)
            while cls_dets:
                best = cls_dets.pop(0)
                out.append(best)
                bx1, by1, bx2, by2 = best[:4]
                b_area = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
                remaining = []
                for d in cls_dets:
                    ix1, iy1 = max(bx1, d[0]), max(by1, d[1])
                    ix2, iy2 = min(bx2, d[2]), min(by2, d[3])
                    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
                    inter = iw * ih
                    d_area = max(0.0, d[2] - d[0]) * max(0.0, d[3] - d[1])
                    union = b_area + d_area - inter
                    if union <= 0 or (inter / union) <= iou_threshold:
                        remaining.append(d)
                cls_dets = remaining

        out.sort(key=lambda d: d[4], reverse=True)
        return out


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

            available = set(ort.get_available_providers())
            providers = ["CPUExecutionProvider"]
            if self.device == "cuda" and "CUDAExecutionProvider" in available:
                providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            elif self.device == "dml" and "DmlExecutionProvider" in available:
                providers = ["DmlExecutionProvider", "CPUExecutionProvider"]
            elif self.device in {"cuda", "dml"}:
                log.warning(
                    "Requested pose provider %s is unavailable (%s); using CPU.",
                    self.device,
                    sorted(available),
                )

            opts = ort.SessionOptions()
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            env_threads = os.getenv("VANTAG_ORT_INTRA_OP_THREADS")
            try:
                opts.intra_op_num_threads = max(1, int(env_threads)) if env_threads else min(
                    4, max(1, (os.cpu_count() or 2) // 2)
                )
            except ValueError:
                opts.intra_op_num_threads = min(4, max(1, (os.cpu_count() or 2) // 2))
            opts.inter_op_num_threads = 1
            self._session = ort.InferenceSession(model_path, sess_options=opts, providers=providers)
            self._input_name = self._session.get_inputs()[0].name
            try:
                warmup = np.zeros((1, 3, self._img_size, self._img_size), dtype=np.float32)
                self._session.run(None, {self._input_name: warmup})
            except Exception as warmup_exc:  # noqa: BLE001
                log.debug("ONNX pose warm-up skipped: %s", warmup_exc)
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
            with self._inference_lock:
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


# ---------------------------------------------------------------------------
# Tier 2 shelf/inventory-movement: open-vocabulary product-count detector
# (YOLO-World via ultralytics). Loaded lazily and ONLY invoked when Tier 1's
# per-frame CV histogram signal (see camera_worker.py) proposes a candidate
# shelf-zone change — it never runs per-frame, so calling the ultralytics
# Python API directly (rather than hand-parsing a custom ONNX export) is the
# right trade-off here: correctness over raw speed, since call frequency is
# at most a handful of times per hour per zone.
# ---------------------------------------------------------------------------

PRODUCT_PROMPT_CLASSES = [
    "packaged product", "bottle", "box", "can", "jar", "carton", "package",
]


class ProductCountDetector:
    """Open-vocabulary product/emptiness counter for a small shelf-zone crop.

    Uses YOLO-World (``yolov8s-worldv2.pt``) with a fixed text-prompt
    vocabulary — zero training data required, per the approved Tier 2 scope.
    Lazily loaded on first actual use so agents with no shelf zones
    configured never pay the extra weight download/load cost, and shared
    as a single instance across all camera workers (main.py creates one and
    passes it to every CameraWorker) so multiple shelf-monitored cameras
    don't each load a separate copy of the model into memory.
    """

    def __init__(self):
        self._model = None
        self._load_failed = False
        # YOLO-World is shared by all camera workers. Ultralytics predictors
        # keep mutable state, so never invoke the same model concurrently.
        self._model_lock = threading.RLock()

    def _ensure_loaded(self):
        if self._model is not None or self._load_failed:
            return
        with self._model_lock:
            if self._model is not None or self._load_failed:
                return
            try:
                from ultralytics import YOLO
                log.info(
                    "Loading YOLO-World (yolov8s-worldv2.pt) for shelf product "
                    "counting (first use only, ~30s)…"
                )
                m = YOLO("yolov8s-worldv2.pt")
                m.set_classes(PRODUCT_PROMPT_CLASSES)
                self._model = m
                log.info("YOLO-World shelf product counter ready.")
            except Exception as e:  # noqa: BLE001
                log.warning(
                    f"YOLO-World unavailable ({e}) — Tier 2 product counting "
                    f"disabled for this session; shelf zones will fall back to "
                    f"the Tier 1 CV-only signal."
                )
                self._load_failed = True

    def count_products(self, crop: np.ndarray, conf_threshold: float = 0.15) -> Optional[dict]:
        """Run product detection on a shelf-zone crop.

        Returns ``None`` if the model isn't available for any reason —
        callers MUST treat that as "no Tier 2 signal" and fall back to
        Tier 1 alone; this method never raises. On success returns
        ``{"count": int, "mean_confidence": float}``.
        """
        self._ensure_loaded()
        if self._model is None:
            return None
        try:
            with self._model_lock:
                results = self._model.predict(crop, conf=conf_threshold, verbose=False)
            if not results:
                return {"count": 0, "mean_confidence": 0.0}
            boxes = results[0].boxes
            if boxes is None or len(boxes) == 0:
                return {"count": 0, "mean_confidence": 0.0}
            confs = boxes.conf.tolist() if boxes.conf is not None else []
            mean_conf = float(sum(confs) / len(confs)) if confs else 0.0
            return {"count": int(len(boxes)), "mean_confidence": round(mean_conf, 3)}
        except Exception as e:  # noqa: BLE001
            log.warning(f"Product count inference failed: {e}")
            return None
