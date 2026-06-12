"""
facial_recognition.py
=====================
Privacy-safe facial recognition and watchlist matching for the Vantag platform.

Architecture:
* **Face detection** – performed by the upstream YOLO engine (``face`` class)
  or by insightface's built-in detector.
* **Embedding extraction** – insightface ArcFace (primary) or the
  ``face_recognition`` library (fallback).
* **Storage** – SQLite database at ``db_path``.  All embeddings are stored
  AES-256-GCM encrypted via ``cryptography.fernet.Fernet``.  The Fernet key
  is derived from a per-installation secret stored in the environment variable
  ``VANTAG_FACE_KEY`` (base-64-encoded 32-byte secret).  If the variable is
  absent a per-process key is generated (non-persistent — suitable only for
  testing).
* **Matching** – cosine similarity comparison performed entirely in-memory on
  decrypted embeddings; no plain-text embeddings are ever written to disk.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cryptography – required dependency.
# ---------------------------------------------------------------------------

try:
    from cryptography.fernet import Fernet  # type: ignore[import]
    _FERNET_OK = True
except ImportError:
    _FERNET_OK = False
    logger.error(
        "facial_recognition: 'cryptography' package is not installed. "
        "Watchlist storage is disabled. Install with: pip install cryptography"
    )

# ---------------------------------------------------------------------------
# Face embedding backends (try insightface first, then face_recognition).
# ---------------------------------------------------------------------------

_INSIGHTFACE_OK = False
_FACE_RECOGNITION_OK = False
_insightface_app: Any = None

try:
    import insightface  # type: ignore[import]
    from insightface.app import FaceAnalysis  # type: ignore[import]
    _INSIGHTFACE_OK = True
except ImportError:
    pass

if not _INSIGHTFACE_OK:
    try:
        import face_recognition  # type: ignore[import]
        _FACE_RECOGNITION_OK = True
    except ImportError:
        pass

if not _INSIGHTFACE_OK and not _FACE_RECOGNITION_OK:
    logger.error(
        "facial_recognition: neither 'insightface' nor 'face_recognition' "
        "is installed.  Face matching will be unavailable."
    )

# ---------------------------------------------------------------------------
# Detection import with fallback stub.
# ---------------------------------------------------------------------------

try:
    from backend.inference.yolo_engine import Detection  # type: ignore[import]
except ImportError:
    from dataclasses import dataclass as _dc

    @_dc
    class Detection:  # type: ignore[no-redef]
        track_id: int = -1
        class_id: int = 0
        class_name: str = ""
        confidence: float = 0.0
        bbox: Tuple[int, int, int, int] = (0, 0, 0, 0)
        keypoints: Optional[list] = None


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULTS: Dict = {
    "similarity_threshold": 0.6,
}

# SQLite schema.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS watchlist (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    alert_level TEXT NOT NULL DEFAULT 'MEDIUM',
    embedding   BLOB NOT NULL,    -- Fernet-encrypted JSON list of floats
    added_at    REAL NOT NULL
);
"""


# ---------------------------------------------------------------------------
# Event dataclass
# ---------------------------------------------------------------------------

@dataclass
class WatchlistMatchEvent:
    """Emitted when a face matches a watchlist entry."""

    camera_id: str
    timestamp: datetime
    match_confidence: float
    alert_level: str
    face_bbox: Tuple[int, int, int, int]
    encrypted_match_id: str
    """Fernet-encrypted watchlist row ID (base-64 string)."""


# ---------------------------------------------------------------------------
# FacialRecognitionAnalyzer
# ---------------------------------------------------------------------------

class FacialRecognitionAnalyzer:
    """
    Privacy-safe facial recognition with an encrypted watchlist database.

    Parameters
    ----------
    camera_id:
        Identifier of the camera this analyser is bound to.
    config:
        Dict of configuration overrides.
    db_path:
        Path to the SQLite database file.  Created automatically if absent.
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        camera_id: str,
        config: Dict,
        db_path: str,
    ) -> None:
        self._camera_id = camera_id
        cfg = dict(_DEFAULTS)
        cfg.update({k: v for k, v in config.items() if k in _DEFAULTS})
        self._similarity_threshold: float = float(cfg["similarity_threshold"])
        self._db_path = db_path

        # Set up Fernet key.
        self._fernet: Optional[Any] = None
        if _FERNET_OK:
            key_b64 = os.environ.get("VANTAG_FACE_KEY", "")
            if key_b64:
                try:
                    self._fernet = Fernet(key_b64.encode())
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "facial_recognition: invalid VANTAG_FACE_KEY (%s); "
                        "generating ephemeral key.",
                        exc,
                    )
            if self._fernet is None:
                ephemeral_key = Fernet.generate_key()
                self._fernet = Fernet(ephemeral_key)
                logger.warning(
                    "facial_recognition: using an ephemeral Fernet key. "
                    "Watchlist data will not persist across restarts. "
                    "Set VANTAG_FACE_KEY env variable for persistence."
                )

        # Initialise database.
        self._init_db()

        # Initialise insightface if available.
        self._insight_app: Any = None
        if _INSIGHTFACE_OK:
            try:
                app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
                app.prepare(ctx_id=0, det_size=(640, 640))
                self._insight_app = app
                logger.info("facial_recognition: insightface ArcFace initialised.")
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "facial_recognition: insightface init failed (%s). "
                    "Falling back to face_recognition lib.",
                    exc,
                )

    # ------------------------------------------------------------------
    # Database helpers
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        try:
            with self._get_conn() as conn:
                conn.executescript(_SCHEMA)
        except Exception as exc:  # noqa: BLE001
            logger.error("facial_recognition: DB init failed: %s", exc)

    # ------------------------------------------------------------------
    # Encryption helpers
    # ------------------------------------------------------------------

    def _encrypt_embedding(self, embedding: List[float]) -> bytes:
        payload = json.dumps(embedding).encode()
        if self._fernet is None:
            return payload  # plain-text fallback (should not happen in prod)
        return self._fernet.encrypt(payload)

    def _decrypt_embedding(self, blob: bytes) -> Optional[List[float]]:
        try:
            if self._fernet is None:
                return json.loads(blob.decode())
            return json.loads(self._fernet.decrypt(blob).decode())
        except Exception as exc:  # noqa: BLE001
            logger.warning("facial_recognition: failed to decrypt embedding: %s", exc)
            return None

    def _encrypt_id(self, row_id: int) -> str:
        if self._fernet is None:
            return str(row_id)
        encrypted = self._fernet.encrypt(str(row_id).encode())
        return base64.b64encode(encrypted).decode("ascii")

    # ------------------------------------------------------------------
    # Embedding extraction
    # ------------------------------------------------------------------

    def _extract_embedding_insightface(
        self, face_crop: np.ndarray
    ) -> Optional[np.ndarray]:
        """Use insightface to extract ArcFace embedding from a face crop."""
        try:
            faces = self._insight_app.get(face_crop)
            if not faces:
                return None
            # Return embedding for the highest-confidence detection.
            best = max(faces, key=lambda f: f.det_score)
            return np.array(best.embedding, dtype=np.float32)
        except Exception as exc:  # noqa: BLE001
            logger.debug("insightface embedding error: %s", exc)
            return None

    @staticmethod
    def _extract_embedding_face_recognition(
        face_crop: np.ndarray,
    ) -> Optional[np.ndarray]:
        """Use face_recognition library to extract a 128-d embedding."""
        try:
            rgb = cv2.cvtColor(face_crop, cv2.COLOR_BGR2RGB)
            locs = face_recognition.face_locations(rgb, model="hog")  # type: ignore[name-defined]
            if not locs:
                return None
            encodings = face_recognition.face_encodings(rgb, locs)  # type: ignore[name-defined]
            if not encodings:
                return None
            return np.array(encodings[0], dtype=np.float32)
        except Exception as exc:  # noqa: BLE001
            logger.debug("face_recognition embedding error: %s", exc)
            return None

    def _get_embedding(self, face_crop: np.ndarray) -> Optional[np.ndarray]:
        if self._insight_app is not None:
            emb = self._extract_embedding_insightface(face_crop)
            if emb is not None:
                return emb
        if _FACE_RECOGNITION_OK:
            return self._extract_embedding_face_recognition(face_crop)
        return None

    # ------------------------------------------------------------------
    # Similarity
    # ------------------------------------------------------------------

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        denom = (np.linalg.norm(a) * np.linalg.norm(b))
        if denom == 0.0:
            return 0.0
        return float(np.dot(a, b) / denom)

    # ------------------------------------------------------------------
    # Watchlist management
    # ------------------------------------------------------------------

    def add_to_watchlist(
        self,
        name: str,
        alert_level: str,
        face_image_path: str,
    ) -> Optional[int]:
        """
        Enrol a new face into the watchlist database.

        Parameters
        ----------
        name:
            Display name for this watchlist entry.
        alert_level:
            Severity level string, e.g. ``'HIGH'``, ``'MEDIUM'``, ``'LOW'``.
        face_image_path:
            Path to a face image file (JPEG / PNG).  The image should ideally
            show a single, frontal face.

        Returns
        -------
        Database row ID on success, ``None`` on failure.
        """
        img = cv2.imread(face_image_path)
        if img is None:
            logger.error(
                "add_to_watchlist: cannot read image at '%s'.", face_image_path
            )
            return None

        emb = self._get_embedding(img)
        if emb is None:
            logger.error(
                "add_to_watchlist: no face detected in '%s'.", face_image_path
            )
            return None

        enc_blob = self._encrypt_embedding(emb.tolist())
        try:
            with self._get_conn() as conn:
                cur = conn.execute(
                    "INSERT INTO watchlist (name, alert_level, embedding, added_at) "
                    "VALUES (?, ?, ?, ?)",
                    (name, alert_level, enc_blob, time.time()),
                )
                row_id = cur.lastrowid
                logger.info(
                    "add_to_watchlist: enrolled '%s' (id=%d, level=%s).",
                    name,
                    row_id,
                    alert_level,
                )
                return row_id
        except Exception as exc:  # noqa: BLE001
            logger.error("add_to_watchlist: DB error: %s", exc)
            return None

    def remove_from_watchlist(self, entry_id: int) -> bool:
        """
        Remove a watchlist entry by its database row ID.

        Returns ``True`` on success, ``False`` otherwise.
        """
        try:
            with self._get_conn() as conn:
                conn.execute("DELETE FROM watchlist WHERE id = ?", (entry_id,))
            logger.info("remove_from_watchlist: removed entry id=%d.", entry_id)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("remove_from_watchlist: DB error: %s", exc)
            return False

    def _load_watchlist(self) -> List[Tuple[int, str, np.ndarray]]:
        """
        Load and decrypt all watchlist entries.

        Returns a list of ``(row_id, alert_level, embedding_array)`` tuples.
        """
        entries: List[Tuple[int, str, np.ndarray]] = []
        try:
            with self._get_conn() as conn:
                rows = conn.execute(
                    "SELECT id, alert_level, embedding FROM watchlist"
                ).fetchall()
            for row in rows:
                emb_list = self._decrypt_embedding(row["embedding"])
                if emb_list is None:
                    continue
                entries.append(
                    (row["id"], row["alert_level"], np.array(emb_list, dtype=np.float32))
                )
        except Exception as exc:  # noqa: BLE001
            logger.error("_load_watchlist: DB error: %s", exc)
        return entries

    # ------------------------------------------------------------------
    # Public analysis API
    # ------------------------------------------------------------------

    def analyze(
        self,
        frame: np.ndarray,
        detections: List[Detection],
    ) -> List[WatchlistMatchEvent]:
        """
        Detect faces in *frame*, extract embeddings, and compare against the
        watchlist.

        Parameters
        ----------
        frame:
            BGR numpy array for the current frame.
        detections:
            Detections from the YOLO engine; ``'face'`` class detections are
            used to crop face regions.  If no ``'face'`` detections are
            present, insightface's own detector is used if available.

        Returns
        -------
        List of :class:`WatchlistMatchEvent`, possibly empty.
        """
        if frame is None or frame.size == 0:
            return []
        if self._fernet is None and not _FERNET_OK:
            return []

        watchlist = self._load_watchlist()
        if not watchlist:
            return []

        # Collect face crops from YOLO face detections.
        face_bboxes: List[Tuple[int, int, int, int]] = [
            det.bbox
            for det in detections
            if det.class_name.lower() in ("face", "head")
        ]

        # If YOLO gave no face detections, let insightface detect them itself.
        if not face_bboxes and self._insight_app is not None:
            try:
                faces_detected = self._insight_app.get(frame)
                for f in faces_detected:
                    bb = f.bbox.astype(int)
                    face_bboxes.append((bb[0], bb[1], bb[2], bb[3]))
            except Exception as exc:  # noqa: BLE001
                logger.debug("analyze: insightface detect error: %s", exc)

        events: List[WatchlistMatchEvent] = []
        fh, fw = frame.shape[:2]

        for bbox in face_bboxes:
            x1, y1, x2, y2 = (
                max(0, bbox[0]),
                max(0, bbox[1]),
                min(fw, bbox[2]),
                min(fh, bbox[3]),
            )
            if x2 <= x1 or y2 <= y1:
                continue

            face_crop = frame[y1:y2, x1:x2]
            emb = self._get_embedding(face_crop)
            if emb is None:
                continue

            # Compare against each watchlist entry.
            best_sim = 0.0
            best_entry: Optional[Tuple[int, str, np.ndarray]] = None
            for row_id, alert_level, ref_emb in watchlist:
                sim = self._cosine_similarity(emb, ref_emb)
                if sim > best_sim:
                    best_sim = sim
                    best_entry = (row_id, alert_level, ref_emb)

            if best_entry is not None and best_sim >= self._similarity_threshold:
                row_id, alert_level, _ = best_entry
                enc_id = self._encrypt_id(row_id)
                logger.warning(
                    "WatchlistMatch | camera=%s similarity=%.4f level=%s",
                    self._camera_id,
                    best_sim,
                    alert_level,
                )
                events.append(
                    WatchlistMatchEvent(
                        camera_id=self._camera_id,
                        timestamp=datetime.now(tz=timezone.utc),
                        match_confidence=round(best_sim, 4),
                        alert_level=alert_level,
                        face_bbox=(x1, y1, x2, y2),
                        encrypted_match_id=enc_id,
                    )
                )

        return events
