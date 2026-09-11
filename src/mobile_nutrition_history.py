"""Versioned, mobile-safe nutrition history projected from the desktop ledger."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .dashboard_data import connect_readonly
from .mobile_snapshot import _mobile_nutrition_summary
from .nutrition_logging import list_meal_records


CONTRACT_KIND = "rhythmos.mobile_nutrition_history"
CONTRACT_VERSION = 1
MAX_DAYS = 28
DEFAULT_DAYS = 28


class MobileNutritionHistoryError(ValueError):
    pass


def build_mobile_nutrition_history(
    db_path: Path | str | None = None,
    *,
    days: int = DEFAULT_DAYS,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build the recent completed nutrition days using desktop calculations."""
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= MAX_DAYS:
        raise MobileNutritionHistoryError(f"days must be between 1 and {MAX_DAYS}")
    connection = connect_readonly(db_path)
    try:
        records = list_meal_records(connection, limit=500)
    finally:
        connection.close()
    dates = sorted({
        str(record["date"])
        for record in records
        if record.get("date") and record.get("status", "completed") == "completed"
    })[-days:]
    entries = []
    for day in dates:
        summary = _mobile_nutrition_summary(db_path, day)
        entries.append({
            "date": day,
            "recorded_meals": summary["recorded_meals"],
            "food_count": summary["food_count"],
            "identified_food_count": summary["identified_food_count"],
            "unidentified_food_count": summary["unidentified_food_count"],
            "energy": summary["energy"],
            "meals": summary["meals"],
        })
    created = generated_at or datetime.now(timezone.utc)
    return {
        "kind": CONTRACT_KIND,
        "version": CONTRACT_VERSION,
        "generated_at": created.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "days": entries,
    }
