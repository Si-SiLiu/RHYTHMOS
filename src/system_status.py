import json
from datetime import date, datetime
from pathlib import Path

try:
    from .dashboard_data import DB_PATH, get_data_freshness, is_database_readable
    from .pipeline.history import HISTORY_PATH, get_last_sync
except ImportError:
    from dashboard_data import DB_PATH, get_data_freshness, is_database_readable
    from pipeline.history import HISTORY_PATH, get_last_sync


BASE_DIR = Path(__file__).resolve().parents[1]
STATE_PATH = BASE_DIR / "project_state.json"
VERSIONS_PATH = BASE_DIR / "config" / "versions.json"
VERSION_FIELDS = (
    "app_version",
    "recovery_engine_version",
    "baseline_engine_version",
    "confidence_engine_version",
    "local_coach_engine_version",
    "personal_logging_version",
    "nutrition_logging_engine_version",
    "supplement_unit_system_version",
    "supplement_catalog_version",
    "manual_logging_engine_version",
    "data_resolution_version",
    "scheduler_version",
    "ai_context_export_version",
    "i18n_engine_version",
    "kubios_screenshot_import_version",
    "database_schema_version",
    "dashboard_version",
)


def _read_json(path, label):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"Unable to read {label}: {exc}"
    if not isinstance(value, dict):
        return None, f"{label} must contain a JSON object"
    return value, None


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _active_p1_issues(state):
    # A blocked or external future-program issue belongs in the dedicated
    # roadmap/governance surfaces. It must not make an otherwise healthy local
    # data system appear degraded.
    closed = {"completed", "closed", "resolved", "blocked", "external_constraint"}
    return [
        issue
        for issue in state.get("prioritized_issues", [])
        if isinstance(issue, dict)
        and issue.get("priority") == "P1"
        and issue.get("status") not in closed
    ]


def load_system_status(
    state_path=STATE_PATH,
    versions_path=VERSIONS_PATH,
    db_path=None,
    sync_history_path=HISTORY_PATH,
    database_check=None,
    sync_reader=None,
    freshness_reader=None,
    freshness=None,
    today=None,
    stale_after_days=3,
):
    """Load governance facts and derive a read-only Dashboard health summary."""
    state, state_error = _read_json(state_path, "project_state.json")
    versions, versions_error = _read_json(versions_path, "config/versions.json")
    state = state or {}
    versions = versions or {}
    database_check = database_check or is_database_readable
    sync_reader = sync_reader or get_last_sync
    freshness_reader = freshness_reader or get_data_freshness
    try:
        database_ok = bool(database_check(db_path))
    except (OSError, RuntimeError, ValueError):
        database_ok = False
    try:
        last_sync = sync_reader(sync_history_path)
    except (OSError, RuntimeError, ValueError):
        last_sync = None

    test_total = state.get("test_total")
    test_passed = state.get("test_passed")
    test_failed = state.get("test_failed")
    test_success = state.get("test_success")
    tests_valid = (
        isinstance(test_total, int)
        and not isinstance(test_total, bool)
        and isinstance(test_passed, int)
        and not isinstance(test_passed, bool)
        and isinstance(test_failed, int)
        and not isinstance(test_failed, bool)
        and isinstance(test_success, bool)
        and test_total == test_passed + test_failed
        and test_success == (test_failed == 0)
    )

    # project_state.json is a governance snapshot and can lag behind a valid
    # local pipeline run. The canonical System page should use the live,
    # aggregate-only freshness result whenever it is reading the real app
    # state; isolated callers retain the supplied snapshot for deterministic
    # tests and tooling.
    latest_data_date = state.get("latest_data_date")
    if Path(state_path).resolve() == STATE_PATH.resolve():
        if freshness is None:
            try:
                freshness = freshness_reader(db_path=db_path, today=today) or {}
            except (OSError, RuntimeError, ValueError):
                freshness = {}
        latest_data_date = (
            freshness.get("latest_daily_metrics_date")
            or freshness.get("latest_source_data_date")
            or latest_data_date
        )
    latest = _parse_date(latest_data_date)
    current_day = today or datetime.now().astimezone().date()
    data_age_days = (current_day - latest).days if latest else None

    version_mismatches = [
        field
        for field in VERSION_FIELDS
        if state.get(field) is not None
        and versions.get(field) is not None
        and state.get(field) != versions.get(field)
    ]

    unhealthy_reasons = []
    warning_reasons = []
    if state_error:
        unhealthy_reasons.append("Project state is unavailable.")
    if not database_ok:
        unhealthy_reasons.append("Database is unavailable or unreadable.")
    if state and (not tests_valid or test_failed > 0):
        unhealthy_reasons.append("Recorded unittest status is invalid or failing.")
    if versions_error:
        warning_reasons.append("Version source is unavailable.")
    if version_mismatches:
        warning_reasons.append("Project state and version source do not match.")
    if state and latest is None:
        warning_reasons.append("Latest data date is missing or invalid.")
    elif data_age_days is not None and data_age_days > stale_after_days:
        warning_reasons.append(f"Latest data is {data_age_days} days old.")
    p1_issues = _active_p1_issues(state)
    if p1_issues:
        warning_reasons.append(f"{len(p1_issues)} active P1 issue(s) remain.")
    sync_warning_count = int(last_sync.get("warning_count", 0) or 0) if last_sync else 0
    # Older history readers expose only one aggregate count. Treat that as a
    # source-data warning for backward compatibility. Current pipeline history
    # separates the fetch-stage count, so optional AI or documentation work
    # cannot make healthy local Polar data look degraded.
    has_source_warning_breakdown = bool(last_sync) and "source_warning_count" in last_sync
    source_sync_warning_count = (
        int(last_sync.get("source_warning_count", 0) or 0)
        if has_source_warning_breakdown
        else sync_warning_count
    )
    auxiliary_sync_warning_count = max(0, sync_warning_count - source_sync_warning_count)
    if source_sync_warning_count and last_sync and bool(last_sync.get("success")):
        warning_reasons.append(
            f"Last Polar sync completed with {source_sync_warning_count} optional data warning(s)."
        )

    if unhealthy_reasons:
        health = "Unhealthy"
        reasons = unhealthy_reasons + warning_reasons
    elif warning_reasons:
        health = "Warning"
        reasons = warning_reasons
    else:
        health = "Healthy"
        reasons = ["Tests, state files, database access, and data freshness are healthy."]

    display_versions = {
        field: versions.get(field, state.get(field, "Unavailable"))
        for field in VERSION_FIELDS
    }
    return {
        **display_versions,
        "test_status": "PASS" if tests_valid and test_success else "FAIL",
        "test_total": test_total,
        "test_passed": test_passed,
        "test_failed": test_failed,
        "latest_data_date": latest_data_date,
        "last_state_update": state.get("updated_at"),
        "current_phase": state.get("current_phase"),
        "next_goal": state.get("next_goal"),
        "system_health": health,
        "health_reasons": reasons,
        "state_error": state_error,
        "versions_error": versions_error,
        "database_readable": database_ok,
        "data_age_days": data_age_days,
        "active_p1_count": len(p1_issues),
        "last_sync": last_sync.get("finish_time") if last_sync else None,
        "last_sync_duration": last_sync.get("duration") if last_sync else None,
        "last_sync_success": bool(last_sync.get("success")) if last_sync else None,
        "last_sync_records_imported": (
            last_sync.get("records_imported") if last_sync else None
        ),
        "last_sync_warning_count": sync_warning_count,
        "last_sync_source_warning_count": source_sync_warning_count,
        "last_sync_auxiliary_warning_count": auxiliary_sync_warning_count,
        "local_coach_ready": state.get("local_coach_ready", False),
        "cloud_ai_runtime_ready": state.get("cloud_ai_runtime_ready", False),
        "last_sync_local_coach_records_updated": (
            last_sync.get("local_coach_records_updated") if last_sync else None
        ),
        "last_sync_prospective_eligible_days": (
            last_sync.get("prospective_eligible_days") if last_sync else None
        ),
    }
