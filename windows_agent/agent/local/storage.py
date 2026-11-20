from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
import time
import zipfile
from contextlib import closing
from pathlib import Path

TABLES = ("cameras", "events", "count_sessions", "counts")


def storage_status(store) -> dict:
    quota = store.get("storage", {}).get("quota_mb", 10240) * 1024 * 1024
    used = sum(path.stat().st_size for path in store.directory.rglob("*") if path.is_file())
    free = shutil.disk_usage(store.directory).free
    return {"used_bytes": used, "quota_bytes": quota, "free_bytes": free, "can_record": used < quota and free >= 256 * 1024 * 1024, "retention": "Keep records until explicitly removed or restored; never evict because internet is absent"}


def require_capacity(store, additional: int = 0) -> None:
    status = storage_status(store)
    if status["used_bytes"] + additional >= status["quota_bytes"] or status["free_bytes"] - additional < 256 * 1024 * 1024:
        raise ValueError("Local storage limit or low disk space: recording stopped. Export a backup, free disk space or increase the quota; existing records are retained.")


def export_backup(store, destination: Path) -> None:
    if shutil.disk_usage(destination.parent).free < store.path.stat().st_size * 2:
        raise ValueError("Not enough disk space to create a backup. Free space or copy the stopped site's data folder to another drive.")
    with store.lock, tempfile.TemporaryDirectory(prefix="vantag-backup-") as directory:
        database = Path(directory) / "site.sqlite3"
        store.backup(database)
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(database, "site.sqlite3")
            archive.writestr("manifest.json", json.dumps({"version": 1, "created_at": time.time(), "scope": "Private site backup; camera credentials require the original Windows account"}))
            evidence = store.directory / "evidence"
            if evidence.is_dir():
                for path in evidence.iterdir():
                    if path.is_file() and len(path.name) == 64 and all(char in "0123456789abcdef" for char in path.name):
                        archive.write(path, "evidence/" + path.name)
    store.audit("Private local backup exported")


def restore_backup(store, archive_path: Path) -> None:
    from .server import validate_stream
    from .vault import unprotect

    with store.lock, tempfile.TemporaryDirectory(prefix="vantag-restore-") as directory:
        staging = Path(directory)
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or "site.sqlite3" not in names or "manifest.json" not in names:
                raise ValueError("Invalid site backup")
            for name in names:
                digest = name.removeprefix("evidence/")
                if name not in {"site.sqlite3", "manifest.json"} and not (name.startswith("evidence/") and len(digest) == 64 and all(char in "0123456789abcdef" for char in digest)):
                    raise ValueError("Unexpected file in backup")
            require_capacity(store, sum(item.file_size for item in archive.infolist()))
            archive.extractall(staging)
        if json.loads((staging / "manifest.json").read_text(encoding="utf-8")).get("version") != 1:
            raise ValueError("Unsupported backup version")
        with closing(sqlite3.connect((staging / "site.sqlite3").as_uri() + "?mode=ro", uri=True)) as source:
            source.execute("PRAGMA trusted_schema=OFF")
            if source.execute("PRAGMA user_version").fetchone()[0] != 1 or source.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("Backup database integrity or version check failed")
            for table in (*TABLES, "settings"):
                schema = source.execute("SELECT type, sql FROM sqlite_master WHERE name=?", (table,)).fetchone()
                if not schema or schema[0] != "table" or not schema[1].upper().startswith("CREATE TABLE"):
                    raise ValueError("Backup schema is not supported")
            for stream, in source.execute("SELECT stream FROM cameras"):
                validate_stream(unprotect(stream))
            evidence = staging / "evidence"
            if evidence.is_dir():
                target = store.directory / "evidence"
                target.mkdir(exist_ok=True)
                for path in evidence.iterdir():
                    with path.open("rb") as image:
                        if hashlib.file_digest(image, "sha256").hexdigest() != path.name:
                            raise ValueError("Backup evidence failed its integrity check")
                for path in evidence.iterdir():
                    path.replace(target / path.name)
            with store.connect() as connection:
                for table in TABLES:
                    connection.execute(f"DELETE FROM {table}")
                    columns = source.execute(f"PRAGMA table_info({table})").fetchall()
                    placeholders = ",".join("?" for _ in columns)
                    connection.executemany(f"INSERT INTO {table} VALUES ({placeholders})", source.execute(f"SELECT * FROM {table}"))
                connection.execute("DELETE FROM settings WHERE key NOT IN ('entitlement', 'installation_id')")
                connection.executemany("INSERT INTO settings VALUES (?, ?)", source.execute("SELECT key, value FROM settings WHERE key NOT IN ('entitlement', 'installation_id')"))
                connection.execute("INSERT INTO audit(created_at, action) VALUES (?, ?)", (time.time(), "Site data restored; current owner, device identity and entitlement high-water mark preserved"))
