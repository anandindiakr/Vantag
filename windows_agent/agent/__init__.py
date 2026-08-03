"""Vantag Windows Edge Agent"""
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
__version__ = "1.6.1"
