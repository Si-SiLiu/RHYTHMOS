import re

from .confidence import field_confidence, overall_confidence
from .config import load_config
from .field_mapping import match_field_label, normalized_label
from .models import OCRResult, ParsedField, ParseResult
from .validation import NUMERIC_FIELDS, parse_date, parse_time, validate_value


NUMBER_RE = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:[.,]\d+)?")
DATE_CANDIDATES = (
    re.compile(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b"),
    re.compile(r"\b\d{1,2}[./]\d{1,2}[./]\d{4}\b"),
    re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{1,2},\s+\d{4}\b", re.I),
)
TIME_RE = re.compile(r"\b(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?(?:\s*[AP]M)?\b", re.I)


def _candidate_value(field, text, config):
    if field == "date":
        for pattern in DATE_CANDIDATES:
            match = pattern.search(text)
            if match:
                value = parse_date(match.group(0), config)
                if value:
                    return value, None
        return None, None
    if field == "measurement_time":
        match = TIME_RE.search(text)
        return (parse_time(match.group(0), config), None) if match else (None, None)
    if field in {"recovery_status", "measurement_quality", "mood_code"}:
        cleaned = str(text).strip()
        if ":" in cleaned:
            cleaned = cleaned.split(":", 1)[1].strip()
        return (cleaned, None) if cleaned and not NUMBER_RE.fullmatch(cleaned) else (None, None)
    match = NUMBER_RE.search(text)
    if match:
        number = float(match.group(0).replace(",", "."))
        unit = next((u for u in config["expected_units"].get(field, []) if re.search(rf"\b{re.escape(u)}\b|{re.escape(u)}", text, re.I)), None)
        return number, unit
    if field == "readiness":
        cleaned = re.sub(r"^[^:]*:?\s*", "", text).strip()
        if cleaned:
            return cleaned, None
    return None, None


def _source_without_label(text, alias):
    # Alias tokens and visual tokens are not always one-to-one: ``(n.u.)`` is
    # one visual token but three normalized tokens. Consume the original text
    # up to the exact normalized alias instead of counting whitespace words.
    for end in range(1, len(text) + 1):
        if normalized_label(text[:end]) == alias:
            return text[end:].lstrip(": ")
    return text


def parse_ocr_result(ocr_result: OCRResult, config=None):
    config = config or load_config()
    blocks = [block for block in ocr_result.text_blocks if block.text.strip()]
    fields = {}
    warnings = list(ocr_result.processing_warnings)

    capture_fields = set(config["capture_fields"])
    for index, block in enumerate(blocks):
        field, alias = match_field_label(block.text, config)
        if not field or field not in capture_fields or field in fields:
            continue
        same_line = _source_without_label(block.text, alias)
        value, unit = _candidate_value(field, same_line, config)
        adjacent = False
        source = block.text
        confidence_values = [block.confidence]
        if value is None and index + 1 < len(blocks):
            next_block = blocks[index + 1]
            value, unit = _candidate_value(field, next_block.text, config)
            if value is not None:
                adjacent = True
                source = f"{block.text} | {next_block.text}"
                confidence_values.append(next_block.confidence)
        if value is None:
            continue
        valid, code = validate_value(field, value, config)
        expected = config["expected_units"].get(field, [])
        unit_match = not expected or unit is not None
        score = field_confidence(
            min(confidence_values), label_exact=normalized_label(block.text) == alias
            or _source_without_label(block.text, alias) != block.text,
            unit_match=unit_match, value_valid=valid, adjacent=adjacent,
        )
        if not valid:
            warnings.append(f"{field}:{code}")
            continue
        fields[field] = ParsedField(value, score, source[:160], unit)

    missing = [name for name in config["minimum_required_fields"] if name not in fields]
    score = overall_confidence(fields, missing, config)
    return ParseResult(fields, missing, warnings, config["parser_version"], score, True)


def merge_parse_results(primary: ParseResult, supplement: ParseResult, config=None):
    """Add valid fields recovered by a focused second OCR pass.

    Existing values always win. A retry is only evidence for a field that was
    absent, never a reason to silently overwrite the first visible reading.
    """
    config = config or load_config()
    fields = dict(primary.fields)
    fields.update({name: value for name, value in supplement.fields.items() if name not in fields})
    missing = [name for name in config["minimum_required_fields"] if name not in fields]
    warnings = list(dict.fromkeys([*primary.warnings, *supplement.warnings]))
    return ParseResult(
        fields,
        missing,
        warnings,
        config["parser_version"],
        overall_confidence(fields, missing, config),
        True,
    )
