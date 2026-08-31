"""Explain today's morning recovery measurements against a personal baseline.

This module is deliberately independent from the legacy 0-100 Recovery Score.
It exposes interpretable signal states and never turns missing data into zero.
"""

from __future__ import annotations

import math
import statistics
from datetime import date, timedelta

from .baseline import calculate_baseline_from_values, load_baseline_config


QUALITY_VALUES = ("excellent", "good", "average", "poor", "unusable", "missing")
QUALITY_ALIASES = {
    "excellent": "excellent", "excellent quality": "excellent",
    "good": "good", "acceptable": "average", "average": "average",
    "fair": "average", "poor": "poor", "invalid": "unusable",
    "unusable": "unusable", "missing": "missing", "none": "missing",
}

METRIC_SPECS = {
    "morning_rmssd": {"label_key": "domain.recovery.morning_rmssd", "unit": "ms", "rule": "rmssd"},
    "morning_mean_hr": {"label_key": "domain.recovery.morning_resting_hr", "unit": "bpm", "rule": "resting_hr"},
    "stress_index": {"label_key": "domain.recovery.stress_index", "unit": "", "rule": "stress"},
    "respiratory_rate": {"label_key": "domain.recovery.respiratory_rate", "unit": "breaths_per_minute", "rule": "respiration"},
    # These extended Kubios measurements are useful personal trend evidence,
    # but do not carry a universal "higher/lower is better" interpretation.
    # They therefore share the same baseline card anatomy while remaining
    # descriptive rather than contributing to the recovery conclusion.
    "pns_index": {"label_key": "kubios_metrics.pns.name", "unit": "", "rule": "context", "positive": False},
    "sns_index": {"label_key": "kubios_metrics.sns.name", "unit": "", "rule": "context", "positive": False},
    "physiological_age": {"label_key": "kubios_metrics.physiological_age.name", "unit": "years", "rule": "context"},
    "mean_rr_ms": {"label_key": "kubios_metrics.mean_rr.name", "unit": "ms", "rule": "context"},
    "sdnn_ms": {"label_key": "kubios_metrics.sdnn.name", "unit": "ms", "rule": "context"},
    "poincare_sd1_ms": {"label_key": "kubios_metrics.sd1.name", "unit": "ms", "rule": "context"},
    "poincare_sd2_ms": {"label_key": "kubios_metrics.sd2.name", "unit": "ms", "rule": "context"},
    "lf_power_ms2": {"label_key": "kubios_metrics.lf_power.name", "unit": "ms²", "rule": "context"},
    "hf_power_ms2": {"label_key": "kubios_metrics.hf_power.name", "unit": "ms²", "rule": "context"},
    "lf_power_nu": {"label_key": "kubios_metrics.lf_nu.name", "unit": "%", "rule": "context"},
    "hf_power_nu": {"label_key": "kubios_metrics.hf_nu.name", "unit": "%", "rule": "context"},
    "lf_hf_ratio": {"label_key": "kubios_metrics.lf_hf.name", "unit": "", "rule": "context"},
}

RECOVERY_SIGNAL_NAMES = (
    "morning_rmssd", "morning_mean_hr", "stress_index", "respiratory_rate",
)


def normalize_measurement_quality(value):
    """Return the canonical lower-case quality code, including legacy values."""
    if value in (None, ""):
        return "missing"
    text = str(value).strip().lower().replace("_", " ")
    return QUALITY_ALIASES.get(text, "missing")


def quality_is_usable(value):
    return normalize_measurement_quality(value) in {"excellent", "good"}


def _number(value, *, positive=False):
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or (positive and value <= 0):
        return None
    return value


def _value_is_valid(metric_name, value):
    number = _number(value, positive=METRIC_SPECS[metric_name].get("positive", True))
    if number is None:
        return None
    if metric_name == "stress_index" and number < 0:
        return None
    return number


def _iqr_range(values):
    ordered = sorted(values)
    if len(ordered) < 4:
        return ordered[0], ordered[-1]
    middle = len(ordered) // 2
    lower = ordered[:middle]
    upper = ordered[-middle:]
    return statistics.median(lower), statistics.median(upper)


def _common_range(baseline):
    center = baseline.get("median_value")
    if center is None:
        return None
    mad = float(baseline.get("mad_value") or 0)
    if mad > 0:
        spread = 1.4826 * mad
        return max(0.0, center - spread), center + spread
    minimum, maximum = baseline.get("min_value"), baseline.get("max_value")
    if minimum is not None and maximum is not None:
        return float(minimum), float(maximum)
    return float(center), float(center)


def _baseline_for_metric(metric_name, history, target_date, window_days=28):
    target = date.fromisoformat(str(target_date))
    start = target - timedelta(days=window_days)
    values = []
    for record in history or []:
        try:
            record_date = date.fromisoformat(str(record.get("date")))
        except (TypeError, ValueError):
            continue
        if not start <= record_date < target or not quality_is_usable(record.get("measurement_quality")):
            continue
        value = _value_is_valid(metric_name, record.get(metric_name))
        if value is not None:
            values.append(value)

    spec = METRIC_SPECS[metric_name]
    config = load_baseline_config()
    config = {**config, "default_window_days": window_days, "minimum_valid_days": 7}
    metric = {
        "name": metric_name,
        "source_column": metric_name,
        "unit": spec["unit"],
        "direction": "higher_is_better" if spec["rule"] == "rmssd" else "lower_is_better",
    }
    baseline = calculate_baseline_from_values(str(target), metric, values, None, config=config)
    baseline["normal_range"] = _common_range(baseline)
    baseline["valid_days"] = len(values)
    return baseline


def _metric_impact(rule, current, baseline):
    center = baseline.get("median_value")
    normal_range = baseline.get("normal_range")
    if current is None:
        return "unavailable", "missing"
    if center is None or baseline.get("valid_days", 0) < 7:
        return "insufficient", "baseline_insufficient"
    lower, upper = normal_range
    delta = current - center
    percent = None if center == 0 else delta / abs(center) * 100
    spread = max((upper - lower) / 2, abs(center) * 0.02, 1e-9)
    extreme_low = current < center - 2 * spread
    extreme_high = current > center + 2 * spread

    if rule == "rmssd":
        if current < lower:
            return "negative", "rmssd_below_range"
        if current > upper:
            return ("observe", "rmssd_extreme_high") if extreme_high else ("supportive", "rmssd_above_range")
        return ("supportive", "rmssd_above_center") if delta > 0 and abs(percent or 0) >= 2 else ("neutral", "within_range")
    if rule == "resting_hr":
        if current > upper:
            return "negative", "hr_above_range"
        if current < lower:
            return ("observe", "hr_extreme_low") if extreme_low else ("supportive", "hr_below_range")
        return ("supportive", "hr_below_center") if delta < 0 and abs(percent or 0) >= 2 else ("neutral", "within_range")
    if rule == "stress":
        if current > upper:
            return "negative", "stress_above_range"
        if current < lower:
            return "supportive", "stress_below_range"
        return ("supportive", "stress_below_center") if delta < 0 and abs(percent or 0) >= 2 else ("neutral", "within_range")
    if rule == "context":
        if current < lower or current > upper:
            return "observe", "context_outside_range"
        return "neutral", "context_within_range"
    if current < lower or current > upper:
        return "negative", "respiration_outside_range"
    return "neutral", "respiration_within_range"


def _maturity(valid_days):
    if valid_days < 7:
        return "collecting"
    if valid_days <= 13:
        return "provisional"
    if valid_days <= 27:
        return "reliable"
    return "stable"


def _status(quality, analyses, maturity):
    if quality not in {"excellent", "good"} or not any(item["current_value"] is not None for item in analyses.values()):
        return "unusable"
    if maturity == "collecting":
        return "building"
    core = [analyses[name]["impact"] for name in ("morning_rmssd", "morning_mean_hr")]
    all_impacts = [analyses[name]["impact"] for name in RECOVERY_SIGNAL_NAMES]
    supportive = sum(impact == "supportive" for impact in all_impacts)
    negative_core = sum(impact == "negative" for impact in core)
    negative_any = sum(impact == "negative" for impact in all_impacts)
    if supportive and negative_any:
        return "conflict"
    if negative_core >= 1 or negative_any >= 2:
        return "low"
    if supportive:
        return "good"
    return "normal"


def build_recovery_details(data, history, target_date=None, window_days=28):
    """Build today's explainable recovery detail view from resolved records."""
    data = data or {}
    target = str(target_date or data.get("date") or date.today().isoformat())
    quality = normalize_measurement_quality(data.get("measurement_quality"))
    baselines = {name: _baseline_for_metric(name, history, target, window_days) for name in METRIC_SPECS}
    analyses = {}
    for name, spec in METRIC_SPECS.items():
        current = _value_is_valid(name, data.get(name))
        impact, explanation = _metric_impact(spec["rule"], current, baselines[name])
        center = baselines[name].get("median_value")
        delta = None if current is None or center is None else current - center
        analyses[name] = {
            "metric_name": name,
            "label_key": spec["label_key"],
            "unit": spec["unit"],
            "current_value": current,
            "baseline_center": center,
            "normal_range": baselines[name].get("normal_range"),
            "absolute_delta": None if delta is None else abs(delta),
            "signed_delta": delta,
            "percent_delta": None if delta is None or center in (None, 0) else delta / abs(center) * 100,
            "impact": impact,
            "explanation": explanation,
            "valid_days": baselines[name].get("valid_days", 0),
        }

    core_days = [analyses[name]["valid_days"] for name in ("morning_rmssd", "morning_mean_hr")]
    maturity_days = min(core_days) if core_days else 0
    maturity = _maturity(maturity_days)
    status = _status(quality, analyses, maturity)
    current_values = sum(item["current_value"] is not None for item in analyses.values())
    quality_factor = {"excellent": 1.0, "good": .9, "average": .6, "poor": .3, "unusable": 0, "missing": 0}[quality]
    maturity_factor = min(maturity_days / window_days, 1.0)
    if status == "unusable":
        confidence = "unavailable"
    elif quality_factor >= .9 and maturity_factor >= .5 and current_values >= 3:
        confidence = "high"
    elif quality_factor >= .6 and maturity_days >= 7:
        confidence = "moderate"
    else:
        confidence = "low"

    supports = []
    watches = []
    for name in RECOVERY_SIGNAL_NAMES:
        item = analyses[name]
        if item["impact"] == "supportive":
            supports.append(f"{name}_support")
        elif item["impact"] in {"negative", "observe"}:
            watches.append(f"{name}_watch")
    if quality in {"excellent", "good"}:
        supports.append("measurement_quality_support")
    if maturity in {"collecting", "provisional"}:
        watches.append("baseline_maturity_watch")
    if status == "conflict":
        watches.insert(0, "signal_conflict_watch")

    return {
        "target_date": target,
        "quality": quality,
        "status": status,
        "maturity": maturity,
        "maturity_days": maturity_days,
        "window_days": window_days,
        "confidence": confidence,
        "current_value_count": current_values,
        "analyses": analyses,
        "support_factors": supports[:3],
        "watch_factors": watches[:3],
        "advice": {"unusable": "data_unavailable", "building": "building", "good": "positive", "normal": "normal", "low": "low", "conflict": "conflict"}[status],
    }
