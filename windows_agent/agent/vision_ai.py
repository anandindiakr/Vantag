"""
VisionAI — visual evidence search (Ultralytics `solutions.VisualAISearch`).

Gives the edge agent a semantic search layer over the incident evidence
snapshots it saves: "find the frames where a person was carrying a bag near
the shelves" instead of scrubbing footage by hand. This is the Ultralytics
VisualAISearch tool — OpenCLIP image/text embeddings in a shared space,
FAISS for fast nearest-neighbour retrieval.

Dependency policy (honest, fail-open — same principle as every other optional
model in this agent):

  * If `open-clip-torch` + `faiss-cpu` are installed, `VisionAISearcher`
    wraps the real `ultralytics.solutions.VisualAISearch`. The CLIP model
    (~400 MB ViT-B-32) downloads on first use and is cached, exactly like the
    YOLO26 weights.
  * If they are NOT installed (default — they are optional extras in
    requirements.txt because store laptops are install-fragile), the searcher
    degrades to `available = False` and every call returns an empty result
    with a warning, never crashing the camera loop. The admin System Health
    tab can report `available` so ops knows whether the feature is live.

Nothing in the camera loop depends on this module: it is an on-demand lookup
tool, so a missing install can never break detection, counting, or alerts.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


class VisionAISearcher:
    """Semantic search over a directory of evidence images.

    Lazy: the VisualAISearch instance (and its ~400 MB model download) only
    happens on first `search()` call, so the agent starts fast even when the
    feature is enabled.
    """

    def __init__(self, data_dir: str, device: str = "cpu"):
        self._data_dir = Path(data_dir)
        self._device = device
        self._searcher = None
        self._lock = threading.Lock()
        self._deps_ok: Optional[bool] = None  # None = not checked yet
        self._build_error: Optional[str] = None

    # ------------------------------------------------------------------
    # Dependency + backend management
    # ------------------------------------------------------------------
    def _check_deps(self) -> bool:
        if self._deps_ok is not None:
            return self._deps_ok
        try:
            import open_clip  # noqa: F401
            import faiss  # noqa: F401
            from ultralytics import solutions  # noqa: F401
            self._deps_ok = True
        except Exception as exc:  # noqa: BLE001 — import errors vary by platform
            self._deps_ok = False
            self._build_error = f"missing optional deps: {exc}"
            logger.warning(
                "VisionAI unavailable (install open-clip-torch + faiss-cpu to enable): %s",
                exc,
            )
        return self._deps_ok

    def _ensure_backend(self) -> bool:
        if self._searcher is not None:
            return True
        with self._lock:
            if self._searcher is not None:
                return True
            if not self._check_deps():
                return False
            try:
                from ultralytics import solutions
                self._data_dir.mkdir(parents=True, exist_ok=True)
                self._searcher = solutions.VisualAISearch(
                    data=str(self._data_dir),
                    device=self._device,
                )
                self._build_error = None
                logger.info("VisionAI backend ready (Ultralytics VisualAISearch, %s)", self._device)
                return True
            except Exception as exc:  # noqa: BLE001
                self._build_error = str(exc)
                logger.error("VisionAI backend failed to initialise: %s", exc)
                return False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def available(self) -> bool:
        """True only if the real VisualAISearch backend is up and ready."""
        return self._ensure_backend()

    @property
    def status(self) -> dict:
        """Small status payload for heartbeats / System Health reporting."""
        return {
            "available": self._searcher is not None,
            "deps_installed": self._deps_ok is True,
            "error": self._build_error,
        }

    def rebuild_index(self) -> bool:
        """Drop and rebuild the FAISS index (call after adding new snapshots)."""
        if not self._ensure_backend():
            return False
        try:
            # Deleting the cached index forces load_or_build_index to re-embed
            # every image on the next search.
            faiss_index = self._data_dir.parent / "faiss.index"
            data_npy = self._data_dir.parent / "paths.npy"
            for p in (faiss_index, data_npy):
                if p.exists():
                    p.unlink()
            self._searcher.load_or_build_index()
            return True
        except Exception as exc:  # noqa: BLE001
            self._build_error = str(exc)
            logger.error("VisionAI reindex failed: %s", exc)
            return False

    def search(self, query: str, k: int = 5) -> List[Tuple[str, float]]:
        """Return up to ``k`` (image_path, similarity) hits for a text query.

        Empty list (never an exception) when the backend is unavailable or
        the query matches nothing.
        """
        if not query or not self._ensure_backend():
            return []
        try:
            results = self._searcher.search(query, k=k)
            out: List[Tuple[str, float]] = []
            for item in results or []:
                # VisualAISearch returns (path, similarity) tuples; tolerate
                # either attribute-style or plain-tuple entries.
                if isinstance(item, (tuple, list)) and len(item) >= 2:
                    out.append((str(item[0]), float(item[1])))
            return out
        except Exception as exc:  # noqa: BLE001
            self._build_error = str(exc)
            logger.error("VisionAI search failed for query %r: %s", query, exc)
            return []
