"""Persistence and personal-baseline analysis for Neural Readiness.

This module is deliberately separate from Recovery Engine.  It only reads the
already-resolved sleep/HRV columns from ``daily_recovery_metrics`` and never
updates them or a recovery score.
"""

from __future__ import annotations

import json
import math
import sqlite3
import statistics
from datetime import date, datetime, timedelta
from typing import Any

from .db import connect, get_current_db_path


PROTOCOL_VERSION = "alertness_probe_v1"
DAILY_SHORT_PROTOCOL_VERSION = "alertness_probe_v1"
CALIBRATION_PROTOCOL_VERSION = "pvt_calibration_3min_v1"
LEGACY_PROTOCOL_VERSION = "pvt_b_v1"
BASELINE_WINDOW_DAYS = 28
BASELINE_MINIMUM_DAYS = 7
BASELINE_RELIABLE_DAYS = 14
_SUMMARY_FIELDS = (
    "trial_count", "valid_trial_count", "median_rt_ms", "mean_rt_ms",
    "mean_response_speed", "fastest_10pct_rt_ms", "slowest_10pct_rt_ms",
    "fastest_20pct_rt_ms", "slowest_20pct_rt_ms",
    "rt_standard_deviation", "rt_coefficient_of_variation", "lapse_355_count",
    "lapse_500_count", "false_start_count", "first_half_median_rt_ms",
    "second_half_median_rt_ms", "time_on_task_change_ms",
)


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _percentile_mean(values: list[float], highest: bool = False, fraction: float = 0.1) -> float | None:
    if not values:
        return None
    ordered = sorted(values, reverse=highest)
    count = max(1, math.ceil(len(ordered) * fraction))
    return statistics.fmean(ordered[:count])


def normalise_trials(trials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply the protocol's validity rules independently of browser values."""
    normalized = []
    for index, trial in enumerate(trials or [], start=1):
        stimulus = _number(trial.get("stimulus_time_ms"))
        response = _number(trial.get("response_time_ms"))
        reaction = _number(trial.get("reaction_time_ms"))
        false_start = bool(trial.get("is_false_start")) or stimulus is None
        if reaction is None and stimulus is not None and response is not None:
            reaction = response - stimulus
        if reaction is not None and reaction < 100:
            false_start = True
        valid = not false_start and reaction is not None and reaction >= 100
        normalized.append({
            # A false start can precede the next stimulus.  The browser's
            # stimulus ordinal is therefore not a unique raw-trial ordinal.
            "trial_index": index,
            "stimulus_time_ms": stimulus,
            "response_time_ms": response,
            "reaction_time_ms": reaction,
            "is_valid": int(valid),
            "is_false_start": int(false_start),
            "is_lapse_355": int(valid and reaction > 355),
            "is_lapse_500": int(valid and reaction > 500),
        })
    return normalized


def calculate_pvt_metrics(trials: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute PVT-B summaries; response speed is mean(1 / RT_ms), in 1/ms."""
    normalized = normalise_trials(trials)
    valid = [item["reaction_time_ms"] for item in normalized if item["is_valid"]]
    midpoint = len(valid) // 2
    first_half, second_half = valid[:midpoint], valid[midpoint:]
    mean_rt = _mean(valid)
    standard_deviation = statistics.stdev(valid) if len(valid) >= 2 else 0.0 if valid else None
    return {
        "trial_count": len(normalized),
        "valid_trial_count": len(valid),
        "median_rt_ms": _median(valid),
        "mean_rt_ms": mean_rt,
        "mean_response_speed": _mean([1 / value for value in valid]),
        "fastest_10pct_rt_ms": _percentile_mean(valid),
        "slowest_10pct_rt_ms": _percentile_mean(valid, highest=True),
        "fastest_20pct_rt_ms": _percentile_mean(valid, fraction=0.2),
        "slowest_20pct_rt_ms": _percentile_mean(valid, highest=True, fraction=0.2),
        "rt_standard_deviation": standard_deviation,
        "rt_coefficient_of_variation": (
            standard_deviation / mean_rt if standard_deviation is not None and mean_rt else None
        ),
        "lapse_355_count": sum(item["is_lapse_355"] for item in normalized),
        "lapse_500_count": sum(item["is_lapse_500"] for item in normalized),
        "false_start_count": sum(item["is_false_start"] for item in normalized),
        "first_half_median_rt_ms": _median(first_half),
        "second_half_median_rt_ms": _median(second_half),
        "time_on_task_change_ms": (
            _median(second_half) - _median(first_half)
            if first_half and second_half else None
        ),
    }


def _baseline(connection, assessment_date: str, *, test_mode: str, protocol_version: str,
              baseline_group: str, device_context: dict[str, Any]) -> tuple[int, dict[str, dict[str, float | None]]]:
    target = date.fromisoformat(assessment_date)
    start = (target - timedelta(days=BASELINE_WINDOW_DAYS)).isoformat()
    rows = connection.execute(
        """SELECT metrics_json, device_context FROM neural_assessments
           WHERE assessment_date>=? AND assessment_date<? AND valid_for_baseline=1
             AND test_mode=? AND protocol_version=? AND baseline_group=?
           ORDER BY assessment_date DESC LIMIT ?""",
        (start, assessment_date, test_mode, protocol_version, baseline_group,
         28 if test_mode == "daily_short" else 12),
    ).fetchall()
    input_mode = (device_context or {}).get("input_mode")
    parsed = []
    for row in rows:
        context = json.loads(row["device_context"] or "{}")
        # Do not blend input methods when both runs state one explicitly.
        if input_mode and context.get("input_mode") and context.get("input_mode") != input_mode:
            continue
        parsed.append(json.loads(row["metrics_json"] or "{}"))
    fields = (
        "median_rt_ms", "mean_response_speed", "lapse_355_count",
        "mental_fatigue", "mental_clarity", "task_motivation", "physical_heaviness",
    )
    result: dict[str, dict[str, float | None]] = {}
    for field in fields:
        values = [_number(row.get(field)) for row in parsed]
        values = [value for value in values if value is not None]
        center = _median(values)
        std = statistics.stdev(values) if len(values) >= 2 else None
        result[field] = {"median": center, "std": std, "sample_count": len(values)}
    return len(parsed), result


def _deviations(current: dict[str, Any], baseline: dict[str, dict[str, float | None]]) -> dict[str, dict[str, float | None]]:
    values = {}
    for name, reference in baseline.items():
        current_value, center = _number(current.get(name)), reference["median"]
        delta = current_value - center if current_value is not None and center is not None else None
        percent = delta / abs(center) * 100 if delta is not None and center not in (None, 0) else None
        z = delta / reference["std"] if delta is not None and reference["std"] not in (None, 0) else None
        values[name] = {
            "baseline_median": center, "absolute_delta": delta,
            "percent_delta": percent, "z_score": z,
        }
    return values


def _baseline_status(sample_count: int, median_rt_deviation: dict[str, float | None]) -> str:
    if sample_count < BASELINE_MINIMUM_DAYS:
        return "insufficient"
    z = median_rt_deviation.get("z_score")
    if z is not None and z >= 1:
        return "slower_than_baseline"
    if z is not None and z <= -1:
        return "faster_than_baseline"
    return "within_baseline"


def _confidence(metrics: dict[str, Any], sample_count: int, *, interrupted: bool, sleep_available: bool) -> str:
    if interrupted or metrics["valid_trial_count"] < 5:
        return "unavailable"
    if sample_count >= BASELINE_RELIABLE_DAYS and metrics["valid_trial_count"] >= 10 and sleep_available:
        return "high"
    if sample_count >= BASELINE_MINIMUM_DAYS and metrics["valid_trial_count"] >= 10:
        return "moderate"
    return "low"


def save_assessment(payload: dict[str, Any], db_path=None) -> dict[str, Any]:
    """Atomically upsert an assessment and its one-per-date daily projection."""
    required = ("id", "assessment_date", "started_at", "completed_at", "timezone")
    missing = [key for key in required if not payload.get(key)]
    if missing:
        raise ValueError(f"Missing neural assessment fields: {', '.join(missing)}")
    assessment_date = str(payload["assessment_date"])
    date.fromisoformat(assessment_date)
    scales = {name: int(payload[name]) for name in (
        "mental_fatigue", "mental_clarity", "task_motivation", "physical_heaviness"
    )}
    if any(value < 0 or value > 10 for value in scales.values()):
        raise ValueError("Neural Readiness scales must be integers from 0 to 10")
    metrics = calculate_pvt_metrics(payload.get("trials", []))
    test_mode = payload.get("test_mode", "daily_short")
    if test_mode not in {"daily_short", "weekly_calibration", "legacy_3min"}:
        raise ValueError("Unknown alertness test mode")
    protocol_version = payload.get("protocol_version") or DAILY_SHORT_PROTOCOL_VERSION
    baseline_group = payload.get("baseline_group") or test_mode
    interrupted = bool(payload.get("interrupted"))
    valid_for_baseline = bool(payload.get("valid_for_baseline")) and not interrupted and metrics["valid_trial_count"] >= 5
    connection = connect(db_path or get_current_db_path())
    try:
        sleep = connection.execute(
            """SELECT sleep_score,nightly_hrv_rmssd,morning_rmssd
               FROM daily_recovery_metrics WHERE date=?""", (assessment_date,)
        ).fetchone()
        sleep_values = dict(sleep) if sleep else {
            "sleep_score": None, "nightly_hrv_rmssd": None, "morning_rmssd": None,
        }
        sample_count, baseline = _baseline(connection, assessment_date, test_mode=test_mode,
            protocol_version=protocol_version, baseline_group=baseline_group,
            device_context=payload.get("device_context") or {})
        current = {**metrics, **scales}
        deviations = _deviations(current, baseline)
        status = _baseline_status(sample_count, deviations["median_rt_ms"])
        confidence = _confidence(
            metrics, sample_count, interrupted=interrupted,
            sleep_available=any(value is not None for value in sleep_values.values()),
        )
        connection.execute(
            """INSERT INTO neural_assessments(
                 id,assessment_date,started_at,completed_at,timezone,protocol_version,
                 mental_fatigue,mental_clarity,task_motivation,physical_heaviness,
                 caffeine_last_2h,exercise_last_2h,illness_or_discomfort,interrupted,
                 valid_for_baseline,device_context,test_mode,duration_seconds,baseline_group,
                 calibration_trigger,calibration_reason,metrics_json
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 completed_at=excluded.completed_at, mental_fatigue=excluded.mental_fatigue,
                 mental_clarity=excluded.mental_clarity, task_motivation=excluded.task_motivation,
                 physical_heaviness=excluded.physical_heaviness, caffeine_last_2h=excluded.caffeine_last_2h,
                 exercise_last_2h=excluded.exercise_last_2h, illness_or_discomfort=excluded.illness_or_discomfort,
                 interrupted=excluded.interrupted, valid_for_baseline=excluded.valid_for_baseline,
                 device_context=excluded.device_context, test_mode=excluded.test_mode,
                 duration_seconds=excluded.duration_seconds, baseline_group=excluded.baseline_group,
                 calibration_trigger=excluded.calibration_trigger, calibration_reason=excluded.calibration_reason,
                 metrics_json=excluded.metrics_json""",
            (payload["id"], assessment_date, payload["started_at"], payload["completed_at"],
             payload["timezone"], protocol_version, *scales.values(),
             int(bool(payload.get("caffeine_last_2h"))), int(bool(payload.get("exercise_last_2h"))),
             int(bool(payload.get("illness_or_discomfort"))), int(interrupted), int(valid_for_baseline),
             json.dumps(payload.get("device_context") or {}, ensure_ascii=False, sort_keys=True), test_mode,
             payload.get("duration_seconds"), baseline_group, payload.get("calibration_trigger"),
             payload.get("calibration_reason"), json.dumps(metrics, ensure_ascii=False, sort_keys=True)),
        )
        connection.execute("DELETE FROM pvt_trials WHERE assessment_id=?", (payload["id"],))
        connection.executemany(
            """INSERT INTO pvt_trials(assessment_id,trial_index,stimulus_time_ms,response_time_ms,
               reaction_time_ms,is_valid,is_false_start,is_lapse_355,is_lapse_500)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            [(payload["id"], item["trial_index"], item["stimulus_time_ms"], item["response_time_ms"],
              item["reaction_time_ms"], item["is_valid"], item["is_false_start"],
              item["is_lapse_355"], item["is_lapse_500"]) for item in normalise_trials(payload.get("trials", []))],
        )
        # The daily projection is deliberately reserved for the short daily protocol.
        if test_mode != "daily_short":
            connection.commit()
            return {"assessment_id": payload["id"], **metrics, **scales, "baseline_status": status,
                    "baseline_sample_count": sample_count, "baseline_deviations": deviations,
                    "confidence_level": confidence, "interrupted": interrupted, "test_mode": test_mode,
                    "valid_for_baseline": valid_for_baseline, **sleep_values}
        columns = (*_SUMMARY_FIELDS, *scales, "sleep_score", "nightly_hrv_rmssd", "morning_rmssd",
                   "baseline_status", "baseline_sample_count", "baseline_deviations_json", "confidence_level",
                   "test_mode", "duration_seconds", "protocol_version", "baseline_group")
        values = [metrics[field] for field in _SUMMARY_FIELDS] + list(scales.values()) + [
            sleep_values["sleep_score"], sleep_values["nightly_hrv_rmssd"], sleep_values["morning_rmssd"],
            status, sample_count, json.dumps(deviations, ensure_ascii=False, sort_keys=True), confidence,
            test_mode, payload.get("duration_seconds"), protocol_version, baseline_group,
        ]
        assignments = ", ".join(f"{column}=excluded.{column}" for column in columns if column != "assessment_id")
        connection.execute(
            f"""INSERT INTO daily_neural_features(date,assessment_id,{','.join(columns)})
                VALUES({','.join('?' for _ in range(len(columns) + 2))})
                ON CONFLICT(date) DO UPDATE SET assessment_id=excluded.assessment_id,{assignments},
                updated_at=CURRENT_TIMESTAMP""",
            [assessment_date, payload["id"], *values],
        )
        connection.commit()
        return {"assessment_id": payload["id"], **metrics, **scales, "baseline_status": status,
                "baseline_sample_count": sample_count, "baseline_deviations": deviations,
                "confidence_level": confidence, "interrupted": interrupted,
                "valid_for_baseline": valid_for_baseline, "test_mode": test_mode, **sleep_values}
    finally:
        connection.close()


def get_daily_result(result_date: str | None = None, db_path=None) -> dict[str, Any] | None:
    connection = connect(db_path or get_current_db_path(), migrate=False)
    try:
        if result_date is None:
            row = connection.execute("SELECT * FROM daily_neural_features ORDER BY date DESC LIMIT 1").fetchone()
        else:
            row = connection.execute("SELECT * FROM daily_neural_features WHERE date=?", (result_date,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["baseline_deviations"] = json.loads(result.pop("baseline_deviations_json") or "{}")
        assessment = connection.execute(
            "SELECT interrupted,valid_for_baseline,caffeine_last_2h,exercise_last_2h,illness_or_discomfort FROM neural_assessments WHERE id=?",
            (result["assessment_id"],),
        ).fetchone()
        result.update(dict(assessment) if assessment else {})
        return result
    except sqlite3.OperationalError:
        # A brand-new database may not have been opened through the write-side
        # connection yet.  The page will create the migration on first save.
        return None
    finally:
        connection.close()


DATA_DICTIONARY = {
    "mean_response_speed": "Mean of 1 / valid reaction time in 1/ms; higher means faster responses.",
    "lapse_355_count": "Count of valid reaction times greater than 355 ms.",
    "lapse_500_count": "Count of valid reaction times greater than 500 ms.",
    "valid_for_baseline": "Only uninterrupted sessions with at least 10 valid trials may enter the personal baseline.",
}


def get_condition_preferences(db_path=None) -> dict[str, bool]:
    """Return remembered condition choices; missing values default to ready-to-test."""
    defaults = {"quiet": True, "dominant": True, "stay": True, "device_ok": True}
    connection = connect(db_path or get_current_db_path())
    try:
        row = connection.execute(
            "SELECT condition_preferences_json FROM neural_assessment_preferences WHERE id=1"
        ).fetchone()
        saved = json.loads(row["condition_preferences_json"] or "{}") if row else {}
        return {key: bool(saved.get(key, value)) for key, value in defaults.items()}
    finally:
        connection.close()


def save_condition_preferences(preferences: dict[str, Any], db_path=None) -> None:
    """Persist only the user's four non-sensitive workflow defaults."""
    values = {key: bool(preferences.get(key)) for key in ("quiet", "dominant", "stay", "device_ok")}
    connection = connect(db_path or get_current_db_path())
    try:
        connection.execute(
            """INSERT INTO neural_assessment_preferences(id,condition_preferences_json)
               VALUES(1,?) ON CONFLICT(id) DO UPDATE SET
               condition_preferences_json=excluded.condition_preferences_json,
               updated_at=CURRENT_TIMESTAMP""",
            (json.dumps(values, ensure_ascii=False, sort_keys=True),),
        )
        connection.commit()
    finally:
        connection.close()
