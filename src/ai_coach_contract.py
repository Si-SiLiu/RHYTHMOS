"""Pure, fail-closed validation for future AI Coach input and output objects."""

import copy
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping


BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = BASE_DIR / "config"
CONTRACT_PATH = CONFIG_DIR / "ai_coach_contract.json"
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\s().-]*){8,15}(?!\d)")
CREDENTIAL_RE = re.compile(
    r"(?i)(?:access[_ -]?token|refresh[_ -]?token|api[_ -]?key|client[_ -]?secret|authorization\s*:)"
)
HTML_RE = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")
URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)\S+")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class AIContractError(ValueError):
    """Raised when an AI Coach contract or payload fails safe validation."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AIContractError(f"Unable to load AI contract: {path.name}") from exc
    if not isinstance(value, dict):
        raise AIContractError(f"AI contract must be an object: {path.name}")
    return value


def load_contract() -> dict[str, Any]:
    """Load and validate contract metadata without network or database access."""

    contract = _load_json(CONTRACT_PATH)
    required = {
        "prompt_version",
        "output_schema_version",
        "safety_policy_version",
        "provider_mode",
        "input_schema",
        "output_schema",
    }
    if set(contract) != required:
        raise AIContractError("AI contract metadata fields do not match authority")
    for key in (
        "prompt_version",
        "output_schema_version",
        "safety_policy_version",
    ):
        if not isinstance(contract[key], str) or not SEMVER_RE.fullmatch(contract[key]):
            raise AIContractError(f"AI contract version is invalid: {key}")
    if contract["provider_mode"] not in {"cloud_zdr", "cloud_standard_retention"}:
        raise AIContractError("AI provider mode is invalid")
    for key in ("input_schema", "output_schema"):
        name = contract[key]
        if not isinstance(name, str) or Path(name).name != name or not name.endswith(".json"):
            raise AIContractError(f"AI schema filename is invalid: {key}")
    return copy.deepcopy(contract)


def _validate_format(value: str, format_name: str, path: str) -> None:
    try:
        if format_name == "date":
            parsed = date.fromisoformat(value)
            if parsed.isoformat() != value:
                raise ValueError
        elif format_name == "date-time":
            parsed_datetime = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed_datetime.tzinfo is None:
                raise ValueError
        else:
            raise AIContractError(f"Unsupported schema format at {path}")
    except ValueError as exc:
        raise AIContractError(f"Invalid {format_name} at {path}") from exc


def _validate_schema(value: Any, schema: Mapping[str, Any], path: str = "$") -> None:
    if "const" in schema and value != schema["const"]:
        raise AIContractError(f"Contract constant mismatch at {path}")
    expected_type = schema.get("type")
    if expected_type == "object":
        if not isinstance(value, Mapping):
            raise AIContractError(f"Expected object at {path}")
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        missing = required - set(value)
        if missing:
            raise AIContractError(f"Missing required fields at {path}: {sorted(missing)}")
        unknown = set(value) - set(properties)
        if schema.get("additionalProperties") is False and unknown:
            raise AIContractError(f"Unknown fields at {path}: {sorted(unknown)}")
        for key, child in value.items():
            if key in properties:
                _validate_schema(child, properties[key], f"{path}.{key}")
        return
    if expected_type == "array":
        if not isinstance(value, list):
            raise AIContractError(f"Expected array at {path}")
        if len(value) > schema.get("maxItems", len(value)):
            raise AIContractError(f"Too many items at {path}")
        for index, item in enumerate(value):
            _validate_schema(item, schema["items"], f"{path}[{index}]")
        return
    if expected_type == "string":
        if not isinstance(value, str):
            raise AIContractError(f"Expected string at {path}")
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", len(value)):
            raise AIContractError(f"String length is invalid at {path}")
        if "enum" in schema and value not in schema["enum"]:
            raise AIContractError(f"Value is not allowlisted at {path}")
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value):
            raise AIContractError(f"String pattern is invalid at {path}")
        if "format" in schema:
            _validate_format(value, schema["format"], path)
        return
    if expected_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise AIContractError(f"Expected integer at {path}")
        if value < schema.get("minimum", value) or value > schema.get("maximum", value):
            raise AIContractError(f"Integer range is invalid at {path}")
        return
    if "enum" in schema and value not in schema["enum"]:
        raise AIContractError(f"Value is not allowlisted at {path}")


def _reject_sensitive_input(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            _reject_sensitive_input(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_sensitive_input(child, f"{path}[{index}]")
    elif isinstance(value, str):
        has_question_identifier = path == "$.user_question" and (
            EMAIL_RE.search(value) or PHONE_RE.search(value)
        )
        if CONTROL_RE.search(value) or CREDENTIAL_RE.search(value) or has_question_identifier:
            raise AIContractError(f"Sensitive or unsafe text rejected at {path}")


def _reject_unsafe_output(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            _reject_unsafe_output(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_unsafe_output(child, f"{path}[{index}]")
    elif isinstance(value, str) and (
        CONTROL_RE.search(value)
        or HTML_RE.search(value)
        or URL_RE.search(value)
        or CREDENTIAL_RE.search(value)
    ):
        raise AIContractError(f"Unsafe output text rejected at {path}")


def _load_schema(contract_key: str) -> tuple[dict[str, Any], dict[str, Any]]:
    contract = load_contract()
    return contract, _load_json(CONFIG_DIR / contract[contract_key])


def validate_input(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and copy an outbound input object; never performs I/O beyond config reads."""

    contract, schema = _load_schema("input_schema")
    _reject_sensitive_input(payload)
    _validate_schema(payload, schema)
    if payload["contract_versions"] != {
        "prompt_version": contract["prompt_version"],
        "output_schema_version": contract["output_schema_version"],
        "safety_policy_version": contract["safety_policy_version"],
    }:
        raise AIContractError("Input contract versions do not match authority")
    return copy.deepcopy(dict(payload))


def validate_output(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and copy untrusted model output before persistence or display."""

    contract, schema = _load_schema("output_schema")
    _reject_unsafe_output(payload)
    _validate_schema(payload, schema)
    audit = payload["audit"]
    for key in ("prompt_version", "output_schema_version", "safety_policy_version"):
        if audit[key] != contract[key]:
            raise AIContractError(f"Output contract version mismatch: {key}")
    if audit["provider_mode"] != contract["provider_mode"]:
        raise AIContractError("Output provider mode mismatch")
    return copy.deepcopy(dict(payload))
