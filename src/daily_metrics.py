import re
from datetime import date, timedelta

try:
    from .db import DB_PATH, connect
except ImportError:
    from db import DB_PATH, connect


ISO_DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+(?:\.\d+)?)D)?"
    r"(?:T(?:(?P<hours>\d+(?:\.\d+)?)H)?"
    r"(?:(?P<minutes>\d+(?:\.\d+)?)M)?"
    r"(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?$"
)


def duration_to_seconds(value):
    if value in (None, ""):
        return 0
    if isinstance(value, (int, float)):
        return int(value)

    text = str(value)
    if text.isdigit():
        return int(text)

    match = ISO_DURATION_RE.match(text)
    if not match:
        return 0

    days = float(match.group("days") or 0)
    hours = float(match.group("hours") or 0)
    minutes = float(match.group("minutes") or 0)
    seconds = float(match.group("seconds") or 0)
    return int(days * 86400 + hours * 3600 + minutes * 60 + seconds)


def seconds_to_iso_duration(total_seconds):
    total_seconds = int(total_seconds or 0)
    if total_seconds <= 0:
        return None

    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts = []
    if hours:
        parts.append(f"{hours}H")
    if minutes:
        parts.append(f"{minutes}M")
    if seconds or not parts:
        parts.append(f"{seconds}S")
    return "PT" + "".join(parts)


def load_activity_rows(connection):
    rows = connection.execute(
        """
        SELECT
            date,
            steps,
            calories,
            active_calories,
            duration
        FROM polar_daily_activity_raw
        """
    ).fetchall()

    by_date = {}
    for row in rows:
        existing = by_date.get(row["date"])
        row_has_activity_values = any(
            row[key] is not None
            for key in ("steps", "calories", "active_calories", "duration")
        )
        existing_has_activity_values = existing and any(
            existing.get(key) is not None
            for key in ("steps", "calories", "active_calories", "activity_duration")
        )
        if existing_has_activity_values and not row_has_activity_values:
            continue
        by_date[row["date"]] = {
            "date": row["date"],
            "steps": row["steps"],
            "calories": row["calories"],
            "active_calories": row["active_calories"],
            "activity_duration": row["duration"],
        }
    return by_date


def load_training_summary(connection):
    rows = connection.execute(
        """
        SELECT
            date,
            duration,
            calories
        FROM polar_training_sessions_raw
        """
    ).fetchall()

    by_date = {}
    for row in rows:
        date_value = row["date"]
        summary = by_date.setdefault(
            date_value,
            {
                "training_count": 0,
                "training_duration_seconds": 0,
                "training_calories": 0,
            },
        )
        summary["training_count"] += 1
        summary["training_duration_seconds"] += duration_to_seconds(row["duration"])
        summary["training_calories"] += int(row["calories"] or 0)
    return by_date


def load_sleep_rows(connection):
    rows = connection.execute(
        """
        SELECT
            date,
            sleep_duration,
            sleep_score
        FROM polar_sleep_raw
        """
    ).fetchall()
    return {
        row["date"]: {
            "sleep_duration": row["sleep_duration"],
            "sleep_score": row["sleep_score"],
        }
        for row in rows
    }


def load_nightly_rows(connection):
    rows = connection.execute(
        """
        SELECT
            date,
            hrv_rmssd,
            resting_hr,
            respiration_rate
        FROM polar_nightly_recharge_raw
        """
    ).fetchall()
    return {
        row["date"]: {
            "nightly_hrv_rmssd": row["hrv_rmssd"],
            "nightly_resting_hr": row["resting_hr"],
            "respiration_rate": row["respiration_rate"],
        }
        for row in rows
    }


def load_morning_recovery_rows(connection):
    """Load the canonical morning measurement for every recorded date.

    Morning measurements can originate from a reviewed Kubios import or from
    a manual recovery record.  The Recovery page already resolves those
    inputs using the configured source priority; daily metrics must use the
    same resolved values so that scoring and baseline calculations see the
    exact data shown in the page.
    """
    try:
        from .data_resolution import resolve_recovery_date
    except ImportError:
        from data_resolution import resolve_recovery_date

    rows = connection.execute(
        """
        SELECT date FROM kubios_morning_hrv_raw
        UNION
        SELECT date FROM manual_recovery_logs
        """
    ).fetchall()
    by_date = {}
    for row in rows:
        date_value = row["date"]
        resolved = resolve_recovery_date(connection, date_value)
        by_date[date_value] = {
            "morning_rmssd": resolved["morning_rmssd"]["value"],
            "morning_mean_hr": resolved["morning_mean_hr"]["value"],
            "kubios_readiness": resolved["kubios_readiness"]["value"],
        }
    return by_date


def _latest_completed_sleep_for_today(sleeps, nightly, date_value):
    """Use last night's completed Polar record for this morning's assessment.

    Polar sleeps are stored under the date on which the session ended. During
    the current day, Recovery can already have a morning measurement while
    that day's new sleep record has not been imported. In that narrow gap,
    attach the immediately preceding night's data to today's derived record.
    Historical gaps remain empty rather than receiving stale sleep data.
    """
    if date_value != date.today().isoformat():
        return {}, {}
    previous_date = (date.fromisoformat(date_value) - timedelta(days=1)).isoformat()
    return sleeps.get(previous_date, {}), nightly.get(previous_date, {})


def build_daily_metrics(connection):
    activities = load_activity_rows(connection)
    training = load_training_summary(connection)
    sleeps = load_sleep_rows(connection)
    nightly = load_nightly_rows(connection)
    morning_recovery = load_morning_recovery_rows(connection)
    dates = sorted(
        set(activities) | set(training) | set(sleeps) | set(nightly) | set(morning_recovery)
    )

    metrics = []
    for date_value in dates:
        activity = activities.get(date_value, {"date": date_value})
        training_summary = training.get(
            date_value,
            {
                "training_count": 0,
                "training_duration_seconds": 0,
                "training_calories": 0,
            },
        )
        sleep = sleeps.get(date_value, {})
        nightly_recharge = nightly.get(date_value, {})
        morning = morning_recovery.get(date_value, {})
        if not sleep and not nightly_recharge:
            prior_sleep, prior_nightly = _latest_completed_sleep_for_today(
                sleeps, nightly, date_value,
            )
            sleep = prior_sleep or sleep
            nightly_recharge = prior_nightly or nightly_recharge
        metrics.append(
            {
                "date": date_value,
                "steps": activity.get("steps"),
                "calories": activity.get("calories"),
                "active_calories": activity.get("active_calories"),
                "activity_duration": activity.get("activity_duration"),
                "training_count": training_summary["training_count"],
                "training_duration": seconds_to_iso_duration(
                    training_summary["training_duration_seconds"]
                ),
                "training_calories": training_summary["training_calories"],
                "sleep_duration": sleep.get("sleep_duration"),
                "sleep_score": sleep.get("sleep_score"),
                "nightly_hrv_rmssd": nightly_recharge.get("nightly_hrv_rmssd"),
                "nightly_resting_hr": nightly_recharge.get("nightly_resting_hr"),
                "respiration_rate": nightly_recharge.get("respiration_rate"),
                "morning_rmssd": morning.get("morning_rmssd"),
                "morning_mean_hr": morning.get("morning_mean_hr"),
                "kubios_readiness": morning.get("kubios_readiness"),
            }
        )
    return metrics


def upsert_daily_metrics(connection, metrics):
    sql = """
    INSERT INTO daily_recovery_metrics (
        date,
        steps,
        calories,
        active_calories,
        activity_duration,
        training_count,
        training_duration,
        training_calories,
        sleep_duration,
        sleep_score,
        nightly_hrv_rmssd,
        nightly_resting_hr,
        respiration_rate,
        morning_rmssd,
        morning_mean_hr,
        kubios_readiness
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(date) DO UPDATE SET
        steps = excluded.steps,
        calories = excluded.calories,
        active_calories = excluded.active_calories,
        activity_duration = excluded.activity_duration,
        training_count = excluded.training_count,
        training_duration = excluded.training_duration,
        training_calories = excluded.training_calories,
        sleep_duration = excluded.sleep_duration,
        sleep_score = excluded.sleep_score,
        nightly_hrv_rmssd = excluded.nightly_hrv_rmssd,
        nightly_resting_hr = excluded.nightly_resting_hr,
        respiration_rate = excluded.respiration_rate,
        morning_rmssd = excluded.morning_rmssd,
        morning_mean_hr = excluded.morning_mean_hr,
        kubios_readiness = excluded.kubios_readiness,
        updated_at = CURRENT_TIMESTAMP
    """
    for metric in metrics:
        connection.execute(
            sql,
            (
                metric["date"],
                metric["steps"],
                metric["calories"],
                metric["active_calories"],
                metric["activity_duration"],
                metric["training_count"],
                metric["training_duration"],
                metric["training_calories"],
                metric["sleep_duration"],
                metric["sleep_score"],
                metric["nightly_hrv_rmssd"],
                metric["nightly_resting_hr"],
                metric["respiration_rate"],
                metric["morning_rmssd"],
                metric["morning_mean_hr"],
                metric["kubios_readiness"],
            ),
        )
    connection.commit()
    return len(metrics)


def rebuild_daily_recovery_metrics(connection=None):
    owns_connection = connection is None
    connection = connection or connect()
    metrics = build_daily_metrics(connection)
    count = upsert_daily_metrics(connection, metrics)

    if owns_connection:
        connection.close()

    return count


def main():
    count = rebuild_daily_recovery_metrics()
    print(f"Database: {DB_PATH}")
    print(f"Daily recovery metrics upserted: {count}")


if __name__ == "__main__":
    main()
