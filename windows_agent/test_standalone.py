import json
import sys
import tempfile
import threading
import time
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


class AgentLifecycleTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "Windows mutex test")
    def test_second_agent_instance_is_rejected(self):
        import uuid
        from agent.single_instance import SingleInstance

        name = f"vantag-test-{uuid.uuid4()}"
        first = SingleInstance(name)
        second = SingleInstance(name)
        self.assertTrue(first.acquire())
        listener = threading.Thread(target=first.listen_for_show_requests, daemon=True)
        listener.start()
        try:
            self.assertFalse(second.acquire())
            second.notify_existing()
            deadline = time.monotonic() + 2
            while not first.requested.is_set() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(first.requested.is_set())
        finally:
            second.release()
            first.release()
        self.assertTrue(second.acquire())
        second.release()

    def test_duplicate_monitoring_start_does_not_create_more_workers(self):
        from agent import main

        with patch.object(main, "_start_monitoring") as start, patch.object(
            main, "_monitoring", False
        ):
            main.start_monitoring()
            main.start_monitoring()
            self.assertEqual(start.call_count, 1)

    def test_status_snapshot_has_camera_health_without_stream_credentials(self):
        from types import SimpleNamespace
        from agent import main

        worker = SimpleNamespace(
            config=SimpleNamespace(id="cam-1", name="Reception", rtsp_url="rtsp://secret"),
            is_connected=False,
            error_msg="Cannot open rtsp://admin:secret@camera.example/stream",
            current_fps=0.0,
        )
        with patch.object(main, "_workers", [worker]), patch.object(
            main, "_config", SimpleNamespace(backend_url="https://example.com")
        ), patch.object(main, "_monitoring", True), patch.object(
            main, "_inference", SimpleNamespace(status={"is_preferred": True})
        ):
            status = main.get_agent_status()
        self.assertEqual(status["cameras"][0]["name"], "Reception")
        self.assertEqual(status["cameras"][0]["status"], "Cannot open rtsp://[hidden]")
        self.assertNotIn("secret", str(status))
        self.assertNotIn("rtsp_url", status["cameras"][0])


if __name__ == "__main__":
    unittest.main()
