"""Publish safe local RHYTHMOS projections through the authenticated Render API."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

import requests

from .mobile_recovery_history import build_mobile_recovery_history
from .mobile_snapshot import build_mobile_daily_snapshot
from .mobile_training_history import build_mobile_training_history


DEFAULT_SYNC_SERVICE_URL = "https://rhythmos-bk8d.onrender.com"
KEYCHAIN_SERVICE = "RHYTHMOS.mobile-sync-token"
KEYCHAIN_ACCOUNT = "RHYTHMOS desktop sync"


class CloudProjectionSyncError(RuntimeError):
    """Raised when an explicitly configured desktop cloud sync fails."""


def load_desktop_sync_settings(
    *,
    environment: Mapping[str, str | None] | None = None,
    keychain_lookup: Callable[[], str | None] | None = None,
) -> dict[str, str | None]:
    """Read desktop sync credentials without putting the bearer token in a file.

    A developer can still provide both values through process environment for
    automation.  On this Mac, the approved device token lives in the login
    Keychain and the production HTTPS endpoint is used by default.
    """
    source = os.environ if environment is None else environment
    base_url = (source.get("RHYTHMOS_SYNC_SERVICE_URL") or "").strip() or None
    token = (source.get("MOBILE_SYNC_API_TOKEN") or "").strip() or None
    if token is None:
        lookup = keychain_lookup or _load_keychain_token
        token = lookup()
    if token and base_url is None:
        base_url = DEFAULT_SYNC_SERVICE_URL
    return {"RHYTHMOS_SYNC_SERVICE_URL": base_url, "MOBILE_SYNC_API_TOKEN": token}


def _load_keychain_token() -> str | None:
    if sys.platform != "darwin":
        return None
    try:
        result = subprocess.run(
            [
                "security", "find-generic-password", "-w",
                "-a", KEYCHAIN_ACCOUNT,
                "-s", KEYCHAIN_SERVICE,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    token = result.stdout.strip() if result.returncode == 0 else ""
    return token or None


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
    current = dict(settings) if settings is not None else load_desktop_sync_settings()
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
