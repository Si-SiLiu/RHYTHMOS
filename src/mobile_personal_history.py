"""Versioned, mobile-safe body-measurement history projection."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from typing import Any

from .dashboard_data import connect_readonly


CONTRACT_KIND = "rhythmos.mobile_personal_history"
CONTRACT_VERSION = 1
# Personal trends use the same rolling 28-day baseline as recovery, sleep,
# nutrition, and training. The window ends on the latest body measurement.
MAX_DAYS = 28
DEFAULT_DAYS = 28


class MobilePersonalHistoryError(ValueError):
    pass


def build_mobile_personal_history(
    db_path: Path | str | None = None,
    *,
    days: int = DEFAULT_DAYS,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Return one latest approved body record per date in the requested window.

    No database identifier, notes, or profile fields are projected. When a
    date has multiple records, the same primary-then-latest ordering used by
    the desktop overview selects its representative trend point.
    """
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= MAX_DAYS:
        raise MobilePersonalHistoryError(f"days must be between 1 and {MAX_DAYS}")
    connection = connect_readonly(db_path)
    try:
        try:
            rows = connection.execute(
                """SELECT date,weight_kg,body_fat_percent,waist_cm
                   FROM body_measurements
                   ORDER BY date DESC,is_primary DESC,id DESC"""
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
    finally:
        connection.close()

    seen_dates: set[str] = set()
    points: list[dict[str, Any]] = []
    latest_measurement_date = date.fromisoformat(str(rows[0]["date"])) if rows else None
    window_start = latest_measurement_date - timedelta(days=days - 1) if latest_measurement_date else None
    for row in rows:
        day = str(row["date"])
        if window_start and date.fromisoformat(day) < window_start:
            break
        if day in seen_dates:
            continue
        seen_dates.add(day)
        points.append({
            "date": day,
            "weight_kg": row["weight_kg"],
            "body_fat_percent": row["body_fat_percent"],
            "waist_cm": row["waist_cm"],
        })
        if len(points) == days:
            break
    created = generated_at or datetime.now(timezone.utc)
    return {
        "kind": CONTRACT_KIND,
        "version": CONTRACT_VERSION,
        "generated_at": created.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "days": list(reversed(points)),
    }
