"""Local-only personal profile, body status, and target storage."""

from __future__ import annotations

from datetime import date
from typing import Any


GENDERS = ("male", "female", "non_binary", "prefer_not_to_say")
TRAINING_GOALS = ("muscle_gain", "fat_loss", "maintenance")


class PersonalProfileValidationError(ValueError):
    """Raised when personal profile or target input is invalid."""


def calculate_age(birth_date: str | date, today: date | None = None) -> int:
    born = birth_date if isinstance(birth_date, date) else date.fromisoformat(str(birth_date))
    current = today or date.today()
    if born > current:
        raise PersonalProfileValidationError("BIRTH_DATE_IN_FUTURE")
    return current.year - born.year - ((current.month, current.day) < (born.month, born.day))


def _optional_positive(name: str, value: Any, maximum: float | None = None) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    if numeric <= 0 or (maximum is not None and numeric > maximum):
        raise PersonalProfileValidationError(f"INVALID_{name.upper()}")
    return numeric


def get_personal_profile(connection) -> dict[str, Any] | None:
    row = connection.execute("SELECT * FROM personal_profile WHERE id = 1").fetchone()
    return dict(row) if row else None


def save_personal_profile(connection, data: dict[str, Any]) -> None:
    name = str(data.get("name") or "").strip()
    if not name:
        raise PersonalProfileValidationError("NAME_REQUIRED")
    gender = data.get("gender")
    if gender not in GENDERS:
        raise PersonalProfileValidationError("INVALID_GENDER")
    birth_date = str(data.get("birth_date") or "")
    try:
        calculate_age(birth_date)
    except (TypeError, ValueError) as exc:
        raise PersonalProfileValidationError("INVALID_BIRTH_DATE") from exc
    height_cm = _optional_positive("height_cm", data.get("height_cm"), 300)
    if height_cm is None:
        raise PersonalProfileValidationError("HEIGHT_REQUIRED")
    connection.execute(
        """
        INSERT INTO personal_profile(id,name,gender,birth_date,height_cm)
        VALUES(1,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name,
            gender=excluded.gender,
            birth_date=excluded.birth_date,
            height_cm=excluded.height_cm,
            updated_at=CURRENT_TIMESTAMP
        """,
        (name, gender, birth_date, height_cm),
    )
    connection.commit()


def get_personal_goals(connection) -> dict[str, Any] | None:
    row = connection.execute("SELECT * FROM personal_goals WHERE id = 1").fetchone()
    return dict(row) if row else None


def save_personal_goals(connection, data: dict[str, Any]) -> None:
    training_goal = data.get("training_goal") or "maintenance"
    if training_goal not in TRAINING_GOALS:
        raise PersonalProfileValidationError("INVALID_TRAINING_GOAL")
    target_weight = _optional_positive("target_weight_kg", data.get("target_weight_kg"), 500)
    target_body_fat = _optional_positive(
        "target_body_fat_percent", data.get("target_body_fat_percent"), 100,
    )
    target_waist = _optional_positive("target_waist_cm", data.get("target_waist_cm"), 300)
    connection.execute(
        """
        INSERT INTO personal_goals(
            id,training_goal,target_weight_kg,target_body_fat_percent,target_waist_cm
        ) VALUES(1,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            training_goal=excluded.training_goal,
            target_weight_kg=excluded.target_weight_kg,
            target_body_fat_percent=excluded.target_body_fat_percent,
            target_waist_cm=excluded.target_waist_cm,
            updated_at=CURRENT_TIMESTAMP
        """,
        (training_goal, target_weight, target_body_fat, target_waist),
    )
    connection.commit()


def latest_body_measurement(connection) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT * FROM body_measurements
        ORDER BY date DESC, is_primary DESC, id DESC
        LIMIT 1
        """
    ).fetchone()
    return dict(row) if row else None
