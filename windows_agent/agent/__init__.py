"""Vantag Windows Edge Agent"""
# 1.5.9 — detector honesty: the agent now verifies which architecture is
# actually loaded by reading the ONNX graph output shape (YOLO26 end-to-end
# vs legacy YOLOv8), re-acquires the model if the cached file does not match,
# applies NMS on the fallback path so a fallback can no longer inflate people
# counts, and reports the verified status in every heartbeat so Admin ->
# System Health shows the truth instead of an assumption.
__version__ = "1.5.9"
