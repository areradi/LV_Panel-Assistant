from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lv_assist.reference_library import import_reference_directory, inspect_reference_directory


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Inspect extracted reference tables or import them into an unverified SQLite library.')
    parser.add_argument('input_directory', type=Path)
    parser.add_argument('--db', type=Path, help='Separate reference database. Omit for inspection without database writes.')
    parser.add_argument('--report', type=Path, help='Write the import summary as JSON.')
    args = parser.parse_args(argv)
    try:
        if args.report and (args.report.resolve().is_relative_to(args.input_directory.resolve())
                            or (args.db and args.report.resolve() == args.db.resolve())):
            raise ValueError('The report must be outside the input directory and separate from the database')
        summary = (import_reference_directory(args.input_directory, args.db) if args.db
                   else inspect_reference_directory(args.input_directory)['summary'])
        rendered = json.dumps(summary, ensure_ascii=False, indent=2) + '\n'
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(rendered, encoding='utf-8')
        print(rendered, end='')
        return 0
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f'Reference import failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
