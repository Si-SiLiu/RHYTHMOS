try:
    from .daily_metrics import duration_to_seconds
    from .db import DB_PATH, connect
except ImportError:
    from daily_metrics import duration_to_seconds
    from db import DB_PATH, connect


def clamp(value, minimum=0, maximum=100):
    return max(minimum, min(maximum, int(round(value))))


def scale_to_score(value, low, high):
    value = float(value or 0)
    if value <= low:
        return 0
    if value >= high:
        return 100
    return clamp(((value - low) / (high - low)) * 100)


def metric_value(metric, key, default=None):
    try:
        return metric[key]
    except (KeyError, IndexError):
        return default


def calculate_activity_load_score(steps, active_calories):
    steps_score = scale_to_score(steps, low=3000, high=15000)
    calories_score = scale_to_score(active_calories, low=300, high=1800)
    return clamp(steps_score * 0.45 + calories_score * 0.55)


def calculate_training_load_score(training_duration, training_calories):
    duration_minutes = duration_to_seconds(training_duration) / 60
    duration_score = scale_to_score(duration_minutes, low=20, high=120)
    calories_score = scale_to_score(training_calories, low=150, high=1000)
    return clamp(duration_score * 0.55 + calories_score * 0.45)


def calculate_hrv_score(rmssd):
    return scale_to_score(rmssd, low=20, high=80)


def calculate_morning_hr_score(mean_hr):
    mean_hr = float(mean_hr or 0)
    if mean_hr <= 0:
        return None
    if mean_hr <= 50:
        return 100
    if mean_hr >= 85:
        return 0
    return clamp(((85 - mean_hr) / 35) * 100)


def calculate_readiness_score(readiness):
    if readiness is None:
        return None

    if isinstance(readiness, (int, float)):
        return clamp(readiness)

    text = str(readiness).strip().lower()
    if not text:
        return None

    mapping = {
        "excellent": 95,
        "very good": 88,
        "good": 80,
        "normal": 75,
        "ok": 70,
        "fair": 60,
        "moderate": 60,
        "low": 45,
        "poor": 30,
        "very low": 20,
        "bad": 20,
        "优秀": 95,
        "良好": 80,
        "正常": 75,
        "一般": 60,
        "偏低": 45,
        "较差": 30,
    }
    if text in mapping:
        return mapping[text]

    try:
        return clamp(float(text))
    except ValueError:
        return None


def calculate_sleep_score(sleep_score):
    if sleep_score is None:
        return None
    return clamp(sleep_score)


def recommendation_for_score(recovery_score):
    if recovery_score >= 80:
        return "正常训练"
    if recovery_score >= 60:
        return "适度训练"
    if recovery_score >= 40:
        return "减量训练"
    return "恢复优先"


def has_kubios_data(metric):
    return any(
        metric_value(metric, key) is not None
        for key in ("morning_rmssd", "morning_mean_hr", "kubios_readiness")
    )


def has_polar_recovery_data(metric):
    return any(
        metric_value(metric, key) is not None
        for key in ("nightly_hrv_rmssd", "sleep_score", "nightly_resting_hr")
    )


def unscored_recovery(metric):
    """Retain load components, but never mistake load alone for recovery."""
    load_only = calculate_recovery_score_v1(metric)
    return {
        **load_only,
        "recovery_score": None,
        "recommendation": None,
        "score_version": "unscored_insufficient_recovery_evidence",
    }


def calculate_recovery_score_v1(metric):
    activity_load_score = calculate_activity_load_score(
        metric["steps"],
        metric["active_calories"],
    )
    training_load_score = calculate_training_load_score(
        metric["training_duration"],
        metric["training_calories"],
    )
    total_load_score = clamp(activity_load_score * 0.6 + training_load_score * 0.4)
    recovery_score = clamp(100 - total_load_score)

    return {
        "date": metric["date"],
        "recovery_score": recovery_score,
        "activity_load_score": activity_load_score,
        "training_load_score": training_load_score,
        "hrv_score": None,
        "morning_hr_score": None,
        "readiness_score": None,
        "score_version": "v0.1",
        "recommendation": recommendation_for_score(recovery_score),
    }


def calculate_recovery_score_v2(metric):
    v1 = calculate_recovery_score_v1(metric)
    hrv_score = calculate_hrv_score(metric_value(metric, "morning_rmssd"))
    morning_hr_score = calculate_morning_hr_score(metric_value(metric, "morning_mean_hr"))
    readiness_score = calculate_readiness_score(metric_value(metric, "kubios_readiness"))

    available_recovery_scores = [
        score
        for score in (hrv_score, morning_hr_score, readiness_score)
        if score is not None
    ]
    recovery_capacity_score = (
        sum(available_recovery_scores) / len(available_recovery_scores)
        if available_recovery_scores
        else v1["recovery_score"]
    )
    load_pressure_score = 100 - v1["recovery_score"]
    recovery_score = clamp(recovery_capacity_score * 0.7 + (100 - load_pressure_score) * 0.3)

    return {
        **v1,
        "recovery_score": recovery_score,
        "hrv_score": hrv_score,
        "morning_hr_score": morning_hr_score,
        "readiness_score": readiness_score,
        "score_version": "v0.2",
        "recommendation": recommendation_for_score(recovery_score),
    }


def calculate_recovery_score_v3(metric):
    v1 = calculate_recovery_score_v1(metric)
    hrv_score = calculate_hrv_score(metric_value(metric, "nightly_hrv_rmssd"))
    sleep_score = calculate_sleep_score(metric_value(metric, "sleep_score"))
    resting_hr_score = calculate_morning_hr_score(metric_value(metric, "nightly_resting_hr"))

    available_recovery_scores = [
        score
        for score in (hrv_score, sleep_score, resting_hr_score)
        if score is not None
    ]
    recovery_capacity_score = (
        sum(available_recovery_scores) / len(available_recovery_scores)
        if available_recovery_scores
        else v1["recovery_score"]
    )
    recovery_score = clamp(recovery_capacity_score * 0.65 + v1["recovery_score"] * 0.35)

    return {
        **v1,
        "recovery_score": recovery_score,
        "hrv_score": hrv_score,
        "morning_hr_score": resting_hr_score,
        "readiness_score": sleep_score,
        "score_version": "v0.3",
        "recommendation": recommendation_for_score(recovery_score),
    }


def baseline_is_usable(row):
    return (
        row is not None
        and row.get("status") != "insufficient_data"
        and row.get("latest_value") is not None
        and row.get("valid_days", 0) >= 7
    )


def baseline_deviation(row):
    if not baseline_is_usable(row):
        return None
    for key in ("robust_z_score", "z_score"):
        value = row.get(key)
        if value is not None:
            return float(value)
    percent = row.get("percent_change")
    if percent is None:
        return None
    return float(percent) / 10


def score_from_baseline(row, direction):
    deviation = baseline_deviation(row)
    if deviation is None:
        return None
    if direction == "higher_is_better":
        return clamp(75 + deviation * 15)
    if direction == "lower_is_better":
        return clamp(75 - deviation * 15)
    if direction == "higher_is_load":
        return clamp(50 + deviation * 15)
    return None


def average_scores(scores):
    available = [score for score in scores if score is not None]
    if not available:
        return None
    return clamp(sum(available) / len(available))


def baseline_score(baselines, metric_name, direction):
    return score_from_baseline(baselines.get(metric_name), direction)


def has_usable_baselines(baselines):
    return any(baseline_is_usable(row) for row in (baselines or {}).values())


def calculate_recovery_score_without_baseline(metric):
    if has_kubios_data(metric):
        return calculate_recovery_score_v2(metric)
    if has_polar_recovery_data(metric):
        return calculate_recovery_score_v3(metric)
    return calculate_recovery_score_v1(metric)


def calculate_recovery_score_v10(metric, baselines):
    fallback = calculate_recovery_score_without_baseline(metric)

    activity_load_score = average_scores(
        [
            baseline_score(baselines, "steps", "higher_is_load"),
            baseline_score(baselines, "active_calories", "higher_is_load"),
        ]
    )
    training_load_score = average_scores(
        [
            baseline_score(baselines, "training_duration", "higher_is_load"),
            baseline_score(baselines, "training_calories", "higher_is_load"),
        ]
    )
    activity_load_score = activity_load_score if activity_load_score is not None else fallback["activity_load_score"]
    training_load_score = training_load_score if training_load_score is not None else fallback["training_load_score"]

    hrv_score = average_scores(
        [
            baseline_score(baselines, "nightly_hrv_rmssd", "higher_is_better"),
            baseline_score(baselines, "morning_rmssd", "higher_is_better"),
        ]
    )
    morning_hr_score = average_scores(
        [
            baseline_score(baselines, "nightly_resting_hr", "lower_is_better"),
            baseline_score(baselines, "morning_mean_hr", "lower_is_better"),
            baseline_score(baselines, "respiration_rate", "lower_is_better"),
        ]
    )
    readiness_score = average_scores(
        [
            baseline_score(baselines, "sleep_score", "higher_is_better"),
            baseline_score(baselines, "sleep_duration", "higher_is_better"),
            baseline_score(baselines, "kubios_readiness", "higher_is_better"),
        ]
    )

    recovery_capacity_score = average_scores(
        [hrv_score, morning_hr_score, readiness_score]
    )
    total_load_score = clamp(activity_load_score * 0.6 + training_load_score * 0.4)
    load_recovery_score = clamp(100 - total_load_score)

    if recovery_capacity_score is None:
        recovery_score = load_recovery_score
    else:
        recovery_score = clamp(recovery_capacity_score * 0.65 + load_recovery_score * 0.35)

    return {
        "date": metric["date"],
        "recovery_score": recovery_score,
        "activity_load_score": activity_load_score,
        "training_load_score": training_load_score,
        "hrv_score": hrv_score,
        "morning_hr_score": morning_hr_score,
        "readiness_score": readiness_score,
        "score_version": "v1.0",
        "recommendation": recommendation_for_score(recovery_score),
    }


def calculate_recovery_score(metric, baselines=None):
    # Training/activity load describes strain, not recovery capacity.  A
    # recovery score needs at least one current Kubios or overnight recovery
    # signal; otherwise its numerical value would be fabricated from load.
    if not has_kubios_data(metric) and not has_polar_recovery_data(metric):
        return unscored_recovery(metric)
    if baselines and has_usable_baselines(baselines):
        return calculate_recovery_score_v10(metric, baselines)
    return calculate_recovery_score_without_baseline(metric)


def load_daily_metrics(connection):
    return connection.execute(
        """
        SELECT
            date,
            steps,
            active_calories,
            training_duration,
            training_calories,
            sleep_score,
            nightly_hrv_rmssd,
            nightly_resting_hr,
            morning_rmssd,
            morning_mean_hr,
            kubios_readiness
        FROM daily_recovery_metrics
        ORDER BY date
        """
    ).fetchall()


def load_baselines_by_date(connection):
    rows = connection.execute(
        """
        SELECT
            date,
            window_days,
            valid_days,
            metric_name,
            mean_value,
            median_value,
            std_value,
            mad_value,
            min_value,
            max_value,
            latest_value,
            percent_change,
            z_score,
            robust_z_score,
            status
        FROM baseline_metrics
        ORDER BY date, metric_name
        """
    ).fetchall()

    baselines = {}
    for row in rows:
        baselines.setdefault(row["date"], {})[row["metric_name"]] = dict(row)
    return baselines


def build_recovery_scores(connection):
    baselines_by_date = load_baselines_by_date(connection)
    return [
        calculate_recovery_score(row, baselines=baselines_by_date.get(row["date"]))
        for row in load_daily_metrics(connection)
    ]


def rebuild_baselines_if_available(connection):
    try:
        from .baseline import calculate_all_baselines
    except ImportError:
        from baseline import calculate_all_baselines

    calculate_all_baselines(connection)


def upsert_recovery_scores(connection, scores):
    sql = """
    INSERT INTO recovery_scores (
        date,
        recovery_score,
        activity_load_score,
        training_load_score,
        hrv_score,
        morning_hr_score,
        readiness_score,
        score_version,
        recommendation
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(date) DO UPDATE SET
        recovery_score = excluded.recovery_score,
        activity_load_score = excluded.activity_load_score,
        training_load_score = excluded.training_load_score,
        hrv_score = excluded.hrv_score,
        morning_hr_score = excluded.morning_hr_score,
        readiness_score = excluded.readiness_score,
        score_version = excluded.score_version,
        recommendation = excluded.recommendation,
        updated_at = CURRENT_TIMESTAMP
    """
    written = 0
    for score in scores:
        if score["recovery_score"] is None:
            # The schema intentionally stores only real numerical scores. This
            # also removes a stale prior score if today's recovery evidence was
            # cleared or became unavailable.
            connection.execute("DELETE FROM recovery_scores WHERE date=?", (score["date"],))
            continue
        connection.execute(
            sql,
            (
                score["date"],
                score["recovery_score"],
                score["activity_load_score"],
                score["training_load_score"],
                score["hrv_score"],
                score["morning_hr_score"],
                score["readiness_score"],
                score["score_version"],
                score["recommendation"],
            ),
        )
        written += 1
    connection.commit()
    return written


def rebuild_recovery_scores(connection=None):
    owns_connection = connection is None
    connection = connection or connect()
    rebuild_baselines_if_available(connection)
    scores = build_recovery_scores(connection)
    count = upsert_recovery_scores(connection, scores)

    if owns_connection:
        connection.close()

    return count


def main():
    count = rebuild_recovery_scores()
    print(f"Database: {DB_PATH}")
    print(f"Recovery scores upserted: {count}")


if __name__ == "__main__":
    main()
