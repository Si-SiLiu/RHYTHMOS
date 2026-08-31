"""Read-only, allowlisted projection for user-reviewed manual upload."""

from datetime import datetime, timedelta
import json

from .safety import require_free_text_confirmation, validate_questions
from .schemas import validate_export
from .whitelist import assert_allowlisted
from src.i18n import get_translator, normalize_language
from src.personal_logging.summaries import build_body_summary
from src.data_resolution import resolve_recovery_date, resolve_sleep_date
from src.nutrition_logging import ai_meal_summaries, ai_supplement_summary
from src.training_logging import ai_training_summaries


SUPPORTED_RANGES = {1, 7, 14, 30}
def observed(value, estimated=False):
    return {"value": value, "status": "missing" if value is None else ("estimated" if estimated else "measured")}


def observed_resolved(field, data_date):
    field = field or {}
    value = field.get("value")
    return {
        "value": value,
        "status": "missing" if value is None else (
            "estimated" if field.get("value_source") == "estimated" else "measured"
        ),
        "value_source": field.get("value_source", "missing"),
        "is_fallback": bool(field.get("is_fallback", False)),
        "is_manual_override": bool(field.get("is_manual_override", False)),
        "data_date": data_date,
    }


def _row(connection, query, params):
    try:
        result = connection.execute(query, params).fetchone()
    except Exception:
        return None
    return dict(result) if result else None


def build_ai_context(connection, analysis_date, range_days=7, questions=None,
                     include_free_text=False, first_confirmation=False,
                     second_confirmation=False, language="zh-CN",
                     include_advanced_kubios=False,
                     advanced_first_confirmation=False,
                     advanced_second_confirmation=False):
    language = normalize_language(language)
    tr = get_translator(language)
    if range_days not in SUPPORTED_RANGES:
        raise ValueError("AI_CONTEXT_UNSUPPORTED_RANGE")
    include_notes = require_free_text_confirmation(
        include_free_text, first_confirmation, second_confirmation
    )
    include_advanced = require_free_text_confirmation(
        include_advanced_kubios, advanced_first_confirmation,
        advanced_second_confirmation,
    )
    user_questions = validate_questions(questions)
    body = build_body_summary(connection, analysis_date)
    recovery = _row(connection, "SELECT recovery_score,recommendation,score_version FROM recovery_scores WHERE date=?", (analysis_date,)) or {}
    daily = _row(connection, "SELECT sleep_duration,sleep_score FROM daily_recovery_metrics WHERE date=?", (analysis_date,)) or {}
    try:
        sleep_resolved = resolve_sleep_date(connection, analysis_date)
    except Exception:
        sleep_resolved = {}
    try:
        recovery_resolved = resolve_recovery_date(connection, analysis_date)
    except Exception:
        recovery_resolved = {}
    try:
        rows = connection.execute(
            """SELECT domain,field_name,resolved_value_json,value_source,
                      is_fallback,is_manual_override
               FROM resolved_daily_fields WHERE date=? AND field_name!='notes'
               ORDER BY updated_at DESC""",
            (analysis_date,),
        ).fetchall()
        persisted_resolved = {}
        for row in rows:
            domain = persisted_resolved.setdefault(row["domain"], {})
            if row["field_name"] in domain:
                continue
            try:
                value = json.loads(row["resolved_value_json"])
            except (TypeError, json.JSONDecodeError):
                value = None
            domain[row["field_name"]] = {
                "value": value,
                "value_source": row["value_source"],
                "is_fallback": bool(row["is_fallback"]),
                "is_manual_override": bool(row["is_manual_override"]),
            }
    except Exception:
        persisted_resolved = {}
    hrv_baseline = _row(connection, "SELECT status,percent_change FROM baseline_metrics WHERE date=? AND metric_name='nightly_hrv_rmssd' ORDER BY window_days DESC LIMIT 1", (analysis_date,)) or {}
    confidence = _row(connection, "SELECT confidence_score,confidence_level,data_completeness_score FROM recovery_confidence WHERE date=?", (analysis_date,)) or {}
    nutrition = _row(connection, "SELECT * FROM daily_nutrition_summary WHERE date=?", (analysis_date,)) or {}
    training = _row(connection, "SELECT * FROM daily_training_summary WHERE date=?", (analysis_date,)) or {}
    coach = _row(connection, "SELECT morning_training_json,evening_training_json,training_summary_json,data_limitations_json FROM local_coach_recommendations WHERE date=? ORDER BY updated_at DESC LIMIT 1", (analysis_date,)) or {}
    kubios = _row(connection, """SELECT n.date,n.source_type,n.core_data_completeness,
        n.rmssd_ms,n.mean_hr_bpm,n.readiness_percent,n.pns_index,n.sns_index,
        n.measurement_quality,n.sdnn_ms,n.respiratory_rate_bpm,n.stress_index,
        d.rmssd_vs_baseline_percent,d.mean_hr_vs_baseline_percent,
        d.sdnn_vs_baseline_percent,d.readiness_vs_baseline_percent,
        d.pns_vs_baseline_delta,d.sns_vs_baseline_delta,
        d.respiratory_rate_vs_baseline_percent,d.stress_index_vs_baseline_percent,
        d.rmssd_7d_trend,d.mean_hr_7d_trend,d.readiness_7d_trend,
        d.pns_7d_trend,d.sns_7d_trend,d.consecutive_rmssd_below_baseline_days,
        d.consecutive_mean_hr_above_baseline_days,d.consecutive_readiness_decline_days,
        d.data_quality_status,d.source_reliability_status,n.source_raw_id,
        n.measurement_group_id
        FROM kubios_hrv_normalized n LEFT JOIN kubios_hrv_derived d ON d.date=n.date
        WHERE n.date=? AND n.selected_as_primary=1 ORDER BY n.measurement_time DESC LIMIT 1""", (analysis_date,)) or {}
    start_date = (datetime.fromisoformat(analysis_date).date() - timedelta(days=range_days - 1)).isoformat()
    trend_rows = connection.execute(
        "SELECT date,total_volume_kg,hiphop_duration_minutes,session_rpe_load FROM daily_training_summary WHERE date BETWEEN ? AND ? ORDER BY date",
        (start_date, analysis_date),
    ).fetchall()
    exercise_rows = connection.execute(
        """SELECT e.exercise_name,COUNT(*) AS sets,SUM(e.reps) AS reps,
                  SUM(CASE WHEN e.weight_kg IS NOT NULL AND e.reps IS NOT NULL
                           THEN e.weight_kg * e.reps END) AS volume_kg
           FROM exercise_sets e JOIN workout_sessions w ON w.id=e.workout_session_id
           WHERE w.date BETWEEN ? AND ? GROUP BY e.exercise_name ORDER BY e.exercise_name""",
        (start_date, analysis_date),
    ).fetchall()
    body_summary = {key: observed(value) for key, value in body.items()}
    nutrition_fields = ("logged_meals", "calories", "protein_g", "carbohydrate_g", "fat_g", "fiber_g", "water_ml", "sodium_mg", "data_completeness")
    training_fields = ("session_count", "total_duration_minutes", "total_sets", "total_reps", "total_volume_kg", "average_session_rpe", "session_rpe_load", "hiphop_duration_minutes", "juggling_duration_minutes")
    limitations = []
    if nutrition.get("data_completeness", 0) < 100:
        limitations.append(tr("reports.missing_nutrition"))
    sleep_duration_field = sleep_resolved.get("actual_sleep_duration_minutes")
    if not sleep_duration_field or sleep_duration_field.get("value") is None:
        sleep_duration_field = {
            "value": daily.get("sleep_duration"), "value_source": "polar" if daily.get("sleep_duration") is not None else "missing",
            "is_fallback": False, "is_manual_override": False,
        }
    sleep_summary = {
        "sleep_duration": observed_resolved(sleep_duration_field, analysis_date),
        "sleep_score": observed_resolved({
            "value": daily.get("sleep_score"),
            "value_source": "polar" if daily.get("sleep_score") is not None else "missing",
            "is_fallback": False, "is_manual_override": False,
        }, analysis_date),
        "hrv_relative_to_baseline": observed({
            "status": hrv_baseline.get("status"),
            "percent_change": round(hrv_baseline["percent_change"], 1)
            if hrv_baseline.get("percent_change") is not None else None,
        } if hrv_baseline else None),
    }
    for name in (
        "subjective_sleep_quality", "awakenings", "nap_duration_minutes",
        "nightly_hrv_rmssd", "nightly_resting_hr", "respiration_rate",
    ):
        field = sleep_resolved.get(name)
        if field and field.get("value") is not None:
            sleep_summary[name] = observed_resolved(field, analysis_date)

    recovery_summary = {
        "recovery_score": observed(recovery.get("recovery_score")),
        "recommendation": observed(recovery.get("recommendation")),
        "score_version": recovery.get("score_version"),
        "confidence": observed(confidence.get("confidence_score")),
        "confidence_level": confidence.get("confidence_level"),
    }
    for name in (
        "morning_rmssd", "morning_mean_hr", "subjective_recovery", "fatigue",
        "muscle_soreness", "mental_energy", "training_motivation", "stress_level",
        "pain_present",
    ):
        field = recovery_resolved.get(name)
        if field and field.get("value") is not None:
            recovery_summary[name] = observed_resolved(field, analysis_date)

    activity_resolved = persisted_resolved.get("activity", {})
    resolved_activity_summary = {
        name: observed_resolved(field, analysis_date)
        for name, field in activity_resolved.items()
        if name in {
            "activity_type", "duration_minutes", "average_hr_bpm", "max_hr_bpm",
            "calories_kcal", "fat_burn_percentage", "distance_m", "session_rpe",
        }
    }

    payload = {
        "schema_version": "1.0.0",
        "export_generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "date": analysis_date, "range_days": range_days,
        "display_language": language,
        "localized_summary": tr("recovery.summary", version=recovery.get("score_version") or tr("recovery.unknown_version"), score=recovery.get("recovery_score") if recovery.get("recovery_score") is not None else tr("common.no_data"), recommendation=recovery.get("recommendation") or tr("recovery.no_recommendation")),
        "data_freshness": {"latest_available_date": analysis_date},
        "body_summary": body_summary,
        "recovery_summary": recovery_summary,
        "sleep_summary": sleep_summary,
        "nutrition_summary": {
            **{key: observed(nutrition.get(key)) for key in nutrition_fields},
            "meals": ai_meal_summaries(connection, analysis_date),
            "supplements": ai_supplement_summary(connection, analysis_date),
        },
        "training_summary": {
            **{key: observed(training.get(key)) for key in training_fields},
            "exercise_summary": [dict(row) for row in exercise_rows],
            "sessions": ai_training_summaries(connection, analysis_date),
            "resolved_activity": resolved_activity_summary,
        },
        "local_coach_summary": {
            "morning_training": json.loads(coach["morning_training_json"]) if coach.get("morning_training_json") else None,
            "evening_training": json.loads(coach["evening_training_json"]) if coach.get("evening_training_json") else None,
            "training_summary": json.loads(coach["training_summary_json"]) if coach.get("training_summary_json") else None,
        },
        "kubios_summary": {
            key: observed_resolved({
                "value": kubios.get(key),
                "value_source": "kubios" if kubios.get(key) is not None else "missing",
                "is_fallback": False,
                "is_manual_override": False,
            }, kubios.get("date") or analysis_date) for key in (
                "date","source_type","core_data_completeness","rmssd_ms","mean_hr_bpm",
                "readiness_percent","pns_index","sns_index","measurement_quality","sdnn_ms",
                "respiratory_rate_bpm","stress_index","rmssd_vs_baseline_percent",
                "mean_hr_vs_baseline_percent","sdnn_vs_baseline_percent",
                "readiness_vs_baseline_percent","pns_vs_baseline_delta","sns_vs_baseline_delta",
                "respiratory_rate_vs_baseline_percent","stress_index_vs_baseline_percent",
                "rmssd_7d_trend","mean_hr_7d_trend","readiness_7d_trend","pns_7d_trend",
                "sns_7d_trend","consecutive_rmssd_below_baseline_days",
                "consecutive_mean_hr_above_baseline_days","consecutive_readiness_decline_days",
                "data_quality_status","source_reliability_status",
            )
        },
        "trend_summary": [dict(row) for row in trend_rows],
        "data_limitations": limitations,
        "user_questions": user_questions,
        "privacy_notice": tr("ai_context.privacy_notice"),
    }
    if include_notes:
        # Free text remains deliberately absent until a dedicated allowlisted field exists.
        payload["data_limitations"].append(tr("reports.missing_nutrition"))
    if include_advanced and kubios.get("source_raw_id"):
        fields = (
            "mean_rr_ms", "poincare_sd1_ms", "poincare_sd2_ms", "lf_power_ms2",
            "hf_power_ms2", "lf_power_nu", "hf_power_nu", "lf_hf_ratio",
            "physiological_age", "mood_code",
        )
        if kubios.get("measurement_group_id"):
            try:
                members = connection.execute(
                    "SELECT * FROM kubios_hrv_measurements_raw WHERE measurement_group_id=? "
                    "ORDER BY source_priority,id",
                    (kubios["measurement_group_id"],),
                ).fetchall()
            except Exception:
                members = []
            advanced = {
                field: next(
                    (member[field] for member in members if member[field] is not None),
                    None,
                )
                for field in fields
            }
        else:
            advanced = _row(
                connection,
                f"SELECT {','.join(fields)} FROM kubios_hrv_measurements_raw WHERE id=?",
                (kubios["source_raw_id"],),
            ) or {}
        payload["kubios_summary"]["advanced_metrics"] = {
            key: observed(value) for key, value in advanced.items()
        }
    return validate_export(assert_allowlisted(payload))
