"""
System tray icon for the Vantag Windows Edge Agent.
Provides start/stop, status, and quit from the Windows system tray.
"""
import logging
import threading
from typing import Callable

import pystray
from PIL import Image

from .resources import bundled_resource

log = logging.getLogger("vantag.tray")

# Brand colour
VIOLET = (139, 92, 246)
DARK = (10, 10, 15)


def _make_icon(online: bool = True) -> Image.Image:
    path = bundled_resource("agent", "assets", "icon.ico")
    if not path.is_file():
        path = bundled_resource("assets", "icon.ico")
    with Image.open(path) as source:
        image = source.convert("RGBA").resize((64, 64))
    if not online:
        image = image.convert("L").convert("RGBA")
    return image


class VantagTrayIcon:
    def __init__(
        self,
        on_start: Callable,
        on_stop: Callable,
        on_settings: Callable,
        on_quit: Callable,
        dashboard_url: str = "https://retail-vantag.com",
        on_open: Callable | None = None,
    ):
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_settings = on_settings
        self._on_open = on_open or self._open_dashboard
        self._on_quit = on_quit
        self._dashboard_url = dashboard_url
        self._icon: pystray.Icon | None = None
        self._running = False

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem("Vantag Edge Agent", None, enabled=False),
            pystray.MenuItem("Open Agent Status", lambda icon, item: self._on_open(), default=True),
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
            callback = self._on_stop
        else:
            callback = self._on_start
        self._running = not self._running
        self._update_icon(online=self._running)

        def apply():
            try:
                callback()
                if self._icon:
                    self._icon.notify("Vantag Agent started" if self._running else "Vantag Agent stopped")
            except Exception as exc:
                log.error("Monitoring control failed: %s", exc)

        threading.Thread(target=apply, daemon=True, name="tray-monitoring-control").start()

    def _update_icon(self, online: bool):
        if self._icon:
            self._icon.icon = _make_icon(online=online)

    def _open_dashboard(self):
        import webbrowser
        webbrowser.open(self._dashboard_url)

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
