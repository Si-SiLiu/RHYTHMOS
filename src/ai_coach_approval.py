"""Fail-closed provider approval gate for AI Coach cloud calls."""

import copy
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from src.ai_coach_contract import CONFIG_DIR, SEMVER_RE, load_contract


APPROVAL_PATH = CONFIG_DIR / "ai_coach_provider_approval.json"
STATUSES = {"blocked", "approved", "expired", "revoked"}
REVIEW_STATES = {"pending", "approved", "rejected"}
BLOCKED_REASONS = {
    "provider_not_eligible",
    "evidence_missing",
    "evidence_expired",
    "approval_revoked",
    "configuration_drift",
}
REQUIRED_FIELDS = {
    "approval_record_version",
    "status",
    "implementation_authorization",
    "data_retention_mode",
    "provider_id",
    "model_snapshot",
    "endpoint",
    "processing_region",
    "region_supported",
    "zdr_verified",
    "no_training_verified",
    "human_review_disabled",
    "subprocessors_accepted",
    "retention_terms_accepted",
    "product_owner_approval",
    "chief_architect_review",
    "evidence_effective_at",
    "evidence_expires_at",
    "configuration_fingerprint",
    "blocked_reason",
}
RETENTION_MODES = {"zero_data_retention", "standard_api_retention"}
CONTROL_FIELDS = (
    "region_supported",
    "zdr_verified",
    "no_training_verified",
    "human_review_disabled",
    "subprocessors_accepted",
    "retention_terms_accepted",
)
IDENTITY_FIELDS = (
    "provider_id",
    "model_snapshot",
    "endpoint",
    "processing_region",
)


class AIApprovalError(RuntimeError):
    """Raised without sensitive detail when a cloud call is not authorized."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AIApprovalError("AI cloud call is not authorized") from exc
    if not isinstance(value, dict) or set(value) != REQUIRED_FIELDS:
        raise AIApprovalError("AI cloud call is not authorized")
    return value


def _parse_aware_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise AIApprovalError("AI cloud call is not authorized")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AIApprovalError("AI cloud call is not authorized") from exc
    if parsed.tzinfo is None:
        raise AIApprovalError("AI cloud call is not authorized")
    return parsed


def _validate_endpoint(value: Any) -> None:
    if not isinstance(value, str) or not value:
        raise AIApprovalError("AI cloud call is not authorized")
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise AIApprovalError("AI cloud call is not authorized")


def configuration_fingerprint(record: Mapping[str, Any]) -> str:
    """Hash the non-secret approval configuration plus active contract versions."""

    material = {
        key: record.get(key)
        for key in sorted(REQUIRED_FIELDS - {"configuration_fingerprint"})
    }
    contract = load_contract()
    material["contract_versions"] = {
        "prompt_version": contract["prompt_version"],
        "output_schema_version": contract["output_schema_version"],
        "safety_policy_version": contract["safety_policy_version"],
        "provider_mode": contract["provider_mode"],
    }
    serialized = json.dumps(
        material,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def load_provider_approval(path: Path = APPROVAL_PATH) -> dict[str, Any]:
    """Load and structurally validate an approval record without external access."""

    record = _load_json(Path(path))
    if (
        not isinstance(record["approval_record_version"], str)
        or not SEMVER_RE.fullmatch(record["approval_record_version"])
        or record["status"] not in STATUSES
        or not isinstance(record["implementation_authorization"], bool)
        or record["data_retention_mode"] not in RETENTION_MODES
        or record["product_owner_approval"] not in REVIEW_STATES
        or record["chief_architect_review"] not in REVIEW_STATES
    ):
        raise AIApprovalError("AI cloud call is not authorized")
    if not all(isinstance(record[field], bool) for field in CONTROL_FIELDS):
        raise AIApprovalError("AI cloud call is not authorized")

    if record["status"] != "approved":
        if record["blocked_reason"] not in BLOCKED_REASONS:
            raise AIApprovalError("AI cloud call is not authorized")
        if (
            record["implementation_authorization"]
            or any(record[field] is not None for field in IDENTITY_FIELDS)
            or record["data_retention_mode"] != "zero_data_retention"
            or any(record[field] for field in CONTROL_FIELDS)
            or record["product_owner_approval"] != "pending"
            or record["chief_architect_review"] != "pending"
            or record["evidence_effective_at"] is not None
            or record["evidence_expires_at"] is not None
            or record["configuration_fingerprint"] is not None
        ):
            raise AIApprovalError("AI cloud call is not authorized")
    elif record["blocked_reason"] is not None:
        raise AIApprovalError("AI cloud call is not authorized")
    return copy.deepcopy(record)


def require_cloud_call_approval(
    *,
    now: datetime,
    path: Path = APPROVAL_PATH,
) -> dict[str, Any]:
    """Return an approved record or fail before any health context is serialized."""

    if not isinstance(now, datetime) or now.tzinfo is None:
        raise AIApprovalError("AI cloud call is not authorized")
    record = load_provider_approval(path)
    if record["status"] != "approved" or not record["implementation_authorization"]:
        raise AIApprovalError("AI cloud call is not authorized")
    if not all(isinstance(record[field], str) and record[field] for field in IDENTITY_FIELDS):
        raise AIApprovalError("AI cloud call is not authorized")
    _validate_endpoint(record["endpoint"])
    if not all(
        record[field] is True
        for field in ("no_training_verified", "subprocessors_accepted", "retention_terms_accepted")
    ):
        raise AIApprovalError("AI cloud call is not authorized")
    if record["data_retention_mode"] == "zero_data_retention":
        if not record["zdr_verified"] or not record["human_review_disabled"]:
            raise AIApprovalError("AI cloud call is not authorized")
    elif record["zdr_verified"]:
        raise AIApprovalError("AI cloud call is not authorized")
    if (
        record["product_owner_approval"] != "approved"
        or record["chief_architect_review"] != "approved"
    ):
        raise AIApprovalError("AI cloud call is not authorized")
    effective_at = _parse_aware_datetime(record["evidence_effective_at"])
    expires_at = _parse_aware_datetime(record["evidence_expires_at"])
    if effective_at >= expires_at or now < effective_at or now >= expires_at:
        raise AIApprovalError("AI cloud call is not authorized")
    fingerprint = record["configuration_fingerprint"]
    if (
        not isinstance(fingerprint, str)
        or len(fingerprint) != 64
        or fingerprint != configuration_fingerprint(record)
    ):
        raise AIApprovalError("AI cloud call is not authorized")
    return copy.deepcopy(record)


def cloud_call_allowed(*, now: datetime, path: Path = APPROVAL_PATH) -> bool:
    """Return False for every missing, partial, expired, drifted, or blocked record."""

    try:
        require_cloud_call_approval(now=now, path=path)
    except AIApprovalError:
        return False
    return True
