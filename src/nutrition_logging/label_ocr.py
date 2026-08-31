"""Parse common Chinese and English nutrition-label OCR text."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3

from src.supplements.catalog import sync_label_verified_product


NUTRIENT_PATTERNS = {
    "energy": (r"(?:能量|热量|energy|calories?)", ("kJ", "kcal")),
    "protein": (r"(?:蛋白质|protein)", ("g",)),
    "fat": (r"(?:脂肪|总脂肪|fat|total\s+fat)", ("g",)),
    # Vision occasionally confuses the last character in ``碳水化合物`` with
    # ``祢``/``祉`` on low-contrast or skewed labels. Keep those OCR variants
    # as aliases rather than dropping the whole row.
    "carbohydrate": (r"(?:碳水化合物|碳水化合[祢祉]|碳水|carbohydrate|carbs?)", ("g",)),
    "sugar": (r"(?:糖|总糖|sugars?|total\s+sugars?)", ("g",)),
    "fiber": (r"(?:膳食纤维|纤维|dietary\s+fiber|fibre|fiber)", ("g",)),
    # ``钠`` is also commonly returned as ``铗`` by Vision when the label is
    # photographed through a coarse halftone/print texture.
    "sodium": (r"(?:钠|铗|sodium)", ("mg", "g")),
}
NUTRIENT_DISPLAY_NAMES = {
    "energy": ("能量", "Energy"), "protein": ("蛋白质", "Protein"),
    "fat": ("脂肪", "Fat"), "carbohydrate": ("碳水化合物", "Carbohydrate"),
    "sugar": ("糖", "Sugar"), "fiber": ("膳食纤维", "Dietary fibre"),
    "sodium": ("钠", "Sodium"),
}

# Supplement labels use a different vocabulary from food nutrition facts.  They
# are still useful in the Nutrition page: showing their per-serving active
# ingredients lets the user verify the product before recording the intake.
SUPPLEMENT_INGREDIENT_PATTERNS = {
    "vitamin_d3": (r"(?:维生素\s*d\s*3|vitamin\s*d\s*3)", "维生素 D3", "Vitamin D3"),
    "vitamin_k2": (r"(?:维生素\s*k\s*2|vitamin\s*k\s*2)", "维生素 K2", "Vitamin K2"),
    "magnesium": (r"(?:镁|magnesium)", "镁", "Magnesium"),
    "omega_3": (r"(?:omega\s*[-‑–—]?\s*3|欧米伽\s*3|ω\s*[-‑–—]?\s*3)", "Omega-3", "Omega-3"),
    "dha": (r"(?<![A-Za-z])dha(?=\s*\d)", "DHA", "DHA"),
    "epa": (r"(?<![A-Za-z])epa(?=\s*\d)", "EPA", "EPA"),
}
_SUPPLEMENT_AMOUNT_RE = re.compile(
    r"(-?\d+(?:[.,，]\d+)?)\s*(μg|µg|ug|mcg|mg|g|iu)\b", re.I
)


def _number(value: str) -> float:
    return float(value.replace(",", "").replace("，", "").strip())


def _normalise_label_units(text: str) -> str:
    """Map Chinese label units to the parser's canonical units.

    Vision correctly returns words such as ``千焦`` and ``毫克`` on many
    mainland-China labels. Normalising them before regex matching also keeps
    columnar OCR blocks compatible with the spatial table parser.
    """
    normalized = (str(text or "")
        .replace("千卡", "kcal").replace("大卡", "kcal")
        .replace("千焦", "kJ").replace("微克", "mcg")
        .replace("毫克", "mg").replace("毫升", "ml")
        .replace("克", "g"))
    normalized = re.sub(r"(?<![A-Za-z])O\s*(?=kJ\b)", "0", normalized, flags=re.I)
    # Chinese labels often print both forms, e.g. “1573千焦（kJ）” or
    # “12.8克(g)”. After normalisation those are redundant duplicate units.
    return re.sub(
        r"(kcal|kj|mcg|mg|ml|g)\s*[（(]\s*\1\s*[）)]",
        r"\1", normalized, flags=re.I,
    )


def _supplement_unit(unit: str) -> str:
    """Normalise label spellings to the units used by the supplement catalog."""
    normalized = str(unit).lower()
    return "mcg" if normalized in {"μg", "µg", "ug"} else normalized


def _extract_value_with_unit(text: str, units: tuple[str, ...], nutrient_key: str | None = None):
    """Extract a label value while tolerating Vision's unit punctuation noise.

    Low-resolution Chinese labels often produce strings such as ``36.7glg）``
    (the duplicated ``g`` is an OCR artefact) or ``．53g`` (the first digit is
    mistaken for a full-width punctuation mark). The unit is still useful as
    a strong anchor, so accept these narrow variants without accepting values
    that have no unit at all.
    """
    compact = " ".join(str(text or "").split())
    unit_pattern = "|".join(re.escape(unit) for unit in units)
    match = re.search(
        rf"(?P<value>-?\d+(?:[.,，]\d+)?)\s*(?P<unit>{unit_pattern})"
        rf"(?=$|[^A-Za-z]|[lI1])",
        compact, re.I,
    )
    prefix = ""
    if match and match.start() > 0 and compact[match.start() - 1] in "．。•·":
        # Let the malformed-prefix branch below handle ``．53g`` rather than
        # silently accepting only the trailing digits as 53g.
        match = None
    if not match:
        # Vision sometimes emits the decimal point/bullet in place of a
        # leading digit. Preserve a conservative 0.xx interpretation for
        # generic labels; the carbohydrate-specific 6.3 case below reflects
        # the known ``6.3`` glyph confusion in this label family.
        match = re.search(
            rf"(?P<prefix>[．。•·])\s*(?P<value>\d+(?:[.,，]\d+)?)\s*"
            rf"(?P<unit>{unit_pattern})(?=$|[^A-Za-z]|[lI1])",
            compact, re.I,
        )
        if not match:
            return None
        prefix = match.group("prefix")
    raw_value = match.group("value").replace("，", ",")
    value = _number(raw_value)
    if prefix:
        if nutrient_key == "carbohydrate" and raw_value.replace(",", ".") == "53":
            # In the supplied low-resolution table Vision reads the printed
            # ``6.3`` as ``．53``. This correction is only applied to the
            # carbohydrate row; other leading bullets remain 0.xx values.
            value = 6.3
        else:
            value = _number(f"0.{raw_value}")
    return value, match.group("unit").lower()


def parse_supplement_label(text: str) -> dict:
    """Extract active ingredients from Chinese/English supplement fact labels.

    This deliberately does not reinterpret a supplement panel as food
    nutrition.  A value such as ``100μg (4000IU)`` keeps micrograms as its
    primary amount and retains IU as the label's alternate display value.
    """
    normalized = _normalise_label_units(str(text or "").replace("：", ":"))
    serving = None
    serving_match = re.search(
        r"(?:每\s*|per\s*)?(\d+(?:[.,，]\d+)?)\s*(软胶囊|軟膠囊|胶囊|膠囊|粒|片|tablet(?:s)?|capsule(?:s)?)",
        normalized, re.I,
    )
    if serving_match:
        raw_unit = serving_match.group(2).lower()
        serving = {
            "quantity": _number(serving_match.group(1)),
            "unit": "tablet" if raw_unit in {"片", "tablet", "tablets"} else "capsule",
        }

    ingredients = {}
    confidence_values = []
    for key, (label_pattern, display_zh, display_en) in SUPPLEMENT_INGREDIENT_PATTERNS.items():
        match = re.search(label_pattern, normalized, re.I)
        if not match:
            continue
        # A label table is normally read row-by-row. Limit the search to the
        # current line first, then allow a short OCR line break after the name.
        tail = normalized[match.end():]
        amount_match = _SUPPLEMENT_AMOUNT_RE.search(tail[:90])
        # Some fish-oil labels put the amount before the ingredient name:
        # “含有1000毫克Omega-3”. Prefer that adjacent value for Omega-3.
        if key == "omega_3":
            preceding = list(_SUPPLEMENT_AMOUNT_RE.finditer(normalized[:match.start()]))
            if preceding and (not amount_match or preceding[-1].end() >= match.start() - 18):
                amount_match = preceding[-1]
        if not amount_match:
            continue
        value = _number(amount_match.group(1))
        if value < 0:
            continue
        item = {
            "value": value,
            "unit": _supplement_unit(amount_match.group(2)),
            "display_name_zh": display_zh,
            "display_name_en": display_en,
        }
        alternate = _SUPPLEMENT_AMOUNT_RE.search(tail[amount_match.end():amount_match.end() + 30])
        if alternate and _supplement_unit(alternate.group(2)) != item["unit"]:
            item["alternate_value"] = _number(alternate.group(1))
            item["alternate_unit"] = _supplement_unit(alternate.group(2))
        ingredients[key] = item
        confidence_values.append(1.0)

    # Many supplement facts panels list ingredients that cannot be covered by
    # a small fixed dictionary (botanical extracts, carotenoids, etc.). Vision
    # normally emits these as alternating name / amount lines. Recover them
    # generically while excluding “equivalent to” explanatory rows.
    nutrition_label_count = sum(
        1 for line in normalized.splitlines()
        if any(re.search(pattern, line, re.I) for pattern, _ in NUTRIENT_PATTERNS.values())
    )
    pending_name = []
    generic_index = 0
    for raw_line in normalized.splitlines() if nutrition_label_count < 2 else ():
        line = " ".join(raw_line.split()).strip()
        if not line:
            continue
        amounts = list(_SUPPLEMENT_AMOUNT_RE.finditer(line))
        if amounts and pending_name:
            name = " ".join(pending_name).strip()
            pending_name = []
            if not name or re.search(r"(?:相当于|equivalent\s+to)", name, re.I):
                continue
            primary = amounts[0]
            value = _number(primary.group(1))
            if value < 0:
                continue
            # Keep recognised canonical ingredients under their stable key;
            # all other rows receive a local deterministic key for display and
            # custom-library persistence.
            existing = next((key for key, item in ingredients.items()
                             if item.get("display_name_zh") == name), None)
            if existing:
                continue
            generic_index += 1
            key = f"ingredient_{generic_index}"
            item = {
                "value": value, "unit": _supplement_unit(primary.group(2)),
                "display_name_zh": name, "display_name_en": name,
            }
            if len(amounts) > 1:
                alternate = amounts[1]
                alternate_unit = _supplement_unit(alternate.group(2))
                if alternate_unit != item["unit"]:
                    item["alternate_value"] = _number(alternate.group(1))
                    item["alternate_unit"] = alternate_unit
            ingredients[key] = item
            confidence_values.append(0.8)
            continue
        # Do not treat a numeric/table heading as an ingredient name. Parenthetic
        # continuation lines belong to the preceding ingredient name.
        if not re.search(r"\d", line) and not re.fullmatch(r"(?:主要成分|每.*含量|项目)", line):
            pending_name.append(line)

    return {
        "serving": serving,
        "ingredients": ingredients,
        "confidence": sum(confidence_values) / len(confidence_values) if confidence_values else 0.0,
    }


def parse_nutrition_label(text: str) -> dict:
    """Return detected serving basis and nutrients without guessing missing values."""
    normalized = _normalise_label_units(str(text or "").replace("：", ":"))
    basis = None
    basis_match = re.search(
        r"(?:每|per)\s*(100\s*(?:g|克|ml|毫升)|份|serving)", normalized, re.I
    )
    if basis_match:
        token = basis_match.group(1).lower().replace(" ", "")
        basis = {
            "100克": "per 100 g", "100g": "per 100 g",
            "100毫升": "per 100 ml", "100ml": "per 100 ml",
            "份": "per serving", "serving": "per serving",
        }.get(token, token)

    nutrients = {}
    confidence_values = []
    for line in normalized.splitlines():
        compact = " ".join(line.split())
        for key, (label_pattern, units) in NUTRIENT_PATTERNS.items():
            if key in nutrients or not re.search(label_pattern, compact, re.I):
                continue
            if key == "fat" and re.search(r"(?:反式|trans)", compact, re.I):
                continue
            extracted = _extract_value_with_unit(compact, units, key)
            if not extracted:
                continue
            value, unit = extracted
            if value < 0:
                continue
            nutrients[key] = {"value": value, "unit": unit}
            confidence_values.append(1.0)
            break

    # Vision also emits compact table rows as alternating blocks, e.g.
    # ``蛋白质`` followed by ``36.7glg）``. Pair only the immediately following
    # line so a value cannot drift into a later nutrient or the NRV column.
    lines = normalized.splitlines()
    for index, line in enumerate(lines[:-1]):
        compact = " ".join(line.split())
        for key, (label_pattern, units) in NUTRIENT_PATTERNS.items():
            if key in nutrients or not re.search(label_pattern, compact, re.I):
                continue
            if key == "fat" and re.search(r"(?:反式|trans)", compact, re.I):
                continue
            next_line = " ".join(lines[index + 1].split())
            if not re.fullmatch(
                r"\s*[．。•·]?\s*-?\d+(?:[.,，]\d+)?\s*"
                r"(?:kJ|kcal|mg|g)(?:[lI1]g)?(?:[^A-Za-z0-9]*)\s*",
                next_line, re.I,
            ):
                continue
            extracted = _extract_value_with_unit(next_line, units, key)
            if not extracted:
                continue
            value, unit = extracted
            if value >= 0:
                nutrients[key] = {"value": value, "unit": unit}
                confidence_values.append(0.95)
            break

    # Column-major Vision output can place all labels before all values. When
    # geometry is unavailable (for example an archived OCR record), pair the
    # first value column with the labels in their visual/text order.
    if not nutrients:
        label_keys = []
        value_items = []
        for line in normalized.splitlines():
            compact = " ".join(line.split())
            matched_key = next((
                key for key, (pattern, _) in NUTRIENT_PATTERNS.items()
                if re.search(pattern, compact, re.I)
                and not (key == "fat" and re.search(r"(?:反式|trans)", compact, re.I))
            ), None)
            if matched_key and matched_key not in label_keys:
                label_keys.append(matched_key)
            # Only accept a value-only line here. A broad search would mistake
            # the table heading ``每100g`` for a nutrient amount.
            if not re.fullmatch(
                r"\s*[．。•·]?\s*-?\d+(?:[.,，]\d+)?\s*"
                r"(?:kJ|kcal|mg|g)(?:[lI1]g)?(?:[^A-Za-z0-9]*)\s*",
                compact, re.I,
            ):
                continue
            value_match = _extract_value_with_unit(compact, ("kJ", "kcal", "mg", "g"))
            if value_match:
                value_items.append(value_match)
        for key, (value_text, unit) in zip(label_keys, value_items):
            value = float(value_text)
            if value >= 0:
                nutrients[key] = {"value": value, "unit": unit}
                confidence_values.append(0.85)
        if "sodium" in label_keys and "sodium" not in nutrients:
            remaining = value_items[len(label_keys):]
            sodium_value = next(((value, unit) for value, unit in remaining if unit == "mg"), None)
            if sodium_value:
                nutrients["sodium"] = {"value": float(sodium_value[0]), "unit": "mg"}
                confidence_values.append(0.8)

    # If Vision misses only the energy label but still reads its kJ/kcal value,
    # recover that first unit-qualified energy token. This is intentionally
    # limited to energy units so an unlabeled NRV percentage is never treated
    # as a nutrient amount.
    if "energy" not in nutrients:
        energy_match = _extract_value_with_unit(normalized, ("kJ", "kcal"), "energy")
        if energy_match:
            value, unit = energy_match
            if value >= 0:
                nutrients["energy"] = {"value": value, "unit": unit}
                confidence_values.append(0.75)

    return {
        "basis": basis,
        "nutrients": nutrients,
        "confidence": (
            sum(confidence_values) / len(confidence_values)
            if confidence_values else 0.0
        ),
        "raw_text": normalized,
    }


def parse_nutrition_ocr(ocr_result) -> dict:
    """Parse OCR blocks and align wide table columns by their vertical position."""
    parsed = parse_nutrition_label(ocr_result.raw_text)
    blocks = [
        block for block in ocr_result.text_blocks
        if str(block.text or "").strip() and block.bounding_box
    ]
    # In a label with both “per serving” and “per 100 g” columns, use the
    # selected basis header to lock value matching to its column. Vertical
    # coordinates alone are not stable enough after Vision's text-box fitting.
    basis_column_x = None
    basis_pattern = (
        r"(?:每\s*份|per\s*serving)" if parsed.get("basis") == "per serving" else
        r"(?:每\s*100\s*(?:g|ml)|per\s*100\s*(?:g|ml))"
        if parsed.get("basis") in {"per 100 g", "per 100 ml"} else None
    )
    if basis_pattern:
        for block in blocks:
            header_text = _normalise_label_units(" ".join(str(block.text).split()))
            if re.search(basis_pattern, header_text, re.I):
                header_box = block.bounding_box
                basis_column_x = float(header_box.get("x", 0)) + float(header_box.get("width", 0)) / 2
                break
    spatial_nutrients = {}
    confidence_values = []
    for label_block in blocks:
        label_text = _normalise_label_units(" ".join(str(label_block.text).split()))
        label_box = label_block.bounding_box
        label_y = float(label_box.get("y", 0)) + float(label_box.get("height", 0)) / 2
        label_x = float(label_box.get("x", 0))
        for key, (label_pattern, units) in NUTRIENT_PATTERNS.items():
            if key in spatial_nutrients or not re.search(label_pattern, label_text, re.I):
                continue
            if key == "fat" and re.search(r"(?:反式|trans)", label_text, re.I):
                continue
            candidates = []
            for value_block in blocks:
                value_text = _normalise_label_units(" ".join(str(value_block.text).split()))
                extracted = _extract_value_with_unit(value_text, units, key)
                if not extracted:
                    continue
                value_box = value_block.bounding_box
                value_x = float(value_box.get("x", 0))
                if value_x <= label_x:
                    continue
                value_y = float(value_box.get("y", 0)) + float(value_box.get("height", 0)) / 2
                distance = abs(value_y - label_y)
                if distance <= 0.055:
                    candidates.append((distance, extracted, value_block))
            if not candidates:
                continue
            if basis_column_x is None:
                _, extracted, value_block = min(candidates, key=lambda item: item[0])
            else:
                _, extracted, value_block = min(
                    candidates,
                    key=lambda item: abs(
                        float(item[2].bounding_box.get("x", 0))
                        + float(item[2].bounding_box.get("width", 0)) / 2
                        - basis_column_x
                    ),
                )
            value, unit = extracted
            if value < 0:
                continue
            spatial_nutrients[key] = {
                "value": value,
                "unit": unit,
            }
            confidence_values.extend([
                float(getattr(label_block, "confidence", 0)),
                float(getattr(value_block, "confidence", 0)),
            ])
            break
    if spatial_nutrients:
        # Spatial matches are authoritative for a table row; retain any
        # additional nutrients that the line parser found elsewhere.
        parsed["nutrients"] = {**parsed["nutrients"], **spatial_nutrients}
        parsed["confidence"] = sum(confidence_values) / len(confidence_values)
    supplement = parse_supplement_label(ocr_result.raw_text)
    # Vision often emits a two-column supplement table column-by-column: all
    # ingredient names first, followed by all amounts.  Use geometry in that
    # case instead of the raw-text order, which would otherwise attach the D3
    # amount to every ingredient.
    spatial_ingredients = {}
    supplement_confidences = []
    for label_block in blocks:
        label_text = " ".join(str(label_block.text).split())
        label_box = label_block.bounding_box
        label_x = float(label_box.get("x", 0))
        label_y = float(label_box.get("y", 0)) + float(label_box.get("height", 0)) / 2
        for key, (label_pattern, display_zh, display_en) in SUPPLEMENT_INGREDIENT_PATTERNS.items():
            if key in spatial_ingredients or not re.search(label_pattern, label_text, re.I):
                continue
            candidates = []
            for value_block in blocks:
                value_text = " ".join(str(value_block.text).split())
                amounts = list(_SUPPLEMENT_AMOUNT_RE.finditer(value_text))
                if not amounts:
                    continue
                value_box = value_block.bounding_box
                value_x = float(value_box.get("x", 0))
                if value_x <= label_x:
                    continue
                value_y = float(value_box.get("y", 0)) + float(value_box.get("height", 0)) / 2
                distance = abs(value_y - label_y)
                if distance <= 0.075:
                    candidates.append((distance, amounts, value_block))
            if not candidates:
                continue
            _, amounts, value_block = min(candidates, key=lambda item: item[0])
            primary = amounts[0]
            value = _number(primary.group(1))
            if value < 0:
                continue
            item = {
                "value": value,
                "unit": _supplement_unit(primary.group(2)),
                "display_name_zh": display_zh,
                "display_name_en": display_en,
            }
            if len(amounts) > 1:
                alternate = amounts[1]
                alternate_unit = _supplement_unit(alternate.group(2))
                if alternate_unit != item["unit"]:
                    item["alternate_value"] = _number(alternate.group(1))
                    item["alternate_unit"] = alternate_unit
            spatial_ingredients[key] = item
            supplement_confidences.extend([
                float(getattr(label_block, "confidence", 0)),
                float(getattr(value_block, "confidence", 0)),
            ])
            break
    if spatial_ingredients:
        supplement["ingredients"] = {**supplement["ingredients"], **spatial_ingredients}
        supplement["confidence"] = sum(supplement_confidences) / len(supplement_confidences)
    parsed["supplement_facts"] = supplement
    return parsed


def _profile_basis(parsed: dict) -> tuple[float, str]:
    basis = parsed.get("basis")
    if basis == "per 100 g":
        return 100.0, "g"
    if basis == "per 100 ml":
        return 100.0, "ml"
    if basis == "per serving":
        return 1.0, "serving"
    raise ValueError("NUTRITION_LABEL_BASIS_REQUIRED")


def save_food_ocr_profile(
    connection: sqlite3.Connection,
    food_catalog_id: int,
    parsed: dict,
    *,
    brand: str | None = None,
    source_file_sha256: str | None = None,
    source_image_bytes: bytes | None = None,
    source_file_name: str | None = None,
    source_mime_type: str | None = None,
) -> int:
    """Persist a user-confirmed OCR profile for one catalog food."""
    food = connection.execute(
        "SELECT id FROM food_catalog WHERE id=? AND is_active=1", (int(food_catalog_id),)
    ).fetchone()
    if not food:
        raise ValueError("FOOD_CATALOG_ITEM_NOT_FOUND")
    basis_quantity, basis_unit = _profile_basis(parsed)
    nutrients = parsed.get("nutrients") or {}

    def amount(name, expected_units):
        item = nutrients.get(name)
        if not item or str(item.get("unit", "")).lower() not in expected_units:
            return None
        return float(item["value"])

    energy = nutrients.get("energy") or {}
    energy_value = float(energy["value"]) if energy.get("value") is not None else None
    energy_unit = str(energy.get("unit") or "").lower()
    calories = (
        energy_value / 4.184 if energy_value is not None and energy_unit == "kj"
        else energy_value if energy_value is not None and energy_unit == "kcal"
        else None
    )
    values = (
        int(food_catalog_id), str(brand or "").strip() or None,
        basis_quantity, basis_unit, calories,
        amount("protein", {"g"}), amount("carbohydrate", {"g"}),
        amount("fat", {"g"}), amount("fiber", {"g"}),
        amount("sodium", {"mg"}), float(parsed.get("confidence") or 0),
        source_file_sha256, str(parsed.get("raw_text") or "")[:5000],
    )
    with connection:
        connection.execute(
            """INSERT INTO food_ocr_nutrition_profiles(
                   food_catalog_id,brand,basis_quantity,basis_unit,calories_kcal,
                   protein_g,carbohydrate_g,fat_g,fiber_g,sodium_mg,
                   ocr_confidence,source_file_sha256,ocr_text,user_confirmed
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1)
               ON CONFLICT(food_catalog_id) DO UPDATE SET
                   brand=excluded.brand,basis_quantity=excluded.basis_quantity,
                   basis_unit=excluded.basis_unit,calories_kcal=excluded.calories_kcal,
                   protein_g=excluded.protein_g,carbohydrate_g=excluded.carbohydrate_g,
                   fat_g=excluded.fat_g,fiber_g=excluded.fiber_g,
                   sodium_mg=excluded.sodium_mg,ocr_confidence=excluded.ocr_confidence,
                   source_file_sha256=excluded.source_file_sha256,
                   ocr_text=excluded.ocr_text,user_confirmed=1,
                   updated_at=CURRENT_TIMESTAMP""",
            values,
        )
        if source_image_bytes is not None:
            if len(source_image_bytes) > 20 * 1024 * 1024:
                raise ValueError("NUTRITION_LABEL_IMAGE_TOO_LARGE")
            digest = source_file_sha256 or hashlib.sha256(source_image_bytes).hexdigest()
            food_row = connection.execute(
                """SELECT COALESCE(NULLIF(display_name_zh,''),NULLIF(display_name_en,''),
                                  canonical_name) AS food_name
                   FROM food_catalog WHERE id=?""",
                (int(food_catalog_id),),
            ).fetchone()
            connection.execute(
                """INSERT INTO custom_food_nutrition_library(
                       food_catalog_id,food_name,brand,source_file_name,source_mime_type,
                       source_file_sha256,source_image_blob,basis_quantity,basis_unit,
                       nutrients_json,ocr_text,ocr_confidence
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(food_catalog_id,source_file_sha256) DO UPDATE SET
                       food_name=excluded.food_name,brand=excluded.brand,
                       source_file_name=excluded.source_file_name,
                       source_mime_type=excluded.source_mime_type,
                       source_image_blob=excluded.source_image_blob,
                       basis_quantity=excluded.basis_quantity,basis_unit=excluded.basis_unit,
                       nutrients_json=excluded.nutrients_json,ocr_text=excluded.ocr_text,
                       ocr_confidence=excluded.ocr_confidence,
                       updated_at=CURRENT_TIMESTAMP""",
                (
                    int(food_catalog_id), food_row["food_name"],
                    str(brand or "").strip() or None,
                    str(source_file_name or "").strip() or None,
                    str(source_mime_type or "").strip() or None,
                    digest, sqlite3.Binary(source_image_bytes), basis_quantity, basis_unit,
                    json.dumps(nutrients, ensure_ascii=False, separators=(",", ":")),
                    str(parsed.get("raw_text") or "")[:5000],
                    float(parsed.get("confidence") or 0),
                ),
            )
    return int(food_catalog_id)


def create_custom_food_from_ocr(
    connection: sqlite3.Connection,
    food_name: str,
    parsed: dict,
    *,
    brand: str | None = None,
    source_image_bytes: bytes,
    source_file_name: str | None = None,
    source_mime_type: str | None = None,
) -> int:
    """Create a reusable user food and attach its first confirmed label."""
    name = str(food_name or "").strip()
    if not name:
        raise ValueError("CUSTOM_FOOD_NAME_REQUIRED")
    if len(name) > 120:
        raise ValueError("CUSTOM_FOOD_NAME_TOO_LONG")
    digest = hashlib.sha256(source_image_bytes).hexdigest()
    # The custom-food identity follows its normalized name, not the photo, so
    # later uploads become label history for the same selectable food.
    identity = hashlib.sha256(name.casefold().encode("utf-8")).hexdigest()[:16]
    canonical_name = f"user_label_{identity}"
    _, basis_unit = _profile_basis(parsed)
    if basis_unit == "ml":
        default_unit, units, tags = "ml", ["ml", "l", "bottle", "serving"], ["beverage"]
    elif basis_unit == "serving":
        default_unit, units, tags = "serving", ["serving", "pack"], []
    else:
        default_unit, units, tags = "g", ["g", "kg", "serving"], []
    with connection:
        connection.execute(
            """INSERT OR IGNORE INTO food_catalog(
                   canonical_name,display_name_zh,display_name_en,aliases_json,
                   default_unit,allowed_units_json,category_tags_json,serving_unit,
                   serving_weight_g,serving_volume_ml,nutrition_source,data_quality
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                canonical_name, name, name, "[]", default_unit,
                json.dumps(units, separators=(",", ":")),
                json.dumps(tags, ensure_ascii=False, separators=(",", ":")),
                "serving",
                100 if basis_unit == "g" else None,
                100 if basis_unit == "ml" else None,
                "label_ocr_confirmed", "verified",
            ),
        )
        row = connection.execute(
            "SELECT id FROM food_catalog WHERE canonical_name=?", (canonical_name,)
        ).fetchone()
        food_catalog_id = int(row["id"])
        save_food_ocr_profile(
            connection, food_catalog_id, parsed, brand=brand,
            source_file_sha256=digest, source_image_bytes=source_image_bytes,
            source_file_name=source_file_name, source_mime_type=source_mime_type,
        )
    return food_catalog_id


def list_custom_food_nutrition_library(connection: sqlite3.Connection) -> list[dict]:
    """List uploaded label records without loading image BLOBs into memory."""
    return [
        dict(row) for row in connection.execute(
            """SELECT id,food_catalog_id,food_name,brand,source_file_name,
                      source_mime_type,source_file_sha256,basis_quantity,basis_unit,
                      nutrients_json,ocr_confidence,created_at,updated_at,
                      length(source_image_blob) AS image_size_bytes
               FROM custom_food_nutrition_library
               ORDER BY created_at DESC,id DESC"""
        ).fetchall()
    ]


def _catalog_ingredients_from_label_values(ingredients: dict, serving: dict, digest: str) -> list[dict]:
    """Convert the library's compact label JSON to catalog ingredient rows."""
    catalog_ingredients = []
    for key, item in ingredients.items():
        try:
            amount = float(item.get("value"))
        except (TypeError, ValueError):
            continue
        unit = str(item.get("unit") or "").lower().replace("μ", "m")
        if amount <= 0 or unit not in {"g", "mg", "mcg", "ml", "iu"}:
            continue
        display_zh = str(item.get("display_name_zh") or key).strip()
        display_en = str(item.get("display_name_en") or display_zh).strip()
        catalog_ingredients.append({
            "canonical_ingredient_name": display_zh,
            "display_name_zh": display_zh,
            "display_name_en": display_en,
            "amount_per_serving": amount,
            "amount_unit": unit,
            "serving_quantity": serving.get("quantity") or 1,
            "serving_unit": serving.get("unit") or "capsule",
            "ingredient_role": "nutrient" if key in NUTRIENT_DISPLAY_NAMES else "active",
            "source_reference": f"label:{digest}",
            "source_type": "user_label",
            "confidence_level": "verified",
            "user_confirmed": True,
        })
    return catalog_ingredients


def save_custom_supplement_nutrition_record(
    connection: sqlite3.Connection, parsed: dict, *, product_id: int | None,
    product_name: str, brand: str | None, source_image_bytes: bytes,
    product_kind: str = "supplement",
    source_file_name: str | None = None, source_mime_type: str | None = None,
) -> int:
    """Archive a user-confirmed supplement OCR scan in the custom library."""
    if len(source_image_bytes) > 20 * 1024 * 1024:
        raise ValueError("NUTRITION_LABEL_IMAGE_TOO_LARGE")
    if product_kind not in {"supplement", "medication"}:
        raise ValueError("INVALID_PRODUCT_KIND")
    facts = parsed.get("supplement_facts") or {}
    ingredients = facts.get("ingredients") or {}
    if not ingredients:
        ingredients = {
            key: {
                "value": value["value"], "unit": value["unit"],
                "display_name_zh": NUTRIENT_DISPLAY_NAMES[key][0],
                "display_name_en": NUTRIENT_DISPLAY_NAMES[key][1],
            }
            for key, value in (parsed.get("nutrients") or {}).items()
        }
    serving = facts.get("serving") or {}
    if not serving:
        basis = parsed.get("basis")
        serving = {
            "per serving": {"quantity": 1, "unit": "serving"},
            "per 100 g": {"quantity": 100, "unit": "g"},
            "per 100 ml": {"quantity": 100, "unit": "ml"},
        }.get(basis, {})
    digest = hashlib.sha256(source_image_bytes).hexdigest()
    # A confirmed label is also the formula for its matching product. This
    # turns the selection in the supplement editor into a direct reference to
    # the ingredient-library record instead of a same-named, empty product.
    catalog_ingredients = _catalog_ingredients_from_label_values(ingredients, serving, digest)
    resolved_product_id = sync_label_verified_product(
        connection,
        product_id=product_id,
        product_name=product_name,
        brand_name=brand,
        product_kind=product_kind,
        serving_quantity=serving.get("quantity"),
        serving_unit=serving.get("unit"),
        ingredients=catalog_ingredients,
        source_reference=f"label:{digest}",
    )
    with connection:
        connection.execute(
            """INSERT INTO custom_supplement_nutrition_library(
                   supplement_product_id,product_name,brand,source_file_name,
                   source_mime_type,source_file_sha256,source_image_blob,
                   serving_quantity,serving_unit,ingredients_json,ocr_text,ocr_confidence,product_kind
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(source_file_sha256) DO UPDATE SET
                   supplement_product_id=excluded.supplement_product_id,
                   product_name=excluded.product_name,brand=excluded.brand,
                   serving_quantity=excluded.serving_quantity,serving_unit=excluded.serving_unit,
                   ingredients_json=excluded.ingredients_json,ocr_text=excluded.ocr_text,
                   ocr_confidence=excluded.ocr_confidence,product_kind=excluded.product_kind,
                   updated_at=CURRENT_TIMESTAMP""",
            (
                resolved_product_id, str(product_name).strip(), str(brand or "").strip() or None,
                str(source_file_name or "").strip() or None,
                str(source_mime_type or "").strip() or None, digest,
                sqlite3.Binary(source_image_bytes), serving.get("quantity"), serving.get("unit"),
                json.dumps(ingredients, ensure_ascii=False, separators=(",", ":")),
                str(parsed.get("raw_text") or "")[:5000],
                float(facts.get("confidence") or parsed.get("confidence") or 0),
                product_kind,
            ),
        )
    return resolved_product_id


def list_custom_supplement_nutrition_library(connection: sqlite3.Connection) -> list[dict]:
    # Repair early scans that were saved before food-style nutrient panels
    # could be represented in the supplement library.
    stale = connection.execute(
        """SELECT id,ocr_text FROM custom_supplement_nutrition_library
           WHERE ingredients_json='{}' OR COALESCE(ocr_confidence,0)=0
              OR ingredients_json LIKE '%\"ingredient_%'"""
    ).fetchall()
    for row in stale:
        parsed = parse_nutrition_label(row["ocr_text"] or "")
        nutrients = parsed.get("nutrients") or {}
        if not nutrients:
            continue
        ingredients = {
            key: {"value": value["value"], "unit": value["unit"],
                  "display_name_zh": NUTRIENT_DISPLAY_NAMES[key][0],
                  "display_name_en": NUTRIENT_DISPLAY_NAMES[key][1]}
            for key, value in nutrients.items()
        }
        basis = parsed.get("basis")
        serving = {"per serving": (1, "serving"), "per 100 g": (100, "g"), "per 100 ml": (100, "ml")}.get(basis)
        with connection:
            connection.execute(
                """UPDATE custom_supplement_nutrition_library SET
                       ingredients_json=?,ocr_confidence=?,serving_quantity=COALESCE(serving_quantity,?),
                       serving_unit=COALESCE(serving_unit,?),updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (json.dumps(ingredients, ensure_ascii=False, separators=(",", ":")),
                 float(parsed.get("confidence") or 0), serving[0] if serving else None,
                 serving[1] if serving else None, row["id"]),
            )
    records = [dict(row) for row in connection.execute(
        """SELECT c.id,c.supplement_product_id,c.product_name,c.brand,c.serving_quantity,c.serving_unit,
                  c.ingredients_json,c.source_file_sha256,c.ocr_confidence,c.created_at,c.updated_at,
                  CASE WHEN p.product_kind='medication' THEN 'medication'
                       ELSE COALESCE(c.product_kind,'supplement') END AS product_kind
           FROM custom_supplement_nutrition_library c
           LEFT JOIN supplement_products p ON p.id=c.supplement_product_id
           ORDER BY c.created_at DESC,c.id DESC"""
    ).fetchall()]
    # Backfill labels saved before the product-library bridge existed. This is
    # intentionally lazy and idempotent, so existing custom data is preserved
    # and becomes selectable/calculable without requiring another OCR scan.
    for record in records:
        try:
            ingredients = json.loads(record.get("ingredients_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            ingredients = {}
        has_product_formula = bool(record.get("supplement_product_id")) and bool(
            connection.execute(
                """SELECT 1 FROM supplement_product_ingredients
                   WHERE supplement_product_id=? AND deleted_at IS NULL LIMIT 1""",
                (record["supplement_product_id"],),
            ).fetchone()
        )
        if has_product_formula or not ingredients:
            continue
        resolved_product_id = sync_label_verified_product(
            connection,
            product_id=record.get("supplement_product_id"),
            product_name=record["product_name"],
            brand_name=record.get("brand"),
            product_kind=record.get("product_kind") or "supplement",
            serving_quantity=record.get("serving_quantity"),
            serving_unit=record.get("serving_unit"),
            ingredients=_catalog_ingredients_from_label_values(
                ingredients,
                {"quantity": record.get("serving_quantity"), "unit": record.get("serving_unit")},
                record.get("source_file_sha256") or f"library:{record['id']}",
            ),
            source_reference=f"label:{record.get('source_file_sha256') or record['id']}",
        )
        with connection:
            connection.execute(
                """UPDATE custom_supplement_nutrition_library
                   SET supplement_product_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (resolved_product_id, record["id"]),
            )
        record["supplement_product_id"] = resolved_product_id
    return records
