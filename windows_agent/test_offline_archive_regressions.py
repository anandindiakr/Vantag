import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import build_exe
from standalone_entry import local_mode_requested


def test_actual_offline_archive_keeps_normal_launch_mode_and_starter(tmp_path):
    stage = tmp_path / 'stage'
    stage.mkdir()
    (stage / 'VantagAgent.exe').write_bytes(b'test fixture')
    build_exe.write_offline_launch_config(stage)
    archive = tmp_path / 'offline.zip'
    build_exe.create_archive(stage, archive, offline=True)
    with zipfile.ZipFile(archive) as package:
        package.extractall(tmp_path / 'extracted')
        assert 'START-OFFLINE.cmd' in package.namelist()
    assert local_mode_requested([], tmp_path / 'extracted')


def test_online_base_archive_never_copies_account_secrets(tmp_path):
    stage = tmp_path / 'stage'
    stage.mkdir()
    (stage / 'config.json').write_text(json.dumps({'api_key': 'not-a-real-secret'}))
    archive = tmp_path / 'online.zip'
    build_exe.create_archive(stage, archive, offline=False)
    with zipfile.ZipFile(archive) as package:
        assert 'config.json' not in package.namelist()


def test_offline_archive_rejects_unexpected_customer_configuration(tmp_path):
    (tmp_path / 'config.json').write_text(json.dumps({'mode': 'offline', 'api_key': 'not-a-real-secret'}))
    with pytest.raises(ValueError, match='configuration'):
        build_exe.create_archive(tmp_path, tmp_path / 'offline.zip', offline=True)
