"""
backend/inference/__init__.py
=============================
Public surface of the Vantag inference package.

Usage::

    from backend.inference import YOLOEngine, TRTEngine, ModelScheduler, Detection
"""

from backend.inference.yolo_engine import Detection, YOLOEngine
from backend.inference.trt_engine import TRTEngine
from backend.inference.model_scheduler import ModelScheduler

__all__ = [
    "YOLOEngine",
    "TRTEngine",
    "ModelScheduler",
    "Detection",
]
