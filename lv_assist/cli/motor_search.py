"""Search extracted component data for motor current-range matches."""

import argparse
import sys
from collections.abc import Sequence

from lv_assist.database.errors import DatabaseError
from lv_assist.database.models import MotorProtectionCandidate
from lv_assist.database.repositories import ComponentRepository
from lv_assist.i18n import i18n, tr
from lv_assist.paths import config_file_path


def search_motor_protection(
    power_kw: float,
    voltage_v: float,
    verified_only: bool = False,
) -> list[MotorProtectionCandidate]:
    """Return matching data records without making a protection decision."""
    return ComponentRepository().find_components_for_motor(
        power_kw, voltage_v, verified_only=verified_only
    )


def _print_results(results: Sequence[MotorProtectionCandidate], verified_only: bool) -> None:
    """Print candidates with provenance and an explicit non-safety classification."""
    if not results:
        key = "motor_search_no_verified" if verified_only else "motor_search_no_results"
        print(tr(key))
        return

    for result in results:
        print(f"{result.manufacturer or '—'} | {result.part_number or '—'}")
        print(f"  {tr('motor_search_status')}: {result.record_status}")
        print(f"  {tr('motor_search_current')}: {result.estimated_motor_current_a:g} A")
        print(
            f"  {tr('motor_search_range')}: "
            f"{result.rated_current_min_a:g}–{result.rated_current_max_a:g} {result.current_unit}"
        )
        print(f"  {tr('motor_search_voltage_rating')}: {result.rated_voltage_v:g} {result.voltage_unit}")
        print(f"  {tr('motor_search_source_file')}: {result.source_file or '—'}")
        print(f"  {tr('motor_search_source_locator')}: {result.source_locator or '—'}")
        if result.preview_warning:
            print(f"  {tr('motor_search_preview_warning')}")
        if not result.is_safety_recommendation:
            print(f"  {tr('motor_search_not_safety')}")


def main(argv: Sequence[str] | None = None) -> int:
    """Parse CLI options, search the configured database, and print the results."""
    i18n.set_config_path(config_file_path())
    parser = argparse.ArgumentParser(description=tr("motor_search_title"))
    parser.add_argument("--power", type=float, required=True, help=tr("motor_search_power_kw"))
    parser.add_argument("--voltage", type=float, required=True, help=tr("motor_search_voltage_v"))
    parser.add_argument("--verified-only", action="store_true", help=tr("motor_search_verified_only"))
    args = parser.parse_args(argv)

    try:
        results = search_motor_protection(args.power, args.voltage, args.verified_only)
    except (DatabaseError, ValueError, TypeError) as exc:
        print(f"{tr('motor_search_error')}: {exc}", file=sys.stderr)
        return 2

    _print_results(results, args.verified_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
