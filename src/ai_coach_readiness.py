"""Aggregate-only pre-provider and runtime readiness gate for AI Coach."""

import argparse
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from src.ai_coach_approval import (
    APPROVAL_PATH,
    AIApprovalError,
    require_cloud_call_approval,
)
from src.ai_coach_contract import CONFIG_DIR, load_contract
from src.ai_coach_evaluation import load_evaluation_config, run_preflight
from src.ai_coach_safety import load_safety_policy


BASE_DIR = Path(__file__).resolve().parents[1]
VERSIONS_PATH = CONFIG_DIR / "versions.json"
PROVIDER_ADAPTER_PATH = BASE_DIR / "src" / "ai_coach_provider.py"
MODEL_EVALUATION_PATH = CONFIG_DIR / "ai_coach_model_evaluation.json"
AUDIT_MIGRATION_PATH = BASE_DIR / "src" / "ai_coach_audit.py"


class AIReadinessError(RuntimeError):
    """Raised when readiness authorities cannot be evaluated safely."""


def _load_versions(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AIReadinessError("AI readiness authorities are invalid") from exc
    if not isinstance(value, dict):
        raise AIReadinessError("AI readiness authorities are invalid")
    return value


def _semver_tuple(value: Any) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    parts = value.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def _model_evaluation_ready(
    path: Path,
    *,
    model_version: Any,
    contract: dict[str, Any],
    evaluation: dict[str, Any],
) -> bool:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    required = {
        "suite_version",
        "model_version",
        "prompt_version",
        "output_schema_version",
        "safety_policy_version",
        "cases_per_run",
        "runs",
        "critical_failures",
        "confidence_language_pass_rate",
        "grounding_pass_rate",
        "unsupported_numeric_claims",
        "secret_or_identifier_leaks",
        "success",
        "evaluated_at",
    }
    if not isinstance(value, dict) or set(value) != required:
        return False
    try:
        evaluated_at = datetime.fromisoformat(value["evaluated_at"].replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return False
    integer_fields = (
        "cases_per_run",
        "runs",
        "critical_failures",
        "unsupported_numeric_claims",
        "secret_or_identifier_leaks",
    )
    rate_fields = ("confidence_language_pass_rate", "grounding_pass_rate")
    if not all(
        isinstance(value[key], int) and not isinstance(value[key], bool)
        for key in integer_fields
    ) or not all(
        isinstance(value[key], (int, float)) and not isinstance(value[key], bool)
        for key in rate_fields
    ):
        return False
    return (
        evaluated_at.tzinfo is not None
        and value["suite_version"] == evaluation["suite_version"]
        and value["model_version"] == model_version
        and value["prompt_version"] == contract["prompt_version"]
        and value["output_schema_version"] == contract["output_schema_version"]
        and value["safety_policy_version"] == contract["safety_policy_version"]
        and value["cases_per_run"] >= evaluation["minimum_cases_per_run"]
        and value["runs"] >= evaluation["required_consecutive_runs"]
        and value["critical_failures"] == 0
        and value["confidence_language_pass_rate"] >= evaluation["confidence_language_pass_rate"]
        and value["grounding_pass_rate"] >= evaluation["grounding_pass_rate"]
        and value["unsupported_numeric_claims"] == 0
        and value["secret_or_identifier_leaks"] == 0
        and value["success"] is True
    )


def evaluate_readiness(
    *,
    now: datetime,
    approval_path: Path = APPROVAL_PATH,
    versions_path: Path = VERSIONS_PATH,
    provider_adapter_path: Path = PROVIDER_ADAPTER_PATH,
    model_evaluation_path: Path = MODEL_EVALUATION_PATH,
    audit_migration_path: Path = AUDIT_MIGRATION_PATH,
    preflight_runner: Callable[..., dict[str, Any]] = run_preflight,
    digest_key: bytes | None = None,
) -> dict[str, Any]:
    """Return aggregate readiness facts without payloads, secrets, or provider calls."""

    if not isinstance(now, datetime) or now.tzinfo is None:
        raise AIReadinessError("AI readiness requires an aware timestamp")
    try:
        contract = load_contract()
        safety = load_safety_policy()
        evaluation = load_evaluation_config()
        versions = _load_versions(Path(versions_path))
        preflight = preflight_runner(
            runs=evaluation["required_consecutive_runs"],
            digest_key=digest_key or secrets.token_bytes(32),
        )
    except Exception as exc:
        if isinstance(exc, AIReadinessError):
            raise
        raise AIReadinessError("AI readiness authorities are invalid") from exc

    contract_ready = (
        contract["provider_mode"] in {"cloud_zdr", "cloud_standard_retention"}
        and safety["safety_policy_version"] == contract["safety_policy_version"]
    )
    local_preflight_ready = (
        preflight.get("success") is True
        and preflight.get("cases_per_run", 0) >= evaluation["minimum_cases_per_run"]
        and preflight.get("runs", 0) >= evaluation["required_consecutive_runs"]
        and preflight.get("critical_failures") == 0
        and preflight.get("model_version") == "unreleased"
        and preflight.get("provider_mode") == "local_preflight_only"
    )
    try:
        approval = require_cloud_call_approval(now=now, path=approval_path)
    except AIApprovalError:
        approval = None
    provider_approval_ready = approval is not None
    model_version = versions.get("model_version")
    model_version_ready = (
        approval is not None
        and isinstance(model_version, str)
        and model_version != "unreleased"
        and model_version == approval["model_snapshot"]
    )
    database_version = versions.get("database_schema_version")
    # Local Coach owns schema 0.4.0. Cloud audit readiness requires its own
    # concrete implementation artifact and cannot be inferred from SemVer.
    audit_migration_ready = Path(audit_migration_path).is_file()
    provider_adapter_ready = Path(provider_adapter_path).is_file()
    exact_model_evaluation_ready = _model_evaluation_ready(
        Path(model_evaluation_path),
        model_version=model_version,
        contract=contract,
        evaluation=evaluation,
    )

    checks = {
        "contract_and_safety_ready": contract_ready,
        "local_preflight_ready": local_preflight_ready,
        "provider_approval_ready": provider_approval_ready,
        "model_version_ready": model_version_ready,
        "audit_migration_ready": audit_migration_ready,
        "provider_adapter_ready": provider_adapter_ready,
        "exact_model_evaluation_ready": exact_model_evaluation_ready,
    }
    local_ready = checks["contract_and_safety_ready"] and checks["local_preflight_ready"]
    runtime_ready = all(checks.values())
    blocker_map = {
        "contract_and_safety_ready": "local_contract_or_safety_invalid",
        "local_preflight_ready": "local_preflight_failed",
        "provider_approval_ready": "provider_approval_not_granted",
        "model_version_ready": "model_version_unreleased",
        "audit_migration_ready": "audit_migration_not_applied",
        "provider_adapter_ready": "provider_adapter_not_implemented",
        "exact_model_evaluation_ready": "exact_model_evaluation_missing",
    }
    return {
        "readiness_version": "1.0.0",
        "local_pre_provider_ready": local_ready,
        "runtime_ready": runtime_ready,
        "checks": checks,
        "blockers": [blocker_map[key] for key, passed in checks.items() if not passed],
        "model_version": model_version,
        "database_schema_version": database_version,
        "local_preflight": {
            "cases_per_run": preflight.get("cases_per_run"),
            "runs": preflight.get("runs"),
            "total_evaluations": preflight.get("total_evaluations"),
            "passed": preflight.get("passed"),
            "failed": preflight.get("failed"),
            "critical_failures": preflight.get("critical_failures"),
        },
    }


def main() -> None:
    """Print aggregate readiness; optionally fail when runtime is not ready."""

    parser = argparse.ArgumentParser(description="Check AI Coach readiness")
    parser.add_argument("--require-runtime", action="store_true")
    args = parser.parse_args()
    result = evaluate_readiness(now=datetime.now(timezone.utc))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if args.require_runtime and not result["runtime_ready"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
