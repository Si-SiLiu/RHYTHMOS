"""Validated iPhone edits for the desktop weekly nutrition-plan grid."""

from __future__ import annotations

from datetime import date, time, timedelta
import json
import math
from typing import Any
from uuid import uuid4

from .db import connect


class MobileNutritionPlanInputError(ValueError):
    """Raised when an iPhone plan-cell edit cannot be applied safely."""


_MEAL_SLOTS = {
    "breakfast", "morning_snack", "lunch", "afternoon_snack", "dinner", "evening_snack",
}
_MARKER = "__nutrition_manual_recipe__"


def save_mobile_nutrition_plan_cycle(
    payload: dict[str, Any], *, db_path: str | None = None,
) -> dict[str, str]:
    """Edit the same cycle name and date range exposed by the desktop app."""
    if not isinstance(payload, dict):
        raise MobileNutritionPlanInputError("INVALID_NUTRITION_CYCLE_PAYLOAD")
    name = str(payload.get("name") or "").strip()
    if not name or len(name) > 120:
        raise MobileNutritionPlanInputError("INVALID_NUTRITION_CYCLE_NAME")
    try:
        original_start = date.fromisoformat(str(payload.get("original_start_date") or ""))
        requested_start = date.fromisoformat(str(payload.get("start_date") or ""))
    except (TypeError, ValueError) as error:
        raise MobileNutritionPlanInputError("INVALID_NUTRITION_CYCLE_DATE") from error
    duration_weeks = payload.get("duration_weeks")
    if isinstance(duration_weeks, bool) or not isinstance(duration_weeks, int) or not 1 <= duration_weeks <= 52:
        raise MobileNutritionPlanInputError("INVALID_NUTRITION_CYCLE_DURATION")
    normalized_start = requested_start - timedelta(days=requested_start.weekday())
    end = normalized_start + timedelta(days=duration_weeks * 7 - 1)

    connection = connect(db_path)
    try:
        cycle = connection.execute(
            """SELECT id FROM nutrition_plan_cycles
               WHERE start_date=? AND status IN ('active','planned')
               ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END,id DESC LIMIT 1""",
            (original_start.isoformat(),),
        ).fetchone()
        if not cycle:
            raise MobileNutritionPlanInputError("NUTRITION_PLAN_CYCLE_UNAVAILABLE")
        connection.execute(
            """UPDATE nutrition_plan_cycles
               SET name=?,start_date=?,end_date=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (name, normalized_start.isoformat(), end.isoformat(), cycle["id"]),
        )
        connection.execute(
            """UPDATE user_weekly_plans SET title=?,updated_at=CURRENT_TIMESTAMP
               WHERE nutrition_cycle_id=? AND deleted_at IS NULL""",
            (name, cycle["id"]),
        )
        connection.commit()
    finally:
        connection.close()
    return {"date": date.today().isoformat()}


def _number(value: Any, error: str) -> float:
    if isinstance(value, bool):
        raise MobileNutritionPlanInputError(error)
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise MobileNutritionPlanInputError(error) from exc
    if not math.isfinite(number) or number <= 0:
        raise MobileNutritionPlanInputError(error)
    return round(number, 2)


def _structured_details(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Normalize the desktop v1 recipe payload without accepting raw notes."""
    source_items = payload.get("items", [])
    source_supplements = payload.get("supplements", [])
    if not isinstance(source_items, list) or not isinstance(source_supplements, list):
        raise MobileNutritionPlanInputError("INVALID_NUTRITION_PLAN_DETAILS")
    if len(source_items) + len(source_supplements) > 30:
        raise MobileNutritionPlanInputError("INVALID_NUTRITION_PLAN_DETAILS")

    items: list[dict[str, Any]] = []
    for item in source_items:
        if not isinstance(item, dict):
            raise MobileNutritionPlanInputError("INVALID_NUTRITION_PLAN_DETAILS")
        name = str(item.get("name") or "").strip()
        item_type = str(item.get("item_type") or "food").strip()
        unit = str(item.get("unit") or "").strip()
        if not name or len(name) > 120 or item_type not in {"food", "beverage"} or not unit or len(unit) > 20:
            raise MobileNutritionPlanInputError("INVALID_NUTRITION_PLAN_DETAILS")
        items.append({
            "food_catalog_id": None,
            "custom_food_name": name,
            "item_type": item_type,
            "quantity": _number(item.get("quantity"), "INVALID_NUTRITION_PLAN_DETAILS"),
            "unit": unit,
        })

    supplements: list[dict[str, Any]] = []
    for item in source_supplements:
        if not isinstance(item, dict):
            raise MobileNutritionPlanInputError("INVALID_NUTRITION_PLAN_DETAILS")
        name = str(item.get("name") or "").strip()
        product_kind = str(item.get("product_kind") or "supplement").strip()
        unit = str(item.get("unit") or "").strip()
        if not name or len(name) > 120 or product_kind not in {"supplement", "medication"} or not unit or len(unit) > 20:
            raise MobileNutritionPlanInputError("INVALID_NUTRITION_PLAN_DETAILS")
        supplements.append({
            "supplement_product_id": None,
            "custom_product_name": name,
            "product_kind": product_kind,
            "quantity": _number(item.get("quantity"), "INVALID_NUTRITION_PLAN_DETAILS"),
            "unit": unit,
        })
    return items, supplements


def save_mobile_nutrition_plan_entry(
    payload: dict[str, Any], *, db_path: str | None = None,
) -> dict[str, str]:
    """Upsert one manual cell in the active desktop nutrition-cycle week."""
    if not isinstance(payload, dict):
        raise MobileNutritionPlanInputError("INVALID_NUTRITION_PLAN_PAYLOAD")
    try:
        week_start = date.fromisoformat(str(payload.get("week_start") or ""))
    except (TypeError, ValueError) as error:
        raise MobileNutritionPlanInputError("INVALID_NUTRITION_PLAN_WEEK") from error
    if week_start.weekday() != 0:
        raise MobileNutritionPlanInputError("INVALID_NUTRITION_PLAN_WEEK")
    weekday = payload.get("weekday")
    if isinstance(weekday, bool) or not isinstance(weekday, int) or not 0 <= weekday <= 6:
        raise MobileNutritionPlanInputError("INVALID_NUTRITION_PLAN_WEEKDAY")
    meal_slot = str(payload.get("meal_slot") or "").strip()
    if meal_slot not in _MEAL_SLOTS:
        raise MobileNutritionPlanInputError("INVALID_NUTRITION_PLAN_MEAL")
    original_meal_slot = str(payload.get("original_meal_slot") or meal_slot).strip()
    if original_meal_slot not in _MEAL_SLOTS:
        raise MobileNutritionPlanInputError("INVALID_NUTRITION_PLAN_MEAL")
    title = str(payload.get("title") or "").strip()
    items, supplements = _structured_details(payload)
    if not title:
        title = "、".join(
            [str(item["custom_food_name"]) for item in items]
            + [str(item["custom_product_name"]) for item in supplements]
        )
    if not title or len(title) > 240:
        raise MobileNutritionPlanInputError("INVALID_NUTRITION_PLAN_TITLE")
    notes_text = str(payload.get("notes") or "").strip()
    if len(notes_text) > 1000:
        raise MobileNutritionPlanInputError("INVALID_NUTRITION_PLAN_DETAILS")
    try:
        start = time.fromisoformat(str(payload.get("start_time") or ""))
        end = time.fromisoformat(str(payload.get("end_time") or ""))
    except (TypeError, ValueError) as error:
        raise MobileNutritionPlanInputError("INVALID_NUTRITION_PLAN_TIME") from error
    if end <= start:
        raise MobileNutritionPlanInputError("INVALID_NUTRITION_PLAN_TIME")

    connection = connect(db_path)
    try:
        cycle = connection.execute(
            """SELECT id,name FROM nutrition_plan_cycles
               WHERE status IN ('active','planned') AND start_date<=? AND end_date>=?
               ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END,start_date DESC,id DESC LIMIT 1""",
            (week_start.isoformat(), week_start.isoformat()),
        ).fetchone()
        if not cycle:
            raise MobileNutritionPlanInputError("NUTRITION_PLAN_CYCLE_UNAVAILABLE")
        plan = connection.execute(
            """SELECT plan_id FROM user_weekly_plans
               WHERE nutrition_cycle_id=? AND week_start=? AND deleted_at IS NULL LIMIT 1""",
            (cycle["id"], week_start.isoformat()),
        ).fetchone()
        if plan:
            plan_id = plan["plan_id"]
        else:
            plan_id = str(uuid4())
            connection.execute(
                """INSERT INTO user_weekly_plans(plan_id,week_start,title,timezone,nutrition_cycle_id)
                   VALUES(?,?,?,?,?)""",
                (plan_id, week_start.isoformat(), cycle["name"], "local", cycle["id"]),
            )
        marker = f"{_MARKER}:{meal_slot}|"
        existing_marker = f"{_MARKER}:{original_meal_slot}|"
        existing = connection.execute(
            """SELECT item_id FROM user_weekly_plan_items
               WHERE plan_id=? AND weekday=? AND category='meal' AND deleted_at IS NULL
                 AND (notes LIKE ? OR notes LIKE ?)
               ORDER BY CASE WHEN notes LIKE ? THEN 0 ELSE 1 END,updated_at DESC LIMIT 1""",
            (plan_id, weekday, f"{existing_marker}%", f"__nutrition_auto_recipe__:{original_meal_slot}|%", f"{existing_marker}%"),
        ).fetchone()
        detail = json.dumps({
            "version": 1, "items": items, "supplements": supplements,
            "notes": notes_text, "legacy_title": title,
        }, ensure_ascii=False, separators=(",", ":"))
        notes = marker + detail
        if existing:
            connection.execute(
                """UPDATE user_weekly_plan_items SET title=?,start_time=?,end_time=?,notes=?,
                       updated_at=CURRENT_TIMESTAMP WHERE item_id=?""",
                (title, start.strftime("%H:%M"), end.strftime("%H:%M"), notes, existing["item_id"]),
            )
        else:
            order = connection.execute(
                """SELECT COALESCE(MAX(sort_order),-1)+1 FROM user_weekly_plan_items
                   WHERE plan_id=? AND weekday=?""",
                (plan_id, weekday),
            ).fetchone()[0]
            connection.execute(
                """INSERT INTO user_weekly_plan_items(
                       item_id,plan_id,weekday,title,start_time,end_time,category,notes,sort_order
                   ) VALUES(?,?,?,?,?,?,'meal',?,?)""",
                (str(uuid4()), plan_id, weekday, title, start.strftime("%H:%M"),
                 end.strftime("%H:%M"), notes, order),
            )
        connection.commit()
    finally:
        connection.close()
    return {"date": (week_start.isoformat())}
