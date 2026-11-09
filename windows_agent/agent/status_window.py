import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable

from .resources import bundled_resource


class AgentStatusWindow:
    def __init__(
        self,
        status_provider: Callable[[], dict] | None = None,
        on_start: Callable = lambda: None,
        on_stop: Callable = lambda: None,
        on_open: Callable = lambda: None,
        on_quit: Callable = lambda: None,
    ):
        self.status_provider = status_provider or (lambda: {"state": "starting", "cameras": []})
        self.on_start = on_start
        self.on_stop = on_stop
        self.on_open = on_open
        self.on_quit = on_quit
        self._closed = False
        self.root = tk.Tk()
        self.root.title("Vantag Edge Agent")
        self.root.geometry("650x480")
        self.root.minsize(560, 400)
        self.root.configure(bg="#11101b")
        try:
            icon_path = bundled_resource("agent", "assets", "icon.ico")
            if not icon_path.is_file():
                icon_path = bundled_resource("assets", "icon.ico")
            self.root.iconbitmap(str(icon_path))
        except tk.TclError:
            pass
        self.root.protocol("WM_DELETE_WINDOW", self.hide)
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Treeview", background="#191827", fieldbackground="#191827", foreground="#eeeeff", rowheight=28)
        style.configure("Treeview.Heading", background="#29243d", foreground="#ffffff")
        tk.Label(self.root, text="Vantag Edge Agent", bg="#11101b", fg="#ffffff", font=("Segoe UI", 20, "bold")).pack(anchor="w", padx=24, pady=(22, 4))
        self.state_label = tk.Label(self.root, text="Starting…", bg="#11101b", fg="#b9a5ff", font=("Segoe UI", 11))
        self.state_label.pack(anchor="w", padx=24)
        self.backend_label = tk.Label(self.root, text="Connecting to your Vantag account", bg="#11101b", fg="#b4b1c3", font=("Segoe UI", 9))
        self.backend_label.pack(anchor="w", padx=24, pady=(4, 0))
        self.model_label = tk.Label(self.root, text="AI model: starting", bg="#11101b", fg="#b4b1c3", font=("Segoe UI", 9))
        self.model_label.pack(anchor="w", padx=24, pady=(2, 12))
        self.camera_list = ttk.Treeview(self.root, columns=("status", "fps"), show="tree headings", height=7)
        self.camera_list.heading("#0", text="Camera")
        self.camera_list.heading("status", text="Status")
        self.camera_list.heading("fps", text="FPS")
        self.camera_list.column("#0", width=260)
        self.camera_list.column("status", width=230)
        self.camera_list.column("fps", width=60, anchor="center")
        self.camera_list.pack(fill="both", expand=True, padx=24, pady=(0, 14))
        controls = tk.Frame(self.root, bg="#11101b")
        controls.pack(fill="x", padx=24, pady=(0, 20))
        self.start_button = tk.Button(controls, text="Start monitoring", command=self.on_start, bg="#7157d9", fg="white", relief="flat", padx=12, pady=7)
        self.start_button.pack(side="left")
        self.stop_button = tk.Button(controls, text="Stop", command=self.on_stop, bg="#2b283b", fg="white", relief="flat", padx=12, pady=7)
        self.stop_button.pack(side="left", padx=8)
        self.open_button = tk.Button(controls, text="Open dashboard", command=self.on_open, bg="#2b283b", fg="white", relief="flat", padx=12, pady=7)
        self.open_button.pack(side="left")
        tk.Button(controls, text="Quit agent", command=self.quit, bg="#2b283b", fg="white", relief="flat", padx=12, pady=7).pack(side="right")
        tk.Label(self.root, text="Closing this window keeps the agent running in the system tray.", bg="#11101b", fg="#89859a", font=("Segoe UI", 8)).pack(pady=(0, 12))
        self.refresh()

    def set_status_provider(self, provider: Callable[[], dict]) -> None:
        self.status_provider = provider

    def refresh(self) -> None:
        if self._closed:
            return
        try:
            status = self.status_provider()
            state = status.get("state", "starting")
            self.state_label.configure(text={"starting": "Starting — please wait", "running": "Monitoring is running", "stopped": "Monitoring is stopped"}.get(state, str(state)))
            self.backend_label.configure(text=status.get("backend_url") or "Preparing backend connection")
            self.model_label.configure(text=f"AI model: {status.get('model') or 'Starting'}")
            existing = set(self.camera_list.get_children())
            cameras = status.get("cameras", [])
            for camera in cameras:
                item = camera.get("id") or camera["name"]
                values = (camera.get("status") or "Unknown", camera.get("fps", 0))
                if item in existing:
                    self.camera_list.item(item, text=camera["name"], values=values)
                    existing.discard(item)
                else:
                    self.camera_list.insert("", "end", iid=item, text=camera["name"], values=values)
            for item in existing:
                self.camera_list.delete(item)
            if not cameras:
                if not self.camera_list.get_children():
                    self.camera_list.insert("", "end", iid="status", text="No active camera workers", values=(status.get("message") or "Waiting for configuration", ""))
            elif "status" in self.camera_list.get_children():
                self.camera_list.delete("status")
        except Exception as exc:
            self.state_label.configure(text=f"Status error: {exc}")
        self.root.after(2000, self.refresh)

    def show(self) -> None:
        if not self._closed:
            self.root.after(0, self._show_now)

    def _show_now(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide(self) -> None:
        self.root.withdraw()

    def quit(self) -> None:
        self.on_quit()
        self._closed = True
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
