"""Validated central configuration for Local Coach rules."""

import copy
import json
import re
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[2]
RULES_PATH = BASE_DIR / "config" / "local_coach_rules.json"
SCHEMA_PATH = BASE_DIR / "config" / "local_coach_output.schema.json"
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class LocalCoachConfigError(ValueError):
    pass


def _read_json(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LocalCoachConfigError(f"Unable to load {Path(path).name}") from exc
    if not isinstance(value, dict):
        raise LocalCoachConfigError(f"{Path(path).name} must contain an object")
    return value


def load_rules(path=RULES_PATH) -> dict[str, Any]:
    rules = _read_json(path)
    required = {
        "rule_config_version", "template_version", "clinically_validated",
        "recovery_score_thresholds", "confidence_thresholds",
        "minimum_data_completeness", "sleep_insufficient_hours",
        "sleep_score_low", "high_load_score", "freshness_days",
        "training_high_duration_minutes", "training_high_rpe_load",
        "neural_fatigue_high", "neural_heaviness_high", "neural_lapse_high",
        "nutrition_min_completeness",
        "training_adjustments", "fixed_schedule",
    }
    if set(rules) != required:
        raise LocalCoachConfigError("Local Coach rule fields do not match authority")
    for key in ("rule_config_version", "template_version"):
        if not isinstance(rules[key], str) or not SEMVER_RE.fullmatch(rules[key]):
            raise LocalCoachConfigError(f"Invalid Local Coach version: {key}")
    if rules["clinically_validated"] is not False:
        raise LocalCoachConfigError("Local Coach must not claim clinical validation")
    recovery = rules["recovery_score_thresholds"]
    confidence = rules["confidence_thresholds"]
    if not (100 >= recovery["high"] > recovery["medium"] > recovery["low"] >= 0):
        raise LocalCoachConfigError("Recovery thresholds are invalid")
    if not (100 >= confidence["high"] > confidence["medium"] > confidence["low"] >= 0):
        raise LocalCoachConfigError("Confidence thresholds are invalid")
    if not 0 <= rules["minimum_data_completeness"] <= 100:
        raise LocalCoachConfigError("Completeness threshold is invalid")
    for key in ("training_high_duration_minutes", "training_high_rpe_load",
                "neural_fatigue_high", "neural_heaviness_high", "neural_lapse_high",
                "nutrition_min_completeness"):
        if not isinstance(rules[key], (int, float)) or rules[key] < 0:
            raise LocalCoachConfigError(f"Invalid combined coaching threshold: {key}")
    expected_adjustments = {"normal", "moderate_reduction", "major_reduction", "technique_only", "mobility_only", "rest"}
    if set(rules["training_adjustments"]) != expected_adjustments:
        raise LocalCoachConfigError("Training adjustment keys are invalid")
    for values in rules["training_adjustments"].values():
        if set(values) != {"volume", "intensity"} or not all(-100 <= value <= 0 for value in values.values()):
            raise LocalCoachConfigError("Training adjustment values are invalid")
    if rules["fixed_schedule"] != {
        "morning_strength": "09:00–11:00",
        "evening_hip_hop": "19:30–21:00",
    }:
        raise LocalCoachConfigError("Fixed schedule is invalid")
    return copy.deepcopy(rules)


def load_output_schema(path=SCHEMA_PATH):
    return _read_json(path)


def validate_output(value, schema=None):
    schema = schema or load_output_schema()

    def resolve(node):
        if "$ref" not in node:
            return node
        prefix = "#/$defs/"
        reference = node["$ref"]
        if not reference.startswith(prefix):
            raise LocalCoachConfigError("Unsupported Local Coach schema reference")
        return schema["$defs"][reference[len(prefix):]]

    def check(item, node, path="$"):
        node = resolve(node)
        if "const" in node and item != node["const"]:
            raise LocalCoachConfigError(f"Local Coach constant mismatch at {path}")
        expected = node.get("type")
        if isinstance(expected, list):
            allowed = []
            for name in expected:
                allowed.append({"integer": int, "null": type(None)}[name])
            if isinstance(item, bool) or not isinstance(item, tuple(allowed)):
                raise LocalCoachConfigError(f"Local Coach type mismatch at {path}")
        elif expected == "object":
            if not isinstance(item, dict):
                raise LocalCoachConfigError(f"Expected object at {path}")
            properties = node.get("properties", {})
            missing = set(node.get("required", [])) - set(item)
            unknown = set(item) - set(properties)
            if missing or (node.get("additionalProperties") is False and unknown):
                raise LocalCoachConfigError(f"Local Coach object mismatch at {path}")
            for key, child in item.items():
                if key in properties:
                    check(child, properties[key], f"{path}.{key}")
            return
        elif expected == "array":
            if not isinstance(item, list):
                raise LocalCoachConfigError(f"Expected array at {path}")
            if len(item) < node.get("minItems", 0) or len(item) > node.get("maxItems", len(item)):
                raise LocalCoachConfigError(f"Local Coach array size mismatch at {path}")
            for index, child in enumerate(item):
                check(child, node["items"], f"{path}[{index}]")
            return
        elif expected == "string":
            if not isinstance(item, str):
                raise LocalCoachConfigError(f"Expected string at {path}")
            if len(item) < node.get("minLength", 0) or len(item) > node.get("maxLength", len(item)):
                raise LocalCoachConfigError(f"Local Coach string size mismatch at {path}")
        elif expected == "integer":
            if isinstance(item, bool) or not isinstance(item, int):
                raise LocalCoachConfigError(f"Expected integer at {path}")
        elif expected == "boolean" and not isinstance(item, bool):
            raise LocalCoachConfigError(f"Expected boolean at {path}")
        if item is not None and "minimum" in node and item < node["minimum"]:
            raise LocalCoachConfigError(f"Local Coach minimum mismatch at {path}")
        if item is not None and "maximum" in node and item > node["maximum"]:
            raise LocalCoachConfigError(f"Local Coach maximum mismatch at {path}")
        if "enum" in node and item not in node["enum"]:
            raise LocalCoachConfigError(f"Local Coach value mismatch at {path}")
        if node.get("format") == "date":
            from datetime import date
            try:
                if date.fromisoformat(item).isoformat() != item:
                    raise ValueError
            except (TypeError, ValueError) as exc:
                raise LocalCoachConfigError(f"Local Coach date mismatch at {path}") from exc

    check(value, schema)
    return copy.deepcopy(value)
