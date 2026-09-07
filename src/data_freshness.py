"""Aggregate-only source-to-database freshness diagnostics."""

import argparse
from functools import lru_cache
import json
import re
import sqlite3
from datetime import date
from pathlib import Path

try:
    from .db import BASE_DIR, DB_PATH, get_current_db_path
except ImportError:
    from db import BASE_DIR, DB_PATH, get_current_db_path


RAW_DIR = BASE_DIR / "data" / "raw"
ENDPOINT_FILES = {
    "daily_activity": "polar_daily_activity.json",
    "training": "polar_training_sessions.json",
    "sleep": "polar_sleep.json",
    "nightly_recharge": "polar_nightly_recharge.json",
    "continuous_heart_rate": "polar_continuous_heart_rate.json",
    "cardio_load": "polar_cardio_load.json",
}
TABLES = {
    "daily_activity": "polar_daily_activity_raw",
    "training": "polar_training_sessions_raw",
    "sleep": "polar_sleep_raw",
    "nightly_recharge": "polar_nightly_recharge_raw",
    "continuous_heart_rate": "polar_continuous_hr_raw",
    "cardio_load": "polar_cardio_load_raw",
}
DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def _collect_dates(value, dates):
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(child, str) and any(token in key.lower() for token in ("date", "time", "start", "end")):
                match = DATE_RE.match(child)
                if match:
                    dates.append(match.group(1))
            _collect_dates(child, dates)
    elif isinstance(value, list):
        for child in value:
            _collect_dates(child, dates)


@lru_cache(maxsize=len(ENDPOINT_FILES) * 2)
def _latest_raw_date_for_revision(path_text, modified_at_ns, size):
    """Parse a raw endpoint file once for each observed file revision."""
    del modified_at_ns, size  # Revision fields intentionally participate in the cache key.
    try:
        value = json.loads(Path(path_text).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(value, dict) and value.get("ok") is False:
        return None
    dates = []
    _collect_dates(value, dates)
    return max(dates) if dates else None


def latest_raw_date(path):
    """Return an endpoint's latest date without reparsing unchanged raw JSON."""
    target = Path(path)
    try:
        stat = target.stat()
    except OSError:
        return None
    return _latest_raw_date_for_revision(
        str(target.resolve()), stat.st_mtime_ns, stat.st_size,
    )


def _max_date(connection, table):
    try:
        row = connection.execute(f"SELECT MAX(date) FROM {table}").fetchone()
        return row[0] if row else None
    except sqlite3.OperationalError:
        return None


def collect_freshness(db_path=None, raw_dir=RAW_DIR, today=None):
    current_day = today or date.today()
    raw_dir = Path(raw_dir)
    raw_dates = {
        endpoint: latest_raw_date(raw_dir / filename)
        for endpoint, filename in ENDPOINT_FILES.items()
    }
    path = get_current_db_path() if db_path is None else Path(db_path)
    if path.exists():
        connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    else:
        connection = sqlite3.connect(":memory:")
    try:
        imported_dates = {endpoint: _max_date(connection, table) for endpoint, table in TABLES.items()}
        stage_dates = {
            "daily_metrics": _max_date(connection, "daily_recovery_metrics"),
            "recovery": _max_date(connection, "recovery_scores"),
            "confidence": _max_date(connection, "recovery_confidence"),
            "local_coach": _max_date(connection, "local_coach_recommendations"),
        }
    finally:
        connection.close()
    source_values = [value for value in raw_dates.values() if value]
    source_latest = max(source_values) if source_values else None
    imported_values = [value for value in imported_dates.values() if value]
    imported_latest = max(imported_values) if imported_values else None
    source_lag = max((current_day - date.fromisoformat(source_latest)).days, 0) if source_latest else None
    if source_latest is None:
        blocker = "source_data_unavailable"
    elif source_latest < current_day.isoformat():
        blocker = "source_data_not_available_for_today"
    elif imported_latest is None or imported_latest < source_latest:
        blocker = "raw_import_lag"
    elif stage_dates["daily_metrics"] is None or stage_dates["daily_metrics"] < source_latest:
        blocker = "daily_metrics_lag"
    elif stage_dates["recovery"] is None or stage_dates["recovery"] < source_latest:
        blocker = "recovery_lag"
    elif stage_dates["confidence"] is None or stage_dates["confidence"] < source_latest:
        blocker = "confidence_lag"
    elif stage_dates["local_coach"] is None or stage_dates["local_coach"] < source_latest:
        blocker = "local_coach_lag"
    else:
        blocker = None
    aligned = bool(source_latest and stage_dates["local_coach"] and stage_dates["local_coach"] >= source_latest)
    return {
        "as_of_date": current_day.isoformat(),
        "latest_source_data_date": source_latest,
        "source_data_lag_days": source_lag,
        "latest_imported_raw_date": imported_latest,
        "latest_daily_metrics_date": stage_dates["daily_metrics"],
        "latest_recovery_date": stage_dates["recovery"],
        "latest_confidence_date": stage_dates["confidence"],
        "latest_local_coach_date": stage_dates["local_coach"],
        "database_aligned_with_source": aligned,
        "today_source_data_available": source_latest == current_day.isoformat(),
        "prospective_collection_blocker": blocker,
        "endpoint_latest_dates": raw_dates,
        "endpoint_imported_dates": imported_dates,
        "contains_health_values": False,
    }


def main(argv=None):
    argparse.ArgumentParser(description="Report aggregate source freshness without health values.").parse_args(argv)
    print(json.dumps(collect_freshness(), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
