import unittest
from unittest.mock import Mock


@unittest.skipUnless(__import__("sys").platform == "win32", "Windows desktop test")
class AgentStatusWindowTests(unittest.TestCase):
    def test_window_displays_agent_and_camera_status(self):
        from agent.status_window import AgentStatusWindow

        callbacks = {name: Mock() for name in ("on_start", "on_stop", "on_open", "on_quit")}
        window = AgentStatusWindow(
            status_provider=lambda: {
                "state": "running",
                "backend_url": "https://example.com",
                "model": "YOLO26 active",
                "cameras": [{"id": "cam-1", "name": "Reception", "status": "Offline", "fps": 0.0}],
            },
            **callbacks,
        )
        try:
            window.refresh()
            self.assertIn("cam-1", window.camera_list.get_children())
            self.assertEqual(window.camera_list.item("cam-1", "text"), "Reception")
            self.assertEqual(window.camera_list.item("cam-1", "values")[0], "Offline")
            self.assertIn("YOLO26 active", window.model_label.cget("text"))
            window.start_button.invoke()
            callbacks["on_start"].assert_called_once()
            window.open_button.invoke()
            callbacks["on_open"].assert_called_once()
            window.hide()
            self.assertEqual(window.root.state(), "withdrawn")
            window.quit()
            callbacks["on_quit"].assert_called_once()
        finally:
            if not window._closed:
                window.root.destroy()


if __name__ == "__main__":
    unittest.main()
