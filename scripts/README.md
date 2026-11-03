# Catalog migration scripts

The `extend_catalog_phase*.py` scripts are used by `migrate_to_sqlite.py` when creating or updating the seed database. Keep their filenames and location until the migration pipeline is deliberately changed.

Historical `apply_priority*.py` repair scripts and the old `git_sync.bat` are not part of the published project. Their changes are already integrated; the original copies remain in the local recovery backup.

To recreate the local database from a fresh checkout, start the application or run `python migrate_to_sqlite.py`. Do not replace a populated user database without a backup.
