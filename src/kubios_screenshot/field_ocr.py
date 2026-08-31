import re
import tempfile
from collections import Counter
from pathlib import Path
from statistics import mean

from .models import ParsedField, ParseResult
from .region_extractor import extract_region, preprocessing_candidates
from .validation import parse_date, parse_time, validate_value


ALLOWED_PATTERNS = {
    "numeric_decimal": re.compile(r"[^0-9.,+\-]"),
    "integer": re.compile(r"[^0-9]"),
    "time": re.compile(r"[^0-9:]"),
    "date": re.compile(r"[^0-9./\-]"),
    "status_text": re.compile(r"[^A-Za-z ]"),
}


def sanitize_candidate(text, field_type):
    text = str(text or "").strip()
    if field_type != "status_text":
        text = text.replace("O", "0").replace("o", "0")
    cleaner = ALLOWED_PATTERNS[field_type]
    return cleaner.sub("", text).strip()


def normalize_candidate(text, field, field_type, config=None):
    cleaned = sanitize_candidate(text, field_type)
    if field_type == "date":
        return parse_date(cleaned, config)
    if field_type == "time":
        return parse_time(cleaned, config)
    if field_type in {"numeric_decimal", "integer"}:
        if not cleaned:
            return None
        if "," in cleaned and "." not in cleaned:
            cleaned = cleaned.replace(",", ".")
        try:
            value = float(cleaned)
        except ValueError:
            return None
        if field_type == "integer":
            value = int(round(value))
        valid, _ = validate_value(field, value, config)
        return value if valid else None
    return cleaned or None


def recognize_field(crop, field, field_definition, adapter, config=None):
    field_type = field_definition["field_type"]
    observations = []
    with tempfile.TemporaryDirectory() as directory:
        for name, candidate_image in preprocessing_candidates(crop).items():
            path = Path(directory) / f"{name}.png"
            candidate_image.save(path, format="PNG")
            try:
                ocr = adapter.recognize(path)
            except Exception:
                continue
            for block in ocr.text_blocks[:2]:
                value = normalize_candidate(block.text, field, field_type, config)
                observations.append({
                    "profile": name,
                    "text": sanitize_candidate(block.text, field_type)[:64],
                    "value": value,
                    "ocr_confidence": block.confidence,
                    "valid": value is not None,
                })
    valid = [item for item in observations if item["valid"]]
    if not valid:
        return None
    counts = Counter(str(item["value"]) for item in valid)
    winner_text, winner_count = counts.most_common(1)[0]
    winner_items = [item for item in valid if str(item["value"]) == winner_text]
    value = winner_items[0]["value"]
    agreement = winner_count / len(valid)
    ocr_score = mean(item["ocr_confidence"] for item in winner_items)
    score = round(min(1.0, agreement * 0.5 + ocr_score * 0.35 + 0.15), 3)
    safe_candidates = [
        {"profile": item["profile"], "value": item["value"],
         "confidence": round(item["ocr_confidence"], 3), "valid": item["valid"]}
        for item in observations
    ]
    return ParsedField(
        value=value,
        confidence=score,
        source_text="region_numeric_ocr",
        unit=field_definition.get("expected_unit"),
        candidates=safe_candidates,
        candidates_consistent=agreement >= 0.67,
    )


def parse_template_regions(image_path, template, adapter, config=None):
    config = config or {}
    capture_fields = set(config.get("capture_fields", ()))
    fields = {}
    warnings = []
    for field, definition in template["field_regions"].items():
        if capture_fields and field not in capture_fields:
            continue
        crop = extract_region(image_path, definition)
        parsed = recognize_field(crop, field, definition, adapter, config)
        if parsed:
            fields[field] = parsed
        else:
            warnings.append(f"{field}:region_ocr_failed")
    required = config.get("minimum_required_fields", ["rmssd", "mean_hr"])
    missing = [field for field in required if field not in fields]
    required_scores = [fields[field].confidence for field in required if field in fields]
    overall = round(mean(required_scores), 3) if required_scores else 0.0
    if missing:
        overall = max(0.0, round(overall - 0.18 * len(missing), 3))
    return ParseResult(fields, missing, warnings, config.get("parser_version", "1.3.0"), overall, True)
