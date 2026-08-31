"""Closed-schema, provider-independent outbound context construction."""

import copy
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from src.ai_coach_approval import APPROVAL_PATH, require_cloud_call_approval
from src.ai_coach_contract import AIContractError, load_contract, validate_input


REQUIRED_SOURCE_FIELDS = {
    "analysis_date",
    "recovery",
    "confidence",
    "daily_metrics",
    "nutrition",
    "baseline_context",
    "presentation",
}
OPTIONAL_SOURCE_FIELDS = {"user_question"}
ALLOWED_SOURCE_FIELDS = REQUIRED_SOURCE_FIELDS | OPTIONAL_SOURCE_FIELDS


class AIContextError(ValueError):
    """Raised with constant safe text when a context source is not allowlisted."""


def build_context(source: Mapping[str, Any]) -> dict[str, Any]:
    """Project a closed source object and inject authoritative contract versions."""

    try:
        if not isinstance(source, Mapping) or set(source) - ALLOWED_SOURCE_FIELDS:
            raise AIContextError("AI context source is not allowed")
        if REQUIRED_SOURCE_FIELDS - set(source):
            raise AIContextError("AI context source is not allowed")
        contract = load_contract()
        context = {
            "analysis_date": copy.deepcopy(source["analysis_date"]),
            "recovery": copy.deepcopy(source["recovery"]),
            "confidence": copy.deepcopy(source["confidence"]),
            "daily_metrics": copy.deepcopy(source["daily_metrics"]),
            "nutrition": copy.deepcopy(source["nutrition"]),
            "baseline_context": copy.deepcopy(source["baseline_context"]),
            "presentation": copy.deepcopy(source["presentation"]),
            "contract_versions": {
                "prompt_version": contract["prompt_version"],
                "output_schema_version": contract["output_schema_version"],
                "safety_policy_version": contract["safety_policy_version"],
            },
        }
        if "user_question" in source:
            context["user_question"] = copy.deepcopy(source["user_question"])
        return validate_input(context)
    except (AIContractError, KeyError, TypeError) as exc:
        raise AIContextError("AI context source is not allowed") from exc


def build_approved_context(
    source: Mapping[str, Any],
    *,
    now: datetime,
    approval_path: Path = APPROVAL_PATH,
) -> dict[str, Any]:
    """Require cloud approval before constructing any provider-bound context."""

    require_cloud_call_approval(now=now, path=approval_path)
    return build_context(source)
