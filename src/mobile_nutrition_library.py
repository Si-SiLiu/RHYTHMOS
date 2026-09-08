"""Mobile access to the desktop's confirmed food-label library."""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any

from .db import connect
from .nutrition_logging.label_ocr import (
    create_custom_food_from_ocr,
    list_custom_food_nutrition_library,
    parse_nutrition_label,
)


class MobileNutritionLibraryError(ValueError):
    """Raised when a mobile food-label request is invalid or incomplete."""


_ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/heic", "image/tiff"}
_MAX_IMAGE_BYTES = 20 * 1024 * 1024


def _text(value: Any, field: str, *, required: bool = False, maximum: int = 5_000) -> str:
    result = str(value or "").strip()
    if (required and not result) or len(result) > maximum:
        raise MobileNutritionLibraryError(f"INVALID_{field.upper()}")
    return result


def _image(value: Any) -> bytes:
    if not isinstance(value, str) or not value:
        raise MobileNutritionLibraryError("NUTRITION_LABEL_IMAGE_REQUIRED")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, TypeError, binascii.Error) as error:
        raise MobileNutritionLibraryError("INVALID_NUTRITION_LABEL_IMAGE") from error
    if not decoded or len(decoded) > _MAX_IMAGE_BYTES:
        raise MobileNutritionLibraryError("INVALID_NUTRITION_LABEL_IMAGE")
    return decoded


def _rounded_label(parsed: dict[str, Any]) -> dict[str, Any]:
    """Keep mobile-created nutrient values consistent with two-decimal display."""
    nutrients = parsed.get("nutrients") or {}
    for nutrient in nutrients.values():
        if isinstance(nutrient, dict) and nutrient.get("value") is not None:
            nutrient["value"] = round(float(nutrient["value"]), 2)
    return parsed


def parse_mobile_food_label(payload: dict[str, Any]) -> dict[str, Any]:
    """Parse iPhone Vision text using the same desktop label parser."""
    if not isinstance(payload, dict):
        raise MobileNutritionLibraryError("INVALID_NUTRITION_LABEL_PAYLOAD")
    raw_text = _text(payload.get("raw_text"), "nutrition_label_text", required=True)
    parsed = _rounded_label(parse_nutrition_label(raw_text))
    if not parsed.get("nutrients"):
        raise MobileNutritionLibraryError("NUTRITION_LABEL_VALUES_NOT_FOUND")
    if parsed.get("basis") not in {"per 100 g", "per 100 ml", "per serving"}:
        raise MobileNutritionLibraryError("NUTRITION_LABEL_BASIS_REQUIRED")
    return {
        "basis": parsed["basis"],
        "nutrients": parsed["nutrients"],
        "confidence": round(float(parsed.get("confidence") or 0), 2),
    }


def save_mobile_food_label(payload: dict[str, Any], *, db_path: str | None = None) -> dict[str, Any]:
    """Create the same reusable custom-food label record used by macOS."""
    preview = parse_mobile_food_label(payload)
    food_name = _text(payload.get("food_name"), "nutrition_label_food_name", required=True, maximum=120)
    brand = _text(payload.get("brand"), "nutrition_label_brand", maximum=120) or None
    image_bytes = _image(payload.get("image_base64"))
    mime_type = _text(payload.get("image_mime_type"), "nutrition_label_image_mime", required=True, maximum=40)
    if mime_type not in _ALLOWED_IMAGE_MIME_TYPES:
        raise MobileNutritionLibraryError("INVALID_NUTRITION_LABEL_IMAGE_MIME")
    file_name = _text(payload.get("image_file_name"), "nutrition_label_image_name", maximum=160) or None

    parsed = {
        "raw_text": _text(payload.get("raw_text"), "nutrition_label_text", required=True),
        **preview,
    }
    connection = connect(db_path)
    try:
        food_catalog_id = create_custom_food_from_ocr(
            connection, food_name, parsed, brand=brand, source_image_bytes=image_bytes,
            source_file_name=file_name, source_mime_type=mime_type,
        )
    finally:
        connection.close()
    return {"food_catalog_id": food_catalog_id, "food_name": food_name}


def mobile_food_nutrition_library(*, db_path: str | None = None) -> dict[str, list[dict[str, Any]]]:
    """Return library metadata and parsed nutrients, never a source image BLOB."""
    connection = connect(db_path)
    try:
        records = list_custom_food_nutrition_library(connection)
    finally:
        connection.close()
    items = []
    for record in records:
        try:
            nutrients = json.loads(record.pop("nutrients_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            nutrients = {}
        items.append({
            "id": record["id"], "food_name": record["food_name"], "brand": record.get("brand"),
            "basis_quantity": round(float(record["basis_quantity"]), 2),
            "basis_unit": record["basis_unit"], "nutrients": nutrients,
            "ocr_confidence": round(float(record.get("ocr_confidence") or 0), 2),
            "created_at": record["created_at"],
        })
    return {"items": items}
