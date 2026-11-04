from pathlib import Path
import shutil


SEED_FILES = ('catalog_devices.json', 'selectivity_rules.json', 'standards_registry.json', 'trip_curves.json')
RELEASE_DATA_FILES = (*SEED_FILES, 'lv_assist.db')


def prepare_release_data(source: Path, target: Path) -> list[Path]:
    source, target = source.resolve(), target.resolve()
    if source == target or (target / 'lv_assist.db').exists():
        raise ValueError('Release data requires a fresh directory separate from development data')
    for name in SEED_FILES:
        if not (source / name).is_file():
            raise FileNotFoundError(source / name)
    target.mkdir(parents=True, exist_ok=True)
    for name in SEED_FILES:
        shutil.copy2(source / name, target / name)
    from migrate_to_sqlite import build_or_migrate_database
    build_or_migrate_database(db_path=target / 'lv_assist.db', data_dir=target, force=True)
    return [target / name for name in RELEASE_DATA_FILES]
