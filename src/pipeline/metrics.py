try:
    from src.daily_metrics import rebuild_daily_recovery_metrics
    from src.db import connect
    from src.kubios_metrics.normalizer import rebuild as rebuild_kubios_normalized
    from src.kubios_metrics.derived import rebuild as rebuild_kubios_derived
    from src.kubios_morning_input import sync_manual_morning_measurements
except ImportError:
    from daily_metrics import rebuild_daily_recovery_metrics
    from db import connect
    from kubios_metrics.normalizer import rebuild as rebuild_kubios_normalized
    from kubios_metrics.derived import rebuild as rebuild_kubios_derived
    from kubios_morning_input import sync_manual_morning_measurements


def run(context, dry_run=False):
    if dry_run:
        return {"metrics_updated": 0}
    daily = rebuild_daily_recovery_metrics()
    with connect() as connection:
        manual = sync_manual_morning_measurements(connection)
        normalized = rebuild_kubios_normalized(connection)
        derived = rebuild_kubios_derived(connection)
    return {"metrics_updated": daily, "manual_kubios_projected": manual,
            "kubios_normalized": normalized["normalized_records"],
            "kubios_derived": derived["derived_records"]}
