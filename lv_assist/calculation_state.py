from lv_assist.models import compute_input_hash


class StaleCalculationStateError(ValueError):
    pass


def require_current_calculation(project, summary, feeders=None):
    expected = summary.verified_input_hash
    source = summary._source_feeders
    if source is None:
        source = summary.calculation_inputs
    if not expected or compute_input_hash(project, source) != expected:
        raise StaleCalculationStateError("STALE: inputs changed or calculation evidence is missing; recalculate before export")
    if feeders is not None:
        if any(f.verified_input_hash != expected for f in feeders):
            raise StaleCalculationStateError("STALE: feeder results belong to a different calculation")
