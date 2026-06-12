"""
backend/models/download_yolo.py
================================
One-time script to download YOLOv8 model weights required by the
Vantag AI pipeline.  Run once before starting the backend.

Usage:
    python -m backend.models.download_yolo

Downloads to the path specified by `yolo_model_path` in cameras.yaml
(default: models/yolov8n.pt relative to the project root).
"""
from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

# ── Model catalogue ────────────────────────────────────────────────────────
MODELS = {
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
    print("  Vantag — YOLOv8 Model Downloader")
    print("=" * 55)

    # Always download the base detection model
    download("yolov8n.pt", dest_dir)

    # Optionally download pose model (for fall detection)
    ans = input("\nDownload pose model too? (enables fall detection, +7 MB) [Y/n]: ").strip().lower()
    if ans in ("", "y", "yes"):
        download("yolov8n-pose.pt", dest_dir)

    print("\n" + "=" * 55)
    print("  Done! Update cameras.yaml → yolo_model_path if needed.")
    print(f"  Default path: {dest_dir / 'yolov8n.pt'}")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()
