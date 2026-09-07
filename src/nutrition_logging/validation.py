"""Validation contract for manually entered meal events and category items."""

from __future__ import annotations

from datetime import date, time
from typing import Any
import math
import re

from .supplements import validate_supplement


class NutritionEventValidationError(ValueError):
    """Raised when a meal event violates the normalized local contract."""


MEAL_TYPES = (
    "breakfast", "morning_snack", "lunch", "afternoon_snack", "dinner",
    "training_fuel", "bedtime_fuel", "free_snack",
)
# The editor is organised by the user's ordinal meals. ``meal_type`` remains
# a nutritional classification so historical summaries remain compatible.
INITIAL_MEAL_SLOTS = ("meal_1", "meal_2", "meal_3")
_MEAL_SLOT_RE = re.compile(r"^meal_([1-9]\d*)$")


def is_meal_slot(value: str) -> bool:
    """A numbered meal has no upper bound: meal_1, meal_2, …"""
    return bool(_MEAL_SLOT_RE.fullmatch(str(value or "")))


def meal_slot_number(value: str) -> int:
    match = _MEAL_SLOT_RE.fullmatch(str(value or ""))
    if not match:
        raise ValueError("INVALID_MEAL_SLOT")
    return int(match.group(1))


def meal_type_for_slot(meal_slot: str, actual_meal_time: str) -> str:
    """Classify a numbered meal from its actual time."""
    if not is_meal_slot(meal_slot):
        raise ValueError("INVALID_MEAL_SLOT")
    try:
        clock = time.fromisoformat(str(actual_meal_time))
    except (TypeError, ValueError) as exc:
        raise ValueError("INVALID_MEAL_DATE_OR_TIME") from exc
    minute = clock.hour * 60 + clock.minute
    if meal_slot == "meal_1" and minute < 9 * 60:
        return "breakfast"
    if 12 * 60 <= minute < 14 * 60:
        return "lunch"
    if 17 * 60 <= minute < 20 * 60:
        return "dinner"
    return {1: "breakfast", 2: "lunch", 3: "dinner"}.get(
        meal_slot_number(meal_slot), "free_snack",
    )


def inferred_meal_slot(meal_type: str, actual_meal_time: str | None = None) -> str:
    """Give historical records a stable numbered-meal slot on first read."""
    if meal_type == "breakfast":
        return "meal_1"
    if meal_type == "lunch":
        return "meal_2"
    if meal_type == "dinner":
        return "meal_3"
    if actual_meal_time:
        try:
            return next(slot for slot in INITIAL_MEAL_SLOTS if meal_type_for_slot(slot, actual_meal_time) == meal_type)
        except (ValueError, StopIteration):
            pass
    # Historical snacks and fuel entries do not have a numbered equivalent;
    # retain them as the first extensible slot after the three core meals.
    return "meal_4"
CORE_CATEGORIES = (
    "carbohydrate", "protein", "fat", "vegetable", "fruit", "dairy", "nuts",
)
EXTENDED_CATEGORIES = ("supplement", "hydration", "caffeine", "alcohol")
CATEGORIES = CORE_CATEGORIES + EXTENDED_CATEGORIES
EXTENDED_MEALS = {
    "breakfast", "morning_snack", "lunch", "afternoon_snack", "dinner",
}
FIXED_UNITS = {
    **{category: "g" for category in CORE_CATEGORIES + ("caffeine",)},
    "hydration": "ml", "alcohol": "ml",
}
NAME_OPTIONAL = {"hydration", "caffeine", "alcohol"}


def categories_for_meal(meal_type: str) -> tuple[str, ...]:
    return CATEGORIES if meal_type in EXTENDED_MEALS else CORE_CATEGORIES


def validate_meal_event(event: dict[str, Any], items: list[dict[str, Any]]) -> None:
    try:
        date.fromisoformat(str(event.get("date")))
    except (TypeError, ValueError) as exc:
        raise NutritionEventValidationError("INVALID_MEAL_DATE") from exc
    meal_type = event.get("meal_type")
    if meal_type not in MEAL_TYPES:
        raise NutritionEventValidationError("INVALID_MEAL_TYPE")
    try:
        time.fromisoformat(str(event.get("actual_meal_time")))
    except (TypeError, ValueError) as exc:
        raise NutritionEventValidationError("INVALID_ACTUAL_MEAL_TIME") from exc

    allowed = set(categories_for_meal(meal_type))
    seen: set[tuple[str, int]] = set()
    counts: dict[str, int] = {}
    for item in items:
        category = item.get("category")
        if category not in allowed:
            raise NutritionEventValidationError("CATEGORY_NOT_ALLOWED_FOR_MEAL")
        try:
            position = int(item.get("position"))
        except (TypeError, ValueError) as exc:
            raise NutritionEventValidationError("INVALID_ITEM_POSITION") from exc
        if not 1 <= position <= 5 or (category, position) in seen:
            raise NutritionEventValidationError("INVALID_ITEM_POSITION")
        seen.add((category, position)); counts[category] = counts.get(category, 0) + 1
        if counts[category] > 5:
            raise NutritionEventValidationError("TOO_MANY_ITEMS_IN_CATEGORY")
        if category not in NAME_OPTIONAL and not str(item.get("item_name") or "").strip():
            raise NutritionEventValidationError("ITEM_NAME_REQUIRED")
        try:
            quantity = float(item.get("quantity"))
        except (TypeError, ValueError) as exc:
            raise NutritionEventValidationError("INVALID_ITEM_QUANTITY") from exc
        if not math.isfinite(quantity) or quantity <= 0:
            raise NutritionEventValidationError("INVALID_ITEM_QUANTITY")
        if category == "supplement":
            try:
                validate_supplement(item)
            except ValueError as exc:
                raise NutritionEventValidationError(str(exc)) from exc
            continue
        unit = item.get("unit")
        fixed = FIXED_UNITS.get(category)
        if fixed and unit != fixed:
            raise NutritionEventValidationError("INVALID_ITEM_UNIT_FOR_CATEGORY")
