from pathlib import Path
import shutil
import sqlite3
import zipfile

import pytest

import build_exe
from lv_assist.distribution import SEED_FILES, RELEASE_DATA_FILES, prepare_release_data


def seed_directory(target):
    target.mkdir(parents=True)
    source = Path(__file__).resolve().parents[1] / 'lv_assist' / 'data'
    for name in SEED_FILES:
        shutil.copy2(source / name, target / name)


def test_release_data_excludes_local_database_and_preserves_seeds(tmp_path):
    source = tmp_path / 'source'
    seed_directory(source)
    (source / 'lv_assist.db').write_bytes(b'LOCAL_DATABASE_MUST_NOT_BE_DISTRIBUTED')
    (source / 'reference_library.db').write_bytes(b'UNREVIEWED_REFERENCE_LIBRARY_MUST_NOT_BE_DISTRIBUTED')
    (source / 'private.log').write_text('LOCAL_ONLY')
    before = {p.name: p.read_bytes() for p in source.iterdir()}
    paths = prepare_release_data(source, tmp_path / 'release')
    assert {p.name for p in paths} == set(RELEASE_DATA_FILES)
    assert {p.name: p.read_bytes() for p in source.iterdir()} == before
    with sqlite3.connect(tmp_path / 'release' / 'lv_assist.db') as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert conn.execute('SELECT count(*) FROM catalog_devices').fetchone()[0] >= 90
    with pytest.raises(ValueError):
        prepare_release_data(source, tmp_path / 'release')


def test_release_archive_uses_only_clean_inputs_and_retains_existing_user_data(tmp_path, monkeypatch):
    root = tmp_path / 'project'
    seed_directory(root / 'lv_assist' / 'data')
    translations = root / 'lv_assist' / 'translations'
    translations.mkdir()
    for lang in ('fa', 'en', 'de'):
        (translations / f'{lang}.json').write_text('{}')
    (root / 'main.py').write_text('')
    (root / 'dist' / 'data').mkdir(parents=True)
    local_db = root / 'dist' / 'data' / 'lv_assist.db'
    local_db.write_bytes(b'KEEP_EXISTING_PORTABLE_USER_DATA')
    monkeypatch.setattr(build_exe, 'ROOT', root)
    monkeypatch.setattr(build_exe, 'ENTRY_SCRIPT', root / 'main.py')
    monkeypatch.setattr(build_exe, 'ensure_pyinstaller', lambda: None)

    def fake_compiler(command, cwd):
        assert '--collect-data=customtkinter' in command
        assert not any(str(root / 'lv_assist' / 'data') in arg for arg in command if arg.startswith('--add-data'))
        (root / 'dist' / build_exe.APP_NAME).write_bytes(b'TEST_EXECUTABLE')

    monkeypatch.setattr(build_exe.subprocess, 'check_call', fake_compiler)
    build_exe.build()
    assert local_db.read_bytes() == b'KEEP_EXISTING_PORTABLE_USER_DATA'
    with zipfile.ZipFile(root / 'dist' / f'{build_exe.APP_NAME}-release.zip') as archive:
        assert set(archive.namelist()) == {build_exe.APP_NAME, *('data/' + name for name in RELEASE_DATA_FILES)}
        assert archive.read('data/lv_assist.db').startswith(b'SQLite format 3')


def test_translation_key_sets_match():
    import json
    root = Path(__file__).resolve().parents[1] / 'lv_assist' / 'translations'
    keys = [set(json.loads((root / f'{lang}.json').read_text())) for lang in ('fa', 'en', 'de')]
    assert keys[0] == keys[1] == keys[2]
