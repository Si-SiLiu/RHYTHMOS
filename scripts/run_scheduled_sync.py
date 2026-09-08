"""LaunchAgent-safe CLI for the existing One-Click Sync Pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import os
import sys


BASE_DIR = Path(__file__).resolve().parents[1]
# launchd cannot directly initialize protected Desktop/Documents paths as its
# WorkingDirectory. The child runner can safely establish the canonical project
# directory after launch, preserving all relative-path behavior.
os.chdir(BASE_DIR)
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.scheduler import TRIGGER_TYPES
from src.scheduler.config import CONFIG_PATH, load_scheduler_config
from src.scheduler.runner import SchedulerRunError, run_triggered_pipeline
from src.cloud_projection_sync import CloudProjectionSyncError, publish_local_projections
from src.cloud_mobile_change_sync import MobileCloudChangeSyncError, pull_mobile_changes


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run the shared sync pipeline from a local scheduler trigger."
    )
    parser.add_argument(
        "--trigger-type",
        choices=TRIGGER_TYPES,
        default="scheduled",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    return parser.parse_args(argv)


def _safe_summary(summary: dict) -> dict:
    allowed = {
        "success",
        "status",
        "trigger_type",
        "scheduler_invocation_id",
        "pipeline_invoked",
        "today_synced",
        "run_id",
        "duration",
        "warning_count",
        "error_code",
        "dry_run",
        "lock_recovered_after_abandonment",
        "cloud_projection_status",
        "cloud_change_pull_status",
    }
    return {key: summary[key] for key in allowed if key in summary}


def _publish_cloud_projection_after_local_sync(*, dry_run: bool) -> str:
    """Publish mobile-safe data without turning a local sync into a failure."""
    if dry_run:
        return "skipped_dry_run"
    try:
        # Use the iOS history span so both recovery and training documents are
        # fresh when the app returns to foreground.
        result = publish_local_projections(history_days=30)
    except (CloudProjectionSyncError, ValueError):
        return "deferred"
    return "published" if result else "not_configured"


def _pull_mobile_changes_before_local_sync(*, dry_run: bool) -> str:
    """Apply iPhone-confirmed writes before rebuilding local projections."""
    if dry_run:
        return "skipped_dry_run"
    try:
        result = pull_mobile_changes()
    except MobileCloudChangeSyncError:
        return "deferred"
    if result is None:
        return "not_configured"
    return "applied" if result.get("changes_applied") else "up_to_date"


def main(argv=None) -> int:
    args = parse_args(argv)
    loaded = load_scheduler_config(args.config)
    if args.trigger_type != "manual" and not loaded.config.enabled:
        print(
            json.dumps(
                {
                    "success": True,
                    "status": "disabled",
                    "trigger_type": args.trigger_type,
                    "pipeline_invoked": False,
                },
                sort_keys=True,
            )
        )
        return 0
    change_pull_status = _pull_mobile_changes_before_local_sync(dry_run=args.dry_run)
    try:
        summary = run_triggered_pipeline(
            args.trigger_type,
            dry_run=args.dry_run,
        )
    except SchedulerRunError as exc:
        print(json.dumps(_safe_summary(exc.summary), sort_keys=True))
        return 2
    if summary.get("pipeline_invoked"):
        summary["cloud_projection_status"] = _publish_cloud_projection_after_local_sync(
            dry_run=args.dry_run
        )
    summary["cloud_change_pull_status"] = change_pull_status
    print(json.dumps(_safe_summary(summary), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
