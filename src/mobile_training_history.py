"""Versioned, mobile-safe training history resolved by the desktop database."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .domain_dashboard_data import get_training_history


CONTRACT_KIND = "rhythmos.mobile_training_history"
CONTRACT_VERSION = 1
MAX_DAYS = 28


class MobileTrainingHistoryError(ValueError):
    pass


def _finite_number(value: Any, *, minimum: float | None = None) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or (minimum is not None and value < minimum):
        return None
    return value


def _session_projection(session: dict[str, Any]) -> dict[str, Any]:
    """Return only display-safe fields; never expose record IDs, notes, or raw payloads."""
    return {
        "source": "polar" if session.get("polar_external_id") else "manual",
        "sport": session.get("sport") if isinstance(session.get("sport"), str) else None,
        "polar_sport": session.get("polar_sport") if isinstance(session.get("polar_sport"), str) else None,
        "start_time": session.get("start_time") if isinstance(session.get("start_time"), str) else None,
        "duration_minutes": _finite_number(session.get("duration_minutes"), minimum=0),
        "calories_kcal": _finite_number(session.get("calories"), minimum=0),
        "average_hr_bpm": _finite_number(session.get("average_hr_bpm"), minimum=0),
        "maximum_hr_bpm": _finite_number(session.get("maximum_hr_bpm"), minimum=0),
        "distance_meters": _finite_number(session.get("distance_m"), minimum=0),
        "fat_burn_percentage": _finite_number(session.get("fat_percentage"), minimum=0),
        "session_rpe": _finite_number(session.get("session_rpe"), minimum=0),
    }


def build_mobile_training_history(
    db_path: Path | str | None = None,
    *,
    days: int = 28,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build recent training days using the desktop's canonical resolved projection."""
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= MAX_DAYS:
        raise MobileTrainingHistoryError(f"days must be between 1 and {MAX_DAYS}")

    entries: list[dict[str, Any]] = []
    # ``get_training_history`` is newest first; send chronological data so the
    # client can use it directly for trends and reverse it for the activity list.
    for training in reversed(get_training_history(db_path, limit=days)):
        sessions = [
            _session_projection(session)
            for session in training.get("sessions", [])
            if not session.get("pending_link")
        ]
        start_times = sorted(session["start_time"] for session in sessions if session["start_time"])
        distances = [session["distance_meters"] for session in sessions if session["distance_meters"] is not None]
        polar_sports = list(dict.fromkeys(
            session["polar_sport"] for session in sessions if session["polar_sport"]
        ))
        entries.append({
            "date": training["date"],
            "session_count": len(sessions),
            "start_time": start_times[0] if start_times else None,
            "duration_minutes": _finite_number(training.get("duration_minutes"), minimum=0),
            "calories_kcal": _finite_number(training.get("calories"), minimum=0),
            "average_hr_bpm": _finite_number(training.get("average_hr_bpm"), minimum=0),
            "maximum_hr_bpm": _finite_number(training.get("maximum_hr_bpm"), minimum=0),
            "distance_meters": sum(distances) if distances else None,
            "sports": [sport for sport in training.get("sports", []) if isinstance(sport, str) and sport],
            "polar_sports": polar_sports,
            "sessions": sessions,
        })

    created = generated_at or datetime.now(timezone.utc)
    return {
        "kind": CONTRACT_KIND,
        "version": CONTRACT_VERSION,
        "generated_at": created.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "days": entries,
    }
