import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent import config


class StandaloneConfigTests(unittest.TestCase):
    def test_frozen_agent_reads_config_next_to_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe_dir = root / "package"
            exe_dir.mkdir()
            (exe_dir / "config.json").write_text(json.dumps({"api_key": "tenant-key"}))
            with patch.object(sys, "frozen", True, create=True), patch.object(
                sys, "executable", str(exe_dir / "VantagAgent.exe")
            ), patch.object(config, "CONFIG_DIR", root / "state"), patch.object(
                config, "CONFIG_FILE", root / "state" / "config.json"
            ):
                self.assertEqual(config.AgentConfig.load().api_key, "tenant-key")

    def test_frozen_detector_does_not_download_missing_core_model(self):
        from agent.inference import YoloInference

        with tempfile.TemporaryDirectory() as tmp, patch.object(
            sys, "frozen", True, create=True
        ), patch.object(sys, "_MEIPASS", tmp, create=True), patch.object(
            YoloInference, "_acquire_model", side_effect=AssertionError("unexpected download")
        ):
            detector = YoloInference()
            self.assertIsNone(detector._session)
            self.assertIn("yolo26n.onnx", detector.status["error"])
            self.assertFalse(detector.status["is_preferred"])

    def test_product_counter_reports_inference_failure_and_recovery(self):
        from agent.inference import ProductCountDetector
        from unittest.mock import Mock

        detector = ProductCountDetector()
        detector._model = Mock()
        detector._model.predict.side_effect = [RuntimeError("native operation missing"), []]
        self.assertIsNone(detector.count_products(None))
        self.assertEqual(detector.status["state"], "failed")
        self.assertIn("native operation missing", detector.status["error"])
        self.assertEqual(detector.count_products(None)["count"], 0)
        self.assertEqual(detector.status["state"], "ready")
        self.assertIsNone(detector.status["error"])

    def test_frozen_detector_rejects_a_legacy_graph(self):
        from agent.inference import YoloInference
        from test_model_export import _Session

        with tempfile.TemporaryDirectory() as tmp:
            models = Path(tmp) / "models"
            models.mkdir()
            (models / "yolo26n.onnx").write_bytes(b"test-model")
            _Session.output_shape = [1, 84, 8400]
            with patch.object(sys, "frozen", True, create=True), patch.object(
                sys, "_MEIPASS", tmp, create=True
            ), patch("onnxruntime.InferenceSession", _Session), patch(
                "onnxruntime.get_available_providers", return_value=["CPUExecutionProvider"]
            ), patch.object(YoloInference, "_ultralytics_version", return_value="test"), patch.object(
                YoloInference, "_acquire_model", side_effect=AssertionError("unexpected download")
            ):
                detector = YoloInference()
                self.assertIsNone(detector._session)
                self.assertFalse(detector.status["is_preferred"])
                self.assertIn("unexpected output shape", detector.status["error"])

    def test_frozen_assets_are_resolved_from_runtime_directory(self):
        from agent import resources

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(sys, "frozen", True, create=True), patch.object(
                sys, "_MEIPASS", str(root), create=True
            ):
                self.assertEqual(resources.bundled_resource("models", "yolo26n.onnx"), root / "models" / "yolo26n.onnx")


if __name__ == "__main__":
    unittest.main()
