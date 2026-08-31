"""Versioned supplement-product catalog and intake services."""

from .catalog import (
    calculate_intake_ingredients, confirm_product, create_product,
    favorite_products, get_product, list_products, product_by_id,
    recent_intake_preferences, recent_products, search_local_products,
    set_product_favorite,
    soft_delete_product, update_product,
)
from .validation import (
    DOSAGE_FORMS, INGREDIENT_ROLES, PRODUCT_KINDS, VERIFICATION_STATUSES,
    normalize_barcode, normalize_ingredient, normalize_intake,
    normalize_product,
)

__all__ = [
    "DOSAGE_FORMS", "INGREDIENT_ROLES", "PRODUCT_KINDS",
    "VERIFICATION_STATUSES", "calculate_intake_ingredients",
    "confirm_product", "create_product", "favorite_products", "get_product",
    "list_products", "normalize_barcode", "normalize_ingredient",
    "normalize_intake", "normalize_product", "product_by_id",
    "recent_intake_preferences", "recent_products", "search_local_products",
    "set_product_favorite",
    "soft_delete_product", "update_product",
]
