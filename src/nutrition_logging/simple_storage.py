"""Repository/service layer for simple food-level meal logging."""

from __future__ import annotations

from datetime import date, time
import json
import sqlite3
from typing import Any
from uuid import uuid4

from .food_catalog import (
    NUTRIENT_COLUMNS, calculate_food_values, food_catalog_by_id, food_display_name,
)
from .supplements import summarize_supplements, validate_supplement
from .validation import MEAL_TYPES
from src.supplements import normalize_intake, product_by_id


MEAL_STATUSES = ("draft", "completed")
MEAL_SOURCES = ("manual", "copied", "template", "imported", "photo_reviewed")


def _uuid() -> str:
    return str(uuid4())


def _normalize_meal(meal: dict[str, Any]) -> dict[str, Any]:
    try:
        meal_date = date.fromisoformat(str(meal.get("date"))).isoformat()
        actual_meal_time = time.fromisoformat(str(
            meal.get("actual_meal_time") or meal.get("eaten_at")
        )).isoformat(timespec="seconds")
        planned_meal_time = time.fromisoformat(str(
            meal.get("planned_meal_time") or actual_meal_time
        )).isoformat(timespec="seconds")
    except (TypeError, ValueError) as exc:
        raise ValueError("INVALID_MEAL_DATE_OR_TIME") from exc
    meal_type = meal.get("meal_type")
    status = meal.get("status", "completed")
    source = meal.get("source", "manual")
    if meal_type not in MEAL_TYPES:
        raise ValueError("INVALID_MEAL_TYPE")
    if status not in MEAL_STATUSES:
        raise ValueError("INVALID_MEAL_STATUS")
    if source not in MEAL_SOURCES:
        raise ValueError("INVALID_MEAL_SOURCE")
    return {
        "date": meal_date, "meal_type": meal_type, "eaten_at": actual_meal_time,
        "planned_meal_time": planned_meal_time, "actual_meal_time": actual_meal_time,
        "status": status, "source": source,
        "notes": str(meal.get("notes") or "").strip() or None,
    }


def _clean_food_items(connection: sqlite3.Connection, items: list[dict]) -> list[dict]:
    catalog = food_catalog_by_id(connection)
    cleaned = []
    for raw in items:
        catalog_id = raw.get("food_catalog_id")
        custom_name = str(raw.get("custom_food_name") or "").strip() or None
        quantity = raw.get("quantity")
        if not catalog_id and custom_name is None and quantity in (None, ""):
            continue
        selected = catalog.get(int(catalog_id)) if catalog_id not in (None, "") else None
        if catalog_id not in (None, "") and not selected:
            raise ValueError("FOOD_CATALOG_ITEM_NOT_FOUND")
        if not selected and not custom_name:
            raise ValueError("FOOD_NAME_REQUIRED")
        calculated = calculate_food_values(selected, quantity, raw.get("unit"))
        tags = list(selected["category_tags"]) if selected else []
        item_type = raw.get("item_type") or (
            "beverage" if any(tag in tags for tag in ("beverage", "hydration")) else "food"
        )
        if item_type not in {"food", "beverage"}:
            raise ValueError("INVALID_FOOD_ITEM_TYPE")
        cleaned.append({
            "uuid": str(raw.get("uuid") or _uuid()),
            "food_catalog_id": selected["id"] if selected else None,
            "custom_food_name": None if selected else custom_name,
            "item_type": item_type,
            **calculated,
            "category_tags_json": json.dumps(tags, ensure_ascii=False, separators=(",", ":")),
            "nutrition_source": (
                "label_ocr_confirmed"
                if calculated.get("_ocr_profile_applied")
                else selected.get("nutrition_source") if selected else None
            ),
            "classification_source": "catalog" if selected else "unclassified",
            "user_confirmed": 1 if raw.get("user_confirmed") else 0,
            "brand": str(raw.get("brand") or "").strip() or None,
            "cooking_method": str(raw.get("cooking_method") or "").strip() or None,
            "notes": str(raw.get("notes") or "").strip() or None,
        })
    return cleaned


def _clean_supplements(connection: sqlite3.Connection, supplements: list[dict], taken_at: str) -> list[dict]:
    products = product_by_id(connection)
    cleaned = []
    for position, raw in enumerate(supplements, 1):
        product_id = raw.get("supplement_product_id")
        selected = products.get(int(product_id)) if product_id not in (None, "") else None
        if product_id not in (None, "") and not selected:
            raise ValueError("SUPPLEMENT_PRODUCT_NOT_FOUND")
        name = str(
            (selected or {}).get("product_name")
            or raw.get("custom_product_name")
            or raw.get("item_name")
            or ""
        ).strip()
        if not name and raw.get("quantity") in (None, ""):
            continue
        if len(cleaned) >= 5:
            raise ValueError("TOO_MANY_SUPPLEMENTS")
        compatibility = validate_supplement({
            **raw, "category": "supplement", "position": position,
            "item_name": name,
            "active_component_name": None,
            "active_amount": None,
            "active_unit": None,
        })
        intake = normalize_intake({
            "supplement_product_id": selected["id"] if selected else None,
            # A scanned label may add a user-entered brand to a catalog
            # product. Keep that intake-specific detail without changing the
            # shared product profile.
            "custom_brand_name": raw.get("custom_brand_name"),
            "custom_product_name": None if selected else name,
            "quantity": compatibility["quantity"],
            "unit": compatibility["unit"],
            "taken_at": raw.get("taken_at") or taken_at,
            "source": raw.get("source") or "manual",
            "notes": raw.get("notes") or raw.get("item_notes"),
        })
        cleaned.append({**compatibility, **intake, "brand_name": (selected or {}).get("brand_name")})
    return cleaned


def save_meal_record(
    connection: sqlite3.Connection,
    meal: dict[str, Any],
    food_items: list[dict],
    supplements: list[dict] | None = None,
    record_id: int | None = None,
) -> int:
    values = _normalize_meal(meal)
    items = _clean_food_items(connection, food_items)
    supplement_items = _clean_supplements(connection, supplements or [], values["eaten_at"])
    with connection:
        if record_id is None:
            legacy_id = connection.execute(
                "INSERT INTO meal_events(date,meal_type,actual_meal_time,notes) VALUES(?,?,?,?)",
                (values["date"], values["meal_type"], values["eaten_at"], values["notes"]),
            ).lastrowid
            record_id = connection.execute(
                """INSERT INTO meal_records(
                       uuid,date,meal_type,eaten_at,planned_meal_time,actual_meal_time,
                       status,source,notes,legacy_meal_event_id
                   ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (_uuid(), values["date"], values["meal_type"], values["eaten_at"],
                 values["planned_meal_time"], values["actual_meal_time"], values["status"],
                 values["source"], values["notes"], legacy_id),
            ).lastrowid
        else:
            row = connection.execute(
                "SELECT legacy_meal_event_id FROM meal_records WHERE id=? AND deleted_at IS NULL",
                (record_id,),
            ).fetchone()
            if not row:
                raise ValueError("MEAL_RECORD_NOT_FOUND")
            legacy_id = row[0]
            connection.execute(
                """UPDATE meal_records SET date=?,meal_type=?,eaten_at=?,planned_meal_time=?,
                       actual_meal_time=?,status=?,source=?,notes=?,updated_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (values["date"], values["meal_type"], values["eaten_at"],
                 values["planned_meal_time"], values["actual_meal_time"], values["status"],
                 values["source"], values["notes"], record_id),
            )
            connection.execute(
                """UPDATE meal_events SET date=?,meal_type=?,actual_meal_time=?,notes=?,
                       updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (values["date"], values["meal_type"], values["eaten_at"], values["notes"], legacy_id),
            )
            connection.execute("DELETE FROM meal_items WHERE meal_record_id=?", (record_id,))
            # Retire the intake rows before replacing their legacy parent rows.
            # The intake rows keep a foreign-key reference to meal_event_items,
            # so deleting the parent first fails even when the intake is soft-deleted.
            # Detach retired rows while keeping their audit data available.
            connection.execute(
                """UPDATE supplement_intake_records SET deleted_at=CURRENT_TIMESTAMP,
                       legacy_meal_event_item_id=NULL,
                       updated_at=CURRENT_TIMESTAMP
                   WHERE meal_record_id=? AND deleted_at IS NULL""",
                (record_id,),
            )
            connection.execute(
                "DELETE FROM meal_event_items WHERE meal_event_id=? AND category='supplement'",
                (legacy_id,),
            )

        connection.executemany(
            """INSERT INTO meal_items(
                   uuid,meal_record_id,food_catalog_id,custom_food_name,item_type,
                   quantity,unit,normalized_weight_g,normalized_volume_ml,
                   category_tags_json,calories_kcal,protein_g,carbohydrate_g,
                   fat_g,fiber_g,water_ml,caffeine_mg,alcohol_g,sodium_mg,nutrition_source,
                   classification_source,user_confirmed,brand,cooking_method,notes
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [(
                item["uuid"], record_id, item["food_catalog_id"], item["custom_food_name"],
                item["item_type"], item["quantity"], item["unit"],
                item["normalized_weight_g"], item["normalized_volume_ml"],
                item["category_tags_json"], *(item[name] for name in NUTRIENT_COLUMNS),
                item["nutrition_source"], item["classification_source"], item["user_confirmed"],
                item["brand"], item["cooking_method"], item["notes"],
            ) for item in items],
        )
        for position, item in enumerate(supplement_items, 1):
            legacy_item_id = connection.execute(
                """INSERT INTO meal_event_items(
                       meal_event_id,category,position,item_name,quantity,unit,
                       active_amount,active_unit,active_component_name,timing,item_notes
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    legacy_id, "supplement", position, item["item_name"], item["quantity"],
                    item["unit"], None, None, None, item["taken_at"], item["notes"],
                ),
            ).lastrowid
            connection.execute(
                """INSERT INTO supplement_intake_records(
                       uuid,meal_record_id,supplement_product_id,custom_brand_name,
                       custom_product_name,quantity,unit,taken_at,source,notes,
                       legacy_meal_event_item_id
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    _uuid(), record_id, item["supplement_product_id"],
                    item["custom_brand_name"], item["custom_product_name"],
                    item["quantity"], item["unit"], item["taken_at"],
                    item["source"], item["notes"], legacy_item_id,
                ),
            )
    return int(record_id)


def create_meal_record(connection, meal, food_items, supplements=None) -> int:
    return save_meal_record(connection, meal, food_items, supplements)


def _record_supplements(connection, legacy_id: int) -> list[dict]:
    rows = connection.execute(
        """SELECT i.*,p.brand_name,p.product_name,p.product_variant,
                  p.verification_status,p.user_confirmed,p.product_kind,
                  l.active_amount,l.active_unit,l.active_component_name,
                  l.position,l.timing,l.item_notes,
                  COALESCE(p.product_name,i.custom_product_name,l.item_name) AS item_name
           FROM supplement_intake_records i
           LEFT JOIN supplement_products p ON p.id=i.supplement_product_id
           LEFT JOIN meal_event_items l ON l.id=i.legacy_meal_event_item_id
           JOIN meal_records r ON r.id=i.meal_record_id
           WHERE r.legacy_meal_event_id=? AND i.deleted_at IS NULL
           ORDER BY COALESCE(l.position,i.id),i.id""",
        (legacy_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_meal_record(connection: sqlite3.Connection, record_id: int) -> dict | None:
    row = connection.execute(
        "SELECT * FROM meal_records WHERE id=? AND deleted_at IS NULL", (record_id,)
    ).fetchone()
    if not row:
        return None
    record = dict(row)
    record["items"] = [dict(item) for item in connection.execute(
        """SELECT * FROM meal_items WHERE meal_record_id=? AND deleted_at IS NULL
           ORDER BY id""", (record_id,)
    ).fetchall()]
    # Older records may have stored a branded catalog display name as
    # custom_food_name before branded labels were accepted by the selector.
    # Resolve those names on read so historical totals immediately use the
    # linked catalog, including any confirmed OCR nutrition profile.
    catalog = food_catalog_by_id(connection)
    name_lookup = {}
    for item in catalog.values():
        for name in (
            item.get("canonical_name"), item.get("display_name_zh"),
            item.get("display_name_en"), food_display_name(item),
        ):
            normalized = str(name or "").strip().casefold()
            if normalized:
                name_lookup[normalized] = item
    for item in record["items"]:
        if item.get("food_catalog_id") is not None:
            continue
        selected = name_lookup.get(str(item.get("custom_food_name") or "").strip().casefold())
        if not selected:
            continue
        item["food_catalog_id"] = selected["id"]
        item["custom_food_name"] = None
        calculated = calculate_food_values(selected, item.get("quantity"), item.get("unit"))
        for nutrient in NUTRIENT_COLUMNS:
            item[nutrient] = calculated.get(nutrient)
        if calculated.get("_ocr_profile_applied"):
            item["nutrition_source"] = "label_ocr_confirmed"
    record["supplements"] = _record_supplements(connection, record["legacy_meal_event_id"])
    record["summary"] = summarize_meal(record["items"])
    return record


def summarize_meal(items: list[dict]) -> dict:
    active = [item for item in items if not item.get("deleted_at")]
    count = len(active)
    identified = sum(item.get("food_catalog_id") is not None for item in active)
    summary = {"food_count": count, "identified_food_count": identified}
    for nutrient in NUTRIENT_COLUMNS:
        known = [float(item[nutrient]) for item in active if item.get(nutrient) is not None]
        summary[nutrient] = round(sum(known), 2) if known else None
    summary["data_completeness"] = round(identified / count, 4) if count else None
    return summary


def list_meal_records(connection: sqlite3.Connection, limit=100) -> list[dict]:
    if limit < 1:
        raise ValueError("INVALID_LIST_LIMIT")
    ids = [row[0] for row in connection.execute(
        """SELECT id FROM meal_records WHERE deleted_at IS NULL
           ORDER BY date DESC,eaten_at DESC,id DESC LIMIT ?""", (limit,)
    ).fetchall()]
    return [get_meal_record(connection, record_id) for record_id in ids]


def recent_meal_times(
    connection: sqlite3.Connection, meal_type: str, limit: int = 3
) -> list[str]:
    if meal_type not in MEAL_TYPES or limit < 1:
        return []
    columns = {row[1] for row in connection.execute("PRAGMA table_info(meal_records)")}
    time_column = (
        "COALESCE(actual_meal_time,eaten_at)" if "actual_meal_time" in columns else "eaten_at"
    )
    rows = connection.execute(
        f"""SELECT {time_column} AS meal_time,MAX(date || ' ' || updated_at) AS last_used
            FROM meal_records WHERE deleted_at IS NULL AND meal_type=?
            GROUP BY {time_column} ORDER BY last_used DESC LIMIT ?""",
        (meal_type, limit),
    ).fetchall()
    return [str(row[0]) for row in rows if row[0]]


def predict_meal_time(
    connection: sqlite3.Connection,
    meal_type: str,
    meal_date: date | str | None = None,
    limit: int = 30,
) -> time | None:
    """Predict a meal time from the user's recent completed meals."""
    if meal_type not in MEAL_TYPES or limit < 1:
        return None
    day_value = (
        meal_date.isoformat() if isinstance(meal_date, date)
        else str(meal_date) if meal_date else None
    )
    rows = connection.execute(
        """SELECT COALESCE(actual_meal_time,eaten_at) AS meal_time
           FROM meal_records
          WHERE deleted_at IS NULL
            AND status = 'completed'
            AND meal_type = ?
            AND COALESCE(actual_meal_time,eaten_at) IS NOT NULL
            AND (? IS NULL OR date < ?)
          ORDER BY date DESC, updated_at DESC, id DESC
          LIMIT ?""",
        (meal_type, day_value, day_value, limit),
    ).fetchall()
    observations = []
    for row in rows:
        try:
            value = time.fromisoformat(str(row[0]))
        except (TypeError, ValueError):
            continue
        observations.append(value.hour * 60 + value.minute + value.second / 60)
    if not observations:
        return None
    weights = [1 / (index + 1) for index in range(len(observations))]
    weighted_minutes = sum(
        value * weight for value, weight in zip(observations, weights)
    ) / sum(weights)
    rounded_minutes = max(0, min(1435, int(weighted_minutes / 5 + 0.5) * 5))
    return time(rounded_minutes // 60, rounded_minutes % 60)


def soft_delete_meal_record(connection: sqlite3.Connection, record_id: int) -> bool:
    with connection:
        cursor = connection.execute(
            """UPDATE meal_records SET deleted_at=CURRENT_TIMESTAMP,
                   updated_at=CURRENT_TIMESTAMP WHERE id=? AND deleted_at IS NULL""",
            (record_id,),
        )
    return cursor.rowcount > 0


def copy_meal_record(
    connection: sqlite3.Connection, source_record_id: int, new_date: str,
    new_eaten_at: str, source="copied",
) -> int:
    original = get_meal_record(connection, source_record_id)
    if not original:
        raise ValueError("MEAL_RECORD_NOT_FOUND")
    items = [{
        key: item.get(key) for key in (
            "food_catalog_id", "custom_food_name", "item_type", "quantity", "unit",
            "brand", "cooking_method", "notes", "user_confirmed",
        )
    } for item in original["items"]]
    supplements = [{
        key: item.get(key) for key in (
            "supplement_product_id", "custom_brand_name", "custom_product_name",
            "item_name", "quantity", "unit", "taken_at", "notes",
        )
    } for item in original["supplements"]]
    return create_meal_record(connection, {
        "date": new_date, "meal_type": original["meal_type"],
        "eaten_at": new_eaten_at, "status": "completed", "source": source,
    }, items, supplements)


def find_previous_meal_id(connection: sqlite3.Connection, before_record_id=None) -> int | None:
    where = "AND id < ?" if before_record_id else ""
    params = (before_record_id,) if before_record_id else ()
    row = connection.execute(
        f"""SELECT id FROM meal_records WHERE deleted_at IS NULL {where}
            ORDER BY date DESC,eaten_at DESC,id DESC LIMIT 1""", params
    ).fetchone()
    return int(row[0]) if row else None


def find_yesterday_meal_id(connection, meal_type: str, today: str) -> int | None:
    row = connection.execute(
        """SELECT id FROM meal_records WHERE deleted_at IS NULL AND meal_type=?
           AND date=date(?,'-1 day') ORDER BY eaten_at DESC,id DESC LIMIT 1""",
        (meal_type, today),
    ).fetchone()
    return int(row[0]) if row else None


def find_meal_id(connection, meal_type: str, meal_date: str) -> int | None:
    """Return the latest active record for one exact date and meal type."""
    if meal_type not in MEAL_TYPES:
        return None
    row = connection.execute(
        """SELECT id FROM meal_records
           WHERE deleted_at IS NULL AND date=? AND meal_type=?
           ORDER BY updated_at DESC,id DESC LIMIT 1""",
        (meal_date, meal_type),
    ).fetchone()
    return int(row[0]) if row else None


def save_meal_template(connection, name: str, meal_type: str, items: list[dict], supplements: list[dict], template_type: str = "meal") -> int:
    template_name = str(name or "").strip()
    if not template_name or meal_type not in MEAL_TYPES or template_type not in {"meal", "food", "beverage", "supplement"}:
        raise ValueError("INVALID_MEAL_TEMPLATE")
    food_payload = [{key: item.get(key) for key in (
        "food_catalog_id", "custom_food_name", "item_type", "quantity", "unit",
        "brand", "cooking_method", "notes", "user_confirmed",
    )} for item in _clean_food_items(connection, items)]
    supplement_payload = [{key: item.get(key) for key in (
        "supplement_product_id", "custom_brand_name", "custom_product_name",
        "item_name", "quantity", "unit", "taken_at", "notes",
    )} for item in _clean_supplements(connection, supplements, "00:00:00")]
    if template_type in {"food", "beverage"}:
        food_payload = [item for item in food_payload if item.get("item_type") == template_type]
        supplement_payload = []
    elif template_type == "supplement":
        food_payload = []
    with connection:
        cursor = connection.execute(
            """INSERT INTO meal_templates(uuid,name,meal_type,template_type,items_json,supplements_json)
               VALUES(?,?,?,?,?,?)""",
            (_uuid(), template_name, meal_type, template_type,
             json.dumps(food_payload, ensure_ascii=False),
             json.dumps(supplement_payload, ensure_ascii=False)),
        )
    return int(cursor.lastrowid)


def list_meal_templates(connection) -> list[dict]:
    return [dict(row) for row in connection.execute(
        "SELECT * FROM meal_templates WHERE deleted_at IS NULL ORDER BY updated_at DESC,id DESC"
    ).fetchall()]


def soft_delete_meal_template(connection, template_id: int) -> bool:
    with connection:
        cursor = connection.execute(
            "UPDATE meal_templates SET deleted_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE id=? AND deleted_at IS NULL",
            (template_id,),
        )
    return cursor.rowcount > 0


def create_meal_from_template(connection, template_id: int, meal_date: str, eaten_at: str) -> int:
    row = connection.execute(
        "SELECT * FROM meal_templates WHERE id=? AND deleted_at IS NULL", (template_id,)
    ).fetchone()
    if not row:
        raise ValueError("MEAL_TEMPLATE_NOT_FOUND")
    return create_meal_record(connection, {
        "date": meal_date, "meal_type": row["meal_type"], "eaten_at": eaten_at,
        "status": "completed", "source": "template",
    }, json.loads(row["items_json"]), json.loads(row["supplements_json"]))


def ai_meal_summaries(connection: sqlite3.Connection, meal_date: str) -> list[dict]:
    rows = connection.execute(
        """SELECT id FROM meal_records WHERE date=? AND status='completed'
           AND deleted_at IS NULL ORDER BY eaten_at,id""", (meal_date,)
    ).fetchall()
    result = []
    for row in rows:
        meal = get_meal_record(connection, row[0])
        result.append({
            "meal_type": meal["meal_type"], "eaten_at": meal["eaten_at"],
            **meal["summary"],
        })
    return result


def meal_time_warning(meal_type: str, eaten_at: str) -> bool:
    hour = time.fromisoformat(eaten_at).hour
    common = {
        "breakfast": range(5, 12), "lunch": range(10, 15), "dinner": range(16, 23),
    }
    return meal_type in common and hour not in common[meal_type]
