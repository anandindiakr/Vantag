import sys
from pathlib import Path


def application_directory() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent


def bundled_resource(*parts: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS).joinpath(*parts)
    return Path(__file__).resolve().parent.parent.joinpath(*parts)
