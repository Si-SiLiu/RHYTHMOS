"""Validated iPhone manual-nutrition input backed by the desktop meal store."""

from __future__ import annotations

from datetime import date, time
from typing import Any

from .db import connect
from .nutrition_logging import (
    MEAL_TYPES,
    create_meal_record,
    inferred_meal_slot,
    is_meal_slot,
    meal_type_for_slot,
    soft_delete_meal_record,
)


_NUTRIENTS = (
    "calories_kcal", "protein_g", "carbohydrate_g", "fat_g", "fiber_g", "water_ml",
)
_MARKER_PREFIX = "__mobile_manual_nutrition__:"
_MAX_FOOD_ITEMS = 5


class MobileNutritionInputError(ValueError):
    """Raised for a rejected manual nutrition entry without database detail."""


def _number(value: Any, field: str) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise MobileNutritionInputError(f"INVALID_{field.upper()}")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise MobileNutritionInputError(f"INVALID_{field.upper()}") from error
    if number < 0:
        raise MobileNutritionInputError(f"INVALID_{field.upper()}")
    return round(number, 2)


def _entry_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Accept the desktop-style multi-food payload and the older one-row form."""
    raw_items = payload.get("items")
    if raw_items is None:
        raw_items = [payload]
    if not isinstance(raw_items, list) or not 1 <= len(raw_items) <= _MAX_FOOD_ITEMS:
        raise MobileNutritionInputError("INVALID_NUTRITION_ITEMS")

    items: list[dict[str, Any]] = []
    for position, raw in enumerate(raw_items, start=1):
        if not isinstance(raw, dict):
            raise MobileNutritionInputError("INVALID_NUTRITION_ITEM")
        food_name = str(raw.get("food_name") or "").strip()
        if not food_name or len(food_name) > 120:
            raise MobileNutritionInputError("INVALID_NUTRITION_FOOD_NAME")
        amount = _number(raw.get("amount"), "nutrition_amount")
        if amount is None or amount <= 0:
            raise MobileNutritionInputError("INVALID_NUTRITION_AMOUNT")
        unit = str(raw.get("unit") or "").strip()
        if not unit or len(unit) > 20:
            raise MobileNutritionInputError("INVALID_NUTRITION_UNIT")
        nutrients = {field: _number(raw.get(field), field) for field in _NUTRIENTS}
        if not any(value is not None for value in nutrients.values()):
            raise MobileNutritionInputError("NUTRITION_VALUE_REQUIRED")
        items.append({
            "position": position, "food_name": food_name, "amount": amount,
            "unit": unit, "nutrients": nutrients,
        })
    return items


def save_mobile_manual_nutrition_entry(
    payload: dict[str, Any], *, db_path: str | None = None,
) -> dict[str, str]:
    """Replace today's one mobile-authored manual nutrient entry.

    This is a normal imported meal record, so the desktop Nutrition page
    includes it in the same daily totals. Only earlier iPhone-authored records
    with the explicit marker are replaced; desktop meals stay untouched.
    """
    if not isinstance(payload, dict):
        raise MobileNutritionInputError("INVALID_NUTRITION_PAYLOAD")
    try:
        day = date.fromisoformat(str(payload.get("date"))).isoformat()
        eaten_at = time.fromisoformat(str(payload.get("eaten_at") or "")).isoformat(timespec="seconds")
    except (TypeError, ValueError) as error:
        raise MobileNutritionInputError("INVALID_NUTRITION_DATE_OR_TIME") from error
    supplied_type = str(payload.get("meal_type") or "").strip()
    supplied_slot = str(payload.get("meal_slot") or "").strip()
    if supplied_slot:
        if not is_meal_slot(supplied_slot):
            raise MobileNutritionInputError("INVALID_NUTRITION_MEAL_SLOT")
        meal_slot = supplied_slot
        meal_type = meal_type_for_slot(meal_slot, eaten_at)
    elif supplied_type in MEAL_TYPES:
        meal_type = supplied_type
        meal_slot = inferred_meal_slot(meal_type, eaten_at)
    else:
        raise MobileNutritionInputError("INVALID_NUTRITION_MEAL_TYPE")
    items = _entry_items(payload)

    marker = f"{_MARKER_PREFIX}{day}:{meal_slot}"
    connection = connect(db_path)
    try:
        rows = connection.execute(
            "SELECT id FROM meal_records WHERE notes=? AND deleted_at IS NULL", (marker,)
        ).fetchall()
        for row in rows:
            soft_delete_meal_record(connection, int(row["id"]))
        record_id = create_meal_record(connection, {
            "date": day, "meal_type": meal_type, "meal_slot": meal_slot,
            "eaten_at": eaten_at, "actual_meal_time": eaten_at,
            "status": "completed", "source": "manual", "notes": marker,
        }, [{
            "custom_food_name": item["food_name"], "quantity": item["amount"],
            "unit": item["unit"], "item_type": "food", "user_confirmed": True,
        } for item in items])
        saved_items = connection.execute(
            "SELECT id FROM meal_items WHERE meal_record_id=? AND deleted_at IS NULL ORDER BY id",
            (record_id,),
        ).fetchall()
        for saved, item in zip(saved_items, items):
            connection.execute(
                """UPDATE meal_items SET calories_kcal=?,protein_g=?,carbohydrate_g=?,fat_g=?,fiber_g=?,water_ml=?,
                       nutrition_source='mobile_manual',classification_source='user',user_confirmed=1
                   WHERE id=?""",
                (*[item["nutrients"][field] for field in _NUTRIENTS], saved["id"]),
            )
        connection.commit()
    finally:
        connection.close()
    return {"date": day}
