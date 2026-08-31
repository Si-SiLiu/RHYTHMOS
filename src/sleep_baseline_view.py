"""Read-only statistics for the Personal Sleep Baseline view."""

from __future__ import annotations

from datetime import date, timedelta
import statistics

from .sleep_regularity import (
    SleepRegularityService,
    calculate_rolling_regularity_scores,
)


def build_sleep_baseline_summary(points, target_date, window_days=28):
    """Summarize one metric over the calendar window before ``target_date``.

    ``points`` contains ``(ISO date, numeric value)`` pairs. Missing dates remain
    explicit ``None`` values in ``series`` so charts never bridge data gaps.
    """
    target = date.fromisoformat(str(target_date))
    start = target - timedelta(days=window_days)
    values_by_date = {
        str(day): float(value)
        for day, value in points
        if value is not None and start <= date.fromisoformat(str(day)) < target
    }
    dates = [start + timedelta(days=index) for index in range(window_days)]
    series = [values_by_date.get(day.isoformat()) for day in dates]
    valid_values = [value for value in series if value is not None]
    center = statistics.median(valid_values) if valid_values else None
    if valid_values:
        mad = statistics.median(abs(value - center) for value in valid_values)
        robust_spread = 1.4826 * mad
        lower = center - robust_spread
        upper = center + robust_spread
    else:
        lower = upper = None

    # Period comparisons use valid nights so a short sync gap does not erase
    # the interpretation. The chart itself remains calendar-based and broken
    # at every missing date.
    recent_values = valid_values[-7:]
    previous_values = valid_values[-14:-7]
    recent_average = statistics.mean(recent_values) if recent_values else None
    previous_average = statistics.mean(previous_values) if previous_values else None
    recent_median = statistics.median(recent_values) if recent_values else None
    previous_median = statistics.median(previous_values) if previous_values else None
    difference = (
        recent_average - previous_average
        if recent_average is not None and previous_average is not None else None
    )
    percent_difference = (
        difference / abs(previous_average) * 100
        if difference is not None and previous_average not in (None, 0) else None
    )
    anomaly_dates = {
        day.isoformat()
        for day, value in zip(dates, series)
        if value is not None and lower is not None and upper is not None
        and (value < lower or value > upper)
    }
    return {
        "dates": [day.isoformat() for day in dates],
        "series": series,
        "valid_nights": len(valid_values),
        "center": center,
        "lower": lower,
        "upper": upper,
        "recent_average": recent_average,
        "previous_average": previous_average,
        "recent_median": recent_median,
        "previous_median": previous_median,
        "difference": difference,
        "percent_difference": percent_difference,
        "anomaly_dates": anomaly_dates,
    }


def build_sleep_regularity_points(records, target_date, window_days=28):
    """Return one trailing-14-night regularity score per eligible sleep date."""
    target = date.fromisoformat(str(target_date))
    start = target - timedelta(days=window_days)
    source = sorted(
        (record for record in records if record and record.get("date")),
        key=lambda record: record["date"],
    )
    rolling_scores = calculate_rolling_regularity_scores(source)
    scored_dates = sorted(rolling_scores)
    points = []
    for record in source:
        record_date = date.fromisoformat(str(record["date"]))
        if not start <= record_date < target:
            continue
        eligible_dates = [day for day in scored_dates if day <= record_date]
        score = rolling_scores.get(eligible_dates[-1]) if eligible_dates else None
        if score is not None:
            points.append((record_date.isoformat(), float(score)))
    return points


def build_sleep_regularity_baseline(records, target_date, window_days=28):
    """Adapt rolling regularity scores to the shared Recovery baseline contract."""
    target = date.fromisoformat(str(target_date))
    eligible = [
        record for record in records
        if record and record.get("date") and date.fromisoformat(str(record["date"])) <= target
    ]
    has_target_record = any(str(record["date"]) == target.isoformat() for record in eligible)
    current_result = SleepRegularityService.calculate_regularity(eligible) if has_target_record else None
    summary = build_sleep_baseline_summary(
        build_sleep_regularity_points(records, target.isoformat(), window_days),
        target.isoformat(),
        window_days=window_days,
    )
    current = current_result.score if current_result is not None else None
    center = summary["center"]
    percent = (
        (current - center) / abs(center) * 100
        if current is not None and center not in (None, 0) else None
    )
    if summary["valid_nights"] < 7 or current is None or center is None:
        status = "insufficient_data"
    elif current < summary["lower"]:
        status = "below_baseline"
    elif current > summary["upper"]:
        status = "above_baseline"
    else:
        status = "within_baseline"
    spread = (
        (summary["upper"] - summary["lower"]) / 2
        if summary["lower"] is not None and summary["upper"] is not None else None
    )
    return current, {
        "date": target.isoformat(),
        "window_days": window_days,
        "valid_days": summary["valid_nights"],
        "metric_name": "sleep_regularity",
        "median_value": center,
        "mad_value": spread / 1.4826 if spread is not None else None,
        "min_value": min((value for value in summary["series"] if value is not None), default=None),
        "max_value": max((value for value in summary["series"] if value is not None), default=None),
        "latest_value": current,
        "percent_change": percent,
        "status": status,
    }
