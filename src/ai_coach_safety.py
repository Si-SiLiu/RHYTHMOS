"""Provider-independent semantic safety gate and deterministic AI fallback."""

import copy
import hashlib
import hmac
import json
import re
from pathlib import Path
from typing import Any, Mapping

from src.ai_coach_contract import (
    AIContractError,
    CONFIG_DIR,
    load_contract,
    validate_input,
    validate_output,
)


POLICY_PATH = CONFIG_DIR / "ai_coach_safety_policy.json"
NUMBER_RE = re.compile(r"\d")
FACT_ID_RE = re.compile(r"[^a-z0-9_]+")


class AISafetyError(ValueError):
    """Raised when syntactically valid model output violates semantic safety."""


def load_safety_policy() -> dict[str, Any]:
    """Load the versioned local safety policy and verify contract alignment."""

    try:
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AISafetyError("Unable to load AI safety policy") from exc
    required = {
        "safety_policy_version",
        "fallback_reason_codes",
        "urgent_terms",
        "escalation_terms",
        "prohibited_medical_phrases",
        "prohibited_medication_phrases",
        "strong_recommendation_phrases",
    }
    if not isinstance(policy, dict) or set(policy) != required:
        raise AISafetyError("AI safety policy fields do not match authority")
    contract = load_contract()
    if policy["safety_policy_version"] != contract["safety_policy_version"]:
        raise AISafetyError("AI safety policy version does not match contract")
    for key in required - {"safety_policy_version"}:
        values = policy[key]
        if not isinstance(values, list) or not values or not all(
            isinstance(value, str) and value for value in values
        ):
            raise AISafetyError(f"AI safety policy list is invalid: {key}")
    return copy.deepcopy(policy)


def _normalized_fact_id(value: str) -> str:
    normalized = FACT_ID_RE.sub("_", value.lower()).strip("_")
    return normalized[:48] or "unknown"


def allowed_fact_ids(input_payload: Mapping[str, Any]) -> set[str]:
    """Return evidence identifiers derived only from validated allowlisted input."""

    validated = validate_input(input_payload)
    result = {"recovery_recommendation", "confidence_level"}
    for factor in validated["recovery"]["factors"]:
        result.add(f"{_normalized_fact_id(factor['metric_name'])}_status")
    result.update(validated["daily_metrics"])
    for baseline in validated["baseline_context"]:
        result.add(f"baseline_{_normalized_fact_id(baseline['metric_name'])}")
    for group in validated["confidence"]["missing_groups"]:
        result.add(f"missing_{_normalized_fact_id(group)}")
    return result


def input_snapshot_digest(input_payload: Mapping[str, Any], digest_key: bytes) -> str:
    """Create a local keyed digest without retaining or transmitting the payload."""

    if not isinstance(digest_key, bytes) or len(digest_key) < 32:
        raise AISafetyError("Digest key must contain at least 32 bytes")
    validated = validate_input(input_payload)
    serialized = json.dumps(
        validated,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hmac.new(digest_key, serialized, hashlib.sha256).hexdigest()


def _narrative_strings(output_payload: Mapping[str, Any]) -> list[str]:
    result = [output_payload["summary"], output_payload["safety_notice"]]
    result.extend(item["statement"] for item in output_payload["evidence"])
    result.extend(output_payload["limitations"])
    result.extend(output_payload["questions_for_user"])
    for action in output_payload["suggested_actions"]:
        result.extend((action["title"], action["rationale"]))
    for item in output_payload["domain_feedback"]:
        result.extend((item["commentary"], item["suggestion"]))
    return result


def _contains_any(text: str, phrases: list[str]) -> bool:
    lowered = text.casefold()
    return any(phrase.casefold() in lowered for phrase in phrases)


def question_is_urgent(input_payload: Mapping[str, Any]) -> bool:
    """Classify only the local allowlisted question using explicit policy terms."""

    validated = validate_input(input_payload)
    question = validated.get("user_question", "")
    return _contains_any(question, load_safety_policy()["urgent_terms"])


def validate_semantic_safety(
    input_payload: Mapping[str, Any],
    output_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate evidence grounding and safety semantics after JSON validation."""

    validated_input = validate_input(input_payload)
    validated_output = validate_output(output_payload)
    policy = load_safety_policy()
    allowed = allowed_fact_ids(validated_input)
    evidence_ids = {item["fact_id"] for item in validated_output["evidence"]}
    unknown = evidence_ids - allowed
    if unknown:
        raise AISafetyError(f"Evidence references are not allowlisted: {sorted(unknown)}")
    domains = [item["domain"] for item in validated_output["domain_feedback"]]
    if set(domains) != {"sleep", "recovery", "training", "nutrition"} or len(set(domains)) != 4:
        raise AISafetyError("Domain feedback must cover each required domain once")

    narrative = "\n".join(_narrative_strings(validated_output))
    if NUMBER_RE.search(narrative):
        raise AISafetyError("Unsupported numeric narrative claim")
    for policy_key in ("prohibited_medical_phrases", "prohibited_medication_phrases"):
        if _contains_any(narrative, policy[policy_key]):
            raise AISafetyError(f"Prohibited safety phrase category: {policy_key}")

    level = validated_input["confidence"]["level"]
    if level in {"medium", "low", "very_low"} and not validated_output["limitations"]:
        raise AISafetyError("Confidence level requires an explicit limitation")
    if level == "low" and len(validated_output["suggested_actions"]) > 1:
        raise AISafetyError("Low confidence permits at most one reversible option")
    if level == "very_low" and validated_output["suggested_actions"]:
        raise AISafetyError("Very low confidence prohibits generated actions")
    if level in {"low", "very_low"} and _contains_any(
        narrative, policy["strong_recommendation_phrases"]
    ):
        raise AISafetyError("Strong recommendation conflicts with confidence")

    if question_is_urgent(validated_input):
        if not _contains_any(validated_output["safety_notice"], policy["escalation_terms"]):
            raise AISafetyError("Urgent question requires local emergency escalation")
        if validated_output["suggested_actions"]:
            raise AISafetyError("Urgent question prohibits generated action options")
    return copy.deepcopy(validated_output)


def build_deterministic_fallback(
    input_payload: Mapping[str, Any],
    reason_code: str,
    generated_at: str,
    digest_key: bytes,
) -> dict[str, Any]:
    """Build a schema-valid local fallback from validated facts, with no model call."""

    validated_input = validate_input(input_payload)
    policy = load_safety_policy()
    if reason_code not in policy["fallback_reason_codes"]:
        raise AISafetyError("Fallback reason code is not allowlisted")
    contract = load_contract()
    limitations = ["云端解释当前不可用，仅显示确定性结果。"]
    if validated_input["confidence"]["level"] != "high":
        limitations.append("当前证据存在限制，请结合已显示的数据完整性理解结果。")
    if validated_input["confidence"]["missing_groups"]:
        limitations.append("部分信号组缺失，系统不会据此生成强建议。")
    safety_notice = "请以确定性恢复结果和已显示的数据限制为准。"
    if question_is_urgent(validated_input):
        safety_notice = "如有紧急或持续加重的症状，请立即联系当地急救服务或合格医疗专业人员。"
    output = {
        "summary": "当前仅提供确定性的恢复结果。",
        "domain_feedback": [
            {
                "domain": domain,
                "status": "insufficient",
                "commentary": "当前没有足够信息形成该维度的个体化解释。",
                "suggestion": "继续记录后再查看该维度反馈。",
            }
            for domain in ("sleep", "recovery", "training", "nutrition")
        ],
        "evidence": [
            {
                "fact_id": "recovery_recommendation",
                "statement": "确定性恢复建议仍是当前有效来源。",
            }
        ],
        "limitations": limitations,
        "suggested_actions": [],
        "questions_for_user": [],
        "safety_notice": safety_notice,
        "audit": {
            "model_version": "deterministic-fallback",
            "prompt_version": contract["prompt_version"],
            "output_schema_version": contract["output_schema_version"],
            "safety_policy_version": contract["safety_policy_version"],
            "input_snapshot_digest": input_snapshot_digest(validated_input, digest_key),
            "generated_at": generated_at,
            "provider_mode": contract["provider_mode"],
        },
    }
    return validate_semantic_safety(validated_input, output)


def safe_output_or_fallback(
    input_payload: Mapping[str, Any],
    output_payload: Mapping[str, Any],
    generated_at: str,
    digest_key: bytes,
) -> tuple[dict[str, Any], bool]:
    """Return validated output or deterministic fallback without exposing failure data."""

    try:
        return validate_semantic_safety(input_payload, output_payload), False
    except (AIContractError, AISafetyError):
        return (
            build_deterministic_fallback(
                input_payload,
                "safety_blocked",
                generated_at,
                digest_key,
            ),
            True,
        )
