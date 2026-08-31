"""Read-only workflow that projects existing observations into fatigue v0.1."""

from __future__ import annotations

import sqlite3
import statistics
from datetime import date, datetime, time
from pathlib import Path

from .db import get_current_db_path
from .neural_fatigue import ALGORITHM_VERSION, COMPONENT_NAMES, NeuralFatigueInputs, calculate_neural_fatigue
from .neural_fatigue_data import adapt_inputs
from .neural_fatigue_history import (
    COMPONENT_NAMES as HISTORY_COMPONENT_NAMES,
    get_daily_snapshot,
    list_component_history,
    list_daily_snapshots,
    save_daily_snapshot,
)
from .neural_fatigue_guidance import GuidanceInputs, calculate_guidance


def build_neural_fatigue_view(*, connection=None, db_path=None, target_date=None, now=None):
    """Return a stable, read-only page model from existing source tables."""
    now = now or datetime.now().astimezone()
    target = _as_date(target_date) or _latest_date(connection, db_path) or now.date()
    owns_connection = connection is None
    if owns_connection:
        path = Path(db_path) if db_path is not None else get_current_db_path()
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
    try:
        records = _records(connection, target, now)
        inputs = adapt_inputs(**records)
        result = calculate_neural_fatigue(inputs, computed_at=now)
        components = {name: getattr(inputs, name) for name in COMPONENT_NAMES}
        return {
            "result": result,
            "target_date": target,
            "latest_observation": max(
                (item.observed_at for item in components.values() if item is not None),
                default=None,
            ),
            "component_rows": tuple(_component_row(name, components[name], result) for name in COMPONENT_NAMES),
            "unavailable_reason": "minimum_data_condition_not_met" if result.status == "insufficient_data" else None,
        }
    finally:
        if owns_connection:
            connection.close()


def compute_current_result(**kwargs):
    """Name the pure current-result operation used by the persistence workflow."""
    return build_neural_fatigue_view(**kwargs)


def save_current_snapshot(*, view=None, connection=None, db_path=None, target_date=None, now=None):
    """Persist one explicitly requested view without reimplementing the algorithm."""
    owns_connection = connection is None
    if owns_connection:
        connection = _connection(db_path)
    try:
        current_view = view or compute_current_result(
            connection=connection, target_date=target_date, now=now,
        )
        result = save_daily_snapshot(connection, current_view)
        saved = get_daily_snapshot(
            connection, current_view["target_date"], current_view["result"].algorithm_version,
        )
        return {
            "persistence_status": result.status,
            "saved_at": saved.get("updated_at") if saved else None,
            "snapshot": saved,
        }
    finally:
        if owns_connection:
            connection.close()


def get_snapshot_for_date(*, snapshot_date, connection=None, db_path=None, algorithm_version=ALGORITHM_VERSION):
    """Return one persisted snapshot or None, with no ambient connection state."""
    owns_connection = connection is None
    if owns_connection:
        connection = _connection(db_path)
    try:
        return get_daily_snapshot(connection, snapshot_date, algorithm_version)
    finally:
        if owns_connection:
            connection.close()


def get_history(*, days, target_date, connection=None, db_path=None, algorithm_version=ALGORITHM_VERSION):
    """Return a bounded daily history view for one algorithm version."""
    owns_connection = connection is None
    if owns_connection:
        connection = _connection(db_path)
    try:
        rows = list_daily_snapshots(
            connection, days=days, end_date=target_date, algorithm_version=algorithm_version,
        )
        return {
            "history_rows": rows,
            "history_range_days": days,
            "available_days": sum(row["status"] == "available" for row in rows),
            "insufficient_days": sum(row["status"] == "insufficient_data" for row in rows),
        }
    finally:
        if owns_connection:
            connection.close()


def get_component_trends(*, days, target_date, connection=None, db_path=None, algorithm_version=ALGORITHM_VERSION):
    """Return each component series with database NULLs kept as Python None."""
    owns_connection = connection is None
    if owns_connection:
        connection = _connection(db_path)
    try:
        return {
            name: list_component_history(
                connection, component_name=name, days=days, end_date=target_date,
                algorithm_version=algorithm_version,
            )
            for name in HISTORY_COMPONENT_NAMES
        }
    finally:
        if owns_connection:
            connection.close()


def build_guidance_view(*, current_view=None, days=7, connection=None, db_path=None, now=None):
    """Build a read-only, deterministic guidance view from current and saved data."""
    if days not in (7, 14, 30):
        raise ValueError("guidance history window must be 7, 14, or 30 days")
    owns_connection = connection is None
    if owns_connection:
        connection = _connection(db_path)
    try:
        view = current_view or compute_current_result(connection=connection, now=now)
        history = get_history(
            connection=connection, days=days, target_date=view["target_date"],
        )
        components = get_component_trends(
            connection=connection, days=days, target_date=view["target_date"],
        )
        return calculate_guidance(GuidanceInputs(
            current_result=view["result"], current_snapshot_date=view["target_date"],
            history_summaries=tuple(history["history_rows"]),
            component_trends={name: tuple(rows) for name, rows in components.items()},
            available_history_days=history["available_days"],
            requested_history_window=days, computed_at=view["result"].computed_at,
        ))
    finally:
        if owns_connection:
            connection.close()


def _connection(db_path=None):
    connection = sqlite3.connect(Path(db_path) if db_path is not None else get_current_db_path())
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _records(connection, target, now):
    current = _daily_record(connection, target)
    observed_at = _observed_at(current.get("date") if current else target, now)
    freshness_hours = _hours_since(observed_at, now)
    baseline_counts = _baseline_counts(connection, target)
    cognitive = _cognitive_record(connection, target, now)
    return {
        "cognitive": cognitive,
        "recovery": ({
            "recovery_score": current.get("recovery_score"), "observed_at": observed_at,
            "baseline_sample_count": baseline_counts["recovery"], "source": "recovery_scores",
            "freshness_hours": freshness_hours,
        } if current else None),
        "sleep": ({
            "sleep_score": current.get("sleep_score"), "observed_at": observed_at,
            "baseline_sample_count": baseline_counts["sleep"], "source": "daily_recovery_metrics.sleep_score",
            "freshness_hours": freshness_hours,
        } if current else None),
        "training": ({
            "percent_difference": _number(current.get("training_percent_change")),
            "observed_at": observed_at, "baseline_sample_count": baseline_counts["training"],
            "source": "training_baseline",
            "freshness_hours": freshness_hours,
        } if current else None),
        "subjective": None,
    }


def _daily_record(connection, target):
    try:
        row = connection.execute(
            """SELECT m.date,m.sleep_score,s.recovery_score,
                      b.percent_change AS training_percent_change
                 FROM daily_recovery_metrics m
                 LEFT JOIN recovery_scores s ON s.date=m.date
                 LEFT JOIN baseline_metrics b ON b.date=m.date
                    AND b.metric_name='training_duration' AND b.window_days=28
                WHERE m.date<=? ORDER BY m.date DESC LIMIT 1""",
            (target.isoformat(),),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    return dict(row) if row else None


def _baseline_counts(connection, target):
    result = {"recovery": 0, "sleep": 0, "training": 0}
    try:
        rows = connection.execute(
            """SELECT metric_name,MAX(valid_days) AS valid_days FROM baseline_metrics
                 WHERE date<=? AND window_days=28
                   AND metric_name IN ('nightly_hrv_rmssd','morning_rmssd','sleep_score','training_duration')
                 GROUP BY metric_name""",
            (target.isoformat(),),
        ).fetchall()
    except sqlite3.OperationalError:
        return result
    values = {row["metric_name"]: int(row["valid_days"] or 0) for row in rows}
    result["recovery"] = max(values.get("nightly_hrv_rmssd", 0), values.get("morning_rmssd", 0))
    result["sleep"] = values.get("sleep_score", 0)
    result["training"] = values.get("training_duration", 0)
    return result


def _cognitive_record(connection, target, now):
    try:
        rows = connection.execute(
            """SELECT s.started_at,r.task_type,r.median_rt_ms,r.accuracy
                 FROM cognitive_training_sessions s
                 JOIN cognitive_training_task_results r ON r.session_id=s.id
                WHERE s.completed=1 AND substr(s.started_at,1,10)<=?
                  AND (r.median_rt_ms IS NOT NULL OR r.accuracy IS NOT NULL)
                ORDER BY s.started_at DESC""",
            (target.isoformat(),),
        ).fetchall()
    except sqlite3.OperationalError:
        return None
    if not rows:
        return None
    latest = dict(rows[0])
    candidates = [dict(row) for row in rows[1:] if row["task_type"] == latest["task_type"]]
    rt_values = [_number(row["median_rt_ms"]) for row in candidates]
    accuracy_values = [_number(row["accuracy"]) for row in candidates]
    rt_values = [value for value in rt_values if value is not None]
    accuracy_values = [value for value in accuracy_values if value is not None]
    observed_at = _parse_timestamp(latest["started_at"], now)
    return {
        "completed": True, "median_rt_ms": latest["median_rt_ms"], "accuracy": latest["accuracy"],
        "baseline_median_rt_ms": statistics.median(rt_values) if rt_values else None,
        "baseline_accuracy": statistics.fmean(accuracy_values) if accuracy_values else None,
        "baseline_sample_count": max(len(rt_values), len(accuracy_values)),
        "observed_at": observed_at, "source": "cognitive_training",
        "freshness_hours": _hours_since(observed_at, now),
    }


def _component_row(name, component, result):
    reasons = tuple(reason for reason in result.reasons if f"component_{name}_" in reason)
    return {
        "name": name, "score": component.score if component else None,
        "weight": result.component_weights.get(name), "source": component.source if component else None,
        "observed_at": component.observed_at if component else None,
        "freshness_hours": component.freshness_hours if component else None,
        "baseline_sample_count": component.baseline_sample_count if component else None,
        "quality": component.quality if component else None,
        "included": name in result.available_components, "reasons": reasons,
    }


def _latest_date(connection, db_path):
    owns_connection = connection is None
    if owns_connection:
        connection = sqlite3.connect(Path(db_path) if db_path else get_current_db_path())
    try:
        row = connection.execute("SELECT MAX(date) FROM daily_recovery_metrics").fetchone()
        return _as_date(row[0]) if row and row[0] else None
    except sqlite3.OperationalError:
        return None
    finally:
        if owns_connection:
            connection.close()


def _as_date(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def _observed_at(value, now):
    candidate = datetime.combine(_as_date(value) or now.date(), time.min, tzinfo=now.tzinfo)
    return min(candidate, now)


def _parse_timestamp(value, now):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        parsed = parsed if parsed.tzinfo else parsed.replace(tzinfo=now.tzinfo)
        return min(parsed, now)
    except ValueError:
        return now


def _number(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _hours_since(observed_at, now):
    return max((now - observed_at).total_seconds() / 3600, 0.0)
