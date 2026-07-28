"""Read-only domain projections for the five top-level App sections."""

from __future__ import annotations

import json
import sqlite3
from datetime import date as date_type
from datetime import datetime, time, timedelta
from pathlib import Path

from .baseline import calculate_baseline_from_values, load_baseline_config
from .dashboard_data import DB_PATH, connect_readonly, duration_to_minutes
from .data_resolution import (
    resolve_activity_fields,
    resolve_recovery_date,
    resolve_sleep_date,
)
from .sport_catalog import resolve_sport_name


def _resolved_value(value, source="missing", record_id=None, *, fallback=False,
                    override=False, reason=None):
    return {
        "field_name": "",
        "value": value,
        "value_source": "missing" if value in (None, "") else source,
        "source_record_id": record_id,
        "is_fallback": bool(fallback),
        "is_manual_override": bool(override),
        "resolution_reason": reason or (
            "no_permitted_source_value_available"
            if value in (None, "") else f"{source}_value_available"
        ),
        "resolved_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def _with_name(field_name, field):
    return {**field, "field_name": field_name}


def _aggregate_resolved(field_name, value, fields):
    available = [field for field in fields if field and field.get("value") not in (None, "")]
    if value in (None, "") or not available:
        return _with_name(field_name, _resolved_value(None))
    sources = {field["value_source"] for field in available}
    source = next(iter(sources)) if len(sources) == 1 else "estimated"
    return _with_name(field_name, _resolved_value(
        value,
        source,
        fallback=any(field.get("is_fallback") for field in available),
        override=any(field.get("is_manual_override") for field in available),
        reason=(
            "aggregate_of_resolved_session_values"
            if len(available) > 1 or len(sources) > 1
            else available[0].get("resolution_reason")
        ),
    ))


def _json(value):
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _first(mapping, *keys):
    for key in keys:
        if mapping.get(key) not in (None, ""):
            return mapping[key]
    return None


def _number(value):
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _nested(mapping, *path):
    value = mapping
    for key in path:
        value = value.get(key) if isinstance(value, dict) else None
    return value


def _duration_value(value):
    if value in (None, ""):
        return None
    text = str(value).strip()
    if text.lower().endswith("s") and not text.startswith("P"):
        return _number(text[:-1])
    return value


def _parse_datetime(value):
    try:
        return datetime.fromisoformat(str(value)) if value not in (None, "") else None
    except ValueError:
        return None


def _sleep_raw_heart_rates(raw):
    samples = raw.get("heart_rate_samples") or raw.get("heartRateSamples")
    if isinstance(samples, dict):
        return [_number(value) for value in samples.values() if _number(value) is not None]
    if isinstance(samples, list):
        values = []
        for sample in samples:
            if isinstance(sample, dict):
                value = _number(_first(sample, "heart_rate", "heartRate", "value"))
                if value is not None:
                    values.append(value)
        return values
    return []


def _continuous_sleep_heart_rates(connection, start_value, end_value):
    start = _parse_datetime(start_value)
    end = _parse_datetime(end_value)
    if not start or not end or end <= start:
        return []
    # Continuous-HR payloads can contain thousands of samples per day.  Sleep
    # views only need the samples inside the sleep window, so compare the raw
    # millisecond offsets first instead of constructing a datetime for every
    # sample.  Besides preserving the exact result, this keeps history-page
    # loading responsive when a month of sleep records is rendered.
    date_bounds = {}
    cursor = start.date()
    while cursor <= end.date():
        midnight = datetime.combine(cursor, time.min, tzinfo=start.tzinfo)
        lower = max(0.0, (start - midnight).total_seconds() * 1000)
        upper = min(86_400_000.0, (end - midnight).total_seconds() * 1000)
        date_bounds[cursor.isoformat()] = (lower, upper)
        cursor += timedelta(days=1)
    dates = tuple(date_bounds)
    placeholders = ",".join("?" for _ in dates)
    rows = connection.execute(
        f"SELECT date,raw_json FROM polar_continuous_hr_raw WHERE date IN ({placeholders})",
        dates,
    ).fetchall()
    values = []
    for row in rows:
        raw = _json(row["raw_json"])
        samples = raw.get("samples")
        if not isinstance(samples, list):
            samples = raw.get("heart_rate_samples") or raw.get("heartRateSamples")
        if not isinstance(samples, list):
            continue
        lower, upper = date_bounds[row["date"]]
        sample_date = None
        midnight = None
        for sample in samples:
            if not isinstance(sample, dict):
                continue
            # Polar's normal shape uses numeric ``heartRate`` and
            # ``offsetMillis``.  Keep the slower compatibility path only for
            # legacy/alternate payloads.
            heart_rate = sample.get("heartRate")
            offset = sample.get("offsetMillis")
            if not isinstance(heart_rate, (int, float)) or not isinstance(offset, (int, float)):
                if heart_rate is None:
                    heart_rate = sample.get("heart_rate")
                if heart_rate is None:
                    heart_rate = sample.get("value")
                if offset is None:
                    offset = sample.get("offset_millis")
                heart_rate = _number(heart_rate)
                offset = _number(offset)
            if offset is not None:
                if heart_rate is not None and lower <= offset <= upper:
                    values.append(heart_rate)
                continue
            if sample_date is None:
                sample_date = date_type.fromisoformat(row["date"])
                midnight = datetime.combine(sample_date, time.min, tzinfo=start.tzinfo)
            clock = sample.get("sample_time", sample.get("sampleTime", sample.get("time")))
            try:
                parsed_time = time.fromisoformat(str(clock))
                timestamp = datetime.combine(sample_date, parsed_time, tzinfo=start.tzinfo)
            except (TypeError, ValueError):
                continue
            if heart_rate is not None and start <= timestamp <= end:
                values.append(heart_rate)
    return values


def _sport_name(value):
    return resolve_sport_name(value)


def _polar_sport(record):
    raw = _json(record.get("raw_json"))
    return _sport_name(_first(raw, "sport")) or record.get("sport")


def _weighted_average(items, value_key, weight_key):
    weighted = [(item.get(value_key), item.get(weight_key)) for item in items]
    weighted = [(float(value), float(weight)) for value, weight in weighted if value is not None and weight not in (None, 0)]
    if weighted:
        return sum(value * weight for value, weight in weighted) / sum(weight for _, weight in weighted)
    values = [float(item[value_key]) for item in items if item.get(value_key) is not None]
    return sum(values) / len(values) if values else None


def get_latest_training(db_path=None, log_date=None):
    connection = connect_readonly(db_path)
    try:
        latest = log_date or connection.execute(
            """SELECT MAX(log_date) FROM (
                   SELECT date AS log_date FROM polar_training_sessions_raw
                   UNION ALL
                   SELECT date AS log_date FROM manual_activity_sessions
                   WHERE start_time IS NOT NULL OR end_time IS NOT NULL
                      OR duration_minutes IS NOT NULL OR activity_type IS NOT NULL
                      OR activity_name IS NOT NULL OR average_hr_bpm IS NOT NULL
                      OR max_hr_bpm IS NOT NULL OR calories_kcal IS NOT NULL
                      OR fat_burn_percentage IS NOT NULL OR distance_m IS NOT NULL
                      OR session_rpe IS NOT NULL OR notes IS NOT NULL
               )"""
        ).fetchone()[0]
        if not latest:
            return None
        polar_rows = connection.execute(
            "SELECT * FROM polar_training_sessions_raw WHERE date=? ORDER BY start_time,id",
            (latest,),
        ).fetchall()
        manual_rows = connection.execute(
            """SELECT * FROM manual_activity_sessions WHERE date=?
               AND (start_time IS NOT NULL OR end_time IS NOT NULL
                    OR duration_minutes IS NOT NULL OR activity_type IS NOT NULL
                    OR activity_name IS NOT NULL OR average_hr_bpm IS NOT NULL
                    OR max_hr_bpm IS NOT NULL OR calories_kcal IS NOT NULL
                    OR fat_burn_percentage IS NOT NULL OR distance_m IS NOT NULL
                    OR session_rpe IS NOT NULL OR notes IS NOT NULL)
               ORDER BY start_time,id""",
            (latest,),
        ).fetchall()
        manual_by_id = {row["id"]: dict(row) for row in manual_rows}
        links = connection.execute(
            """SELECT * FROM polar_manual_session_links
               WHERE confirmed_by_user=1 AND manual_activity_session_id IS NOT NULL"""
        ).fetchall()
        link_by_polar = {
            row["polar_session_external_id"]: row["manual_activity_session_id"]
            for row in links
        }
        linked_manual_ids = set(link_by_polar.values())
        sessions = []
        for row in polar_rows:
            polar = dict(row)
            manual = manual_by_id.get(link_by_polar.get(row["external_id"]))
            resolved = resolve_activity_fields(
                polar, manual, link_confirmed=True,
            )
            sessions.append({
                "session_key": f"polar:{row['external_id']}",
                "polar_external_id": row["external_id"],
                "manual_record_id": manual.get("id") if manual else None,
                "sport": _sport_name(resolved["activity_type"]["value"]),
                "polar_sport": _polar_sport(polar),
                "start_time": resolved["start_time"]["value"],
                "duration_minutes": resolved["duration_minutes"]["value"],
                "average_hr_bpm": resolved["average_hr_bpm"]["value"],
                "maximum_hr_bpm": resolved["max_hr_bpm"]["value"],
                "calories": resolved["calories_kcal"]["value"],
                "fat_percentage": resolved["fat_burn_percentage"]["value"],
                "distance_m": resolved["distance_m"]["value"],
                "session_rpe": resolved["session_rpe"]["value"],
                "resolved_fields": resolved,
                "link_confirmed": manual is not None,
                "pending_link": False,
            })
        for row in manual_rows:
            if row["id"] in linked_manual_ids:
                continue
            manual = dict(row)
            resolved = resolve_activity_fields(None, manual, link_confirmed=False)
            pending = bool(manual.get("linked_polar_session_id"))
            sessions.append({
                "session_key": f"manual:{row['id']}",
                "polar_external_id": None,
                "manual_record_id": row["id"],
                "sport": _sport_name(resolved["activity_type"]["value"]),
                "polar_sport": None,
                "start_time": resolved["start_time"]["value"],
                "duration_minutes": resolved["duration_minutes"]["value"],
                "average_hr_bpm": resolved["average_hr_bpm"]["value"],
                "maximum_hr_bpm": resolved["max_hr_bpm"]["value"],
                "calories": resolved["calories_kcal"]["value"],
                "fat_percentage": resolved["fat_burn_percentage"]["value"],
                "distance_m": resolved["distance_m"]["value"],
                "session_rpe": resolved["session_rpe"]["value"],
                "resolved_fields": resolved,
                "link_confirmed": False,
                "pending_link": pending,
            })
        aggregate_sessions = [item for item in sessions if not item["pending_link"]]
        total_duration = sum(item["duration_minutes"] or 0 for item in aggregate_sessions) or None
        total_calories = sum(item["calories"] or 0 for item in aggregate_sessions) or None
        average_hr = _weighted_average(aggregate_sessions, "average_hr_bpm", "duration_minutes")
        maximum_hr = max((item["maximum_hr_bpm"] for item in aggregate_sessions if item["maximum_hr_bpm"] is not None), default=None)
        fat_percentage = _weighted_average(aggregate_sessions, "fat_percentage", "calories")
        sports = sorted({item["sport"] for item in aggregate_sessions if item["sport"]})
        resolved = {
            "activity_type": _aggregate_resolved(
                "activity_type", sports,
                [item["resolved_fields"]["activity_type"] for item in aggregate_sessions],
            ),
            "duration_minutes": _aggregate_resolved(
                "duration_minutes", total_duration,
                [item["resolved_fields"]["duration_minutes"] for item in aggregate_sessions],
            ),
            "average_hr_bpm": _aggregate_resolved(
                "average_hr_bpm", average_hr,
                [item["resolved_fields"]["average_hr_bpm"] for item in aggregate_sessions],
            ),
            "max_hr_bpm": _aggregate_resolved(
                "max_hr_bpm", maximum_hr,
                [item["resolved_fields"]["max_hr_bpm"] for item in aggregate_sessions],
            ),
            "calories_kcal": _aggregate_resolved(
                "calories_kcal", total_calories,
                [item["resolved_fields"]["calories_kcal"] for item in aggregate_sessions],
            ),
            "fat_burn_percentage": _aggregate_resolved(
                "fat_burn_percentage", fat_percentage,
                [item["resolved_fields"]["fat_burn_percentage"] for item in aggregate_sessions],
            ),
        }
        return {
            "date": latest,
            "sports": sports,
            "duration_minutes": total_duration,
            "average_hr_bpm": average_hr,
            "maximum_hr_bpm": maximum_hr,
            "calories": total_calories,
            "fat_percentage": fat_percentage,
            "sessions": sessions,
            "resolved_fields": resolved,
        }
    except sqlite3.OperationalError:
        return None
    finally:
        connection.close()


def get_latest_sleep(db_path=None, log_date=None):
    connection = connect_readonly(db_path)
    try:
        latest = log_date or connection.execute(
            """SELECT MAX(log_date) FROM (
                   SELECT date AS log_date FROM daily_recovery_metrics
                   WHERE sleep_duration IS NOT NULL OR sleep_score IS NOT NULL
                      OR nightly_hrv_rmssd IS NOT NULL OR nightly_resting_hr IS NOT NULL
                      OR respiration_rate IS NOT NULL
                   UNION ALL SELECT date FROM polar_sleep_raw
                   UNION ALL SELECT date FROM polar_nightly_recharge_raw
                   UNION ALL SELECT sleep_date FROM manual_sleep_logs
               )"""
        ).fetchone()[0]
        if not latest:
            return None
        row = connection.execute(
            """SELECT date,sleep_duration,sleep_score,nightly_hrv_rmssd,
                      nightly_resting_hr,respiration_rate
               FROM daily_recovery_metrics WHERE date=?""",
            (latest,),
        ).fetchone()
        daily = dict(row) if row else {
            "date": latest, "sleep_duration": None, "sleep_score": None,
            "nightly_hrv_rmssd": None, "nightly_resting_hr": None,
            "respiration_rate": None,
        }
        sleep_raw = connection.execute(
            "SELECT raw_json FROM polar_sleep_raw WHERE date=? ORDER BY id DESC LIMIT 1",
            (latest,),
        ).fetchone()
        raw = _json(sleep_raw[0]) if sleep_raw else {}
        manual_row = connection.execute(
            "SELECT id FROM manual_sleep_logs WHERE sleep_date=? ORDER BY id DESC LIMIT 1",
            (latest,),
        ).fetchone()
        nightly_raw = connection.execute(
            "SELECT 1 FROM polar_nightly_recharge_raw WHERE date=? LIMIT 1",
            (latest,),
        ).fetchone()
        result = raw.get("sleepResult") if isinstance(raw.get("sleepResult"), dict) else {}
        hypnogram = result.get("hypnogram") if isinstance(result.get("hypnogram"), dict) else {}
        evaluation = raw.get("sleepEvaluation") if isinstance(raw.get("sleepEvaluation"), dict) else {}
        phases = evaluation.get("phaseDurations") if isinstance(evaluation.get("phaseDurations"), dict) else {}
        bedtime = _first(hypnogram, "sleepStart") or _first(
            raw, "bedtimeStart", "sleepStartTime", "sleep_start_time", "startTime"
        )
        wake_time = _first(hypnogram, "sleepEnd") or _first(
            raw, "bedtimeEnd", "wakeUpTime", "wake_time", "sleep_end_time", "endTime"
        )
        heart_rates = _sleep_raw_heart_rates(raw)
        if not heart_rates:
            heart_rates = _continuous_sleep_heart_rates(connection, bedtime, wake_time)
        projection = {
            **daily,
            "bedtime": bedtime,
            "wake_time": wake_time,
            "sleep_state_changes": hypnogram.get("sleepStateChanges") or [],
            "total_sleep_duration": _duration_value(
                _first(evaluation, "sleepSpan")
                or _first(raw, "totalSleep", "total_sleep", "sleepDuration", "sleep_duration")
                or daily["sleep_duration"]
            ),
            "actual_sleep_duration": _duration_value(
                _first(evaluation, "asleepDuration")
                or _first(raw, "actualSleep", "actualSleepDuration", "actual_sleep_duration")
            ),
            "deep_sleep_duration": _duration_value(
                _first(phases, "deep")
                or _first(raw, "deep_sleep", "deepSleep", "deepSleepDuration", "deep_sleep_duration")
            ),
            "rem_sleep_duration": _duration_value(
                _first(phases, "rem")
                or _first(raw, "rem_sleep", "remSleep", "remSleepDuration", "rem_sleep_duration")
            ),
            "average_sleep_hr_bpm": (
                sum(heart_rates) / len(heart_rates)
                if heart_rates
                else _number(_first(raw, "averageHeartRate", "sleepAvgHr", "heartRateAvg"))
            ),
            "minimum_sleep_hr_bpm": (
                min(heart_rates)
                if heart_rates
                else _number(_first(raw, "lowestHeartRate", "minimumHeartRate", "sleepMinHr"))
            ),
        }
        resolved = resolve_sleep_date(connection, latest)

        def device_fallback(name, value):
            field = resolved.get(name)
            if field and field.get("value") not in (None, ""):
                return _with_name(name, field)
            return _with_name(name, _resolved_value(value, "polar"))

        projection["resolved_fields"] = {
            "sleep_start_time": device_fallback("sleep_start_time", bedtime),
            "wake_time": device_fallback("wake_time", wake_time),
            "total_sleep_duration_minutes": device_fallback(
                "total_sleep_duration_minutes",
                duration_to_minutes(projection["total_sleep_duration"]),
            ),
            "actual_sleep_duration_minutes": device_fallback(
                "actual_sleep_duration_minutes",
                duration_to_minutes(projection["actual_sleep_duration"]),
            ),
            "deep_sleep_duration_minutes": device_fallback(
                "deep_sleep_duration_minutes",
                duration_to_minutes(projection["deep_sleep_duration"]),
            ),
            "rem_sleep_duration_minutes": device_fallback(
                "rem_sleep_duration_minutes",
                duration_to_minutes(projection["rem_sleep_duration"]),
            ),
            "average_sleep_hr_bpm": device_fallback(
                "average_sleep_hr_bpm", projection["average_sleep_hr_bpm"],
            ),
            "minimum_sleep_hr_bpm": device_fallback(
                "minimum_sleep_hr_bpm", projection["minimum_sleep_hr_bpm"],
            ),
            "nightly_hrv_rmssd": device_fallback(
                "nightly_hrv_rmssd", daily["nightly_hrv_rmssd"],
            ),
            "nightly_resting_hr": device_fallback(
                "nightly_resting_hr", daily["nightly_resting_hr"],
            ),
            "respiration_rate": device_fallback(
                "respiration_rate", daily["respiration_rate"],
            ),
            **{
                name: _with_name(name, resolved[name])
                for name in (
                    "bed_time", "get_up_time", "nap_duration_minutes",
                    "subjective_sleep_quality", "awakenings",
                ) if name in resolved
            },
        }
        projection["manual_record_id"] = manual_row[0] if manual_row else None
        projection["has_observed_data"] = bool(
            sleep_raw or manual_row or nightly_raw or any(
                daily.get(name) is not None
                for name in (
                    "sleep_duration", "sleep_score", "nightly_hrv_rmssd",
                    "nightly_resting_hr", "respiration_rate",
                )
            )
        )
        return projection
    except sqlite3.OperationalError:
        return None
    finally:
        connection.close()


def get_latest_recovery(db_path=None, log_date=None):
    connection = connect_readonly(db_path)
    try:
        latest = log_date or connection.execute(
            """SELECT MAX(log_date) FROM (
                   SELECT date AS log_date FROM daily_recovery_metrics
                   WHERE morning_rmssd IS NOT NULL OR morning_mean_hr IS NOT NULL
                   UNION ALL SELECT date FROM kubios_morning_hrv_raw
                   UNION ALL SELECT date FROM manual_recovery_logs
               )"""
        ).fetchone()[0]
        if not latest:
            return None
        row = connection.execute(
            """SELECT m.date,m.morning_rmssd,m.morning_mean_hr,s.recovery_score,
                      s.recommendation,s.score_version
               FROM daily_recovery_metrics m
               LEFT JOIN recovery_scores s ON s.date=m.date WHERE m.date=?""",
            (latest,),
        ).fetchone()
        data = dict(row) if row else {
            "date": latest, "morning_rmssd": None, "morning_mean_hr": None,
            "recovery_score": None, "recommendation": None, "score_version": None,
        }
        resolved = resolve_recovery_date(connection, latest)
        manual_row = connection.execute(
            "SELECT id FROM manual_recovery_logs WHERE date=? ORDER BY id DESC LIMIT 1",
            (latest,),
        ).fetchone()
        kubios_row = connection.execute(
            """SELECT stress_index,respiratory_rate,measurement_quality
               FROM kubios_morning_hrv_raw WHERE date=?
               ORDER BY is_daily_preferred DESC, reviewed DESC,
                        measurement_time DESC, updated_at DESC, id DESC LIMIT 1""",
            (latest,),
        ).fetchone()
        for name, legacy_name in (
            ("morning_rmssd", "morning_rmssd"),
            ("morning_mean_hr", "morning_mean_hr"),
        ):
            if resolved[name]["value"] in (None, "") and data[legacy_name] is not None:
                resolved[name] = _resolved_value(data[legacy_name], "kubios")
        data["resolved_fields"] = {
            name: _with_name(name, field) for name, field in resolved.items()
            if name != "notes"
        }
        data["morning_rmssd"] = data["resolved_fields"]["morning_rmssd"]["value"]
        data["morning_mean_hr"] = data["resolved_fields"]["morning_mean_hr"]["value"]
        data["measurement_time"] = data["resolved_fields"].get("measurement_time", {}).get("value")
        data["manual_record_id"] = manual_row[0] if manual_row else None
        data["stress_index"] = kubios_row[0] if kubios_row else None
        data["respiratory_rate"] = kubios_row[1] if kubios_row else None
        data["measurement_quality"] = kubios_row[2] if kubios_row else None
        return data
    except sqlite3.OperationalError:
        return None
    finally:
        connection.close()


def get_recovery_history(db_path=None, limit=60):
    """Return resolved core recovery fields plus reviewed Kubios morning inputs."""
    connection = connect_readonly(db_path)
    try:
        dates = [row[0] for row in connection.execute(
            """SELECT log_date FROM (
                   SELECT date AS log_date FROM daily_recovery_metrics
                   WHERE morning_rmssd IS NOT NULL OR morning_mean_hr IS NOT NULL
                   UNION SELECT date FROM kubios_morning_hrv_raw
                   UNION SELECT date FROM manual_recovery_logs
               ) ORDER BY log_date DESC LIMIT ?""",
            (limit,),
        ).fetchall()]
        records = []
        for date_value in dates:
            resolved = resolve_recovery_date(connection, date_value)
            raw = connection.execute(
                """SELECT stress_index,respiratory_rate,measurement_quality
                   FROM kubios_morning_hrv_raw WHERE date=?
                   ORDER BY is_daily_preferred DESC,reviewed DESC,
                            measurement_time DESC,updated_at DESC,id DESC LIMIT 1""",
                (date_value,),
            ).fetchone()
            records.append({
                "date": date_value,
                "morning_rmssd": resolved["morning_rmssd"]["value"],
                "morning_mean_hr": resolved["morning_mean_hr"]["value"],
                "stress_index": raw[0] if raw else None,
                "respiratory_rate": raw[1] if raw else None,
                "measurement_quality": raw[2] if raw else None,
            })
        return records
    except sqlite3.OperationalError:
        return []
    finally:
        connection.close()


def get_recovery_baselines(db_path=None, target_date=None, window_days=28):
    """Build morning baselines from the same resolved values shown on Recovery."""
    connection = connect_readonly(db_path)
    try:
        target = target_date or connection.execute(
            """SELECT MAX(log_date) FROM (
                   SELECT date AS log_date FROM daily_recovery_metrics
                   WHERE morning_rmssd IS NOT NULL OR morning_mean_hr IS NOT NULL
                   UNION ALL SELECT date FROM kubios_morning_hrv_raw
                   UNION ALL SELECT date FROM manual_recovery_logs
               )"""
        ).fetchone()[0]
        if not target:
            return {}

        target_day = date_type.fromisoformat(str(target))
        start = (target_day - timedelta(days=window_days)).isoformat()
        dates = [row[0] for row in connection.execute(
            """SELECT log_date FROM (
                   SELECT date AS log_date FROM daily_recovery_metrics
                   WHERE morning_rmssd IS NOT NULL OR morning_mean_hr IS NOT NULL
                   UNION SELECT date FROM kubios_morning_hrv_raw
                   UNION SELECT date FROM manual_recovery_logs
               ) WHERE log_date>=? AND log_date<? ORDER BY log_date""",
            (start, target_day.isoformat()),
        ).fetchall()]
        def resolved_values(log_date):
            fields = resolve_recovery_date(connection, log_date)
            legacy = connection.execute(
                "SELECT morning_rmssd,morning_mean_hr FROM daily_recovery_metrics WHERE date=?",
                (log_date,),
            ).fetchone()
            if legacy:
                for metric_name in ("morning_rmssd", "morning_mean_hr"):
                    if fields[metric_name]["value"] is None and legacy[metric_name] is not None:
                        fields[metric_name] = _with_name(
                            metric_name,
                            _resolved_value(legacy[metric_name], "kubios"),
                        )
            return fields

        resolved_history = [resolved_values(value) for value in dates]
        current = resolved_values(target_day.isoformat())

        config = load_baseline_config()
        config = {**config, "default_window_days": int(window_days)}
        metrics = {
            item["name"]: item for item in config["metrics"]
            if item["name"] in {"morning_rmssd", "morning_mean_hr"}
        }
        results = {}
        for metric_name, metric in metrics.items():
            values = [
                fields[metric_name]["value"]
                for fields in resolved_history
                if fields[metric_name]["value"] is not None
            ]
            results[metric_name] = calculate_baseline_from_values(
                target_day.isoformat(),
                metric,
                values,
                current[metric_name]["value"],
                config=config,
            )
        return results
    except (sqlite3.OperationalError, ValueError):
        return {}
    finally:
        connection.close()


def get_latest_nutrition(db_path=None):
    connection = connect_readonly(db_path)
    try:
        row = connection.execute(
            "SELECT * FROM daily_nutrition_summary ORDER BY date DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None
    except sqlite3.OperationalError:
        return None
    finally:
        connection.close()


def get_recent_nutrition(db_path=None, limit=30):
    connection = connect_readonly(db_path)
    try:
        rows = connection.execute(
            "SELECT date,calories,protein_g,carbohydrate_g,fat_g,fiber_g,water_ml,data_completeness FROM daily_nutrition_summary ORDER BY date DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in reversed(rows)]
    except sqlite3.OperationalError:
        return []
    finally:
        connection.close()


def _available_dates(db_path, queries, limit):
    connection = connect_readonly(db_path)
    try:
        union = " UNION ".join(queries)
        rows = connection.execute(
            f"SELECT log_date FROM ({union}) WHERE log_date IS NOT NULL ORDER BY log_date DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [row[0] for row in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        connection.close()


def get_training_history(db_path=None, limit=30):
    dates = _available_dates(db_path, (
        "SELECT date AS log_date FROM polar_training_sessions_raw",
        """SELECT date AS log_date FROM manual_activity_sessions
           WHERE start_time IS NOT NULL OR end_time IS NOT NULL
              OR duration_minutes IS NOT NULL OR activity_type IS NOT NULL
              OR activity_name IS NOT NULL OR average_hr_bpm IS NOT NULL
              OR max_hr_bpm IS NOT NULL OR calories_kcal IS NOT NULL
              OR fat_burn_percentage IS NOT NULL OR distance_m IS NOT NULL
              OR session_rpe IS NOT NULL OR notes IS NOT NULL""",
    ), limit)
    return [item for item in (get_latest_training(db_path, value) for value in dates) if item]


def get_sleep_history(db_path=None, limit=30):
    dates = _available_dates(db_path, (
        "SELECT date AS log_date FROM polar_sleep_raw",
        "SELECT date AS log_date FROM polar_nightly_recharge_raw",
        "SELECT sleep_date AS log_date FROM manual_sleep_logs",
        "SELECT date AS log_date FROM daily_recovery_metrics WHERE sleep_duration IS NOT NULL",
    ), limit)
    return [item for item in (get_latest_sleep(db_path, value) for value in dates) if item]


def get_domain_baselines(metric_names, db_path=None, window_days=28):
    connection = connect_readonly(db_path)
    try:
        placeholders = ",".join("?" for _ in metric_names)
        rows = connection.execute(
            f"""SELECT * FROM baseline_metrics WHERE window_days=?
                AND metric_name IN ({placeholders})
                AND date=(SELECT MAX(date) FROM baseline_metrics)
                ORDER BY metric_name""",
            (window_days, *metric_names),
        ).fetchall()
        return {row["metric_name"]: dict(row) for row in rows}
    except sqlite3.OperationalError:
        return {}
    finally:
        connection.close()
