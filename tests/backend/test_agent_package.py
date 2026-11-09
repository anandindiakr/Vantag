import json
import zipfile
from pathlib import Path

import pytest

from backend.services import agent_package


def create_base(path: Path, version: str = "1.11.4"):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("VantagAgent.exe", b"test-exe")
        archive.writestr("PACKAGE_VERSION.txt", version)
        archive.writestr("_internal/python311.dll", b"test-runtime")


def test_account_archives_keep_credentials_isolated(tmp_path):
    base = tmp_path / "base.zip"
    create_base(base)
    one = agent_package.build_windows_package(base, {"api_key": "tenant-one"}, "1.11.4", tmp_path)
    two = agent_package.build_windows_package(base, {"api_key": "tenant-two"}, "1.11.4", tmp_path)
    try:
        with zipfile.ZipFile(one) as archive:
            assert json.loads(archive.read("config.json"))["api_key"] == "tenant-one"
            assert b"tenant-two" not in archive.read("config.json")
            assert "VantagAgent.exe" in archive.namelist()
        with zipfile.ZipFile(two) as archive:
            assert json.loads(archive.read("config.json"))["api_key"] == "tenant-two"
        with zipfile.ZipFile(base) as archive:
            assert "config.json" not in archive.namelist()
    finally:
        agent_package.remove_package(one)
        agent_package.remove_package(two)
    assert not Path(one).exists() and not Path(two).exists()


def test_missing_or_mismatched_package_fails_without_leaking_temp_files(tmp_path):
    with pytest.raises(agent_package.PackageUnavailable):
        agent_package.build_windows_package(tmp_path / "missing.zip", {}, "1.11.4", tmp_path)
    base = tmp_path / "base.zip"
    create_base(base, "1.11.3")
    with pytest.raises(agent_package.PackageUnavailable):
        agent_package.build_windows_package(base, {}, "1.11.4", tmp_path)
    assert sorted(item.name for item in tmp_path.iterdir()) == ["base.zip"]


def test_rejects_preconfigured_base_archive(tmp_path):
    base = tmp_path / "base.zip"
    create_base(base)
    with zipfile.ZipFile(base, "a") as archive:
        archive.writestr("config.json", '{"api_key":"wrong-tenant"}')
    with pytest.raises(agent_package.PackageUnavailable):
        agent_package.build_windows_package(base, {}, "1.11.4", tmp_path)
