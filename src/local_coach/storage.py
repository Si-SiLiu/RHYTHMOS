"""Read-only input assembly and idempotent Local Coach persistence."""

import json
from datetime import date as date_type

from ..daily_metrics import duration_to_seconds
from ..recovery_explain import generate_recovery_explanation
from .models import CoachInput

ENGINE_VERSION = "1.0.0"


def _dict(row):
    return dict(row) if row else {}


def _duration(value, divisor):
    seconds = duration_to_seconds(value)
    return seconds / divisor if seconds else None


def _average(values):
    values = [float(value) for value in values if value is not None]
    return sum(values) / len(values) if values else None


def _row_or_empty(connection, sql, parameters=()):
    """Read an optional sidecar table without making old databases fail."""
    try:
        row = connection.execute(sql, parameters).fetchone()
    except Exception:
        return {}
    return _dict(row)


def _nutrition_context(connection, coach_date):
    """Prefer the current meal editor, then fall back to legacy nutrition logs."""
    modern = _row_or_empty(
        connection,
        """
        SELECT COUNT(DISTINCT r.id) AS logged_meals,
               SUM(i.calories_kcal) AS calories,
               SUM(i.protein_g) AS protein_g,
               SUM(i.carbohydrate_g) AS carbohydrate_g,
               SUM(i.water_ml) AS water_ml,
               COUNT(i.id) AS item_count,
               SUM(CASE WHEN i.calories_kcal IS NOT NULL
                             OR i.protein_g IS NOT NULL
                             OR i.carbohydrate_g IS NOT NULL
                             OR i.water_ml IS NOT NULL THEN 1 ELSE 0 END) AS known_item_count
        FROM meal_records r
        LEFT JOIN meal_items i ON i.meal_record_id = r.id
             AND i.deleted_at IS NULL
        WHERE r.date = ? AND r.status = 'completed' AND r.deleted_at IS NULL
        """,
        (coach_date,),
    )
    if modern.get("logged_meals"):
        item_count = modern.get("item_count") or 0
        completeness = (
            (modern.get("known_item_count") or 0) / item_count * 100
            if item_count else 0
        )
        source = modern
        source["data_completeness"] = round(completeness)
    else:
        source = _row_or_empty(
            connection,
            "SELECT logged_meals,calories,protein_g,carbohydrate_g,water_ml,data_completeness "
            "FROM daily_nutrition_summary WHERE date = ?",
            (coach_date,),
        )
    targets = {}
    try:
        targets = {
            row["metric"]: (row["minimum_value"], row["maximum_value"])
            for row in connection.execute(
                "SELECT metric,minimum_value,maximum_value FROM nutrition_targets"
            ).fetchall()
        }
    except Exception:
        pass
    completeness = source.get("data_completeness")
    if completeness is not None and float(completeness) <= 1:
        completeness = float(completeness) * 100
    return {
        "logged_meals": source.get("logged_meals"),
        "calories": source.get("calories"),
        "protein_g": source.get("protein_g"),
        "carbohydrate_g": source.get("carbohydrate_g"),
        "water_ml": source.get("water_ml"),
        "data_completeness": completeness,
        "targets": targets,
    }


def available_dates(connection):
    return [row[0] for row in connection.execute("SELECT date FROM recovery_scores ORDER BY date")]


def latest_date(connection):
    row = connection.execute("SELECT MAX(date) FROM recovery_scores").fetchone()
    return row[0] if row and row[0] else None


def load_input(connection, coach_date, today=None, freshness_days=3):
    row = connection.execute(
        """
        SELECT m.*, s.recovery_score, s.activity_load_score, s.training_load_score,
               s.hrv_score, s.morning_hr_score, s.readiness_score, s.score_version,
               c.data_completeness_score, c.confidence_score, c.confidence_level
        FROM daily_recovery_metrics m
        JOIN recovery_scores s ON s.date = m.date
        LEFT JOIN recovery_confidence c ON c.date = m.date
        WHERE m.date = ?
        """, (coach_date,)
    ).fetchone()
    if not row:
        raise ValueError(f"No deterministic recovery result for {coach_date}")
    values = _dict(row)
    previous = _dict(connection.execute(
        "SELECT * FROM daily_recovery_metrics WHERE date < ? ORDER BY date DESC LIMIT 1", (coach_date,)
    ).fetchone())
    baselines = {item["metric_name"]: dict(item) for item in connection.execute(
        "SELECT * FROM baseline_metrics WHERE date = ? AND window_days = 28", (coach_date,)
    )}
    manual_training = _row_or_empty(
        connection,
        "SELECT * FROM daily_training_summary WHERE date = ?",
        (coach_date,),
    )
    nutrition = _nutrition_context(connection, coach_date)
    neural = _row_or_empty(
        connection,
        """SELECT mental_fatigue,mental_clarity,physical_heaviness,
                  baseline_status,confidence_level,lapse_355_count,slowest_20pct_rt_ms
           FROM daily_neural_features WHERE date = ?""",
        (coach_date,),
    )
    target, today = date_type.fromisoformat(coach_date), today or date_type.today()
    freshness = max((today - target).days, 0)
    return CoachInput(
        date=coach_date, recovery_score=values.get("recovery_score"), score_version=values.get("score_version"),
        recovery_capacity_score=_average((values.get("hrv_score"), values.get("morning_hr_score"), values.get("readiness_score"))),
        stress_load_score=_average((values.get("activity_load_score"), values.get("training_load_score"))),
        overall_confidence_score=values.get("confidence_score"), confidence_level=values.get("confidence_level"),
        data_completeness=values.get("data_completeness_score"),
        fallback_used=values.get("score_version") not in {"1.0.0", "v1.0"},
        sleep_duration_hours=_duration(values.get("sleep_duration"), 3600), sleep_score=values.get("sleep_score"),
        nightly_hrv_rmssd=values.get("nightly_hrv_rmssd"), nightly_resting_hr=values.get("nightly_resting_hr"),
        respiration_rate=values.get("respiration_rate"), morning_rmssd=values.get("morning_rmssd"),
        morning_mean_hr=values.get("morning_mean_hr"), kubios_readiness=values.get("kubios_readiness"),
        previous_training_duration_minutes=_duration(previous.get("training_duration"), 60),
        previous_training_calories=previous.get("training_calories"), active_calories=values.get("active_calories"),
        training_count=values.get("training_count"),
        current_training_duration_minutes=_duration(values.get("training_duration"), 60),
        current_training_session_rpe_load=manual_training.get("session_rpe_load"),
        manual_training_session_count=manual_training.get("session_count"),
        manual_training_duration_minutes=manual_training.get("total_duration_minutes"),
        manual_training_rpe_load=manual_training.get("session_rpe_load"),
        nutrition_logged_meals=nutrition.get("logged_meals"),
        nutrition_data_completeness=nutrition.get("data_completeness"),
        nutrition_calories=nutrition.get("calories"),
        nutrition_protein_g=nutrition.get("protein_g"),
        nutrition_carbohydrate_g=nutrition.get("carbohydrate_g"),
        nutrition_water_ml=nutrition.get("water_ml"),
        nutrition_targets=nutrition.get("targets", {}),
        neural_available=bool(neural),
        neural_mental_fatigue=neural.get("mental_fatigue"),
        neural_mental_clarity=neural.get("mental_clarity"),
        neural_physical_heaviness=neural.get("physical_heaviness"),
        neural_baseline_status=neural.get("baseline_status"),
        neural_confidence_level=neural.get("confidence_level"),
        neural_lapse_355_count=neural.get("lapse_355_count"),
        neural_slowest_20pct_rt_ms=neural.get("slowest_20pct_rt_ms"),
        baseline_status={name: item.get("status") for name, item in baselines.items()},
        explanation_json=generate_recovery_explanation(values, baselines), freshness_days=freshness,
        is_historical=freshness > freshness_days,
    )


def upsert_recommendation(connection, output):
    payload = lambda key: json.dumps(output[key], ensure_ascii=False, sort_keys=True)
    connection.execute(
        """
        INSERT INTO local_coach_recommendations (
            date, morning_training_json, evening_training_json, training_summary_json, sleep_advice_json,
            hydration_advice_json, nutrition_advice_json, recovery_advice_json,
            rationale_json, data_limitations_json, safety_notices_json,
            engine_version, rule_config_version, generated_without_cloud_ai
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(date, engine_version) DO UPDATE SET
            morning_training_json=excluded.morning_training_json,
            evening_training_json=excluded.evening_training_json,
            training_summary_json=excluded.training_summary_json,
            sleep_advice_json=excluded.sleep_advice_json,
            hydration_advice_json=excluded.hydration_advice_json,
            nutrition_advice_json=excluded.nutrition_advice_json,
            recovery_advice_json=excluded.recovery_advice_json,
            rationale_json=excluded.rationale_json,
            data_limitations_json=excluded.data_limitations_json,
            safety_notices_json=excluded.safety_notices_json,
            rule_config_version=excluded.rule_config_version,
            generated_without_cloud_ai=excluded.generated_without_cloud_ai,
            updated_at=CURRENT_TIMESTAMP
        """,
        (output["date"], payload("morning_training"), payload("evening_training"), payload("training_summary"), payload("sleep_advice"),
         payload("hydration_advice"), payload("nutrition_advice"), payload("recovery_advice"), payload("rationale"),
         payload("data_limitations"), payload("safety_notices"), output["engine_version"],
         output["rule_config_version"], int(output["generated_without_cloud_ai"])),
    )


def load_recommendation(connection, coach_date):
    row = connection.execute(
        "SELECT * FROM local_coach_recommendations WHERE date = ? ORDER BY updated_at DESC LIMIT 1", (coach_date,)
    ).fetchone()
    if not row:
        return None
    result = dict(row)
    for key in ("morning_training", "evening_training", "training_summary", "sleep_advice", "hydration_advice", "nutrition_advice",
                "recovery_advice", "rationale", "data_limitations", "safety_notices"):
        result[key] = json.loads(result.pop(f"{key}_json"))
    result["generated_without_cloud_ai"] = bool(result["generated_without_cloud_ai"])
    return result
