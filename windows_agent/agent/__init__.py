"""Vantag Windows Edge Agent"""
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
__version__ = "1.6.0"
