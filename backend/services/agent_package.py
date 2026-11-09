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


def remove_package(path: str) -> None:
    Path(path).unlink(missing_ok=True)


def build_windows_package(base: Path, config: dict, version: str, temp_dir: Path | None = None) -> str:
    try:
        with zipfile.ZipFile(base) as archive:
            names = archive.namelist()
            if (
                names.count("VantagAgent.exe") != 1
                or names.count("PACKAGE_VERSION.txt") != 1
                or "config.json" in names
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
            archive.writestr("README.txt", WINDOWS_README)
        return filename
    except BaseException:
        remove_package(filename)
        raise
