"""Publish safe local RHYTHMOS projections through the authenticated Render API."""

from __future__ import annotations

import os
from datetime import date
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

import requests

from .mobile_recovery_history import build_mobile_recovery_history
from .mobile_snapshot import build_mobile_daily_snapshot
from .mobile_training_history import build_mobile_training_history


class CloudProjectionSyncError(RuntimeError):
    """Raised when an explicitly configured desktop cloud sync fails."""


def publish_local_projections(
    *,
    settings: Mapping[str, str | None] | None = None,
    history_days: int = 14,
    source_device: str = "macos-local",
    snapshot_builder: Callable[..., dict[str, Any] | None] = build_mobile_daily_snapshot,
    recovery_history_builder: Callable[..., dict[str, Any]] = build_mobile_recovery_history,
    training_history_builder: Callable[..., dict[str, Any]] = build_mobile_training_history,
    http_post: Callable[..., requests.Response] = requests.post,
) -> dict[str, Any] | None:
    """Publish mobile-safe projections, or do nothing until desktop sync is configured.

    The function deliberately never sends a SQLite database, source screenshots,
    notes, provider tokens, or an iOS/macOS credential.  It only submits the
    existing versioned mobile projections to the Render HTTPS boundary.
    """
    current = dict(settings or {
        "RHYTHMOS_SYNC_SERVICE_URL": os.getenv("RHYTHMOS_SYNC_SERVICE_URL"),
        "MOBILE_SYNC_API_TOKEN": os.getenv("MOBILE_SYNC_API_TOKEN"),
    })
    base_url = current.get("RHYTHMOS_SYNC_SERVICE_URL")
    token = current.get("MOBILE_SYNC_API_TOKEN")
    if not base_url and not token:
        return None
    if not base_url or not token:
        raise CloudProjectionSyncError("desktop cloud sync settings are incomplete")
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise CloudProjectionSyncError("desktop cloud sync URL must use HTTPS")
    if not isinstance(history_days, int) or isinstance(history_days, bool) or not 1 <= history_days <= 30:
        raise ValueError("history_days must be between 1 and 30")
    if not source_device or len(source_device) > 160:
        raise ValueError("invalid cloud source device")

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    endpoint = base_url.rstrip("/") + "/v1/cloud/documents"
    sent: list[tuple[str, str]] = []

    def publish(document_type: str, document_key: str, payload: dict[str, Any]) -> None:
        response = http_post(
            f"{endpoint}/{document_type}/{document_key}",
            headers=headers,
            json={"payload": payload, "source_device": source_device},
            timeout=30,
        )
        if response.status_code != 201:
            raise CloudProjectionSyncError("desktop cloud projection publish failed")
        sent.append((document_type, document_key))

    recovery_history = recovery_history_builder(days=history_days)
    for entry in recovery_history.get("days", []):
        snapshot_date = entry.get("date") if isinstance(entry, dict) else None
        if isinstance(snapshot_date, str):
            snapshot = snapshot_builder(snapshot_date=snapshot_date)
            if isinstance(snapshot, dict):
                publish("daily_snapshot", snapshot_date, snapshot)
    # Empty histories remain meaningful and make removal of stale client state
    # explicit rather than silently retaining an earlier projection.
    publish("recovery_history", f"days:{history_days}", recovery_history)
    publish("training_history", f"days:{history_days}", training_history_builder(days=history_days))
    return {"success": True, "documents_published": len(sent), "history_days": history_days}
