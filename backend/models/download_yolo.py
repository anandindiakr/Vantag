"""
backend/models/download_yolo.py
================================
One-time script to download the YOLO26 model weights required by the
Vantag AI pipeline.  Run once before starting the backend.

Usage:
    python -m backend.models.download_yolo

Downloads the primary detector (``yolo26n.pt``) and the pose estimator
(``yolo26n-pose.pt``) to the directory specified by ``VANTAG_MODEL_DIR``
(default: ``models/`` relative to the project root).
"""
from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

# ── Model catalogue ────────────────────────────────────────────────────────
MODELS = {
    # Current generation (default) — YOLO26 is NMS-free and DFL-free.
    "yolo26n.pt":      "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26n.pt",
    "yolo26n-pose.pt": "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26n-pose.pt",
    # Legacy YOLOv8 fallbacks (kept for existing deployments / A-B rollbacks).
    "yolov8n.pt":      "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt",
    "yolov8n-pose.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n-pose.pt",
}

# Default target directory (relative to this file's grandparent = project root)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DIR = _PROJECT_ROOT / "models"


def _progress(block_count: int, block_size: int, total: int) -> None:
    downloaded = min(block_count * block_size, total)
    pct = downloaded / total * 100 if total > 0 else 0
    bar = "█" * int(pct // 4) + "░" * (25 - int(pct // 4))
    print(f"\r  [{bar}] {pct:5.1f}%  {downloaded // 1_048_576:.1f} / {total // 1_048_576:.1f} MB", end="", flush=True)


def download(name: str, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / name
    if dest.exists():
        print(f"  ✓ {name} already exists at {dest} — skipping.")
        return dest
    url = MODELS[name]
    print(f"\n  Downloading {name} from ultralytics …")
    urllib.request.urlretrieve(url, dest, reporthook=_progress)
    print(f"\n  ✓ Saved to {dest}")
    return dest


def main() -> None:
    dest_dir = Path(os.getenv("VANTAG_MODEL_DIR", str(DEFAULT_DIR)))

    print("=" * 55)
    print("  Vantag — YOLO26 Model Downloader")
    print("=" * 55)

    # Detection model (primary pipeline) + pose model (fall detection and the
    # High-Value Counter hand-reach keypoints).
    download("yolo26n.pt", dest_dir)
    download("yolo26n-pose.pt", dest_dir)

    print("\n" + "=" * 55)
    print("  Done! Update cameras.yaml → yolo_model_path if needed.")
    print(f"  Default path: {dest_dir / 'yolo26n.pt'}")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()
