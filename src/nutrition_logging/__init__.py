"""Normalized manual meal-event logging with at most five items per category."""

from .storage import (
    CATEGORIES,
    CORE_CATEGORIES,
    EXTENDED_CATEGORIES,
    MEAL_TYPES,
    create_meal_event,
    delete_meal_event,
    get_meal_event,
    list_meal_events,
    save_meal_event,
)
from .validation import NutritionEventValidationError
from .supplement_catalog import (
    CATALOG_VERSION, CUSTOM_SUPPLEMENT, allowed_units, catalog_by_name,
    default_unit, list_catalog,
)
from .supplements import ai_supplement_summary, summarize_supplements
from .units import COUNT_UNITS, SUPPLEMENT_UNITS, SupplementUnit, unit_label_key
from .food_units import (
    FOOD_COUNT_UNITS, FOOD_UNITS, FoodUnit, food_unit_label_key,
)
from .food_catalog import (
    CUSTOM_FOOD, FOOD_CATALOG_VERSION, allowed_food_units, calculate_food_values,
    favorite_foods, food_catalog_by_id, food_catalog_by_name, food_display_name,
    ensure_manual_food_option, list_food_catalog,
    recent_foods, search_food_catalog, set_food_favorite,
)
from .simple_storage import (
    MEAL_SOURCES, MEAL_STATUSES, ai_meal_summaries, copy_meal_record,
    create_meal_from_template, create_meal_record, find_meal_id, find_previous_meal_id,
    find_yesterday_meal_id, get_meal_record, list_meal_records,
    list_meal_templates, meal_time_warning, predict_meal_time, recent_meal_times, save_meal_record,
    save_meal_template, soft_delete_meal_record, soft_delete_meal_template, summarize_meal,
)

__all__ = [
    "MEAL_TYPES", "CATEGORIES", "CORE_CATEGORIES", "EXTENDED_CATEGORIES",
    "NutritionEventValidationError", "create_meal_event", "save_meal_event",
    "delete_meal_event", "get_meal_event", "list_meal_events",
    "SupplementUnit", "SUPPLEMENT_UNITS", "COUNT_UNITS", "unit_label_key",
    "CATALOG_VERSION", "CUSTOM_SUPPLEMENT", "list_catalog", "catalog_by_name",
    "default_unit", "allowed_units", "summarize_supplements",
    "ai_supplement_summary",
    "FoodUnit", "FOOD_UNITS", "FOOD_COUNT_UNITS", "food_unit_label_key",
    "CUSTOM_FOOD", "FOOD_CATALOG_VERSION", "list_food_catalog",
    "food_catalog_by_id", "food_catalog_by_name", "search_food_catalog",
    "food_display_name",
    "allowed_food_units", "calculate_food_values", "ensure_manual_food_option", "recent_foods",
    "favorite_foods", "set_food_favorite", "MEAL_STATUSES", "MEAL_SOURCES",
    "create_meal_record", "save_meal_record", "get_meal_record",
    "list_meal_records", "soft_delete_meal_record", "copy_meal_record",
    "find_meal_id", "find_previous_meal_id", "find_yesterday_meal_id", "predict_meal_time", "recent_meal_times", "save_meal_template",
    "list_meal_templates", "create_meal_from_template", "soft_delete_meal_template", "summarize_meal",
    "ai_meal_summaries", "meal_time_warning",
]
