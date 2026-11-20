import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path


class PackageUnavailable(RuntimeError):
    pass


WINDOWS_README = """Vantag Edge Agent for Windows

1. Extract all files from this ZIP into a private folder.
2. Keep config.json and the _internal folder beside VantagAgent.exe.
3. Double-click VantagAgent.exe. The agent runs in the Windows system tray.
4. Keep the computer powered on and connected to the camera network and internet.

This package contains your account credentials. Do not share it.
Python and pip do not need to be installed. Logs: %APPDATA%\\Vantag\\agent.log
Optional AI features may require additional downloads or dependencies.
"""


PUBLIC_AGENT_HOSTS = frozenset({
    "retailnazar.com", "retailnazar.in", "retailnazar.info", "retail-vantag.com",
    "jagajaga.my", "retailjagajaga.com", "retailbantay.com", "retailbantay.ph",
    "retailpantau.com",
})


def agent_backend_url(host: str, forwarded_proto: str) -> str:
    hostname = host.split(":", 1)[0].lower()
    scheme = "https" if hostname in PUBLIC_AGENT_HOSTS else forwarded_proto
    return f"{scheme}://{host}"


def validate_offline_windows_artifact(artifact: Path, version: str) -> dict:
    try:
        with zipfile.ZipFile(artifact) as source:
            qualification = json.loads(source.read("OFFLINE_CAPABILITIES.json"))
            if qualification.get("version") != version or not qualification.get("disconnected_core_validated") or not qualification.get("commercial_redistribution_approved"):
                raise ValueError("Offline qualification has not passed")
            keys = json.loads(source.read("_internal/offline_keys.json"))
            from cryptography.hazmat.primitives import serialization
            from .offline_entitlement import signing_key
            key_id, private = signing_key()
            expected = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
            if keys.get(key_id) != expected:
                raise ValueError("The package does not trust the licence signer")
    except (zipfile.BadZipFile, KeyError, ValueError, OSError) as exc:
        raise PackageUnavailable("The offline artifact is not qualified for distribution") from exc
    return qualification


def build_offline_windows_package(artifact: Path, envelope: dict, version: str, temporary_directory: Path | None = None) -> str:
    validate_offline_windows_artifact(artifact, version)
    readme = """Vantag Offline Site Console

Extract all files. Keep config.json, offline-entitlement.json and _internal beside VantagAgent.exe.
Run VantagAgent.exe. Create a LOCAL owner login in the console opened on this PC.
Configure NVR/camera channels on the same local network; internet is not required for supported local functions.
AI feature coverage and hardware requirements are listed in OFFLINE_CAPABILITIES.json and local health.
After entitlement expiry there is seven days of grace, then live viewing and new AI processing stop.
Saved records and reports remain accessible. Export a device renewal request and import a signed renewal file.
Cloud email, hosted dashboards, online payments and off-site live viewing are not live offline.
Keep this account-specific package private. Back up the local site data before upgrades.
"""
    filename = build_windows_package(artifact, {"mode": "offline"}, version, temporary_directory, readme=readme)
    try:
        with zipfile.ZipFile(filename, "a", compression=zipfile.ZIP_DEFLATED) as output:
            output.writestr("offline-entitlement.json", json.dumps(envelope, indent=2))
        return filename
    except BaseException:
        remove_package(filename)
        raise


def remove_package(path: str) -> None:
    Path(path).unlink(missing_ok=True)


def build_windows_package(base: Path, config: dict, version: str, temp_dir: Path | None = None, readme: str = WINDOWS_README) -> str:
    try:
        with zipfile.ZipFile(base) as archive:
            names = archive.namelist()
            if (
                names.count("VantagAgent.exe") != 1
                or names.count("PACKAGE_VERSION.txt") != 1
                or "config.json" in names
                or "offline-entitlement.json" in names
                or archive.read("PACKAGE_VERSION.txt").decode("utf-8").strip() != version
            ):
                raise PackageUnavailable("The standalone Windows agent package is invalid or outdated.")
    except (OSError, zipfile.BadZipFile, KeyError, UnicodeError) as exc:
        raise PackageUnavailable("The standalone Windows agent package is unavailable.") from exc

    descriptor, filename = tempfile.mkstemp(prefix="vantag-agent-", suffix=".zip", dir=temp_dir)
    try:
        with os.fdopen(descriptor, "wb") as output, base.open("rb") as source:
            shutil.copyfileobj(source, output, length=1024 * 1024)
        with zipfile.ZipFile(filename, "a", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("config.json", json.dumps(config, indent=2))
            archive.writestr("VERSION.txt", f"Vantag Edge Agent v{version}\n")
            archive.writestr("README.txt", readme)
        return filename
    except BaseException:
        remove_package(filename)
        raise
