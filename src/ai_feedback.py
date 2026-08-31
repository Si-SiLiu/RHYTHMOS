"""Generate and persist a Codex explanation from minimum-necessary daily data."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Mapping

from src.ai_coach_approval import load_provider_approval
from src.ai_coach_context import build_context
from src.ai_coach_provider import AIProviderError, generate_coach_output
from src.daily_metrics import duration_to_seconds
from src.db import connect


class AIFeedbackError(RuntimeError):
    """A safe, user-facing failure for the optional Codex feedback layer."""


_BASELINE_METRICS = {
    "sleep_duration": ("sleep", "higher_is_better"),
    "sleep_score": ("sleep", "higher_is_better"),
    "nightly_hrv_rmssd": ("hrv", "higher_is_better"),
    "morning_rmssd": ("hrv", "higher_is_better"),
    "nightly_resting_hr": ("resting_hr", "lower_is_better"),
    "morning_mean_hr": ("resting_hr", "lower_is_better"),
    "respiration_rate": ("respiration", "lower_is_better"),
    "training_duration": ("training", "higher_is_load"),
    "training_calories": ("training", "higher_is_load"),
    "steps": ("activity", "higher_is_load"),
    "active_calories": ("activity", "higher_is_load"),
    "kubios_readiness": ("readiness", "higher_is_better"),
}


def _band(value: Any, *, low: float, high: float, names: tuple[str, str, str], unknown: str = "unknown") -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return unknown
    if number < low:
        return names[0]
    if number > high:
        return names[2]
    return names[1]


def _duration_hours(value: Any) -> float | None:
    seconds = duration_to_seconds(value)
    return seconds / 3600 if seconds is not None else None


def _baseline_status(value: Any) -> str:
    return {
        "above_baseline": "above",
        "below_baseline": "below",
        "within_baseline": "within",
    }.get(value, "insufficient")


def _deviation_band(row: Mapping[str, Any]) -> str:
    magnitude = None
    for name in ("robust_z_score", "z_score"):
        try:
            if row.get(name) is not None:
                magnitude = abs(float(row[name]))
                break
        except (TypeError, ValueError):
            continue
    if magnitude is None:
        try:
            magnitude = abs(float(row.get("percent_change"))) / 10
        except (TypeError, ValueError):
            return "unknown"
    return "strong" if magnitude >= 2 else "moderate" if magnitude >= 1 else "small" if magnitude > 0 else "within"


def _factor_direction(status: str, direction: str) -> str:
    if status == "insufficient":
        return "missing"
    if status == "within":
        return "neutral"
    supportive = (direction == "higher_is_better" and status == "above") or (
        direction == "lower_is_better" and status == "below"
    ) or (direction == "higher_is_load" and status == "below")
    return "supportive" if supportive else "pressure"


def _presentation_locale(language: str) -> str:
    return {"zh-CN": "zh-CN", "zh-TW": "zh-TW", "en": "en-US", "en-US": "en-US"}.get(language, "zh-CN")


def _nutrition_bands(connection: sqlite3.Connection, analysis_date: str) -> dict[str, str]:
    """Project today’s nutrition logging into non-identifying categorical bands."""
    try:
        row = connection.execute(
            """SELECT logged_meals, data_completeness
                 FROM daily_nutrition_summary WHERE date=?""",
            (analysis_date,),
        ).fetchone()
    except sqlite3.OperationalError:
        row = None
    if not row or int(row["logged_meals"] or 0) <= 0:
        return {"recording_band": "unlogged", "coverage_band": "none"}
    completeness = int(row["data_completeness"] or 0)
    return {
        "recording_band": "complete" if completeness >= 80 else "partial",
        "coverage_band": "adequate" if completeness >= 80 else "limited",
    }


def _local_readiness(daily_metrics: Mapping[str, str]) -> dict[str, str]:
    """Derive a sleep-led local readiness category without impersonating Kubios.

    The result is deliberately qualitative.  Sleep duration and sleep score
    determine whether a readiness category can be formed; overnight HRV and
    resting heart rate refine that category when present.
    """
    duration = daily_metrics.get("sleep_duration_band", "unknown")
    sleep_score = daily_metrics.get("sleep_score_band", "unknown")
    hrv = daily_metrics.get("hrv_band", "unknown")
    resting_hr = daily_metrics.get("resting_hr_band", "unknown")
    if duration == "unknown" and sleep_score == "unknown":
        return {"status": "insufficient", "basis": "sleep_only"}

    pressure = sum((
        duration == "low",
        sleep_score == "low",
        hrv == "low",
        resting_hr == "high",
    ))
    support = sum((
        duration == "high",
        sleep_score == "high",
        hrv == "high",
        resting_hr == "low",
    ))
    status = (
        "recovery_priority" if pressure >= 2 else "cautious" if pressure == 1
        else "ready" if support >= 2 else "steady"
    )
    return {
        "status": status,
        "basis": "sleep_and_recovery" if hrv != "unknown" or resting_hr != "unknown" else "sleep_only",
    }


def build_feedback_source(connection: sqlite3.Connection, analysis_date: str, *, language: str = "zh-CN") -> dict[str, Any]:
    """Build the closed, coarse-grained context sent to the API.

    Exact measurements, identifiers, notes, device records, and database rows
    are deliberately excluded. The provider receives only categorical bands and
    deterministic outcomes already shown in the application.
    """

    row = connection.execute(
        """
        SELECT m.*, s.recovery_score, s.recommendation, s.score_version,
               c.confidence_score, c.confidence_level, c.confidence_version,
               c.available_groups_json, c.missing_groups_json
          FROM daily_recovery_metrics m
          JOIN recovery_scores s ON s.date=m.date
          JOIN recovery_confidence c ON c.date=m.date
         WHERE m.date=?
        """,
        (analysis_date,),
    ).fetchone()
    if not row:
        raise AIFeedbackError("当前数据尚不足以生成 Codex 综合反馈")
    metric = dict(row)
    try:
        available_groups = json.loads(metric.get("available_groups_json") or "[]")
        missing_groups = json.loads(metric.get("missing_groups_json") or "[]")
    except json.JSONDecodeError as exc:
        raise AIFeedbackError("当前数据尚不足以生成 Codex 综合反馈") from exc
    if not isinstance(available_groups, list) or not isinstance(missing_groups, list):
        raise AIFeedbackError("当前数据尚不足以生成 Codex 综合反馈")

    baseline_rows = [dict(item) for item in connection.execute(
        """SELECT metric_name,valid_days,status,percent_change,z_score,robust_z_score
             FROM baseline_metrics
            WHERE date=? AND window_days=28
            ORDER BY metric_name
            LIMIT 12""",
        (analysis_date,),
    ).fetchall()]
    factors: list[dict[str, str]] = []
    seen_metrics: set[str] = set()
    baseline_context: list[dict[str, str]] = []
    for baseline in baseline_rows:
        metric_name = str(baseline["metric_name"])
        status = _baseline_status(baseline.get("status"))
        valid_days = int(baseline.get("valid_days") or 0)
        baseline_context.append({
            "metric_name": metric_name[:64],
            "comparison_status": status,
            "maturity_band": "mature" if valid_days >= 21 else "developing" if valid_days >= 7 else "immature",
            "deviation_band": _deviation_band(baseline),
        })
        category = _BASELINE_METRICS.get(metric_name)
        if not category or category[0] in seen_metrics:
            continue
        seen_metrics.add(category[0])
        factors.append({
            "metric_name": category[0],
            "direction": _factor_direction(status, category[1]),
            "status": status,
            "deviation_band": _deviation_band(baseline),
        })

    sleep_hours = _duration_hours(metric.get("sleep_duration"))
    training_hours = _duration_hours(metric.get("training_duration"))
    training_count = metric.get("training_count")
    daily_metrics = {
        "sleep_duration_band": _band(sleep_hours, low=6, high=9, names=("low", "typical", "high"), unknown="unknown"),
        "sleep_score_band": _band(metric.get("sleep_score"), low=60, high=80, names=("low", "typical", "high"), unknown="unknown"),
        "hrv_band": _band(metric.get("nightly_hrv_rmssd") or metric.get("morning_rmssd"), low=25, high=70, names=("low", "typical", "high"), unknown="unknown"),
        "resting_hr_band": _band(metric.get("nightly_resting_hr") or metric.get("morning_mean_hr"), low=50, high=70, names=("low", "typical", "high"), unknown="unknown"),
        "respiration_band": _band(metric.get("respiration_rate"), low=12, high=18, names=("low", "typical", "high"), unknown="unknown"),
        "training_duration_band": _band(training_hours, low=0.34, high=1.34, names=("light", "moderate", "high"), unknown="unknown") if training_hours not in (None, 0) else "none",
        "training_count_band": "none" if training_count in (None, 0) else "single" if int(training_count) == 1 else "multiple",
        "activity_band": _band(metric.get("active_calories"), low=200, high=700, names=("low", "typical", "high"), unknown="unknown"),
        "kubios_readiness_label": "available" if metric.get("kubios_readiness") not in (None, "") else "unavailable",
    }
    local_readiness = _local_readiness(daily_metrics)
    daily_metrics.update({
        "local_readiness_status": local_readiness["status"],
        "local_readiness_basis": local_readiness["basis"],
    })
    source = {
        "analysis_date": analysis_date,
        "recovery": {
            "score": int(metric["recovery_score"]),
            "recommendation": str(metric["recommendation"]),
            "score_version": str(metric["score_version"]),
            "factors": factors,
        },
        "confidence": {
            "score": int(metric["confidence_score"]),
            "level": str(metric["confidence_level"]),
            "confidence_version": str(metric["confidence_version"]),
            "available_groups": [str(item)[:64] for item in available_groups[:12]],
            "missing_groups": [str(item)[:64] for item in missing_groups[:12]],
        },
        "daily_metrics": daily_metrics,
        "nutrition": _nutrition_bands(connection, analysis_date),
        "baseline_context": baseline_context,
        "presentation": {"locale": _presentation_locale(language), "unit_system": "metric"},
    }
    try:
        # Validate the outbound projection here, but return the caller-owned
        # source shape. The provider gate injects authoritative contract
        # versions immediately before serialization.
        build_context(source)
        return source
    except Exception as exc:
        raise AIFeedbackError("当前数据尚不足以生成 Codex 综合反馈") from exc


def generate_feedback_for_date(analysis_date: str, *, language: str = "zh-CN") -> dict[str, Any]:
    """Call the approved provider once and atomically replace this date's feedback."""

    connection = connect()
    try:
        source = build_feedback_source(connection, analysis_date, language=language)
        now = datetime.now(timezone.utc)
        try:
            output = generate_coach_output(source, now=now)
            approval = load_provider_approval()
        except AIProviderError as exc:
            if str(exc) == "AI provider quota is unavailable":
                raise AIFeedbackError("Codex 综合反馈暂时无法生成：当前 API 项目没有可用额度，已保留本地规则建议") from exc
            raise AIFeedbackError("Codex 综合反馈暂时无法生成，已保留本地规则建议") from exc
        audit = output["audit"]
        connection.execute(
            """
            INSERT INTO ai_feedback_outputs(
                date,provider_id,model_version,data_retention_mode,
                input_snapshot_digest,output_json,generated_at
            ) VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(date) DO UPDATE SET
                provider_id=excluded.provider_id,
                model_version=excluded.model_version,
                data_retention_mode=excluded.data_retention_mode,
                input_snapshot_digest=excluded.input_snapshot_digest,
                output_json=excluded.output_json,
                generated_at=excluded.generated_at,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                analysis_date,
                approval["provider_id"],
                audit["model_version"],
                approval["data_retention_mode"],
                audit["input_snapshot_digest"],
                json.dumps(output, ensure_ascii=False, sort_keys=True),
                audit["generated_at"],
            ),
        )
        connection.commit()
        return output
    finally:
        connection.close()


def generate_latest_feedback(*, language: str = "zh-CN") -> dict[str, Any]:
    """Generate feedback for the newest deterministic recovery date."""

    connection = connect()
    try:
        row = connection.execute("SELECT MAX(date) FROM recovery_scores").fetchone()
        analysis_date = row[0] if row else None
    finally:
        connection.close()
    if not analysis_date:
        raise AIFeedbackError("当前数据尚不足以生成 Codex 综合反馈")
    return generate_feedback_for_date(str(analysis_date), language=language)
