"""
backend/analyzers/__init__.py
=============================
Public surface of the Vantag analyser package.

Import all analyser classes and their event dataclasses here so that
downstream code can do::

    from backend.analyzers import (
        ProductSweepingDetector, SweepingEvent,
        DwellTimeAnalyzer, DwellEvent,
        EmptyShelfDetector, ShelfEvent,
        FacialRecognitionAnalyzer, WatchlistMatchEvent,
        QueueDetector, QueueEvent,
        SlipFallDetector, AccidentEvent,
        StaffMonitor, StaffAlertEvent,
        HeatmapTracker,
    )
"""

from backend.analyzers.dwell_time import DwellEvent, DwellTimeAnalyzer
from backend.analyzers.empty_shelf import EmptyShelfDetector, ShelfEvent
from backend.analyzers.facial_recognition import (
    FacialRecognitionAnalyzer,
    WatchlistMatchEvent,
)
from backend.analyzers.heatmap_tracker import HeatmapTracker
from backend.analyzers.product_sweeping import ProductSweepingDetector, SweepingEvent
from backend.analyzers.queue_detector import QueueDetector, QueueEvent
from backend.analyzers.slip_fall_detector import AccidentEvent, SlipFallDetector
from backend.analyzers.staff_monitor import StaffAlertEvent, StaffMonitor
from backend.analyzers.tamper_detector import TamperDetector, TamperEvent

__all__ = [
    # Product sweeping
    "ProductSweepingDetector",
    "SweepingEvent",
    # Dwell time
    "DwellTimeAnalyzer",
    "DwellEvent",
    # Empty shelf
    "EmptyShelfDetector",
    "ShelfEvent",
    # Facial recognition / watchlist
    "FacialRecognitionAnalyzer",
    "WatchlistMatchEvent",
    # Queue detection
    "QueueDetector",
    "QueueEvent",
    # Slip and fall
    "SlipFallDetector",
    "AccidentEvent",
    # Staff monitoring
    "StaffMonitor",
    "StaffAlertEvent",
    # Heatmap tracking
    "HeatmapTracker",
    # Tamper detection
    "TamperDetector",
    "TamperEvent",
]
