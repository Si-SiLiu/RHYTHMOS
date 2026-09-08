"""Apply private iOS write events to the local RHYTHMOS database.

The cloud is only a short, authenticated delivery queue.  It does not become
a second desktop database and it never receives Polar credentials or raw
screenshots.  Reapplying an already acknowledged event is avoided locally.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import requests

from .cloud_projection_sync import load_desktop_sync_settings
from .mobile_kubios_import import (
    import_mobile_morning_hrv_measurement,
    import_mobile_screenshot_measurement,
)
from .mobile_nutrition_input import save_mobile_manual_nutrition_entry
from .mobile_nutrition_library import save_mobile_food_label
from .mobile_nutrition_plan_input import save_mobile_nutrition_plan_entry
from .mobile_personal_input import save_mobile_body_measurement, save_mobile_personal_profile


STATE_PATH = Path(__file__).resolve().parents[1] / "data" / "mobile_cloud_change_state.json"
MAX_APPLIED_IDS = 500


class MobileCloudChangeSyncError(RuntimeError):
    """Raised only for a malformed or unreachable explicitly configured inbox."""


def _load_state(path: Path = STATE_PATH) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError, TypeError):
        return []
    values = data.get("applied_ids") if isinstance(data, dict) else None
    return [value for value in values if isinstance(value, str)][-MAX_APPLIED_IDS:] if isinstance(values, list) else []


def _save_state(ids: list[str], path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"applied_ids": ids[-MAX_APPLIED_IDS:]}, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def _apply(kind: str, payload: dict[str, Any]) -> None:
    handlers = {
        "kubios_screenshot": import_mobile_screenshot_measurement,
        "morning_hrv": import_mobile_morning_hrv_measurement,
        "nutrition_entry": save_mobile_manual_nutrition_entry,
        "nutrition_plan_entry": save_mobile_nutrition_plan_entry,
        "personal_profile": save_mobile_personal_profile,
        "body_measurement": save_mobile_body_measurement,
        "food_nutrition_label": save_mobile_food_label,
    }
    handler = handlers.get(kind)
    if handler is None:
        raise MobileCloudChangeSyncError("unsupported mobile cloud change")
    handler(payload)


def pull_mobile_changes(
    *,
    settings: Mapping[str, str | None] | None = None,
    state_path: Path = STATE_PATH,
    http_get: Any = requests.get,
) -> dict[str, int] | None:
    """Apply pending iOS-confirmed changes, returning a safe compact summary."""
    current = dict(settings) if settings is not None else load_desktop_sync_settings()
    base_url = current.get("RHYTHMOS_SYNC_SERVICE_URL")
    token = current.get("MOBILE_SYNC_API_TOKEN")
    if not base_url and not token:
        return None
    if not base_url or not token:
        raise MobileCloudChangeSyncError("desktop cloud sync settings are incomplete")
    try:
        response = http_get(
            base_url.rstrip("/") + "/v1/cloud/changes",
            headers={"Authorization": f"Bearer {token}"},
            params={"limit": "200"}, timeout=30,
        )
    except requests.RequestException as error:
        raise MobileCloudChangeSyncError("mobile cloud change lookup failed") from error
    if response.status_code != 200:
        raise MobileCloudChangeSyncError("mobile cloud change lookup failed")
    try:
        body = response.json()
        changes = body["changes"]
    except (TypeError, ValueError, KeyError) as error:
        raise MobileCloudChangeSyncError("mobile cloud change response is invalid") from error
    if not isinstance(changes, list):
        raise MobileCloudChangeSyncError("mobile cloud change response is invalid")

    applied_ids = _load_state(state_path)
    known_ids = set(applied_ids)
    applied = 0
    for change in changes:
        if not isinstance(change, dict):
            raise MobileCloudChangeSyncError("mobile cloud change item is invalid")
        change_id = change.get("id")
        envelope = change.get("payload")
        if not isinstance(change_id, str) or not isinstance(envelope, dict):
            raise MobileCloudChangeSyncError("mobile cloud change item is invalid")
        if change_id in known_ids:
            continue
        kind = envelope.get("kind")
        payload = envelope.get("payload")
        if not isinstance(kind, str) or not isinstance(payload, dict):
            raise MobileCloudChangeSyncError("mobile cloud change payload is invalid")
        _apply(kind, payload)
        applied_ids.append(change_id)
        known_ids.add(change_id)
        _save_state(applied_ids, state_path)
        applied += 1
    return {"changes_applied": applied, "changes_seen": len(changes)}
