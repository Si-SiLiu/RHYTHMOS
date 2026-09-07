"""Read-only, per-exercise strength-progress calculations."""

from __future__ import annotations

from collections import defaultdict

from src.training_logging.summary import LB_TO_KG, VOLUME_SET_TYPES


ESTIMATED_1RM_REP_LIMIT = 12


def _exercise_name(exercise, catalog_names):
    """Resolve the stable display name stored for an exercise."""
    return str(
        catalog_names.get(exercise.get("exercise_catalog_id"))
        or exercise.get("custom_exercise_name")
        or ""
    ).strip()


def _load_in_kg(set_item):
    """Return a comparable external load in kilograms, if one was recorded."""
    load = set_item.get("load_value")
    if load in (None, ""):
        return None
    try:
        load = float(load)
    except (TypeError, ValueError):
        return None
    if load < 0:
        return None
    if set_item.get("load_unit") == "kg":
        return load
    if set_item.get("load_unit") == "lb":
        return load * LB_TO_KG
    return None


def strength_progress_records(sessions, *, catalog_names=None):
    """Aggregate completed, comparable strength work into daily action records.

    The result intentionally keeps actions separate: kilograms, estimated 1RM,
    and volume from different movements must never be combined into one trend.
    Multiple sessions containing the same action on one date are merged so the
    chart has one unambiguous point per day.
    """
    catalog_names = catalog_names or {}
    grouped = defaultdict(lambda: {
        "max_load_kg": None,
        "estimated_1rm_kg": None,
        "volume_kg": 0.0,
        "working_set_count": 0,
    })
    for session in sessions or []:
        if session.get("status") != "completed":
            continue
        session_date = str(session.get("date") or "").strip()
        if not session_date:
            continue
        for exercise in session.get("exercises") or []:
            name = _exercise_name(exercise, catalog_names)
            if not name:
                continue
            record = grouped[(name, session_date)]
            for set_item in exercise.get("sets") or []:
                if not set_item.get("completed"):
                    continue
                if set_item.get("set_type") not in VOLUME_SET_TYPES:
                    continue
                load_kg = _load_in_kg(set_item)
                reps = set_item.get("reps")
                try:
                    reps = int(reps)
                except (TypeError, ValueError):
                    continue
                if load_kg is None or load_kg <= 0 or reps <= 0:
                    continue
                record["max_load_kg"] = max(record["max_load_kg"] or 0.0, load_kg)
                record["volume_kg"] += load_kg * reps
                record["working_set_count"] += 1
                if reps <= ESTIMATED_1RM_REP_LIMIT:
                    estimated_1rm = load_kg * (1 + reps / 30)
                    record["estimated_1rm_kg"] = max(
                        record["estimated_1rm_kg"] or 0.0,
                        estimated_1rm,
                    )
    return [
        {
            "exercise": name,
            "date": session_date,
            "max_load_kg": round(values["max_load_kg"], 2),
            "estimated_1rm_kg": (
                round(values["estimated_1rm_kg"], 2)
                if values["estimated_1rm_kg"] is not None else None
            ),
            "volume_kg": round(values["volume_kg"], 2),
            "working_set_count": values["working_set_count"],
        }
        for (name, session_date), values in sorted(
            grouped.items(), key=lambda item: (item[0][0], item[0][1])
        )
        if values["max_load_kg"] is not None
    ]


def filter_strength_progress_records(records, exercise, *, start_date=None):
    """Return one action's history, optionally starting at an ISO date."""
    return [
        record for record in records or []
        if record.get("exercise") == exercise
        and (start_date is None or record.get("date", "") >= start_date)
    ]
