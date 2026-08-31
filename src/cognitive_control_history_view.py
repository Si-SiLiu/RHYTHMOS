"""Presentation helpers for the Cognitive Control history panel.

These functions only format persisted records for display.  They deliberately
leave calculation, persistence, and comparison grouping to cognitive_training.
"""

from __future__ import annotations

import math

from .i18n import format_date, get_translator


TEST_KEYS = {
    "focus_target": "test_focus_target",
    "focus_gonogo": "test_focus_gonogo",
    "focus_visual_search": "test_focus_visual_search",
    "memory_grid": "test_memory_grid",
    "sequence_memory": "test_sequence_memory",
    "nback_lite": "test_nback_lite",
    "stroop_control": "test_stroop_control",
    "task_switching": "test_task_switching",
    "symbol_match": "test_symbol_match",
}
MODE_KEYS = {"quick": "mode_quick", "standard": "mode_standard"}
DEVICE_KEYS = {
    "desktop": "device_desktop",
    "mobile": "device_mobile",
    "tablet": "device_tablet",
    "unknown": "device_unknown",
}
INPUT_KEYS = {
    "unknown": "input_unknown",
    "touch": "input_touch",
    "keyboard": "input_keyboard",
    "mouse": "input_mouse",
}


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _tr(language):
    return get_translator(language)


def missing(language):
    return _tr(language)("cognitive_control_history.missing")


def display_percent(value, language):
    number = _number(value)
    return missing(language) if number is None else f"{number * 100:.2f}%"


def display_response_time(value, language):
    number = _number(value)
    if number is None:
        return missing(language)
    rounded = math.floor(number + 0.5) if number >= 0 else math.ceil(number - 0.5)
    return _tr(language)("cognitive_control_history.milliseconds", value=f"{rounded:,}")


def display_difficulty(value, language):
    number = _number(value)
    return missing(language) if number is None else _tr(language)(
        "cognitive_control_history.difficulty_value", value=f"{number:.0f}"
    )


def _display(value, mapping, language):
    key = mapping.get(value)
    return _tr(language)(f"cognitive_control_history.{key}") if key else missing(language)


def display_test(value, language):
    return _display(value, TEST_KEYS, language)


def display_mode(value, language):
    return _display(value, MODE_KEYS, language)


def display_device(value, language):
    return _display(value, DEVICE_KEYS, language)


def display_input(value, language):
    if not isinstance(value, str) or not value:
        return missing(language)
    labels = []
    for item in value.split(","):
        key = INPUT_KEYS.get(item.strip())
        if key is None:
            return missing(language)
        labels.append(_tr(language)(f"cognitive_control_history.{key}"))
    return _tr(language)("cognitive_control_history.input_separator", values=" / ".join(labels))


def is_complete(record):
    return _number(record.get("accuracy")) is not None and _number(record.get("median_rt_ms")) is not None


def comparable_records(records):
    """Use the full comparable_group emitted by the data service unchanged."""
    valid = [record for record in records if is_complete(record)]
    if not valid:
        return [], None
    group = valid[0].get("comparable_group")
    return [record for record in valid if record.get("comparable_group") == group], valid[0]


def summary(records, language):
    comparable, latest = comparable_records(records)
    if latest is None:
        return None
    tr = _tr(language)
    return {
        "test": display_test(latest.get("task_type"), language),
        "mode": display_mode(latest.get("session_mode"), language),
        "accuracy": display_percent(latest.get("accuracy"), language),
        "reaction_time": display_response_time(latest.get("median_rt_ms"), language),
        "difficulty": display_difficulty(latest.get("difficulty_end"), language),
        "valid_records": tr("cognitive_control_history.valid_records", count=len(comparable), total=len(records)),
        "trend_status": tr(
            "cognitive_control_history.trend_available" if len(comparable) >= 3
            else "cognitive_control_history.trend_insufficient"
        ),
        "latest": latest,
        "comparable": comparable,
    }


def history_rows(records, language):
    tr = _tr(language)
    return [{
        tr("cognitive_control_history.date"): format_date(record.get("started_at"), language),
        tr("cognitive_control_history.test"): display_test(record.get("task_type"), language),
        tr("cognitive_control_history.mode"): display_mode(record.get("session_mode"), language),
        tr("cognitive_control_history.difficulty"): display_difficulty(record.get("difficulty_end"), language),
        tr("cognitive_control_history.accuracy"): display_percent(record.get("accuracy"), language),
        tr("cognitive_control_history.median_response_time"): display_response_time(record.get("median_rt_ms"), language),
        tr("cognitive_control_history.data_status"): tr(
            "cognitive_control_history.data_complete" if is_complete(record)
            else "cognitive_control_history.data_incomplete"
        ),
    } for record in records]


def technical_rows(records, language):
    tr = _tr(language)
    return [{
        tr("cognitive_control_history.technical_test_code"): record.get("task_type") or missing(language),
        tr("cognitive_control_history.technical_protocol"): record.get("protocol_version") or missing(language),
        tr("cognitive_control_history.technical_difficulty_config"): record.get("difficulty_config_hash") or missing(language),
        tr("cognitive_control_history.technical_device"): record.get("device_class") or missing(language),
        tr("cognitive_control_history.technical_input"): record.get("input_method") or missing(language),
        tr("cognitive_control_history.technical_group"): record.get("comparable_group") or missing(language),
    } for record in records]


def derived_metric(record, language):
    """Only label metrics with explicit definitions in control_speed_metrics."""
    mapping = {
        "stroop_control": ("interference_cost_ms", "derived_stroop", "derived_stroop_explanation", "ms"),
        "task_switching": ("switch_cost_ms", "derived_switch", "derived_switch_explanation", "ms"),
        "symbol_match": ("correct_per_minute", "derived_symbol", "derived_symbol_explanation", "rpm"),
    }
    item = mapping.get(record.get("task_type"))
    if item is None:
        return None
    metric_key, label_key, explanation_key, unit = item
    value = _number((record.get("metrics") or {}).get(metric_key))
    if value is None:
        return None
    value_text = display_response_time(value, language) if unit == "ms" else _tr(language)(
        "cognitive_control_history.responses_per_minute", value=f"{value:.1f}"
    )
    return {
        "label": _tr(language)(f"cognitive_control_history.{label_key}"),
        "value": value_text,
        "explanation": _tr(language)(f"cognitive_control_history.{explanation_key}"),
    }
