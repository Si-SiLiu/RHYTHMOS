"""Versioned, mobile-safe objective recovery and sleep history projection."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .dashboard_data import connect_readonly
from .mobile_snapshot import build_mobile_daily_snapshot


CONTRACT_KIND = "rhythmos.mobile_recovery_history"
CONTRACT_VERSION = 1
# Recovery readiness is calibrated from the most recent 28 daily records.  Keep
# the mobile history contract within that same window so a longer list cannot
# imply a different personal baseline.
MAX_DAYS = 28
DEFAULT_DAYS = 28


class MobileRecoveryHistoryError(ValueError):
    pass


def build_mobile_recovery_history(
    db_path: Path | str | None = None,
    *,
    days: int = DEFAULT_DAYS,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= MAX_DAYS:
        raise MobileRecoveryHistoryError(f"days must be between 1 and {MAX_DAYS}")
    connection = connect_readonly(db_path)
    try:
        rows = connection.execute(
            """SELECT log_date FROM (
                   SELECT date AS log_date FROM daily_recovery_metrics
                   UNION SELECT date FROM recovery_scores
                   UNION SELECT date FROM kubios_morning_hrv_raw
                   UNION SELECT date FROM polar_sleep_raw
                   UNION SELECT date FROM polar_nightly_recharge_raw
                   UNION SELECT sleep_date FROM manual_sleep_logs
               ) ORDER BY log_date DESC LIMIT ?""",
            (days,),
        ).fetchall()
    finally:
        connection.close()

    entries: list[dict[str, Any]] = []
    for row in reversed(rows):
        snapshot = build_mobile_daily_snapshot(db_path, row[0])
        if snapshot is None:
            continue
        recovery = snapshot["recovery"]
        sleep = snapshot["sleep"]
        entries.append({
            "date": snapshot["date"],
            "status": recovery["status"],
            "score": recovery["score"],
            "confidence_level": (recovery["confidence"] or {}).get("level"),
            "morning_hrv_rmssd_ms": recovery["morning_hrv_rmssd_ms"],
            "morning_resting_hr_bpm": recovery["morning_resting_hr_bpm"],
            # Keep the same permitted, resolved Kubios detail fields as the
            # daily projection. This lets a historical date show the same
            # recovery evidence as today's date without exposing raw samples.
            "details": recovery["details"],
            "sleep_duration_minutes": sleep["duration_minutes"],
            "sleep_score": sleep["score"],
            # Historical sleep rows use exactly the same safe daily sleep
            # projection as the "今日睡眠数据" disclosure. This keeps fields,
            # sources, and missing-value semantics consistent by date.
            "sleep_details": sleep,
        })
    created = generated_at or datetime.now(timezone.utc)
    return {
        "kind": CONTRACT_KIND,
        "version": CONTRACT_VERSION,
        "generated_at": created.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "days": entries,
    }
