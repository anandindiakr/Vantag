# Agent Status Repair Implementation Plan

> **For agentic workers:** Execute inline with test-driven development. Do not commit or deploy until every test passes.

**Goal:** Make the standalone Windows agent visibly report status and prevent duplicate camera/MQTT workers.

**Architecture:** A named Windows mutex protects the process. Tkinter owns the UI thread, pystray owns a tray thread, and the existing agent bootstrap runs in the background. A lock serializes monitoring lifecycle operations.

**Tech Stack:** Python 3.11, tkinter, ctypes, pystray, unittest, PyInstaller.

## Tasks

- [ ] Add failing tests proving a second mutex acquisition is rejected, duplicate monitoring starts call the worker startup once, and status snapshots contain camera state without credentials.
- [ ] Implement `agent/single_instance.py`, monitoring locks, and a read-only `get_agent_status()` snapshot.
- [ ] Add failing UI tests for initial status, refreshing camera data, hide-to-tray and quit callbacks.
- [ ] Implement `agent/status_window.py`; wire `standalone_entry.py` and `tray_icon.py` to the window and branded icon.
- [ ] Run focused agent tests, frontend typecheck/build, and the real PyInstaller inference and UI smoke tests.
- [ ] Commit only task files and the pending download-page fix, push, upload the tested ZIP, and verify authenticated production download.
