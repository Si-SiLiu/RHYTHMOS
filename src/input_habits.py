"""Local learning for repeated structured input habits.

Learning stays on-device.  It records completed forms, commonly selected
structured names (such as food or exercise), categorical choices, and numeric
means so the next matching form can be pre-filled.  Free-text notes, symptom
descriptions, questions, and device payloads are never used as defaults.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Mapping
from typing import Any


HABIT_VERSION = "1.0.0"
_MAX_KEYS = 48


def _empty_habits() -> dict[str, Any]:
    return {
        "version": HABIT_VERSION,
        "surfaces": {},
        "fields": {},
        "choices": {},
        "numeric": {},
    }


def _read(connection: sqlite3.Connection) -> tuple[bool, int, dict[str, Any]]:
    row = connection.execute(
        "SELECT enabled,event_count,habits_json FROM user_input_habits WHERE id=1"
    ).fetchone()
    if not row:
        connection.execute("INSERT OR IGNORE INTO user_input_habits(id) VALUES(1)")
        connection.commit()
        return True, 0, _empty_habits()
    try:
        habits = json.loads(row[2] or "{}")
    except (TypeError, json.JSONDecodeError):
        habits = {}
    base = _empty_habits()
    base.update({key: value for key, value in habits.items() if key in base})
    return bool(row[0]), int(row[1] or 0), base


def get_input_habits(connection: sqlite3.Connection) -> dict[str, Any]:
    """Return the local profile, including whether learning is enabled."""
    enabled, event_count, habits = _read(connection)
    return {"enabled": enabled, "event_count": event_count, **habits}


def set_input_habits_enabled(connection: sqlite3.Connection, enabled: bool) -> None:
    connection.execute(
        "UPDATE user_input_habits SET enabled=?,updated_at=CURRENT_TIMESTAMP WHERE id=1",
        (int(bool(enabled)),),
    )
    connection.commit()


def clear_input_habits(connection: sqlite3.Connection) -> None:
    """Delete learned aggregates without touching health or training records."""
    connection.execute(
        "UPDATE user_input_habits SET event_count=0,habits_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=1",
        (json.dumps(_empty_habits(), ensure_ascii=False, sort_keys=True),),
    )
    connection.commit()


def _increment(bucket: dict[str, Any], key: str, amount: int = 1) -> None:
    if not key or len(bucket) >= _MAX_KEYS and key not in bucket:
        return
    bucket[key] = int(bucket.get(key, 0)) + amount


def record_input_habit(
    connection: sqlite3.Connection,
    surface: str,
    *,
    fields: Iterable[str] = (),
    choices: Mapping[str, Any] | None = None,
    numeric: Mapping[str, Any] | None = None,
) -> None:
    """Record one completed form using aggregate-only data."""
    enabled, event_count, habits = _read(connection)
    if not enabled:
        return
    _increment(habits["surfaces"], str(surface).strip())
    for field in fields:
        _increment(habits["fields"], str(field).strip())
    for name, value in (choices or {}).items():
        values = value if isinstance(value, (list, tuple, set)) else (value,)
        choice_bucket = habits["choices"].setdefault(str(name).strip(), {})
        for choice in values:
            if choice in (None, ""):
                continue
            _increment(choice_bucket, str(choice).strip())
    for name, value in (numeric or {}).items():
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number <= 0:
            continue
        bucket = habits["numeric"].setdefault(str(name).strip(), {"count": 0, "sum": 0.0})
        bucket["count"] = int(bucket.get("count", 0)) + 1
        bucket["sum"] = round(float(bucket.get("sum", 0.0)) + number, 4)
    connection.execute(
        "UPDATE user_input_habits SET event_count=?,habits_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=1",
        (event_count + 1, json.dumps(habits, ensure_ascii=False, sort_keys=True)),
    )
    connection.commit()


def bootstrap_input_habits(connection: sqlite3.Connection) -> int:
    """Learn from existing structured history once, without storing raw values."""
    enabled, event_count, _ = _read(connection)
    if not enabled or event_count:
        return 0
    learned = 0
    queries = (
        (
            "SELECT meal_type FROM meal_records WHERE deleted_at IS NULL",
            "nutrition.meal_type",
            "nutrition.history",
        ),
        (
            "SELECT resolved_sport_type AS session_type,duration_seconds FROM training_sessions WHERE deleted_at IS NULL",
            "training.session_type",
            "training.history",
        ),
        (
            "SELECT session_type,duration_minutes,session_rpe FROM workout_sessions",
            "training.session_type",
            "training.legacy_history",
        ),
        (
            "SELECT test_mode FROM neural_assessments WHERE test_mode IS NOT NULL",
            "neural.test_mode",
            "neural.history",
        ),
    )
    for query, choice_name, surface in queries:
        try:
            rows = connection.execute(query).fetchall()
        except sqlite3.OperationalError:
            continue
        for row in rows:
            values = dict(row)
            choice = values.get("meal_type") or values.get("session_type") or values.get("test_mode")
            if choice in {"15", 15}:
                choice = "strength"
            elif choice in {"121", 121}:
                choice = "hiphop"
            elif choice in {"83", 83, "36", 36}:
                choice = "other"
            numeric = {
                key: values.get(key)
                for key in ("duration_minutes", "session_rpe")
                if values.get(key) is not None
            }
            if values.get("duration_seconds") is not None:
                numeric["duration_minutes"] = float(values["duration_seconds"]) / 60
            record_input_habit(
                connection,
                surface,
                choices={choice_name: choice},
                numeric={f"training.{key}": value for key, value in numeric.items()},
            )
            learned += 1
    return learned


def _most_common(habits: dict[str, Any], name: str, minimum_events: int = 2) -> str | None:
    bucket = habits.get("choices", {}).get(name) or {}
    if not bucket:
        return None
    choice, count = max(bucket.items(), key=lambda item: (item[1], item[0]))
    return choice if int(count) >= minimum_events else None


def get_input_habit_defaults(connection: sqlite3.Connection) -> dict[str, Any]:
    """Return conservative defaults learned after at least two repetitions."""
    profile = get_input_habits(connection)
    habits = profile
    defaults: dict[str, Any] = {
        "meal_type": _most_common(habits, "nutrition.meal_type"),
        "training_type": _most_common(habits, "training.session_type"),
    }
    for key, target in (
        ("training.duration_minutes", "training_duration_minutes"),
        ("training.session_rpe", "training_session_rpe"),
        ("training.weight_kg", "training_weight_kg"),
        ("training.reps", "training_reps"),
        ("training.set_count", "training_set_count"),
        ("nutrition.amount", "nutrition_amount"),
        ("neural.mental_fatigue", "neural_mental_fatigue"),
        ("neural.mental_clarity", "neural_mental_clarity"),
        ("neural.task_motivation", "neural_task_motivation"),
        ("neural.physical_heaviness", "neural_physical_heaviness"),
    ):
        bucket = habits.get("numeric", {}).get(key) or {}
        count = int(bucket.get("count", 0))
        if count >= 2:
            defaults[target] = round(float(bucket.get("sum", 0.0)) / count, 1)
    for key, target in (
        ("nutrition.food_name", "nutrition_food_name"),
        ("nutrition.unit", "nutrition_unit"),
        ("training.exercise_name", "training_exercise_name"),
        ("training.exercise_category", "training_exercise_category"),
        ("neural.work_phase", "neural_work_phase"),
        ("personal.training_goal", "personal_training_goal"),
    ):
        value = _most_common(habits, key)
        if value:
            defaults[target] = value
    defaults["event_count"] = profile["event_count"]
    return defaults


def format_input_habit_summary(connection: sqlite3.Connection) -> str | None:
    """Provide a short user-facing explanation without exposing raw data."""
    profile = get_input_habits(connection)
    if not profile["enabled"] or profile["event_count"] < 2:
        return None
    defaults = get_input_habit_defaults(connection)
    parts = []
    if defaults.get("meal_type"):
        meal_labels = {
            "breakfast": "早餐", "morning_snack": "上午加餐", "lunch": "午餐",
            "afternoon_snack": "下午加餐", "dinner": "晚餐", "training_fuel": "训练补给",
            "bedtime_fuel": "睡前补给", "free_snack": "零食",
        }
        parts.append(f"常用餐次：{meal_labels.get(defaults['meal_type'], defaults['meal_type'])}")
    if defaults.get("training_type"):
        training_labels = {"strength": "力量训练", "hiphop": "Hip-Hop", "other": "其它训练"}
        parts.append(f"常用训练：{training_labels.get(defaults['training_type'], defaults['training_type'])}")
    if defaults.get("training_duration_minutes"):
        parts.append(f"常用时长约 {defaults['training_duration_minutes']:g} 分钟")
    return "、".join(parts) if parts else f"已学习 {profile['event_count']} 次输入习惯"
