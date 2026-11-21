from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import threading
import time
import uuid
from contextlib import closing, contextmanager
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit

from .vault import protect, unprotect


def stream_identity(url: str) -> dict:
    parts = urlsplit(url)
    match = re.fullmatch(r"/Streaming/Channels/([1-9]\d*)(01|02)", parts.path, re.IGNORECASE)
    query = parse_qs(parts.query)
    channel = int(match[1]) if match else None
    stream_type = ("Main" if match[2] == "01" else "Substream") if match else "Custom"
    if parts.path.lower() == "/cam/realmonitor" and query.get("channel", [""])[0].isdigit():
        channel = int(query["channel"][0])
        stream_type = "Main" if query.get("subtype") == ["0"] else "Substream" if query.get("subtype") == ["1"] else "Custom"
    allowed = {}
    if parts.path.lower() == "/cam/realmonitor":
        allowed = {"channel": r"[1-9]\d*", "subtype": r"[01]"}
    elif parts.path == "/axis-media/media.amp":
        allowed = {"camera": r"[1-9]\d*", "videocodec": r"h264|h265|jpeg", "streamprofile": r"[\w.-]{1,100}"}
        channel = int(query.get("camera", ["1"])[0]) if query.get("camera", ["1"])[0].isdigit() else None
        stream_type = "Device default"
    elif re.fullmatch(r"/profile[1-9]\d*/media.smp", parts.path):
        channel = 1
        stream_type = "Profile " + parts.path.split("/")[1][7:]
    elif match := re.fullmatch(r"/LiveChannel/(\d+)/media.smp", parts.path):
        channel, stream_type = int(match[1]) + 1, "Device default"
    elif parts.path == "/" and "line" in query and "inst" in query:
        allowed = {"line": r"[1-9]\d*", "inst": r"[12]"}
        channel = int(query["line"][0]) if query["line"][0].isdigit() else None
        stream_type = "Main" if query["inst"] == ["1"] else "Substream"
    elif match := re.fullmatch(r"/Src/MediaInput/stream_([1-4])(?:/ch_([1-4]))?", parts.path):
        channel = int(match[2] or 1)
        stream_type = "Main" if match[1] == "1" else "Substream" if match[1] == "2" else "Stream " + match[1]
    elif parts.path in {"/live.sdp", "/live2.sdp"}:
        channel, stream_type = 1, "Main" if parts.path == "/live.sdp" else "Substream"
    elif parts.path == "/media2/stream.sdp":
        allowed = {"profile": r"[\w.-]{1,100}"}
        channel, stream_type = 1, "Profile " + query.get("profile", ["unknown"])[0] if re.fullmatch(allowed["profile"], query.get("profile", [""])[0]) else "Custom"
    elif parts.path in {"/defaultPrimary", "/defaultSecondary"}:
        allowed = {"streamType": r"u|m"}
        channel, stream_type = 1, "Main" if parts.path == "/defaultPrimary" else "Substream"
    safe_query = [(key, value) for key, value in parse_qsl(parts.query) if key in allowed and re.fullmatch(allowed[key], value)]
    display_path = parts.path + ("?" + urlencode(safe_query) if safe_query else "")
    return {"host": parts.hostname, "port": parts.port or 554, "path": display_path, "path_complete": len(safe_query) == len(parse_qsl(parts.query, keep_blank_values=True)), "channel": channel, "stream_type": stream_type}


def stream_key(url: str) -> tuple:
    identity = stream_identity(url)
    parts = urlsplit(url)
    return (identity["host"], identity["port"], identity["channel"] if identity["channel"] is not None else (parts.path, parts.query))


class SiteStore:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "site.sqlite3"
        self.lock = threading.RLock()
        with self.connect() as connection:
            if connection.execute("PRAGMA user_version").fetchone()[0] > 2:
                raise RuntimeError("This site database requires a newer agent; restore a compatible backup instead of downgrading")
            connection.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS owner (id INTEGER PRIMARY KEY CHECK (id=1), username TEXT NOT NULL, salt TEXT NOT NULL, password_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS cameras (id TEXT PRIMARY KEY, data TEXT NOT NULL, stream TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, camera_id TEXT NOT NULL, created_at REAL NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS count_sessions (camera_id TEXT NOT NULL, day TEXT NOT NULL, run_id TEXT NOT NULL, entries INTEGER NOT NULL, PRIMARY KEY(camera_id, day, run_id));
                CREATE TABLE IF NOT EXISTS counts (camera_id TEXT NOT NULL, day TEXT NOT NULL, people_visible INTEGER NOT NULL, updated_at REAL NOT NULL, PRIMARY KEY(camera_id, day));
                CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, created_at REAL NOT NULL, action TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS staff_profiles (id TEXT PRIMARY KEY, staff_code TEXT NOT NULL UNIQUE COLLATE NOCASE, name TEXT NOT NULL, consent_note TEXT NOT NULL, consent_at REAL NOT NULL, templates TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS person_observations (id TEXT PRIMARY KEY, camera_id TEXT NOT NULL, run_id TEXT NOT NULL, track_id INTEGER NOT NULL, first_seen REAL NOT NULL, last_seen REAL NOT NULL, descriptor TEXT NOT NULL, thumbnail TEXT NOT NULL, staff_id TEXT, staff_score REAL);
                CREATE INDEX IF NOT EXISTS person_observation_time ON person_observations(last_seen DESC);
                CREATE TABLE IF NOT EXISTS person_links (seed_id TEXT NOT NULL, target_id TEXT NOT NULL, state TEXT NOT NULL, reviewed_at REAL NOT NULL, PRIMARY KEY(seed_id,target_id));
                CREATE TABLE IF NOT EXISTS incident_reviews (event_id TEXT PRIMARY KEY, state TEXT NOT NULL, note TEXT NOT NULL, reviewed_at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS events_created ON events(created_at DESC, id DESC);
                CREATE INDEX IF NOT EXISTS events_camera_created ON events(camera_id, created_at DESC);
                PRAGMA user_version=2;
            """)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def get(self, key: str, default=None):
        with self.lock, self.connect() as connection:
            row = connection.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def set(self, key: str, value) -> None:
        with self.lock, self.connect() as connection:
            connection.execute("INSERT INTO settings VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value)))

    def audit(self, action: str) -> None:
        with self.lock, self.connect() as connection:
            connection.execute("INSERT INTO audit(created_at, action) VALUES (?, ?)", (time.time(), action))

    def has_owner(self) -> bool:
        with self.connect() as connection:
            return connection.execute("SELECT 1 FROM owner").fetchone() is not None

    def create_owner(self, username: str, password: str) -> None:
        if not username.strip() or len(username) > 100 or not 12 <= len(password) <= 256:
            raise ValueError("Use a username and a password of 12 to 256 characters")
        salt = secrets.token_hex(24)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600000).hex()
        with self.lock, self.connect() as connection:
            if connection.execute("SELECT 1 FROM owner").fetchone():
                raise ValueError("An owner already exists")
            connection.execute("INSERT INTO owner VALUES (1, ?, ?, ?)", (username.strip(), salt, digest))
        self.audit("Local owner created")

    def authenticate(self, username: str, password: str) -> bool:
        if len(password) > 256:
            return False
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM owner WHERE id=1").fetchone()
        salt = row["salt"] if row else "00" * 24
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600000).hex()
        return bool(row and hmac.compare_digest(row["username"], username) and hmac.compare_digest(row["password_hash"], digest))

    def save_camera(self, camera: dict) -> str:
        data = dict(camera)
        data.pop("stream_info", None)
        camera_id = str(data.get("id") or uuid.uuid4())
        if not data.get("name") or len(str(data["name"])) > 200:
            raise ValueError("A camera name is required (maximum 200 characters)")
        with self.lock, self.connect() as connection:
            previous = connection.execute("SELECT stream FROM cameras WHERE id=?", (camera_id,)).fetchone()
            url = data.pop("rtsp_url", "")
            if url:
                if not url.startswith("rtsp://") or len(url) > 2048:
                    raise ValueError("A valid RTSP URL is required")
                identity = stream_key(url)
                for existing in connection.execute("SELECT id, stream FROM cameras WHERE id<>?", (camera_id,)).fetchall():
                    if stream_key(unprotect(existing["stream"])) == identity:
                        raise ValueError("This device/channel is already saved. Edit the existing camera instead of adding its main/substream twice.")
                stream = protect(url)
            elif previous:
                stream = previous["stream"]
            else:
                raise ValueError("An RTSP URL is required")
            data["id"] = camera_id
            connection.execute("INSERT INTO cameras VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET data=excluded.data, stream=excluded.stream", (camera_id, json.dumps(data), stream))
        self.audit(f"Camera configuration saved: {camera_id}")
        return camera_id

    def cameras(self, include_secrets: bool = False) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM cameras ORDER BY id").fetchall()
        result = []
        for row in rows:
            data = json.loads(row["data"])
            if include_secrets:
                data["rtsp_url"] = unprotect(row["stream"])
            else:
                data["stream_info"] = stream_identity(unprotect(row["stream"]))
            result.append(data)
        return result

    def delete_camera(self, camera_id: str) -> None:
        with self.lock, self.connect() as connection:
            connection.execute("DELETE FROM cameras WHERE id=?", (camera_id,))
        self.audit(f"Camera removed: {camera_id}")

    def record_event(self, event: dict) -> bool:
        from .storage import require_capacity
        require_capacity(self, len(json.dumps(event, default=str)))
        data = dict(event)
        event_id = str(data.get("event_id") or data.get("incident_id") or uuid.uuid4())
        evidence = {}

        def archive_images(record, prefix=""):
            for key in list(record):
                value = record[key]
                if isinstance(value, dict):
                    archive_images(value, prefix + key + ".")
                elif key.endswith("_b64") and isinstance(value, str):
                    if len(value) > 12 * 1024 * 1024:
                        raise ValueError("Evidence image exceeds the local size limit")
                    raw = base64.b64decode(value, validate=True)
                    digest = hashlib.sha256(raw).hexdigest()
                    directory = self.directory / "evidence"
                    directory.mkdir(exist_ok=True)
                    target = directory / digest
                    if not target.is_file():
                        temporary = directory / (digest + "." + secrets.token_hex(6) + ".tmp")
                        try:
                            temporary.write_bytes(raw)
                            temporary.replace(target)
                        finally:
                            temporary.unlink(missing_ok=True)
                    evidence[prefix + key] = "/api/evidence/" + digest
                    del record[key]

        data = json.loads(json.dumps(data, default=str))
        archive_images(data)
        data.update(event_id=event_id, evidence=evidence, verification_state="not_verified_offline")
        with self.lock, self.connect() as connection:
            cursor = connection.execute("INSERT OR IGNORE INTO events VALUES (?, ?, ?, ?)", (event_id, str(data.get("camera_id", "")), time.time(), json.dumps(data, default=str)))
            return cursor.rowcount == 1

    def events(self, limit: int = 200) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute("SELECT created_at, data FROM events ORDER BY created_at DESC LIMIT ?", (min(1000, max(1, limit)),)).fetchall()
        return [dict(json.loads(row["data"]), recorded_at=row["created_at"]) for row in rows]

    def incident_search(self, **filters) -> dict:
        from .reports import search_incidents
        return search_incidents(self, **filters)

    def record_count(self, camera_id: str, day: str, visible: int, entries: int, run_id: str, updated_at: float | None = None) -> None:
        if min(visible, entries) < 0:
            raise ValueError("Counts cannot be negative")
        with self.lock, self.connect() as connection:
            connection.execute("INSERT INTO count_sessions VALUES (?, ?, ?, ?) ON CONFLICT(camera_id,day,run_id) DO UPDATE SET entries=MAX(entries,excluded.entries)", (camera_id, day, run_id, entries))
            connection.execute("INSERT INTO counts VALUES (?, ?, ?, ?) ON CONFLICT(camera_id,day) DO UPDATE SET people_visible=excluded.people_visible, updated_at=excluded.updated_at", (camera_id, day, visible, time.time() if updated_at is None else updated_at))

    def counts(self, day: str) -> list[dict]:
        with self.connect() as connection:
            return [dict(row) for row in connection.execute("SELECT c.*, COALESCE((SELECT SUM(s.entries) FROM count_sessions s WHERE s.camera_id=c.camera_id AND s.day=c.day),0) AS entries FROM counts c WHERE c.day=? ORDER BY c.camera_id", (day,)).fetchall()]

    def backup(self, destination: Path) -> None:
        with self.lock, self.connect() as source, closing(sqlite3.connect(destination)) as target:
            source.backup(target)
