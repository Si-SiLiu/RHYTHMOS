"""Food catalog repository, classification, conversion, and nutrition math."""

from __future__ import annotations

import json
import hashlib
import sqlite3

from .food_units import FOOD_UNITS, normalize_food_unit, positive_food_quantity


CUSTOM_FOOD = "custom"
FOOD_CATALOG_VERSION = "1.1.0"
NUTRIENT_COLUMNS = (
    "calories_kcal", "protein_g", "carbohydrate_g", "fat_g", "fiber_g",
    "water_ml", "caffeine_mg", "alcohol_g", "sodium_mg",
)
PER_100G_COLUMNS = {
    "calories_kcal": "calories_per_100g",
    "protein_g": "protein_per_100g",
    "carbohydrate_g": "carbohydrate_per_100g",
    "fat_g": "fat_per_100g",
    "fiber_g": "fiber_per_100g",
    "water_ml": "water_per_100g",
    "caffeine_mg": "caffeine_per_100g",
    "alcohol_g": "alcohol_per_100g",
}
OCR_PROFILE_COLUMNS = (
    "calories_kcal", "protein_g", "carbohydrate_g", "fat_g", "fiber_g",
    "sodium_mg",
)


def _decode(row) -> dict:
    item = dict(row)
    for source, target in (
        ("aliases_json", "aliases"),
        ("allowed_units_json", "allowed_units"),
        ("category_tags_json", "category_tags"),
    ):
        item[target] = tuple(json.loads(item[source]))
    return item


def list_food_catalog(connection: sqlite3.Connection, active_only=True) -> list[dict]:
    where = "WHERE is_active=1" if active_only else ""
    items = [_decode(row) for row in connection.execute(
        f"SELECT * FROM food_catalog {where} ORDER BY id"
    ).fetchall()]
    try:
        profiles = {
            int(row["food_catalog_id"]): dict(row)
            for row in connection.execute(
                "SELECT * FROM food_ocr_nutrition_profiles WHERE user_confirmed=1"
            ).fetchall()
        }
    except sqlite3.OperationalError:
        profiles = {}
    for item in items:
        item["ocr_nutrition_profile"] = profiles.get(int(item["id"]))
    return items


def food_catalog_by_id(connection: sqlite3.Connection) -> dict[int, dict]:
    return {item["id"]: item for item in list_food_catalog(connection)}


def food_catalog_by_name(connection: sqlite3.Connection) -> dict[str, dict]:
    return {item["canonical_name"]: item for item in list_food_catalog(connection)}


def food_display_name(catalog: dict, language: str = "zh-CN") -> str:
    """Include a confirmed label brand while preserving the stable catalog ID."""
    name = str(
        catalog.get("display_name_en" if language == "en" else "display_name_zh")
        or catalog.get("canonical_name")
        or ""
    )
    profile = catalog.get("ocr_nutrition_profile") or {}
    brand = str(profile.get("brand") or "").strip()
    return f"{name}（{brand}）" if brand else name


def search_food_catalog(connection: sqlite3.Connection, query: str, limit=20) -> list[dict]:
    needle = str(query or "").strip().casefold()
    items = list_food_catalog(connection)
    if not needle:
        return items[:limit]
    matches = []
    for item in items:
        values = (
            item["canonical_name"], item["display_name_zh"], item["display_name_en"],
            *item["aliases"],
        )
        if any(needle in str(value).casefold() for value in values):
            matches.append(item)
    return matches[:limit]


def ensure_manual_food_option(connection: sqlite3.Connection, name: str, item_type: str = "food") -> int | None:
    """Persist a user-entered food name as a reusable, data-limited option.

    The option intentionally has no fabricated nutrient values. Its catalog
    entry only makes the name available for future selection and later
    enrichment through the custom nutrition/OCR workflow.
    """
    display_name = str(name or "").strip()
    if not display_name:
        return None
    normalized = display_name.casefold()
    for item in list_food_catalog(connection):
        names = (
            item.get("canonical_name"), item.get("display_name_zh"),
            item.get("display_name_en"), *item.get("aliases", ()),
        )
        if any(str(value or "").strip().casefold() == normalized for value in names):
            return int(item["id"])

    digest = hashlib.sha256(f"{item_type}:{normalized}".encode("utf-8")).hexdigest()[:20]
    canonical_name = f"manual_{digest}"
    beverage = item_type == "beverage"
    default_unit = "ml" if beverage else "g"
    allowed_units = ("ml", "l", "g", "cup") if beverage else ("g", "kg", "piece", "serving")
    tags = ["custom", "beverage"] if beverage else ["custom"]
    connection.execute(
        """INSERT OR IGNORE INTO food_catalog(
               canonical_name,display_name_zh,display_name_en,aliases_json,
               default_unit,allowed_units_json,category_tags_json,serving_unit,
               nutrition_source,data_quality
           ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (
            canonical_name, display_name, display_name, "[]", default_unit,
            json.dumps(list(allowed_units), ensure_ascii=False),
            json.dumps(tags, ensure_ascii=False), None,
            "manual_user_input", "limited",
        ),
    )
    row = connection.execute(
        "SELECT id FROM food_catalog WHERE canonical_name=?", (canonical_name,)
    ).fetchone()
    return int(row["id"]) if row else None


def allowed_food_units(catalog: dict | None) -> tuple[str, ...]:
    return tuple(catalog["allowed_units"]) if catalog else FOOD_UNITS


def validate_food_unit(catalog: dict | None, unit: object) -> str:
    normalized = normalize_food_unit(unit)
    if catalog and normalized not in allowed_food_units(catalog):
        raise ValueError("FOOD_UNIT_NOT_ALLOWED")
    return normalized


def calculate_food_values(catalog: dict | None, quantity: object, unit: object) -> dict:
    quantity_value = positive_food_quantity(quantity)
    unit_value = validate_food_unit(catalog, unit)
    result = {
        "quantity": quantity_value,
        "unit": unit_value,
        "normalized_weight_g": None,
        "normalized_volume_ml": None,
        "_ocr_profile_applied": False,
        **{name: None for name in NUTRIENT_COLUMNS},
    }
    if not catalog:
        return result

    weight = volume = None
    if unit_value == "g":
        weight = quantity_value
    elif unit_value == "kg":
        weight = quantity_value * 1000
    elif unit_value in {"ml", "l"}:
        volume = quantity_value * (1000 if unit_value == "l" else 1)
        if catalog.get("serving_weight_g") and catalog.get("serving_volume_ml"):
            weight = volume * catalog["serving_weight_g"] / catalog["serving_volume_ml"]
    elif unit_value == catalog.get("serving_unit"):
        if catalog.get("serving_weight_g"):
            weight = quantity_value * catalog["serving_weight_g"]
        if catalog.get("serving_volume_ml"):
            volume = quantity_value * catalog["serving_volume_ml"]

    result["normalized_weight_g"] = round(weight, 4) if weight is not None else None
    result["normalized_volume_ml"] = round(volume, 4) if volume is not None else None
    if weight is not None:
        for output, source in PER_100G_COLUMNS.items():
            per_100g = catalog.get(source)
            if per_100g is not None:
                result[output] = round(weight * float(per_100g) / 100, 4)
    profile = catalog.get("ocr_nutrition_profile")
    if profile:
        basis_unit = profile["basis_unit"]
        basis_quantity = float(profile["basis_quantity"])
        scale = None
        if basis_unit == "g" and weight is not None:
            scale = weight / basis_quantity
        elif basis_unit == "ml" and volume is not None:
            scale = volume / basis_quantity
        elif basis_unit == "serving":
            if unit_value in {"serving", catalog.get("serving_unit")}:
                scale = quantity_value / basis_quantity
            elif weight is not None and catalog.get("serving_weight_g"):
                scale = weight / float(catalog["serving_weight_g"]) / basis_quantity
        if scale is not None:
            for nutrient in OCR_PROFILE_COLUMNS:
                value = profile.get(nutrient)
                if value is not None:
                    result[nutrient] = round(float(value) * scale, 4)
                    result["_ocr_profile_applied"] = True
    return result


def recent_foods(connection: sqlite3.Connection, limit: int | None = 8) -> list[dict]:
    """Return latest saved preference for each food.

    ``limit=None`` deliberately has no database limit.  It is used by editors
    when resolving learned amount/unit defaults, so an older learned food is
    never forgotten merely because newer foods exist.  Callers that render a
    compact recent list continue to use the default limit.
    """
    query = """WITH ranked AS (
               SELECT i.food_catalog_id,i.custom_food_name,i.item_type,i.quantity,i.unit,i.created_at,
                      COUNT(*) OVER (PARTITION BY i.food_catalog_id,i.custom_food_name) AS usage_count,
                      ROW_NUMBER() OVER (
                          PARTITION BY i.food_catalog_id,i.custom_food_name
                          ORDER BY i.created_at DESC,i.id DESC
                      ) AS preference_rank
               FROM meal_items i JOIN meal_records r ON r.id=i.meal_record_id
               WHERE i.deleted_at IS NULL AND r.deleted_at IS NULL
           ) SELECT * FROM ranked WHERE preference_rank=1
             ORDER BY usage_count DESC,created_at DESC"""
    parameters: tuple[int, ...] = ()
    if limit is not None:
        query += " LIMIT ?"
        parameters = (max(0, int(limit)),)
    rows = connection.execute(query, parameters).fetchall()
    catalog = food_catalog_by_id(connection)
    result = []
    for row in rows:
        result.append({
            "food_catalog_id": row["food_catalog_id"],
            "custom_food_name": row["custom_food_name"],
            "item_type": row["item_type"],
            "quantity": row["quantity"],
            "unit": row["unit"],
            "usage_count": row["usage_count"],
            "catalog": catalog.get(row["food_catalog_id"]),
        })
    return result


def favorite_foods(connection: sqlite3.Connection) -> list[dict]:
    rows = connection.execute(
        """SELECT f.* FROM food_catalog f JOIN food_favorites x
           ON x.food_catalog_id=f.id WHERE f.is_active=1 ORDER BY x.created_at DESC"""
    ).fetchall()
    return [_decode(row) for row in rows]


def set_food_favorite(connection: sqlite3.Connection, food_catalog_id: int, enabled: bool) -> None:
    with connection:
        if enabled:
            connection.execute(
                "INSERT OR IGNORE INTO food_favorites(food_catalog_id) VALUES(?)",
                (food_catalog_id,),
            )
        else:
            connection.execute(
                "DELETE FROM food_favorites WHERE food_catalog_id=?", (food_catalog_id,)
            )
