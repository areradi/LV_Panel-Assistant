from pathlib import Path


def test_catalog_repository_uses_temp_db(tmp_path):
    from lv_assist.catalog import CatalogRepository, catalog_repo

    repo = CatalogRepository()
    expected_db = tmp_path / "test_catalog.db"
    assert repo.db_path == expected_db
    assert catalog_repo.db_path == expected_db


def test_migration_does_not_touch_real_db(tmp_path):
    from lv_assist.catalog import _ensure_database

    real_db = Path(__file__).resolve().parents[1] / "lv_assist" / "data" / "lv_assist.db"
    mtime_before = real_db.stat().st_mtime
    result = _ensure_database()
    mtime_after = real_db.stat().st_mtime

    assert result == tmp_path / "test_catalog.db"
    assert mtime_after == mtime_before


def test_no_backup_created_in_real_data_dir():
    from lv_assist.catalog import _ensure_database

    data_dir = Path(__file__).resolve().parents[1] / "lv_assist" / "data"
    backups_before = set(data_dir.glob("lv_assist.db.backup-v*"))
    _ensure_database()
    backups_after = set(data_dir.glob("lv_assist.db.backup-v*"))

    assert backups_after == backups_before, f"Test leaked backups: {backups_after - backups_before}"
