"""Versioned, mobile-safe daily projection exported from the desktop database.

The mobile contract intentionally contains only the facts needed by the iOS
Today surface. It never exposes raw provider payloads, OAuth material, notes,
or local database identifiers. This module is read-only with respect to SQLite.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .dashboard_data import connect_readonly, get_day_metrics, get_kubios_advanced_metrics
from .domain_dashboard_data import (
    get_latest_recovery,
    get_latest_sleep,
    get_latest_training,
)


CONTRACT_KIND = "rhythmos.mobile_daily_snapshot"
CONTRACT_VERSION = 1

_RECOMMENDATION_CODES = {
    "正常训练": "normal_training",
    "适度训练": "moderate_training",
    "减量训练": "reduced_training",
    "恢复优先": "recovery_first",
}

_READINESS_BY_RECOMMENDATION = {
    "normal_training": "ready",
    "moderate_training": "steady",
    "reduced_training": "conserve",
    "recovery_first": "conserve",
}

_RECOVERY_STATUSES = frozenset({"ready", "steady", "conserve", "insufficient_data"})
_CONFIDENCE_LEVELS = frozenset({"high", "medium", "low", "very_low", "insufficient"})
_TIMESTAMP_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")


class MobileSnapshotContractError(ValueError):
    """Raised when a value cannot be represented by mobile snapshot v1."""


def _require_exact_keys(value: Any, expected: set[str], path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MobileSnapshotContractError(f"{path} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise MobileSnapshotContractError(f"{path} keys must be strings")
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        details = []
        if missing:
            details.append(f"missing keys: {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected keys: {', '.join(unexpected)}")
        raise MobileSnapshotContractError(f"{path} has {'; '.join(details)}")
    return value


def _require_string(value: Any, path: str, *, allow_none: bool = False) -> str | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or not value:
        suffix = " or null" if allow_none else ""
        raise MobileSnapshotContractError(f"{path} must be a non-empty string{suffix}")
    return value


def _require_number(
    value: Any,
    path: str,
    *,
    allow_none: bool = False,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float | int | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        suffix = " or null" if allow_none else ""
        raise MobileSnapshotContractError(f"{path} must be a finite number{suffix}")
    if minimum is not None and value < minimum:
        raise MobileSnapshotContractError(f"{path} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise MobileSnapshotContractError(f"{path} must be at most {maximum}")
    return value


def _validate_metric(
    value: Any,
    path: str,
    *,
    minimum: float | None = 0,
    maximum: float | None = None,
) -> None:
    metric = _require_exact_keys(value, {"value", "provenance"}, path)
    metric_value = _require_number(
        metric["value"], f"{path}.value", allow_none=True, minimum=minimum, maximum=maximum,
    )
    provenance = _require_exact_keys(
        metric["provenance"],
        {"value", "source", "is_fallback", "is_manual_override", "reason"},
        f"{path}.provenance",
    )
    provenance_value = _require_number(
        provenance["value"], f"{path}.provenance.value", allow_none=True,
        minimum=minimum, maximum=maximum,
    )
    if metric_value != provenance_value:
        raise MobileSnapshotContractError(f"{path}.value must equal its provenance value")
    _require_string(provenance["source"], f"{path}.provenance.source")
    _require_string(provenance["reason"], f"{path}.provenance.reason")
    for name in ("is_fallback", "is_manual_override"):
        if not isinstance(provenance[name], bool):
            raise MobileSnapshotContractError(f"{path}.provenance.{name} must be a boolean")


def _validate_text_metric(value: Any, path: str) -> None:
    metric = _require_exact_keys(value, {"value", "provenance"}, path)
    metric_value = _require_string(metric["value"], f"{path}.value", allow_none=True)
    provenance = _require_exact_keys(
        metric["provenance"],
        {"value", "source", "is_fallback", "is_manual_override", "reason"},
        f"{path}.provenance",
    )
    provenance_value = _require_string(
        provenance["value"], f"{path}.provenance.value", allow_none=True,
    )
    if metric_value != provenance_value:
        raise MobileSnapshotContractError(f"{path}.value must equal its provenance value")
    _require_string(provenance["source"], f"{path}.provenance.source")
    _require_string(provenance["reason"], f"{path}.provenance.reason")
    for name in ("is_fallback", "is_manual_override"):
        if not isinstance(provenance[name], bool):
            raise MobileSnapshotContractError(f"{path}.provenance.{name} must be a boolean")


def validate_mobile_daily_snapshot(snapshot: Any) -> dict[str, Any]:
    """Validate the complete, JSON-safe mobile snapshot v1 contract.

    The validator deliberately rejects unknown object members, non-finite
    numbers, and internally inconsistent resolved values. That makes contract
    drift fail at the desktop export boundary instead of silently reaching a
    mobile client with a subtly different shape.
    """
    try:
        json.dumps(snapshot, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise MobileSnapshotContractError("snapshot must be JSON-safe") from error

    root = _require_exact_keys(
        snapshot,
        {"kind", "version", "generated_at", "date", "recovery", "sleep", "training"},
        "snapshot",
    )
    if root["kind"] != CONTRACT_KIND:
        raise MobileSnapshotContractError(f"snapshot.kind must be {CONTRACT_KIND!r}")
    if root["version"] != CONTRACT_VERSION or isinstance(root["version"], bool):
        raise MobileSnapshotContractError(f"snapshot.version must be {CONTRACT_VERSION}")
    generated_at = _require_string(root["generated_at"], "snapshot.generated_at")
    if not _TIMESTAMP_PATTERN.fullmatch(generated_at):
        raise MobileSnapshotContractError("snapshot.generated_at must be a UTC timestamp with second precision")
    try:
        datetime.strptime(generated_at, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise MobileSnapshotContractError("snapshot.generated_at is not a real timestamp") from error
    snapshot_date = _require_string(root["date"], "snapshot.date")
    try:
        parsed_date = date.fromisoformat(snapshot_date)
    except ValueError as error:
        raise MobileSnapshotContractError("snapshot.date must be an ISO calendar date") from error
    if parsed_date.isoformat() != snapshot_date:
        raise MobileSnapshotContractError("snapshot.date must be an ISO calendar date")

    recovery = _require_exact_keys(
        root["recovery"],
        {
            "status", "score", "score_version", "recommendation_code", "confidence",
            "morning_hrv_rmssd_ms", "morning_resting_hr_bpm", "details",
        },
        "snapshot.recovery",
    )
    if recovery["status"] not in _RECOVERY_STATUSES:
        raise MobileSnapshotContractError("snapshot.recovery.status is not supported")
    score = _require_number(recovery["score"], "snapshot.recovery.score", allow_none=True, minimum=0, maximum=100)
    _require_string(recovery["score_version"], "snapshot.recovery.score_version", allow_none=True)
    recommendation = recovery["recommendation_code"]
    if recommendation is not None and recommendation not in _READINESS_BY_RECOMMENDATION:
        raise MobileSnapshotContractError("snapshot.recovery.recommendation_code is not supported")
    expected_status = (
        _READINESS_BY_RECOMMENDATION[recommendation]
        if recommendation is not None
        else ("insufficient_data" if score is None else "steady")
    )
    if recovery["status"] != expected_status:
        raise MobileSnapshotContractError("snapshot.recovery.status is inconsistent with its score and recommendation")
    confidence = recovery["confidence"]
    if confidence is not None:
        confidence = _require_exact_keys(
            confidence, {"score", "level", "missing_groups", "version"}, "snapshot.recovery.confidence",
        )
        _require_number(confidence["score"], "snapshot.recovery.confidence.score", allow_none=True, minimum=0, maximum=100)
        level = _require_string(confidence["level"], "snapshot.recovery.confidence.level", allow_none=True)
        if level is not None and level not in _CONFIDENCE_LEVELS:
            raise MobileSnapshotContractError("snapshot.recovery.confidence.level is not supported")
        if not isinstance(confidence["missing_groups"], list) or not all(
            isinstance(group, str) and group for group in confidence["missing_groups"]
        ):
            raise MobileSnapshotContractError("snapshot.recovery.confidence.missing_groups must be an array of strings")
        _require_string(confidence["version"], "snapshot.recovery.confidence.version", allow_none=True)
    _validate_metric(recovery["morning_hrv_rmssd_ms"], "snapshot.recovery.morning_hrv_rmssd_ms", maximum=1_000)
    _validate_metric(recovery["morning_resting_hr_bpm"], "snapshot.recovery.morning_resting_hr_bpm", maximum=300)
    details = _require_exact_keys(
        recovery["details"],
        {
            "pns_index", "sns_index", "physiological_age_years", "mean_rr_ms",
            "sdnn_ms", "poincare_sd1_ms", "poincare_sd2_ms", "stress_index",
            "respiration_rate_bpm", "measurement_quality",
        },
        "snapshot.recovery.details",
    )
    _validate_metric(details["pns_index"], "snapshot.recovery.details.pns_index", minimum=None)
    _validate_metric(details["sns_index"], "snapshot.recovery.details.sns_index", minimum=None)
    _validate_metric(details["physiological_age_years"], "snapshot.recovery.details.physiological_age_years", maximum=130)
    _validate_metric(details["mean_rr_ms"], "snapshot.recovery.details.mean_rr_ms", maximum=3_000)
    _validate_metric(details["sdnn_ms"], "snapshot.recovery.details.sdnn_ms", maximum=1_000)
    _validate_metric(details["poincare_sd1_ms"], "snapshot.recovery.details.poincare_sd1_ms", maximum=1_000)
    _validate_metric(details["poincare_sd2_ms"], "snapshot.recovery.details.poincare_sd2_ms", maximum=2_000)
    _validate_metric(details["stress_index"], "snapshot.recovery.details.stress_index", maximum=10_000)
    _validate_metric(details["respiration_rate_bpm"], "snapshot.recovery.details.respiration_rate_bpm", maximum=100)
    _validate_text_metric(details["measurement_quality"], "snapshot.recovery.details.measurement_quality")

    sleep = _require_exact_keys(
        root["sleep"],
        {
            "duration_minutes", "score", "sleep_start_time", "wake_time",
            "actual_duration_minutes", "deep_duration_minutes", "rem_duration_minutes",
            "average_hr_bpm", "nightly_hrv_rmssd_ms", "resting_hr_bpm",
            "respiration_rate_bpm",
        },
        "snapshot.sleep",
    )
    _validate_metric(sleep["duration_minutes"], "snapshot.sleep.duration_minutes", maximum=1_440)
    _validate_metric(sleep["score"], "snapshot.sleep.score", maximum=100)
    _validate_text_metric(sleep["sleep_start_time"], "snapshot.sleep.sleep_start_time")
    _validate_text_metric(sleep["wake_time"], "snapshot.sleep.wake_time")
    _validate_metric(sleep["actual_duration_minutes"], "snapshot.sleep.actual_duration_minutes", maximum=1_440)
    _validate_metric(sleep["deep_duration_minutes"], "snapshot.sleep.deep_duration_minutes", maximum=1_440)
    _validate_metric(sleep["rem_duration_minutes"], "snapshot.sleep.rem_duration_minutes", maximum=1_440)
    _validate_metric(sleep["average_hr_bpm"], "snapshot.sleep.average_hr_bpm", maximum=300)
    _validate_metric(sleep["nightly_hrv_rmssd_ms"], "snapshot.sleep.nightly_hrv_rmssd_ms", maximum=1_000)
    _validate_metric(sleep["resting_hr_bpm"], "snapshot.sleep.resting_hr_bpm", maximum=300)
    _validate_metric(sleep["respiration_rate_bpm"], "snapshot.sleep.respiration_rate_bpm", maximum=100)

    training = _require_exact_keys(
        root["training"], {"session_count", "duration_minutes", "calories_kcal", "sports"}, "snapshot.training",
    )
    session_count = training["session_count"]
    if isinstance(session_count, bool) or not isinstance(session_count, int) or session_count < 0:
        raise MobileSnapshotContractError("snapshot.training.session_count must be a non-negative integer")
    _require_number(training["duration_minutes"], "snapshot.training.duration_minutes", allow_none=True, minimum=0)
    _require_number(training["calories_kcal"], "snapshot.training.calories_kcal", allow_none=True, minimum=0)
    if not isinstance(training["sports"], list) or not all(
        isinstance(sport, str) and sport for sport in training["sports"]
    ):
        raise MobileSnapshotContractError("snapshot.training.sports must be an array of strings")
    if len(training["sports"]) != len(set(training["sports"])):
        raise MobileSnapshotContractError("snapshot.training.sports must not contain duplicates")
    if session_count == 0 and any(
        value is not None for value in (training["duration_minutes"], training["calories_kcal"])
    ):
        raise MobileSnapshotContractError("empty training summaries cannot contain duration or calories")
    return root


def _iso_timestamp(value: datetime | str | None) -> str:
    if isinstance(value, str):
        return value
    instant = value or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _normalize_date(value: date | str) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return date.fromisoformat(str(value)).isoformat()


def _latest_date(db_path: Path | str | None) -> str | None:
    """Find a factual date without causing a schema migration or write."""
    connection = connect_readonly(db_path)
    try:
        try:
            row = connection.execute(
                """SELECT MAX(log_date) FROM (
                       SELECT date AS log_date FROM daily_recovery_metrics
                       UNION ALL SELECT date FROM recovery_scores
                       UNION ALL SELECT date FROM polar_training_sessions_raw
                       UNION ALL SELECT date FROM polar_sleep_raw
                       UNION ALL SELECT date FROM polar_nightly_recharge_raw
                       UNION ALL SELECT date FROM kubios_morning_hrv_raw
                       UNION ALL SELECT date FROM manual_recovery_logs
                       UNION ALL SELECT sleep_date FROM manual_sleep_logs
                       UNION ALL SELECT date FROM manual_activity_sessions
                   )"""
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        return row[0] if row else None
    finally:
        connection.close()


def _confidence_for_date(db_path: Path | str | None, snapshot_date: str) -> dict[str, Any] | None:
    connection = connect_readonly(db_path)
    try:
        try:
            row = connection.execute(
                """SELECT confidence_score,confidence_level,missing_groups_json,
                          confidence_version
                   FROM recovery_confidence WHERE date=?
                   ORDER BY updated_at DESC LIMIT 1""",
                (snapshot_date,),
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        if not row:
            return None
        try:
            missing_groups = json.loads(row["missing_groups_json"] or "[]")
        except (TypeError, json.JSONDecodeError):
            missing_groups = []
        return {
            "score": row["confidence_score"],
            "level": row["confidence_level"],
            "missing_groups": missing_groups if isinstance(missing_groups, list) else [],
            "version": row["confidence_version"],
        }
    finally:
        connection.close()


def _field(field: dict[str, Any] | None) -> dict[str, Any]:
    """Expose provenance state without desktop row IDs or raw-source contents."""
    field = field or {}
    snapshot = {
        "value": field.get("value"),
        "source": field.get("value_source", "missing"),
        "is_fallback": bool(field.get("is_fallback")),
        "is_manual_override": bool(field.get("is_manual_override")),
        "reason": field.get("resolution_reason", "no_permitted_source_value_available"),
    }
    return snapshot


def _metric(
    value: Any,
    field: dict[str, Any] | None = None,
    *,
    default_source: str = "missing",
) -> dict[str, Any]:
    if field is None and value is not None:
        field = {
            "value": value,
            "value_source": default_source,
            "resolution_reason": f"{default_source}_value_available",
        }
    return {"value": value, "provenance": _field(field)}


def _text_metric(
    value: Any,
    field: dict[str, Any] | None = None,
    *,
    default_source: str = "missing",
) -> dict[str, Any]:
    if field is None and value is not None:
        field = {
            "value": value,
            "value_source": default_source,
            "resolution_reason": f"{default_source}_value_available",
        }
    return {"value": value, "provenance": _field(field)}


def build_mobile_daily_snapshot(
    db_path: Path | str | None = None,
    snapshot_date: date | str | None = None,
    *,
    generated_at: datetime | str | None = None,
) -> dict[str, Any] | None:
    """Build a JSON-safe Today projection for one calendar day.

    ``None`` means there is no factual date to export. Supplying
    ``snapshot_date`` is useful for an explicitly selected empty day: the
    returned projection keeps all unavailable measurements as ``null``.
    """
    target_date = _normalize_date(snapshot_date) if snapshot_date else _latest_date(db_path)
    if not target_date:
        return None

    daily = get_day_metrics(target_date, db_path) or {"date": target_date}
    recovery = get_latest_recovery(db_path, log_date=target_date) or {}
    sleep = get_latest_sleep(
        db_path,
        log_date=target_date,
        include_continuous_hr=False,
    ) or {}
    training = get_latest_training(db_path, log_date=target_date) or {}

    recommendation_code = _RECOMMENDATION_CODES.get(recovery.get("recommendation"))
    readiness = _READINESS_BY_RECOMMENDATION.get(
        recommendation_code,
        "insufficient_data" if recovery.get("recovery_score") is None else "steady",
    )
    recovery_fields = recovery.get("resolved_fields") or {}
    sleep_fields = sleep.get("resolved_fields") or {}
    advanced_rows = get_kubios_advanced_metrics(db_path, limit=1, date_value=target_date)
    advanced = advanced_rows[0] if advanced_rows else {}

    snapshot = {
        "kind": CONTRACT_KIND,
        "version": CONTRACT_VERSION,
        "generated_at": _iso_timestamp(generated_at),
        "date": target_date,
        "recovery": {
            "status": readiness,
            "score": recovery.get("recovery_score"),
            "score_version": recovery.get("score_version"),
            "recommendation_code": recommendation_code,
            "confidence": _confidence_for_date(db_path, target_date),
            "morning_hrv_rmssd_ms": _metric(
                recovery.get("morning_rmssd"), recovery_fields.get("morning_rmssd"),
            ),
            "morning_resting_hr_bpm": _metric(
                recovery.get("morning_mean_hr"), recovery_fields.get("morning_mean_hr"),
            ),
            "details": {
                "pns_index": _metric(advanced.get("pns_index"), default_source="kubios"),
                "sns_index": _metric(advanced.get("sns_index"), default_source="kubios"),
                "physiological_age_years": _metric(advanced.get("physiological_age"), default_source="kubios"),
                "mean_rr_ms": _metric(advanced.get("mean_rr_ms"), default_source="kubios"),
                "sdnn_ms": _metric(advanced.get("sdnn_ms"), default_source="kubios"),
                "poincare_sd1_ms": _metric(advanced.get("poincare_sd1_ms"), default_source="kubios"),
                "poincare_sd2_ms": _metric(advanced.get("poincare_sd2_ms"), default_source="kubios"),
                "stress_index": _metric(
                    advanced.get("stress_index")
                    if advanced.get("stress_index") is not None
                    else recovery.get("stress_index"),
                    default_source="kubios",
                ),
                "respiration_rate_bpm": _metric(
                    advanced.get("respiratory_rate_bpm")
                    if advanced.get("respiratory_rate_bpm") is not None
                    else recovery.get("respiratory_rate"),
                    default_source="kubios",
                ),
                "measurement_quality": _text_metric(
                    advanced.get("measurement_quality")
                    if advanced.get("measurement_quality") is not None
                    else recovery.get("measurement_quality"),
                    default_source="kubios",
                ),
            },
        },
        "sleep": {
            "duration_minutes": _metric(
                sleep_fields.get("total_sleep_duration_minutes", {}).get("value"),
                sleep_fields.get("total_sleep_duration_minutes"),
            ),
            "score": _metric(daily.get("sleep_score"), default_source="daily_metric"),
            "sleep_start_time": _text_metric(
                sleep_fields.get("sleep_start_time", {}).get("value"),
                sleep_fields.get("sleep_start_time"),
            ),
            "wake_time": _text_metric(
                sleep_fields.get("wake_time", {}).get("value"),
                sleep_fields.get("wake_time"),
            ),
            "actual_duration_minutes": _metric(
                sleep_fields.get("actual_sleep_duration_minutes", {}).get("value"),
                sleep_fields.get("actual_sleep_duration_minutes"),
            ),
            "deep_duration_minutes": _metric(
                sleep_fields.get("deep_sleep_duration_minutes", {}).get("value"),
                sleep_fields.get("deep_sleep_duration_minutes"),
            ),
            "rem_duration_minutes": _metric(
                sleep_fields.get("rem_sleep_duration_minutes", {}).get("value"),
                sleep_fields.get("rem_sleep_duration_minutes"),
            ),
            "average_hr_bpm": _metric(
                sleep_fields.get("average_sleep_hr_bpm", {}).get("value"),
                sleep_fields.get("average_sleep_hr_bpm"),
            ),
            "nightly_hrv_rmssd_ms": _metric(
                sleep.get("nightly_hrv_rmssd"), sleep_fields.get("nightly_hrv_rmssd"),
            ),
            "resting_hr_bpm": _metric(
                sleep.get("nightly_resting_hr"), sleep_fields.get("nightly_resting_hr"),
            ),
            "respiration_rate_bpm": _metric(
                sleep.get("respiration_rate"), sleep_fields.get("respiration_rate"),
            ),
        },
        "training": {
            "session_count": len(training.get("sessions") or []),
            "duration_minutes": training.get("duration_minutes"),
            "calories_kcal": training.get("calories"),
            "sports": training.get("sports") or [],
        },
    }
    return validate_mobile_daily_snapshot(snapshot)


def write_mobile_daily_snapshot(
    output_path: Path | str,
    db_path: Path | str | None = None,
    snapshot_date: date | str | None = None,
    *,
    generated_at: datetime | str | None = None,
) -> bool:
    """Atomically write a projection. Returns false when no day can be exported."""
    snapshot = build_mobile_daily_snapshot(db_path, snapshot_date, generated_at=generated_at)
    if snapshot is None:
        return False
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(
        json.dumps(snapshot, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output)
    return True
