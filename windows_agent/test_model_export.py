"""Regression tests for the real YOLO26 export path.

Run from windows_agent: python -m unittest test_model_export.py -v
These tests do not download a model or open a camera.
"""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from agent.inference import YoloInference


class _Session:
    output_shape = [1, 300, 6]

    def __init__(self, *args, **kwargs):
        pass

    def get_outputs(self):
        output = unittest.mock.Mock()
        output.shape = self.output_shape
        return [output]

    def get_inputs(self):
        input_ = unittest.mock.Mock()
        input_.name = "images"
        return [input_]

    def get_providers(self):
        return ["CPUExecutionProvider"]

    def run(self, *args, **kwargs):
        return []


class _Model:
    exported = None

    def __init__(self, exported):
        self.exported = exported

    def export(self, **kwargs):
        assert kwargs["nms"] is False, "YOLO26 requires nms=False for its native head"
        return self.exported


class YoloExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vantag-yolo-export-test-")
        self.directory = Path(self.temp.name)
        self.exported = self.directory / "export.onnx"
        self.exported.write_bytes(b"test-onnx")

    def tearDown(self):
        self.temp.cleanup()

    def test_native_export_is_requested_and_recorded(self):
        _Session.output_shape = [1, 300, 6]
        detector = object.__new__(YoloInference)
        detector.status = {"acquire_error": None}
        detector._img_size = 640
        target = self.directory / "yolo26n.onnx"
        with patch("ultralytics.YOLO", return_value=_Model(self.exported)), patch(
            "onnxruntime.InferenceSession", _Session
        ), patch.object(shutil, "copyfile", side_effect=lambda source, dest: Path(dest).write_bytes(b"test-onnx")), patch(
            "urllib.request.urlretrieve", side_effect=AssertionError("network not expected")
        ):
            detector._acquire_model(str(target))
        self.assertEqual(detector.status["model"], "yolo26n")
        self.assertIsNone(detector.status["acquire_error"])

    def test_legacy_export_is_never_cached_as_yolo26(self):
        _Session.output_shape = [1, 84, 8400]
        detector = object.__new__(YoloInference)
        detector.status = {"acquire_error": None}
        detector._img_size = 640
        target = self.directory / "yolo26n.onnx"
        with patch("ultralytics.YOLO", return_value=_Model(self.exported)), patch(
            "onnxruntime.InferenceSession", _Session
        ), patch.object(YoloInference, "_ultralytics_version", return_value="8.4.202"), patch(
            "urllib.request.urlretrieve", side_effect=AssertionError("network not expected")
        ):
            with self.assertRaisesRegex(RuntimeError, "Could not obtain a detection model"):
                detector._acquire_model(str(target))
        self.assertIn("native end-to-end head", detector.status["acquire_error"])
        self.assertFalse(target.exists())
        self.assertFalse(target.with_suffix(".json").exists())

    def test_failed_cache_repair_does_not_retry_recursively(self):
        _Session.output_shape = [1, 84, 8400]
        detector = object.__new__(YoloInference)
        detector.status = {
            "architecture": "unknown",
            "is_preferred": False,
            "model": None,
            "acquire_error": None,
            "error": None,
        }
        detector.device = "cpu"
        detector._img_size = 640
        detector._session = None
        detector._acquire_model = Mock()
        cache_dir = self.directory / ".vantag" / "models"
        cache_dir.mkdir(parents=True)
        target = cache_dir / "yolo26n.onnx"
        target.write_bytes(b"legacy-onnx")
        target.with_suffix(".json").write_text('{"model": "yolo26n"}', encoding="utf-8")

        with patch.object(Path, "home", return_value=self.directory), patch(
            "onnxruntime.InferenceSession", _Session
        ), patch("onnxruntime.get_available_providers", return_value=["CPUExecutionProvider"]):
            detector._load_model(None)

        self.assertEqual(detector._acquire_model.call_count, 1)
        self.assertFalse(detector.status["is_preferred"])


if __name__ == "__main__":
    unittest.main()
