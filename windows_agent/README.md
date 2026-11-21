# Vantag Windows Edge Agent

Runs on a store Windows PC. Connects your LAN cameras to the Vantag cloud platform.

## What it does
- Scans your local network (192.168.x.x) for IP cameras automatically
- Streams RTSP video and runs AI (YOLO26) to detect: shoplifting, loitering, empty shelves, camera tampering
- Sends incidents + thumbnails to your Vantag dashboard in real-time
- Receives commands (door lock/unlock) via MQTT from the dashboard

---

## Option A — Test without building .exe (Quickest for LAN testing)

**Requirements:** Python 3.11 or 3.12, Windows 10/11 64-bit, connected to the store LAN

```
1. Get your API key:
   → Log in to https://retail-vantag.com → Install Edge Agent page → Copy API Key

2. Copy the template config:
   copy config.template.json config.json

3. Edit config.json — set api_key:
   "api_key": "paste-your-key-here"

4. Double-click setup.bat
   (OR run: pip install -r requirements.txt && python run_agent.py)
```

The agent will:
- Register itself with the backend (auto-assigns agent_id)
- Scan your LAN for cameras → results appear in Dashboard → Agent Status page
- Show a shield icon in your Windows taskbar tray

---

## Option B — Build standalone .exe (for store deployment)

**Build requirements:** dedicated 64-bit Python 3.11 environment with `requirements-standalone-lock.txt`. The target PC does not need a separate Python installation.

```powershell
build\standalone_venv\Scripts\python.exe build_exe.py
```

Run from `windows_agent`. Online output: `build/standalone_output/windows-agent.zip` with `VantagAgent.exe` and `_internal`. The build runs packaged smoke checks before producing the ZIP.

Distribute online packages through the authenticated account download, which supplies the account's `config.json`. Keep that file private and beside the executable; extract the entire ZIP before running the agent.

---

## Configuration (`config.json`)

| Field | Description |
|-------|-------------|
| `api_key` | **Required.** Get from retail-vantag.com/download |
| `agent_id` | Leave blank — assigned automatically on first run |
| `backend_url` | `https://retail-vantag.com` (default, do not change) |
| `mqtt_host` | `retail-vantag.com` (default) |
| `cameras` | Leave blank — auto-discovered from LAN scan |
| `inference_device` | `cpu` (default), `cuda` if GPU available |
| `inference_fps` | Frames per second for AI (default 5, reduce to 2 on slow PCs) |
| `confidence_threshold` | 0.6 = 60% confidence required to fire an event |

---

## Offline Site Console — development, not a qualified release

The offline mode extends the same executable. It is separate from online/cloud mode: camera configuration, local owner login, evidence, counts and reports are stored on the agent PC. The console binds only to `127.0.0.1` on an available port. No public domain is required for local startup. Existing online configurations do not switch modes automatically.

### Build and launch

Build with the dedicated 64-bit Python 3.11 environment and the pinned standalone dependencies. Provide `offline_keys.json` containing trusted **Ed25519 public verification keys only**; keep signing private keys on the issuing server. The development key must not be used for customer distribution.

```powershell
windows_agent\build\standalone_venv\Scripts\python.exe windows_agent\build_exe.py --offline-bundle
```

Run that command from the repository root. The offline ZIP is produced separately at `windows_agent/build/standalone_output/offline/windows-offline-agent.zip`, leaving the online ZIP separate. The build includes the console assets, model hash manifest, bundled runtime and model files, and runs packaged model/UI/local-console smoke checks before writing the ZIP. These development-host checks are **not** a clean-PC, firewall-isolated or field-accuracy qualification.

The generic offline build includes `config.json` with `{"mode":"offline"}` so normal double-click startup selects the local console, not cloud mode. Account-specific distribution must additionally include a valid signed `offline-entitlement.json`; a generic build alone does not grant camera access. Extract the entire package; keep both files and `_internal` beside `VantagAgent.exe`. A customer does not need to install Python separately. Create a local owner account, set the site timezone, add the NVR channels and test decoded video. Enter the actual NVR password, including `#`; the wizard percent-encodes it once. A reachable IP or RTSP port does not establish that a video frame can be decoded.

### Isolated engineering-test setup

`python windows_agent/build_offline_test.py --output windows_agent/build/my-offline-test` wraps an existing generic offline build in a single per-user setup EXE. The setup embeds the payload, verifies its SHA-256, shows extraction progress and creates shortcuts. It uses the Windows .NET Framework already supplied with supported Windows installations; it does not install system Python, download dependencies or replace GPU drivers. The separate portable ZIP must be opened through `VantagOfflineTest.exe`, not the nested engine EXE.

The test package contains an eight-camera engineering grant valid for three days **from package creation**, followed by seven days of grace. Its key is generated in memory, only the public verification key is packaged, and it cannot grant a production customer subscription. Camera entitlement is not a measured hardware-capacity recommendation. Customer release gates stay disabled. The installer is unsigned unless separately code-signed.

The test launcher isolates site data under `%LOCALAPPDATA%\Vantag\OfflineEngineeringTest\Sites\<build-id>\.vantag\offline-site`; existing online/customer sites are not changed. Reopening the same test build preserves its owner, cameras and records. `python windows_agent/verify_offline_test.py <build-output> --report <report.json>` drives the actual setup button and normal launcher, verifies the signed licence, owner login, disabled camera/zone persistence, exports and restart. Its camera fixtures are disabled; this is not real-NVR, accuracy or clean-PC qualification.

Save camera settings and zones, then start/apply monitoring. The local console does not bypass NVR authentication. If opening video fails and a bounded authenticated diagnostic returns 401/403 (or unsupported authentication), that camera pauses instead of repeatedly submitting rejected credentials. Its tile explains how to retry: verify the NVR account, channel and remote live-view permission, then save that camera or choose **Start / apply configuration**. Other cameras continue; temporary network/service failures still reconnect with capped backoff. Healthy streams do not perform the extra authentication diagnostic. Failure backoff resets only after 30 seconds of decoded video, not merely an opened connection. Use the recorder's actual channel inventory: direct-camera channel numbers and NVR channel numbers are not interchangeable.

### Entitlement and renewal

- Expiry is derived from the account's paid-through date, trial or explicit extension, followed by seven days of grace. There is no mandatory cloud check on each startup.
- After grace, live viewing and new AI processing stop. Saved incidents, evidence, count reports, private backups and licence import remain accessible.
- Export a device renewal request, transfer it to an internet-connected PC, obtain a newer signed entitlement for the account/device, and import it locally. A website payment or extension does not reach a disconnected PC until the renewed file is imported.
- Signatures, device binding, revision rollback and clock rollback are checked locally. Completely offline software cannot provide perfect anti-cloning, trusted time or immediate remote revocation. A bootstrap package is not perfectly copy-proof before first activation.

### Internal team and evaluation licences

Superadmin → **Offline demos** issues separate signed demo licences. Export **Licence & health → Export device renewal request** on the target PC, transfer the JSON to the connected admin PC, import it in Offline demos, confirm the tenant ID and choose the policy. Use **Internal team demo** only for trusted staff devices: it has no expiry and requires device binding. Use **Customer / dealer evaluation** for 1–365 days followed by seven days of grace. Select the camera entitlement explicitly; it is not a hardware performance guarantee. Download the signed JSON and import it on the target PC under Licence & health. Existing customer subscriptions, billing dates and ordinary renewal rules are unchanged. Issuance is audit logged. Do not share a staff licence or the running site's folder.

Production signing uses `VANTAG_OFFLINE_SIGNING_KEY_FILE` and `VANTAG_OFFLINE_KEY_ID`. Back up the server-only private key securely; never commit it or package it. The installer trusts only configured public keys. The production Compose defaults point to `/app/data/offline-keys/issuer.pem`, persisted in the existing data volume; provisioning the key is an operator step, not an automatic fallback. Older console builds cannot validate the new permanent-demo policy and must be upgraded first. These controls do not override customer package qualification gates.

### Fall and theft demo checks

In **Cameras**, select the intended camera, expand **AI detection and schedules**, enable `fall_detected` and/or `shoplifting`, then save. A saved switch is not a completed detection test. The selected camera's **Detection readiness** panel explains disabled functions, schedule restrictions, missing shelf zones, unavailable pose analysis and recent analysis. Check **Licence & health** for model/provider details. Theft heuristics stay active regardless of the daily schedule; fall detection follows it. Inventory movement also requires a saved shelf zone.

Test one camera first, with enough memory and an unobstructed full-body view. Fall candidates require an observed upright person followed by sustained horizontal pose; starting already prone is not a fall transition. Do not stage unsafe falls: use an approved labelled recording or supervised safe procedure. Concealment candidates require a visible upright torso and repeated hand proximity to a bounded band below the hips, not merely a hand anywhere below hip height. They are not proven theft; ordinary reaching can generate a candidate and genuine theft can be missed. Excluded areas do not contribute pose candidates. Check a positive case, normal movement/negative cases, time to incident, the actual evidence image and persistence after restart. Physical accuracy and clean-PC disconnected qualification remain unverified until those tests are performed.

### Repeatable on-site AI checks

1. On **Video wall**, confirm a fresh image and the expected room. Use **Configure → AI detection and schedules**, select the required functions and **Save camera**. Live video does not enable AI. Each tile shows Fall, Theft and Shelf readiness; resolve Off, schedule, missing-zone and inference-error states before testing.
2. Test one camera first. For shelf movement, save a tight shelf zone, leave it unchanged while its baseline becomes ready, then remove and replace one item. Repeat with no item movement and ordinary walking as negative cases. Verify the affected area and person in saved evidence rather than counting alerts alone.
3. For fall checks, use continuous, consented test footage showing the same person's upright state and transition to the floor; include walking, sitting, bending and an already-lying person as negative controls. Do not ask anyone to perform an unsafe fall. A clip that starts with someone already down cannot test the observed-fall transition rule.
4. For theft candidates, use consented continuous footage with a visible person, shelf interaction and a visible concealment gesture, plus ordinary reaching, item return and hands-at-sides controls. A text overlay saying "theft detected", a phone-screen montage or ordinary product removal is not a known-positive concealment case. These heuristics cannot establish criminal intent.
5. Record the camera, local time, enabled settings, expected outcome, observed alert, evidence, delay and any model error for every positive and negative trial. Confirm the record remains after restart. Report missed events and false alerts separately; synthetic and regression results do not establish field accuracy.

### Data and recovery

Local site data is under `%USERPROFILE%\.vantag\offline-site`, outside the application folder. Upgrading binaries must not replace it. NVR credentials and installation identity use Windows DPAPI; credential restoration requires the original Windows user/account context. Backups contain private customer evidence and must be protected.

Use **Storage & backup** to export a private ZIP before upgrades or restores. Console restore is limited to 2 GB, replaces site records, stops monitoring and preserves the current owner, installation binding and entitlement. New recording stops at the configured storage quota or below 256 MB free space; old incidents are not silently evicted. Larger sites need a stopped-site filesystem backup and a separately validated recovery procedure.

People-count entries are tracked appearances, not guaranteed unique visitors or directional door crossings. Camera overlap and restarted tracks can count the same person again. A missing/failed inference is not a measured zero; the UI distinguishes absent and stale samples. Candidate theft/inventory alerts are not proof of theft or exact stock quantities.

### Qualification and unavailable capabilities

The model manifest verifies file integrity; it does not establish commercial redistribution rights or field accuracy. GPU preference requires completed inference using the requested provider. Calibration currently measures synthetic detector frames, **not** total pose/product workload or supported camera capacity. GPU failure is surfaced with CPU fallback status; automatic driver installation is not performed.

Local staff matching, VLM alert verification, visual search, assistant and high-value-counter qualification are incomplete and explicitly unavailable. There is no silent cloud fallback. Cloud email, online payments, hosted dashboards and off-site live access are not available offline.

Customer download remains disabled unless `VANTAG_OFFLINE_RELEASE_READY=1`, the artifact's `OFFLINE_CAPABILITIES.json` records disconnected-core validation and commercial redistribution approval, and its trusted public key matches the configured server signer. Do not change those gates merely to enable a download. Required release evidence includes a clean Windows PC without Python, empty caches, blocked public internet with LAN video retained, representative real-camera positive/negative cases, CPU/GPU failure and load testing, and signed expiry/renewal transitions.

## Logs

Online mode: `%APPDATA%\Vantag\agent.log`. Offline console: `%USERPROFILE%\.vantag\offline-site\console.log`. Logs may contain private operational information; inspect and redact before sharing.

Open log in PowerShell: `Get-Content "$env:APPDATA\Vantag\agent.log" -Wait`

---

## Architecture

```
VantagAgent (main.py)
  ├── Discovery (discovery.py)    — WS-Discovery + TCP :554 scan → reports to backend
  ├── CameraWorker × N            — RTSP capture + YOLO26 inference per camera
  ├── VantagApiClient             — POST events / heartbeat / discovered cameras
  ├── VantagMqttClient            — Subscribes to door control commands
  └── VantagTrayIcon              — Windows system tray (start/stop/quit)
```

## Detected Events

| Event | How it triggers |
|-------|-----------------|
| `shoplifting` | Person near high-value item for >2 seconds |
| `restricted_zone` | Person stationary in zone for >30 seconds |
| `inventory_movement` | No shelf items detected for >60 seconds |
| `camera_tamper` | Camera blocked or moved (no objects detected) |
