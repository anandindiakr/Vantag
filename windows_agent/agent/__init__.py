"""Vantag Windows Edge Agent"""
# 1.11.2 — Shelf baselines survive restarts + the detector can no longer
# fail silently. Root cause of "picked an item right after upgrading the
# agent and NO incident fired": baselines lived only in RAM, so the first
# person-free frame after the restart quietly became the new baseline — if
# that frame was the post-theft scene, the event could never fire. Cell
# baselines (descriptor + crop) now persist to ~/.vantag/inventory_baselines
# .json (geometry-guarded: frame size, grid and zone bbox must all still
# match, so an edited zone never resurrects stale geometry) and are
# restored on the first analysis pass after startup. Baselines also
# auto-refresh after 50 consecutive stable person-free passes so slow
# lighting drift never accumulates into a phantom change, and every zone
# now reports diagnostics (baseline cell count, last decision, last skip
# reason — "person in view", "no change detected", "waiting for cooldown")
# in the heartbeat under inventory_status, surfaced on the backend's agent
# status so a not-firing shelf is visibly explained instead of silent.
#
# 1.11.1 — Inventory evidence now shows the FULL picture. Previously the
# alert snapshot drew only the single highest-scoring changed cell, which
# read as "the yellow box is in the wrong place" whenever a shadow or
# settling movement scored a neighbouring cell higher than the slot that
# truly changed. Evidence now draws the complete zone outline (thin, dim),
# EVERY cell that measured a change (thin yellow), and the strongest cell
# (thick yellow) — plus all changed-cell bboxes in event metadata. Also
# honest note on limits: cell localisation is slot-level (grid cells of
# ~60-120 px), not pixel-exact per product; Tier 3 VLM verification is
# what semantically confirms which product moved.
#
# 1.11.0 — Tier 2 shelf product counting ACTUALLY works. Honest admission:
# the YOLO-World product counter shipped earlier never ran on ANY store
# machine — set_classes() requires the git-only `clip` package, which was
# never in requirements.txt, so the model load failed silently and every
# shelf event fell back to the Tier 1 CV-only signal. This build ships
# pre-baked CLIP ViT-B/32 text embeddings for the fixed product vocabulary
# (agent/assets/yolo_world_product_prompts.npy, ~14 KB) and injects them
# directly into WorldModel.txt_feats — functionally identical to
# set_classes() but with no clip package, no ~340 MB CLIP download and no
# runtime package installs (YOLO_AUTOINSTALL is forced off; ultralytics
# once tried to pip-install a full torch wheel at runtime and filled the
# disk). Weights now cache under ~/.vantag/models like every other model.
# The heartbeat reports product_count_status (idle/ready/failed) so the
# dashboard can state plainly whether Tier 2 is live on a given machine,
# and the backend now puts the counts in the incident description
# ("6 → 5 products") with a badge on the Incidents page.
#
# 1.10.0 — BoT-SORT + VisionAI. The people-count tracker (agent/tracker.py)
# now pairs ByteTrack's two-tier confidence association with a real 8-state
# Kalman-filter motion model (agent/kalman_filter.py, pure numpy — the
# BoT-SORT motion component from Aharon et al. 2022), replacing the 2-frame
# velocity heuristic. Tracks predict forward while unmatched, so a person
# briefly hidden or re-entering within max_age re-attaches to the SAME id
# instead of spawning a duplicate — the honest source of the last
# double-counting. Also adds agent/vision_ai.py: a fail-open wrapper around
# ultralytics.solutions.VisualAISearch (OpenCLIP + FAISS) for semantic
# evidence search; optional deps (open-clip-torch, faiss-cpu) are commented
# in requirements.txt so the agent never breaks on machines without them,
# and the heartbeat now reports visionai_status for System Health.
#
# 1.9.0 — universal plug-and-play door relay + MQTT security. The relay
# driver layer (agent/relay.py) now exposes one interface across five
# hardware backends — simulate, http (Shelly/Tasmota/ESPHome/Sonoff/custom
# REST boards), gpio, serial (USB/RS-485) and modbus_tcp — each importing
# its optional dependency lazily and degrading to a logged no-op so the
# agent never crashes on missing hardware. Added best-effort LAN relay
# discovery (discover_relays) whose candidates the agent reports in its
# heartbeat for the dashboard's Door Relay setup wizard. MQTT now
# auto-enables TLS when pointed at the public MQTTS port 8883 (system CA
# bundle) and authenticates with the edge broker credentials, so
# door-control traffic is encrypted in transit.
#
# 1.8.0 — per-finger hand tracking + fixed MQTT door control. Ported the
# MediaPipe 21-point HandLandmarker into agent/hand_landmarks.py (bundled
# hand_landmarker.task in the download zip) and wired it into the High-Value
# Counter handover detector, which now measures a reach from the real
# fingertips with the bbox-proportional fallback intact. Also fixed door
# control: the agent now subscribes to the canonical
# vantag/stores/+/doors/+/command topic, actuates a configurable relay
# (simulate/http/gpio) and publishes door status back, and the default
# broker port is corrected to 1883.
#
# 1.7.0 — High-Value Counter detectors run on-box. Ported the three
# jewellery / luxury-counter analyzers (jewelry_handover reach-in→withdraw,
# jewelry_tray foreground-change-while-person-present, grab_and_run fast
# case→exit traversal) into windows_agent/agent/jewelry.py and wired them
# into DetectionAnalyzer. The backend's /api/edge/config now ships the
# camera's normalized High-Value Counter polygons (serving counter, display
# tray, display case, exit, approach) under "high_value_counter", and the
# agent scales them to each frame. Each detector stays OFF until its polygons
# are drawn, and all three fire as operator-review candidates alongside the
# existing detectors — one camera keeps running every enabled analytic at
# once on the same stream.
#
# 1.6.1 — shelf/inventory accuracy. The old detector compared a 32-bin
# GRAYSCALE histogram of a coarse 2x3 grid, so it could not distinguish a
# removed product from a shadow (both just shift grey levels), and a single
# removal was diluted across a cell holding ~2 products. Replaced with a
# per-cell appearance descriptor (HS colour histogram + Sobel edge energy +
# mean luminance) that requires BOTH a colour change AND a structure/edge
# change before firing — removing an item destroys its outline, a lighting
# change does not. Added per-zone illumination normalisation, a re-baseline
# abort when lighting moves beyond honest correction, a minimum consecutive
# confirming-frame count (wall-clock debounce alone is unsafe on a stuttering
# RTSP stream), and an adaptive grid sized to roughly one product per cell.
# Measured on synthetic shelves: genuine removal scores 0.865 against a 0.35
# threshold, while shadow / dimming / brightening / defocus / noise all stay
# at or below 0.165. Every emitted event now carries the individual signals
# (colour_change, edge_change, confirm_frames, lum_gain) so an incident can
# be audited instead of trusted blindly.
#
# 1.6.0 — THE actual reason agents kept reporting YOLOv8: requirements.txt
# pinned `ultralytics>=8.3.100`, but YOLO26 does not exist before ultralytics
# 8.4.0. Every machine that resolved 8.3.x satisfied the pin, failed to load
# yolo26n.pt, and fell back to YOLOv8n. Fixed by raising the floor to >=8.4.0,
# checking the installed version explicitly (so the recorded failure names the
# real cause instead of an opaque exception), pinning the ONNX export to
# opset=19 + dynamic=False + simplify=True for a deterministic end-to-end head,
# and self-correcting the cache manifest when the exported graph turns out to
# be the legacy head so the next start re-exports instead of silently staying
# on the fallback forever.
#
# 1.5.9 — detector honesty: the agent verifies which architecture is actually
# loaded by reading the ONNX graph output shape (YOLO26 end-to-end vs legacy
# YOLOv8), re-acquires the model if the cached file does not match, applies
# NMS on the fallback path so a fallback can no longer inflate people counts,
# and reports the verified status in every heartbeat so Admin -> System Health
# shows the truth instead of an assumption.
__version__ = "1.11.2"
