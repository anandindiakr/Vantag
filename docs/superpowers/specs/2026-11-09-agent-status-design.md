# Standalone agent startup and status repair

## Evidence
- v1.11.4 successfully loads YOLO26 and registers, but every launch creates another process with the same MQTT client ID.
- The windowed executable exposes only a tray icon. `start_monitoring()` has no lifecycle guard.

## Approved design
- Acquire a Windows named mutex before application imports. A repeated launch foregrounds the existing status window and exits.
- Open a native Tkinter status window immediately. It displays startup, backend, model and per-camera states, with dashboard, start/stop and quit controls. Closing it leaves the agent in the tray.
- Use the packaged Vantag icon. Run tray operations on a dedicated thread and UI operations on Tk's main thread.
- Serialize monitoring start/stop and ignore duplicate starts. Stop exits without calling `sys.exit()` on a background thread.
- Add unit tests and packaged UI/lifecycle smoke tests. Build, upload and deploy only after tests pass. Real camera connectivity still requires on-site validation.
