"""LaunchAgent entry point for private iOS-to-macOS RHYTHMOS changes."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
os.chdir(BASE_DIR)
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.cloud_mobile_change_sync import MobileCloudChangeSyncError, pull_mobile_changes
from src.cloud_projection_sync import CloudProjectionSyncError, publish_local_projections


def main() -> int:
    try:
        result = pull_mobile_changes()
    except MobileCloudChangeSyncError:
        print(json.dumps({"status": "deferred"}, sort_keys=True))
        return 0
    if result is None:
        print(json.dumps({"status": "not_configured"}, sort_keys=True))
        return 0
    if result["changes_applied"]:
        try:
            publish_local_projections(history_days=30)
        except (CloudProjectionSyncError, ValueError):
            print(json.dumps({"status": "applied_publish_deferred"}, sort_keys=True))
            return 0
        print(json.dumps({"status": "applied_and_published"}, sort_keys=True))
        return 0
    print(json.dumps({"status": "up_to_date"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
