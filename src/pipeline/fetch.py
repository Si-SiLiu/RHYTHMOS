from datetime import date, datetime, timedelta
import hashlib
from pathlib import Path

try:
    from src.polar_fetch import (
        fetch_and_save_result,
        fetch_continuous_heart_rate_for_dates,
        fetch_nightly_recharge_with_samples,
        fetch_sleep_details,
        sleep_dates,
    )
except ImportError:
    from polar_fetch import (
        fetch_and_save_result,
        fetch_continuous_heart_rate_for_dates,
        fetch_nightly_recharge_with_samples,
        fetch_sleep_details,
        sleep_dates,
    )

from . import token as token_step
from .errors import PipelineStepError

try:
    from src.polar_client import RAW_DIR
except ImportError:
    from polar_client import RAW_DIR


DATASETS = (
    "profile",
    "sports",
    "daily_activity",
    "training",
    "sleep",
    "nightly_recharge",
    "continuous_heart_rate",
    "cardio_load",
)
SCHEDULED_DATASETS = (
    "daily_activity",
    "training",
    "sleep",
    "nightly_recharge",
    "continuous_heart_rate",
)
SCHEDULED_HOURS = (12, 18, 23)
ROUTINE_SLEEP_HISTORY_DAYS = 7

SNAPSHOT_FILES = tuple(
    f"polar_{name}.json"
    for name in (
        "sports", "daily_activity", "training_sessions", "sleep", "nightly_recharge",
        "continuous_heart_rate", "cardio_load",
    )
)


def scheduled_dataset_names(now: datetime | None = None) -> tuple[str, ...]:
    """Return the complete health refresh set at each fixed daily slot."""
    current = now or datetime.now().astimezone()
    if current.hour not in SCHEDULED_HOURS:
        return ()
    return SCHEDULED_DATASETS


def source_snapshot(raw_dir=RAW_DIR):
    digest = hashlib.sha256()
    found = False
    for filename in SNAPSHOT_FILES:
        path = Path(raw_dir) / filename
        if path.is_file():
            found = True
            digest.update(filename.encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest() if found else None


def _item_count(value):
    if isinstance(value, list):
        return len(value)
    return 1 if value else 0


def run(context, dry_run=False, today=None, raw_dir=RAW_DIR):
    current_day = today or date.today()
    from_date = (current_day - timedelta(days=27)).isoformat()
    # Initial/manual runs rebuild the full baseline window. Scheduled and
    # app-open runs only need recent nights to capture late Polar updates;
    # historical rows already imported locally remain intact.
    sleep_history_days = (
        ROUTINE_SLEEP_HISTORY_DAYS
        if context.get("trigger_type") in {"scheduled", "catch_up"}
        else 59
    )
    sleep_history_from_date = (current_day - timedelta(days=sleep_history_days)).isoformat()
    to_date = current_day.isoformat()
    if dry_run:
        return {"datasets_checked": len(DATASETS), "items_fetched": 0}

    before_snapshot = source_snapshot(raw_dir)

    if "polar_client" not in context:
        token_step.run(context, dry_run=False)
    client = context["polar_client"]
    fetched_sleep_dates = []

    def sleep_fetcher():
        payload = fetch_sleep_details(
            client,
            from_date=sleep_history_from_date,
            to_date=to_date,
            ensure_date=to_date,
        )
        fetched_sleep_dates[:] = sleep_dates(payload)
        return payload

    fetchers = (
        ("profile", "Profile", "polar_user_account.json", client.get_user_account_info, True, False),
        ("sports", "Sports", "polar_sports.json", client.get_sports, False, True),
        (
            "daily_activity",
            "Daily activity",
            "polar_daily_activity.json",
            lambda: client.get_daily_activity_v3(from_date=from_date, to_date=to_date),
            True, False,
        ),
        (
            "training",
            "Training",
            "polar_training_sessions.json",
            lambda: client.get_training_sessions(from_date=from_date, to_date=to_date),
            True, False,
        ),
        (
            "sleep",
            "Sleep",
            "polar_sleep.json",
            sleep_fetcher,
            True, False,
        ),
        (
            "nightly_recharge",
            "Nightly Recharge",
            "polar_nightly_recharge.json",
            lambda: fetch_nightly_recharge_with_samples(
                client, from_date=sleep_history_from_date, to_date=to_date,
                sample_dates=fetched_sleep_dates,
            ),
            True, False,
        ),
        (
            "continuous_heart_rate",
            "Continuous HR",
            "polar_continuous_heart_rate.json",
            lambda: fetch_continuous_heart_rate_for_dates(client, fetched_sleep_dates),
            False, False,
        ),
        ("cardio_load", "Cardio load", "polar_cardio_load.json", client.get_cardio_load, False, False),
    )
    if context.get("trigger_type") == "scheduled":
        allowed = set(scheduled_dataset_names())
        fetchers = tuple(item for item in fetchers if item[0] in allowed)
        if not fetchers:
            return {
                "datasets_checked": 0,
                "items_fetched": 0,
                "scheduled_noop": True,
                "reason": "scheduled_window_closed",
            }
    endpoint_results = []
    for name, label, filename, fetcher, required, preserve_existing in fetchers:
        result = fetch_and_save_result(
            label, filename, fetcher,
            preserve_existing_on_error=preserve_existing,
        )
        count = _item_count(result["data"])
        if result["ok"]:
            status = "success"
        elif required:
            status = "failure"
        elif name == "cardio_load" and result["status_code"] == 404:
            # Polar's Cardio Load endpoint is not available to this account and
            # its raw response is not consumed by any current RHYTHMOS metric.
            # Preserve the capability result without reporting each routine
            # sync as degraded. Other optional endpoint failures still remain
            # explicit warnings for review.
            status = "unavailable"
        else:
            status = "warning"
        endpoint_results.append(
            {
                "endpoint": name,
                "status": status,
                "required": required,
                "status_code": result["status_code"],
                "items": count,
            }
        )

    failures = [item for item in endpoint_results if item["status"] == "failure"]
    warnings = [
        f"OPTIONAL_ENDPOINT_UNAVAILABLE:{item['endpoint']}:{item['status_code']}"
        for item in endpoint_results
        if item["status"] == "warning"
    ]
    if failures:
        failed_names = ",".join(item["endpoint"] for item in failures)
        raise PipelineStepError(
            "FETCH_REQUIRED_ENDPOINT_FAILED",
            f"Required Polar endpoint(s) failed: {failed_names}. Resume after the endpoint is available.",
        )
    after_snapshot = source_snapshot(raw_dir)
    return {
        "datasets_checked": len(endpoint_results),
        "items_fetched": sum(item["items"] for item in endpoint_results),
        "endpoint_results": endpoint_results,
        "warnings": warnings,
        "warning_count": len(warnings),
        "source_changed": before_snapshot is None or before_snapshot != after_snapshot,
    }
