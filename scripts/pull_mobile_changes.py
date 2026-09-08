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


PUBLISH_STATE_PATH = BASE_DIR / "data" / "local_cloud_publish_state.json"


def local_data_signature() -> list[dict[str, int | str]]:
    """A compact change marker; health data itself never enters this state file."""
    records: list[dict[str, int | str]] = []
    for path in sorted((BASE_DIR / "data").glob("*.db")):
        stat = path.stat()
        records.append({"name": path.name, "mtime_ns": stat.st_mtime_ns, "size": stat.st_size})
    return records


def local_data_changed(signature: list[dict[str, int | str]]) -> bool:
    try:
        previous = json.loads(PUBLISH_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return True
    return previous.get("signature") != signature if isinstance(previous, dict) else True


def save_local_data_signature(signature: list[dict[str, int | str]]) -> None:
    PUBLISH_STATE_PATH.write_text(json.dumps({"signature": signature}, sort_keys=True), encoding="utf-8")


def main() -> int:
    try:
        result = pull_mobile_changes()
    except MobileCloudChangeSyncError:
        print(json.dumps({"status": "deferred"}, sort_keys=True))
        return 0
    if result is None:
        print(json.dumps({"status": "not_configured"}, sort_keys=True))
        return 0
    signature = local_data_signature()
    should_publish = bool(result["changes_applied"]) or local_data_changed(signature)
    if should_publish:
        try:
            publish_local_projections(history_days=30)
        except (CloudProjectionSyncError, ValueError):
            print(json.dumps({"status": "applied_publish_deferred"}, sort_keys=True))
            return 0
        save_local_data_signature(local_data_signature())
        status = "applied_and_published" if result["changes_applied"] else "mac_changes_published"
        print(json.dumps({"status": status}, sort_keys=True))
        return 0
    print(json.dumps({"status": "up_to_date"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
