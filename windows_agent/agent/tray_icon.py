"""
System tray icon for the Vantag Windows Edge Agent.
Provides start/stop, status, and quit from the Windows system tray.
"""
import logging
import threading
from pathlib import Path
from typing import Callable

import pystray
from PIL import Image, ImageDraw

log = logging.getLogger("vantag.tray")

# Brand colour
VIOLET = (139, 92, 246)
DARK = (10, 10, 15)


def _make_icon(online: bool = True) -> Image.Image:
    """Generate a 64×64 icon image programmatically."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = VIOLET if online else (100, 100, 100)
    # Shield shape (simplified as rounded rectangle + circle)
    draw.rounded_rectangle([8, 4, 56, 56], radius=10, fill=color)
    draw.ellipse([22, 18, 42, 38], fill=(255, 255, 255))
    return img


class VantagTrayIcon:
    def __init__(
        self,
        on_start: Callable,
        on_stop: Callable,
        on_settings: Callable,
        on_quit: Callable,
    ):
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_settings = on_settings
        self._on_quit = on_quit
        self._icon: pystray.Icon | None = None
        self._running = False

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem("Vantag Edge Agent", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Start Monitoring",
                lambda icon, item: self._toggle_start(),
                checked=lambda item: self._running,
            ),
            pystray.MenuItem("Settings / Setup", lambda icon, item: self._on_settings()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open Web Dashboard", lambda icon, item: self._open_dashboard()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit Vantag Agent", lambda icon, item: self._quit()),
        )

    def _toggle_start(self):
        if self._running:
            self._on_stop()
            self._running = False
            self._update_icon(online=False)
            self._icon.notify("Vantag Agent stopped")
        else:
            self._on_start()
            self._running = True
            self._update_icon(online=True)
            self._icon.notify("Vantag Agent started")

    def _update_icon(self, online: bool):
        if self._icon:
            self._icon.icon = _make_icon(online=online)

    def _open_dashboard(self):
        import webbrowser
        webbrowser.open("http://localhost:3000")

    def _quit(self):
        self._on_quit()
        if self._icon:
            self._icon.stop()

    def run(self):
        """Block the calling thread with the tray icon event loop."""
        self._icon = pystray.Icon(
            "vantag",
            _make_icon(online=False),
            "Vantag Edge Agent",
            menu=self._build_menu(),
        )
        self._icon.run()
