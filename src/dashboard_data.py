import re
import sqlite3
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:
    from .db import DB_PATH, get_current_db_path
except ImportError:
    from db import DB_PATH, get_current_db_path


ISO_DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+(?:\.\d+)?)D)?"
    r"(?:T(?:(?P<hours>\d+(?:\.\d+)?)H)?"
    r"(?:(?P<minutes>\d+(?:\.\d+)?)M)?"
    r"(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?$"
)

METRICS_QUERY = """
SELECT
    m.date,
    m.steps,
    m.calories,
    m.active_calories,
    m.activity_duration,
    m.training_count,
    m.training_duration,
    m.training_calories,
    m.sleep_duration,
    m.sleep_score,
    m.nightly_hrv_rmssd,
    m.nightly_resting_hr,
    m.respiration_rate,
    m.morning_rmssd,
    m.morning_mean_hr,
    m.kubios_readiness,
    s.recovery_score,
    s.activity_load_score,
    s.training_load_score,
    s.hrv_score,
    s.morning_hr_score,
    s.readiness_score,
    s.score_version,
    s.recommendation
FROM daily_recovery_metrics m
LEFT JOIN recovery_scores s ON s.date = m.date
"""

BASELINE_QUERY = """
SELECT
    date,
    window_days,
    valid_days,
    metric_name,
    mean_value,
    median_value,
    latest_value,
    percent_change,
    z_score,
    robust_z_score,
    status
FROM baseline_metrics
WHERE date = (
    SELECT MAX(date) FROM baseline_metrics
)
AND window_days = ?
"""

CONFIDENCE_QUERY = """
SELECT date, data_completeness_score, baseline_maturity_score,
       confidence_score, confidence_level, missing_groups_json,
       confidence_version
FROM recovery_confidence
ORDER BY date DESC LIMIT 1
"""


def duration_to_seconds(value):
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return int(value)

    text = str(value).strip()
    if text.isdigit():
        return int(text)

    match = ISO_DURATION_RE.match(text)
    if not match:
        return None

    days = float(match.group("days") or 0)
    hours = float(match.group("hours") or 0)
    minutes = float(match.group("minutes") or 0)
    seconds = float(match.group("seconds") or 0)
    return int(days * 86400 + hours * 3600 + minutes * 60 + seconds)


def duration_to_hours(value):
    seconds = duration_to_seconds(value)
    if seconds is None:
        return None
    return round(seconds / 3600, 2)


def duration_to_minutes(value):
    seconds = duration_to_seconds(value)
    if seconds is None:
        return None
    return round(seconds / 60, 1)


def row_to_dict(row):
    if row is None:
        return None
    data = dict(row)
    data["activity_duration_hours"] = duration_to_hours(data.get("activity_duration"))
    data["training_duration_hours"] = duration_to_hours(data.get("training_duration"))
    data["training_duration_minutes"] = duration_to_minutes(data.get("training_duration"))
    data["sleep_duration_hours"] = duration_to_hours(data.get("sleep_duration"))
    return data


def connect_readonly(db_path=None):
    db_path = get_current_db_path() if db_path is None else Path(db_path)
    if not db_path.exists():
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        return connection
    uri = f"file:{db_path.resolve()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def is_database_readable(db_path=None):
    """Return whether the configured SQLite file can answer a read-only query."""
    db_path = get_current_db_path() if db_path is None else Path(db_path)
    if not db_path.exists():
        return False
    try:
        connection = connect_readonly(db_path)
        try:
            connection.execute("SELECT 1").fetchone()
        finally:
            connection.close()
    except sqlite3.Error:
        return False
    return True


def get_latest_day(db_path=None):
    connection = connect_readonly(db_path)
    try:
        try:
            row = connection.execute(
                METRICS_QUERY + " ORDER BY m.date DESC LIMIT 1"
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        return row_to_dict(row)
    finally:
        connection.close()


def get_day_metrics(day, db_path=None):
    connection = connect_readonly(db_path)
    try:
        try:
            row = connection.execute(
                METRICS_QUERY + " WHERE m.date=? LIMIT 1", (day,)
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        return row_to_dict(row)
    finally:
        connection.close()


def get_recent_days(limit, db_path=None):
    connection = connect_readonly(db_path)
    try:
        try:
            rows = connection.execute(
                METRICS_QUERY + " ORDER BY m.date DESC LIMIT ?",
                (limit,),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [row_to_dict(row) for row in reversed(rows)]
    finally:
        connection.close()


def get_last_7_days(db_path=None):
    return get_recent_days(7, db_path=db_path)


def get_last_30_days(db_path=None):
    return get_recent_days(30, db_path=db_path)


def get_personal_logging_trends(db_path=None, limit=90):
    """Return local aggregate trends and degrade to empty when schema is absent."""
    connection = connect_readonly(db_path)
    try:
        try:
            body = connection.execute(
                "SELECT date,weight_kg,waist_cm,body_fat_percent FROM body_measurements ORDER BY date DESC,is_primary DESC,id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            nutrition = connection.execute(
                "SELECT date,calories,protein_g,carbohydrate_g,fat_g,data_completeness FROM daily_nutrition_summary ORDER BY date DESC LIMIT ?",
                (limit,),
            ).fetchall()
            training = connection.execute(
                "SELECT date,total_volume_kg,hiphop_duration_minutes,session_rpe_load FROM daily_training_summary ORDER BY date DESC LIMIT ?",
                (limit,),
            ).fetchall()
        except sqlite3.OperationalError:
            return {"body": [], "nutrition": [], "training": []}
        return {
            "body": [dict(row) for row in reversed(body)],
            "nutrition": [dict(row) for row in reversed(nutrition)],
            "training": [dict(row) for row in reversed(training)],
        }
    finally:
        connection.close()


def get_latest_baselines(db_path=None, window_days=28, metric_names=None):
    connection = connect_readonly(db_path)
    try:
        try:
            rows = connection.execute(BASELINE_QUERY, (window_days,)).fetchall()
        except sqlite3.OperationalError:
            return {}

        baselines = {row["metric_name"]: dict(row) for row in rows}
        if metric_names is None:
            return baselines
        return {
            metric_name: baselines.get(metric_name)
            for metric_name in metric_names
        }
    finally:
        connection.close()


def get_latest_confidence(db_path=None):
    connection = connect_readonly(db_path)
    try:
        try:
            row = connection.execute(CONFIDENCE_QUERY).fetchone()
        except sqlite3.OperationalError:
            return None
        if not row:
            return None
        result = dict(row)
        result["missing_groups"] = json.loads(result.pop("missing_groups_json"))
        return result
    finally:
        connection.close()


def get_latest_kubios_core(db_path=None, today=None, stale_after_days=3):
    """Return only the latest reviewed daily primary core/derived projection."""
    connection = connect_readonly(db_path)
    try:
        try:
            row = connection.execute(
                """SELECT n.date,n.measurement_time,n.source_type,n.rmssd_ms,n.mean_hr_bpm,
                          n.readiness_percent,n.pns_index,n.sns_index,n.measurement_quality,
                          n.core_data_completeness,d.rmssd_vs_baseline_percent,
                          d.mean_hr_vs_baseline_percent,d.readiness_vs_baseline_percent,
                          d.pns_vs_baseline_delta,d.sns_vs_baseline_delta,d.data_quality_status
                   FROM kubios_hrv_normalized n
                   LEFT JOIN kubios_hrv_derived d ON d.date=n.date
                   WHERE n.selected_as_primary=1 ORDER BY n.date DESC,n.measurement_time DESC LIMIT 1"""
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        if not row:
            return None
        result = dict(row)
        age = max(((today or date.today()) - date.fromisoformat(result["date"])).days, 0)
        result["freshness_days"] = age
        result["is_historical"] = age > stale_after_days
        return result
    finally:
        connection.close()


def get_kubios_advanced_metrics(db_path=None, limit=28, date_value=None):
    """Read full selected Kubios metrics, optionally for one measurement date."""
    connection = connect_readonly(db_path)
    try:
        try:
            query = """SELECT n.*,r.mean_rr_ms,r.poincare_sd1_ms,r.poincare_sd2_ms,
                          r.lf_power_ms2,r.hf_power_ms2,r.lf_power_nu,r.hf_power_nu,
                          r.lf_hf_ratio,r.mood_code,d.rmssd_7d_trend,d.mean_hr_7d_trend,
                          d.readiness_7d_trend,d.pns_7d_trend,d.sns_7d_trend,
                          d.rmssd_vs_baseline_percent,d.mean_hr_vs_baseline_percent,
                          d.readiness_vs_baseline_percent,d.data_quality_status,
                          d.source_reliability_status
                   FROM kubios_hrv_normalized n
                   JOIN kubios_hrv_measurements_raw r ON r.id=n.source_raw_id
                   LEFT JOIN kubios_hrv_derived d ON d.date=n.date
                   WHERE n.selected_as_primary=1"""
            params = []
            if date_value:
                query += " AND n.date=?"
                params.append(date_value)
            query += " ORDER BY n.date DESC,n.measurement_time DESC LIMIT ?"
            rows = connection.execute(query, (*params, limit)).fetchall()
        except sqlite3.OperationalError:
            return []
        results = [dict(row) for row in rows]
        group_fields = (
            "mean_rr_ms", "poincare_sd1_ms", "poincare_sd2_ms", "lf_power_ms2",
            "hf_power_ms2", "lf_power_nu", "hf_power_nu", "lf_hf_ratio", "mood_code",
        )
        for result in results:
            group_id = result.get("measurement_group_id")
            if not group_id:
                continue
            members = connection.execute(
                "SELECT * FROM kubios_hrv_measurements_raw WHERE measurement_group_id=? "
                "ORDER BY source_priority,id",
                (group_id,),
            ).fetchall()
            for field in group_fields:
                result[field] = next(
                    (member[field] for member in members if member[field] is not None),
                    result.get(field),
                )
        return results
    finally:
        connection.close()


def get_latest_local_coach(db_path=None, today=None, stale_after_days=3, coach_date=None):
    """Load a scored local recommendation read-only and fail softly if absent."""
    connection = connect_readonly(db_path)
    try:
        try:
            query = """SELECT c.*
                       FROM local_coach_recommendations c
                       JOIN recovery_scores s ON s.date=c.date
                       WHERE s.recovery_score IS NOT NULL"""
            params = []
            if coach_date:
                query += " AND c.date=?"
                params.append(coach_date)
            query += " ORDER BY c.date DESC, c.updated_at DESC LIMIT 1"
            row = connection.execute(query, params).fetchone()
        except sqlite3.OperationalError:
            return None
        if not row:
            return None
        result = dict(row)
        for key in ("morning_training", "evening_training", "training_summary", "sleep_advice", "hydration_advice",
                    "nutrition_advice", "recovery_advice", "rationale", "data_limitations", "safety_notices"):
            try:
                raw = result.pop(f"{key}_json", "{}")
                result[key] = json.loads(raw) if raw else {}
            except (KeyError, TypeError, json.JSONDecodeError):
                return None
        current = today or date.today()
        age = max((current - date.fromisoformat(result["date"])).days, 0)
        result["freshness_days"] = age
        result["is_historical"] = age > stale_after_days
        result["generated_without_cloud_ai"] = bool(result["generated_without_cloud_ai"])
        return result
    finally:
        connection.close()


def get_latest_ai_feedback(db_path=None, analysis_date=None):
    """Load the latest validated Codex feedback without exposing request data."""

    connection = connect_readonly(db_path)
    try:
        try:
            if analysis_date:
                row = connection.execute(
                    "SELECT * FROM ai_feedback_outputs WHERE date=?", (analysis_date,)
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT * FROM ai_feedback_outputs ORDER BY date DESC, generated_at DESC LIMIT 1"
                ).fetchone()
        except sqlite3.OperationalError:
            return None
        if not row:
            return None
        value = dict(row)
        try:
            output = json.loads(value.pop("output_json"))
        except (KeyError, TypeError, json.JSONDecodeError):
            return None
        if not isinstance(output, dict):
            return None
        result = {**value, **output}
        result["is_stale"] = _ai_feedback_is_stale(connection, result)
        return result
    finally:
        connection.close()


def _parse_timestamp(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _ai_feedback_is_stale(connection, feedback):
    """Do not present an AI explanation after its deterministic inputs changed."""
    generated_at = _parse_timestamp(feedback.get("generated_at"))
    feedback_date = feedback.get("date")
    if generated_at is None or not feedback_date:
        return True
    try:
        prior_date = (date.fromisoformat(str(feedback_date)) - timedelta(days=1)).isoformat()
    except ValueError:
        return True
    try:
        from src.ai_coach_contract import load_contract

        audit = feedback.get("audit") or {}
        contract = load_contract()
        if (
            audit.get("prompt_version") != contract["prompt_version"]
            or audit.get("output_schema_version") != contract["output_schema_version"]
            or audit.get("safety_policy_version") != contract["safety_policy_version"]
        ):
            return True
    except (ImportError, ValueError, TypeError):
        return True
    try:
        source_rows = connection.execute(
            """
            SELECT MAX(updated_at) FROM daily_recovery_metrics WHERE date=?
            UNION ALL SELECT MAX(updated_at) FROM baseline_metrics WHERE date=?
            UNION ALL SELECT MAX(updated_at) FROM recovery_scores WHERE date=?
            UNION ALL SELECT MAX(updated_at) FROM recovery_confidence WHERE date=?
            UNION ALL SELECT MAX(updated_at) FROM daily_recovery_metrics WHERE date=?
            UNION ALL SELECT MAX(updated_at) FROM daily_training_summary WHERE date=?
            UNION ALL SELECT MAX(updated_at) FROM daily_nutrition_summary WHERE date=?
            UNION ALL SELECT MAX(updated_at) FROM meal_records
                             WHERE date=? AND deleted_at IS NULL
            """,
            (
                feedback_date, feedback_date, feedback_date, feedback_date,
                prior_date, prior_date, prior_date, prior_date,
            ),
        ).fetchall()
    except sqlite3.OperationalError:
        return True
    return any(
        updated_at is not None and (_parse_timestamp(updated_at) is None or _parse_timestamp(updated_at) > generated_at)
        for (updated_at,) in source_rows
    )


def get_prospective_progress(db_path=None, today=None):
    """Return aggregate prospective progress without exposing recommendation data."""
    try:
        from .local_coach.prospective import evaluate_prospective
        connection = connect_readonly(db_path)
        try:
            return evaluate_prospective(connection, today=today)
        finally:
            connection.close()
    except (OSError, RuntimeError, ValueError, sqlite3.Error):
        return None


def get_daily_collection_status(db_path=None, today=None):
    try:
        from .local_coach.collection import monitor_daily_collection
        connection = connect_readonly(db_path)
        try:
            return monitor_daily_collection(connection, today=today)
        finally:
            connection.close()
    except (OSError, RuntimeError, ValueError, sqlite3.Error):
        return None


def get_data_freshness(db_path=None, today=None):
    try:
        from .data_freshness import collect_freshness
        return collect_freshness(db_path=db_path, today=today)
    except (OSError, RuntimeError, ValueError, sqlite3.Error):
        return None


def display_value(value, suffix="", default="暂无数据"):
    if value is None or value == "":
        return default
    if isinstance(value, float):
        value = round(value, 2)
    return f"{value}{suffix}"
