from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from build_exe import ROOT, write_offline_launch_config

FEATURES = ["people_count", "shoplifting", "inventory_movement", "fall_detected", "restricted_zone", "loitering", "suspicious_behavior", "crowding"]


def stage_test_package(source: Path, destination: Path, now: datetime | None = None) -> dict:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    configuration = source / "config.json"
    if configuration.is_file() and json.loads(configuration.read_text(encoding="utf-8")) != {"mode": "offline"}:
        raise ValueError("Refusing to package customer configuration; use a generic offline build")
    if (source / "offline-entitlement.json").exists():
        raise ValueError("Refusing to replace a customer entitlement")
    required = ["VantagAgent.exe", "_internal/offline-ui/offline.html", "_internal/models/offline-manifest.json", "_internal/offline_keys.json"]
    for name in required:
        if not (source / name).is_file():
            raise FileNotFoundError(f"Generic offline build is incomplete: {name}")
    shutil.copytree(source, destination)
    write_offline_launch_config(destination)
    issued = now or datetime.now(timezone.utc)
    expires = issued + timedelta(days=3)
    key_id = "engineering-test-" + uuid.uuid4().hex
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii")
    claims = {
        "version": 1, "key_id": key_id, "issuer": "Vantag engineering test - not a customer subscription",
        "tenant_id": "engineering-test", "entitlement_id": str(uuid.uuid4()), "revision": 1,
        "issued_at": issued.timestamp(), "not_before": (issued - timedelta(minutes=5)).timestamp(),
        "expires_at": expires.timestamp(), "grace_days": 7, "camera_limit": 8, "features": FEATURES,
        "device_id": None, "purpose": "engineering-test-not-for-resale",
    }
    payload = base64.urlsafe_b64encode(json.dumps(claims, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).decode("ascii")
    envelope = {"payload": payload, "signature": base64.urlsafe_b64encode(private_key.sign(payload.encode("ascii"))).decode("ascii")}
    (destination / "_internal" / "offline_keys.json").write_text(json.dumps({key_id: public_key}, indent=2), encoding="utf-8")
    (destination / "offline-entitlement.json").write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    metadata = {
        "version": "1.11.5", "purpose": "engineering-test-not-for-resale", "camera_limit": 8,
        "issued_at_utc": issued.isoformat(), "expires_at_utc": expires.isoformat(),
        "grace_ends_at_utc": (expires + timedelta(days=7)).isoformat(),
        "disconnected_core_validated": False, "commercial_redistribution_approved": False,
        "status": "Engineering test only. No production subscription or production signing keys are included.",
        "unavailable": ["staff_matching", "visual_verification", "visual_search", "assistant", "high_value_counter"],
        "requirements": "Windows 10/11 x64; existing Windows .NET Framework 4.5+ for setup; no separate Python or pip. CPU inference; GPU drivers are not installed.",
    }
    for name in ("OFFLINE_CAPABILITIES.json", "TEST_PACKAGE.json"):
        (destination / name).write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (destination / "PACKAGE_VERSION.txt").write_text("1.11.5 engineering test", encoding="utf-8")
    return metadata


def build_test_installer(source: Path, output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=False)
    payload_root = output / "payload"
    stage = payload_root / "engine"
    metadata = stage_test_package(source, stage)
    build_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    compiler = Path(os.environ["WINDIR"]) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
    if not compiler.is_file():
        raise FileNotFoundError("The build host needs the Windows .NET Framework C# compiler")
    references = [
        "/reference:System.Windows.Forms.dll", "/reference:System.Drawing.dll", "/reference:System.Core.dll",
        "/reference:System.IO.Compression.dll", "/reference:System.IO.Compression.FileSystem.dll", "/reference:Microsoft.CSharp.dll",
    ]
    template = (ROOT / "installer" / "OfflineTestSetup.cs").read_text(encoding="utf-8")
    template = template.replace("%%BUILD_ID%%", build_id).replace("%%EXPIRY%%", metadata["expires_at_utc"]).replace("%%GRACE_END%%", metadata["grace_ends_at_utc"])
    launcher_source = output / "OfflineTestLauncher.cs"
    launcher_source.write_text(template.replace("%%PAYLOAD_SHA256%%", "launcher"), encoding="utf-8")
    subprocess.run([
        str(compiler), "/nologo", "/target:winexe", "/platform:x64", "/optimize+", "/define:LAUNCHER", *references,
        f"/win32icon:{ROOT / 'assets' / 'icon.ico'}", f"/out:{payload_root / 'VantagOfflineTest.exe'}", str(launcher_source),
    ], check=True)
    metadata["build_id"] = build_id
    (output / "TEST_PACKAGE.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    archive_path = output / "VantagOfflineTest-1.11.5.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as archive:
        for path in payload_root.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(payload_root).as_posix())
    with zipfile.ZipFile(archive_path) as archive:
        damaged = archive.testzip()
        if damaged:
            raise ValueError(f"Archive integrity failed: {damaged}")
    with archive_path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    template = template.replace("%%PAYLOAD_SHA256%%", digest)
    generated = output / "OfflineTestSetup.cs"
    generated.write_text(template, encoding="utf-8")
    installer = output / "VantagOfflineTestSetup-1.11.5.exe"
    subprocess.run([
        str(compiler), "/nologo", "/target:winexe", "/platform:x64", "/optimize+", *references,
        f"/win32icon:{ROOT / 'assets' / 'icon.ico'}", f"/resource:{archive_path},vantag.payload.zip",
        f"/out:{installer}", str(generated),
    ], check=True)
    for path in (archive_path, installer):
        with path.open("rb") as stream:
            checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        path.with_suffix(path.suffix + ".sha256").write_text(f"{checksum}  {path.name}\n", encoding="ascii")
    print(json.dumps({"installer": str(installer), "portable_zip": str(archive_path), "metadata": metadata}, indent=2), flush=True)
    return installer


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=ROOT / "build" / "standalone_output" / "offline" / "VantagAgent")
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    build_test_installer(arguments.source, arguments.output)
