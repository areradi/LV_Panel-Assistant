from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

import lv_assist.paths as paths_module


_REPO_ROOT = Path(__file__).resolve().parents[1]
_REAL_DATA_DIR = _REPO_ROOT / "lv_assist" / "data"
_SEED_DB = _REAL_DATA_DIR / "lv_assist.db"
_BOOTSTRAP_DATA_DIR = Path(tempfile.mkdtemp(
    prefix=".pytest-catalog-bootstrap-", dir=_REPO_ROOT
))
shutil.copy2(_SEED_DB, _BOOTSTRAP_DATA_DIR / "lv_assist.db")

# catalog.py creates its module singleton during import. Point that first open
# at a disposable copy before any test module can import catalog.py.
_original_get_data_dir = paths_module.get_data_dir
paths_module.get_data_dir = lambda: _BOOTSTRAP_DATA_DIR
try:
    import lv_assist.catalog as catalog_module
finally:
    paths_module.get_data_dir = _original_get_data_dir


@pytest.fixture(scope="session", autouse=True)
def remove_bootstrap_db_after_session():
    yield
    shutil.rmtree(_BOOTSTRAP_DATA_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def isolate_catalog_db(tmp_path, monkeypatch):
    """Give every test a private catalog copy and redirect the singleton."""
    temp_db = tmp_path / "test_catalog.db"
    shutil.copy2(_SEED_DB, temp_db)
    monkeypatch.setattr(catalog_module, "DB_PATH", temp_db)
    monkeypatch.setattr(catalog_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(paths_module, "get_data_dir", lambda: tmp_path)

    singleton = catalog_module.catalog_repo
    original_db_path = singleton.db_path
    singleton.db_path = catalog_module._ensure_database(temp_db)
    singleton.reload()
    yield
    singleton.db_path = original_db_path
    singleton.reload()


def pytest_unconfigure(config):
    shutil.rmtree(_BOOTSTRAP_DATA_DIR, ignore_errors=True)
