import json
import math
import sqlite3
import statistics
from bisect import bisect_left
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    from .dashboard_data import duration_to_seconds
    from .db import get_current_db_path, connect
except ImportError:
    from dashboard_data import duration_to_seconds
    from db import get_current_db_path, connect


BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = BASE_DIR / "config" / "baseline_config.json"
STATUSES = {
    "insufficient_data",
    "below_baseline",
    "within_baseline",
    "above_baseline",
}


def load_baseline_config(path=CONFIG_PATH):
    with open(path, "r", encoding="utf-8") as file:
        config = json.load(file)

    required_keys = {
        "default_window_days",
        "minimum_valid_days",
        "outlier_method",
        "robust_z_thresholds",
        "metrics",
    }
    missing = required_keys - set(config)
    if missing:
        raise ValueError(f"Missing baseline config keys: {', '.join(sorted(missing))}")

    if not isinstance(config["metrics"], list) or not config["metrics"]:
        raise ValueError("Baseline config must define at least one metric")

    metric_names = set()
    for metric in config["metrics"]:
        for key in ("name", "source_column", "unit", "direction"):
            if key not in metric:
                raise ValueError(f"Baseline metric is missing {key}")
        if metric["name"] in metric_names:
            raise ValueError(f"Duplicate baseline metric: {metric['name']}")
        metric_names.add(metric["name"])

    return config


def parse_iso_date(value):
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def median_absolute_deviation(values, median_value=None):
    if not values:
        return None
    if median_value is None:
        median_value = statistics.median(values)
    return statistics.median([abs(value - median_value) for value in values])


def robust_z_score(value, median_value, mad_value):
    if value is None or median_value is None or mad_value is None:
        return None
    if mad_value == 0:
        return 0.0 if value == median_value else None
    return 0.6745 * (value - median_value) / mad_value


def z_score(value, mean_value, std_value):
    if value is None or mean_value is None or std_value is None:
        return None
    if std_value == 0:
        return 0.0 if value == mean_value else None
    return (value - mean_value) / std_value


def percent_change(value, baseline_value):
    if value is None or baseline_value in (None, 0):
        return None
    return ((value - baseline_value) / abs(baseline_value)) * 100


def readiness_to_number(value):
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    try:
        return float(text)
    except ValueError:
        pass

    mapping = {
        "excellent": 90.0,
        "good": 75.0,
        "fair": 60.0,
        "moderate": 60.0,
        "low": 40.0,
        "poor": 30.0,
        "very low": 20.0,
    }
    return mapping.get(text.lower())


def normalize_metric_value(value, metric):
    if value in (None, ""):
        return None

    if metric["name"] == "kubios_readiness":
        numeric = readiness_to_number(value)
    elif metric.get("duration_unit"):
        seconds = duration_to_seconds(value)
        if seconds is None:
            return None
        if metric["duration_unit"] == "hours":
            numeric = seconds / 3600
        elif metric["duration_unit"] == "minutes":
            numeric = seconds / 60
        else:
            numeric = seconds
    else:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None

    if numeric is None or not math.isfinite(numeric) or (numeric < 0 and not metric.get("allow_negative")):
        return None
    return float(numeric)


def classify_baseline_status(valid_days, minimum_valid_days, latest_value, robust_z=None, z=None, percent=None, thresholds=None):
    if valid_days < minimum_valid_days or latest_value is None:
        return "insufficient_data"

    thresholds = thresholds or {}
    below = thresholds.get("below", -1.0)
    above = thresholds.get("above", 1.0)

    score = robust_z if robust_z is not None else z
    if score is not None:
        if score <= below:
            return "below_baseline"
        if score >= above:
            return "above_baseline"
        return "within_baseline"

    if percent is not None:
        if percent <= -10:
            return "below_baseline"
        if percent >= 10:
            return "above_baseline"
    return "within_baseline"


def filter_outliers(values, config):
    if config.get("outlier_method") != "median_mad" or len(values) < 3:
        return values

    median_value = statistics.median(values)
    mad_value = median_absolute_deviation(values, median_value)
    if not mad_value:
        return values

    outlier_limit = config.get("robust_z_thresholds", {}).get("outlier", 3.5)
    filtered = [
        value
        for value in values
        if abs(robust_z_score(value, median_value, mad_value) or 0) <= outlier_limit
    ]
    return filtered or values


def get_metric_history(connection, target_date, metric, window_days):
    target = parse_iso_date(target_date)
    start = target - timedelta(days=window_days)
    source_column = metric["source_column"]

    source_table = metric.get("source_table", "daily_recovery_metrics")
    primary_filter = " AND selected_as_primary=1" if source_table == "kubios_hrv_normalized" else ""
    try:
        rows = connection.execute(
            f"SELECT date,{source_column} AS value FROM {source_table} WHERE date>=? AND date<?{primary_filter} ORDER BY date",
            (start.isoformat(), target.isoformat()),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    return [
        normalize_metric_value(row["value"], metric)
        for row in rows
        if normalize_metric_value(row["value"], metric) is not None
    ]


def get_latest_metric_value(connection, target_date, metric):
    source_column = metric["source_column"]
    source_table = metric.get("source_table", "daily_recovery_metrics")
    primary_filter = " AND selected_as_primary=1" if source_table == "kubios_hrv_normalized" else ""
    try:
        row = connection.execute(
            f"SELECT {source_column} AS value FROM {source_table} WHERE date=?{primary_filter} ORDER BY id DESC LIMIT 1",
            (str(target_date),),
        ).fetchone()
    except sqlite3.OperationalError:
        row = None
    if row is None:
        return None
    return normalize_metric_value(row["value"], metric)


def calculate_baseline_for_metric(connection, target_date, metric, config=None):
    config = config or load_baseline_config()
    window_days = int(config["default_window_days"])
    raw_values = get_metric_history(connection, target_date, metric, window_days)
    latest_value = get_latest_metric_value(connection, target_date, metric)

    return calculate_baseline_from_values(
        target_date,
        metric,
        raw_values,
        latest_value,
        config=config,
    )


def calculate_baseline_from_values(
    target_date,
    metric,
    raw_values,
    latest_value,
    config=None,
):
    """Calculate one baseline from already resolved canonical values."""
    config = config or load_baseline_config()
    window_days = int(config["default_window_days"])
    minimum_valid_days = int(config["minimum_valid_days"])
    observed_values = list(raw_values)
    valid_days = len(observed_values)
    values = filter_outliers(observed_values, config)

    result = {
        "date": str(target_date),
        "window_days": window_days,
        "valid_days": valid_days,
        "metric_name": metric["name"],
        "mean_value": None,
        "median_value": None,
        "std_value": None,
        "mad_value": None,
        "min_value": None,
        "max_value": None,
        "latest_value": latest_value,
        "percent_change": None,
        "z_score": None,
        "robust_z_score": None,
        "status": "insufficient_data",
    }

    if values:
        mean_value = statistics.mean(values)
        median_value = statistics.median(values)
        std_value = statistics.pstdev(values) if len(values) > 1 else 0.0
        mad_value = median_absolute_deviation(values, median_value) or 0.0
        pct = percent_change(latest_value, median_value)
        z = z_score(latest_value, mean_value, std_value)
        rz = robust_z_score(latest_value, median_value, mad_value)

        result.update(
            {
                "mean_value": mean_value,
                "median_value": median_value,
                "std_value": std_value,
                "mad_value": mad_value,
                "min_value": min(values),
                "max_value": max(values),
                "percent_change": pct,
                "z_score": z,
                "robust_z_score": rz,
                "status": classify_baseline_status(
                    valid_days,
                    minimum_valid_days,
                    latest_value,
                    robust_z=rz,
                    z=z,
                    percent=pct,
                    thresholds=config.get("robust_z_thresholds", {}),
                ),
            }
        )

    return result


def upsert_baseline(connection, baseline):
    connection.execute(
        """
        INSERT INTO baseline_metrics (
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
            status,
            updated_at
        )
        VALUES (
            :date,
            :window_days,
            :valid_days,
            :metric_name,
            :mean_value,
            :median_value,
            :std_value,
            :mad_value,
            :min_value,
            :max_value,
            :latest_value,
            :percent_change,
            :z_score,
            :robust_z_score,
            :status,
            CURRENT_TIMESTAMP
        )
        ON CONFLICT(date, metric_name, window_days) DO UPDATE SET
            valid_days = excluded.valid_days,
            mean_value = excluded.mean_value,
            median_value = excluded.median_value,
            std_value = excluded.std_value,
            mad_value = excluded.mad_value,
            min_value = excluded.min_value,
            max_value = excluded.max_value,
            latest_value = excluded.latest_value,
            percent_change = excluded.percent_change,
            z_score = excluded.z_score,
            robust_z_score = excluded.robust_z_score,
            status = excluded.status,
            updated_at = CURRENT_TIMESTAMP
        """,
        baseline,
    )


def calculate_baseline_for_date(connection, target_date, config=None):
    config = config or load_baseline_config()
    results = [
        calculate_baseline_for_metric(connection, str(target_date), metric, config=config)
        for metric in config["metrics"]
    ]
    for result in results:
        upsert_baseline(connection, result)
    connection.commit()
    return results


def _load_baseline_series(connection, metric, start_date, end_date):
    """Read and normalize each source once per rebuild, never across runs."""
    table = metric.get("source_table", "daily_recovery_metrics")
    column = metric["source_column"]
    primary = " AND selected_as_primary=1" if table == "kubios_hrv_normalized" else ""
    try:
        rows = connection.execute(
            f"SELECT date,{column} AS value FROM {table} "
            f"WHERE date>=? AND date<=?{primary} ORDER BY date,id",
            (start_date, end_date),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    days, values, latest = [], [], {}
    for row in rows:
        value = normalize_metric_value(row["value"], metric)
        latest[row["date"]] = value
        if value is not None:
            days.append(row["date"])
            values.append(value)
    return days, values, latest


def calculate_all_baselines(connection=None, config=None):
    owns_connection = connection is None
    if owns_connection:
        connection = connect()

    try:
        config = config or load_baseline_config()
        dates = [
            row["date"]
            for row in connection.execute(
                "SELECT date FROM daily_recovery_metrics ORDER BY date"
            ).fetchall()
        ]
        total = 0
        status_counts = {status: 0 for status in STATUSES}
        insufficient_metrics = set()
        window_days = int(config["default_window_days"])
        series = [
            _load_baseline_series(
                connection, metric,
                (parse_iso_date(dates[0]) - timedelta(days=window_days)).isoformat(),
                dates[-1],
            )
            for metric in config["metrics"]
        ] if dates else []

        for target_date in dates:
            start = (parse_iso_date(target_date) - timedelta(days=window_days)).isoformat()
            results = []
            for metric, (days, values, latest) in zip(config["metrics"], series):
                result = calculate_baseline_from_values(
                    target_date, metric,
                    values[bisect_left(days, start):bisect_left(days, target_date)],
                    latest.get(target_date), config=config,
                )
                upsert_baseline(connection, result)
                results.append(result)
            connection.commit()
            total += len(results)
            for result in results:
                status_counts[result["status"]] = status_counts.get(result["status"], 0) + 1
                if result["status"] == "insufficient_data":
                    insufficient_metrics.add(result["metric_name"])

        return {
            "dates": len(dates),
            "records": total,
            "status_counts": status_counts,
            "insufficient_metrics": sorted(insufficient_metrics),
        }
    finally:
        if owns_connection:
            connection.close()


def main():
    connection = connect()
    try:
        summary = calculate_all_baselines(connection)
        print(f"Database: {get_current_db_path()}")
        print(f"Baseline dates processed: {summary['dates']}")
        print(f"Baseline records upserted: {summary['records']}")
        print(f"Status counts: {summary['status_counts']}")
        if summary["insufficient_metrics"]:
            print("Insufficient metrics: " + ", ".join(summary["insufficient_metrics"]))
        else:
            print("Insufficient metrics: none")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
