"""Validated iPhone writes for the desktop-owned personal profile."""

from __future__ import annotations

import math
from datetime import date
from typing import Any

from .db import connect
from .personal_logging.storage import create_body_measurement
from .personal_profile import PersonalProfileValidationError, save_personal_profile


class MobilePersonalInputError(ValueError):
    """A mobile personal-profile payload failed validation."""


def _number(value: Any, field: str, *, required: bool, minimum: float, maximum: float) -> float | None:
    if value in (None, ""):
        if required:
            raise MobilePersonalInputError(f"{field.upper()}_REQUIRED")
        return None
    if isinstance(value, bool):
        raise MobilePersonalInputError(f"INVALID_{field.upper()}")
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise MobilePersonalInputError(f"INVALID_{field.upper()}") from error
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise MobilePersonalInputError(f"INVALID_{field.upper()}")
    return result


def save_mobile_personal_profile(
    payload: dict[str, Any], *, db_path: str | None = None,
) -> dict[str, str]:
    """Save the iPhone's reviewed basic information into the desktop profile."""
    if not isinstance(payload, dict):
        raise MobilePersonalInputError("INVALID_PROFILE_PAYLOAD")
    try:
        profile = {
            "name": str(payload.get("name") or "").strip(),
            "gender": str(payload.get("gender") or "").strip(),
            "birth_date": date.fromisoformat(str(payload.get("birth_date") or "")).isoformat(),
            "height_cm": _number(payload.get("height_cm"), "height_cm", required=True, minimum=50, maximum=300),
        }
    except (TypeError, ValueError) as error:
        raise MobilePersonalInputError("INVALID_PROFILE_PAYLOAD") from error
    connection = connect(db_path)
    try:
        save_personal_profile(connection, profile)
    except PersonalProfileValidationError as error:
        raise MobilePersonalInputError(str(error)) from error
    finally:
        connection.close()
    return {"date": date.today().isoformat()}


def save_mobile_body_measurement(
    payload: dict[str, Any], *, db_path: str | None = None,
) -> dict[str, str]:
    """Append an explicitly reviewed iPhone body measurement to desktop history."""
    if not isinstance(payload, dict):
        raise MobilePersonalInputError("INVALID_BODY_PAYLOAD")
    try:
        measurement_date = date.fromisoformat(str(payload.get("date") or ""))
    except (TypeError, ValueError) as error:
        raise MobilePersonalInputError("INVALID_BODY_DATE") from error
    if measurement_date > date.today():
        raise MobilePersonalInputError("INVALID_BODY_DATE")
    measurement = {
        "date": measurement_date.isoformat(),
        "height_cm": _number(payload.get("height_cm"), "height_cm", required=True, minimum=50, maximum=300),
        "weight_kg": _number(payload.get("weight_kg"), "weight_kg", required=True, minimum=1, maximum=500),
        "body_fat_percent": _number(payload.get("body_fat_percent"), "body_fat_percent", required=False, minimum=0, maximum=100),
        "waist_cm": _number(payload.get("waist_cm"), "waist_cm", required=False, minimum=1, maximum=300),
        "is_primary": True,
        "notes": "__mobile_body_measurement__",
    }
    connection = connect(db_path)
    try:
        # Body history is intentionally append-only: each approved mobile save
        # remains a dated observation instead of overwriting a Mac entry.
        create_body_measurement(connection, measurement)
    except ValueError as error:
        raise MobilePersonalInputError(str(error)) from error
    finally:
        connection.close()
    return {"date": date.today().isoformat()}
