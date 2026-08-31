"""Deterministic morning strength and evening Hip-Hop recommendations."""

from .models import CoachInput


def _advice(status, session):
    labels = {
        "normal": "可按既定安排进行，训练中仍根据主观状态调整。",
        "moderate_reduction": "建议适度减少训练量，保留动作质量并避免额外加量。",
        "major_reduction": "建议明显减量，以低风险动作和充分组间恢复为主。",
        "technique_only": "建议只做轻量技术练习，不追求强度或训练量。",
        "mobility_only": "建议改为灵活性、节奏走位或轻松活动。",
        "rest": "建议暂停本次训练，把恢复和状态观察放在首位。",
    }
    return f"{session}：{labels[status]}"


def _entry(status, schedule, session, rules, adjustments=True):
    values = rules["training_adjustments"][status]
    return {
        "status": status,
        "schedule": schedule,
        "volume_adjustment_percent": values["volume"] if adjustments else None,
        "intensity_adjustment_percent": values["intensity"] if adjustments else None,
        "advice": _advice(status, session),
    }


def _nutrition_shortfall(data):
    shortfalls = []
    for field, label in (
        ("nutrition_protein_g", "蛋白质"),
        ("nutrition_carbohydrate_g", "碳水化合物"),
        ("nutrition_water_ml", "水分"),
    ):
        value = getattr(data, field)
        target = data.nutrition_targets.get(field.removeprefix("nutrition_"))
        if value is not None and target and target[0] is not None and value < target[0]:
            shortfalls.append(label)
    return shortfalls


def _domain_signals(data, rules):
    sleep_low = (
        (data.sleep_duration_hours is not None and
         data.sleep_duration_hours < rules["sleep_insufficient_hours"])
        or (data.sleep_score is not None and data.sleep_score < rules["sleep_score_low"])
    )
    current_duration = data.current_training_duration_minutes or 0
    manual_duration = data.manual_training_duration_minutes or 0
    training_high = (
        (data.stress_load_score is not None and data.stress_load_score >= rules["high_load_score"])
        or current_duration >= rules["training_high_duration_minutes"]
        or manual_duration >= rules["training_high_duration_minutes"]
        or (data.manual_training_rpe_load is not None and
            data.manual_training_rpe_load >= rules["training_high_rpe_load"])
    )
    neural_low = data.neural_available and (
        (data.neural_mental_fatigue is not None and data.neural_mental_fatigue >= rules["neural_fatigue_high"])
        or (data.neural_physical_heaviness is not None and data.neural_physical_heaviness >= rules["neural_heaviness_high"])
        or data.neural_baseline_status == "slower_than_baseline"
        or (data.neural_lapse_355_count is not None and
            data.neural_lapse_355_count >= rules["neural_lapse_high"])
    )
    nutrition_shortfalls = _nutrition_shortfall(data)
    nutrition_low = bool(nutrition_shortfalls) and data.nutrition_data_completeness is not None and data.nutrition_data_completeness >= rules["nutrition_min_completeness"]
    return {
        "sleep_low": sleep_low,
        "training_high": training_high,
        "neural_low": neural_low,
        "nutrition_low": nutrition_low,
        "nutrition_shortfalls": nutrition_shortfalls,
        "sleep_available": data.sleep_duration_hours is not None or data.sleep_score is not None,
        "training_available": any(value is not None for value in (
            data.training_count, data.current_training_duration_minutes,
            data.manual_training_session_count, data.manual_training_duration_minutes,
        )),
        "neural_available": data.neural_available,
        "nutrition_available": data.nutrition_logged_meals is not None and data.nutrition_logged_meals > 0,
    }


def _status_rank(status):
    return {"normal": 0, "moderate_reduction": 1, "major_reduction": 2,
            "technique_only": 3, "mobility_only": 4, "rest": 5}.get(status, 0)


def _max_status(first, second):
    return first if _status_rank(first) >= _status_rank(second) else second


def generate_training_advice(data: CoachInput, rules):
    schedule = rules["fixed_schedule"]
    score = data.recovery_score
    level = data.confidence_level
    completeness = data.data_completeness
    missing_score = score is None
    low_confidence = level in {None, "very_low", "insufficient"}
    incomplete = completeness is None or completeness < rules["minimum_data_completeness"]
    hrv_down = data.baseline_status.get("nightly_hrv_rmssd") == "below_baseline"
    hr_up = data.baseline_status.get("nightly_resting_hr") == "above_baseline"
    signals = _domain_signals(data, rules)
    sleep_low = signals["sleep_low"]
    triple_pressure = hrv_down and hr_up and sleep_low
    stress_high = signals["training_high"]

    if missing_score:
        morning, evening, adjustments = "technique_only", "mobility_only", False
    elif low_confidence or incomplete:
        morning, evening, adjustments = "technique_only", "mobility_only", True
    elif triple_pressure:
        morning, evening, adjustments = "major_reduction", "technique_only", True
    elif score >= rules["recovery_score_thresholds"]["high"]:
        morning, evening, adjustments = "normal", "normal", True
    elif score >= rules["recovery_score_thresholds"]["medium"]:
        if sleep_low or stress_high:
            morning, evening = "moderate_reduction", "technique_only"
        else:
            morning, evening = "normal", "moderate_reduction"
        adjustments = True
    elif score >= rules["recovery_score_thresholds"]["low"]:
        morning, evening, adjustments = "major_reduction", "technique_only", True
    else:
        morning, evening, adjustments = "rest", "mobility_only", True

    # These signals are intentionally one-way: they can reduce a planned
    # session, but a single favourable signal never overrides poor recovery.
    if signals["neural_low"]:
        morning = _max_status(morning, "major_reduction")
        evening = _max_status(evening, "technique_only")
    if signals["sleep_low"] and signals["neural_low"]:
        morning = _max_status(morning, "major_reduction")
        evening = _max_status(evening, "technique_only")
    if signals["training_high"] and signals["sleep_low"]:
        morning = _max_status(morning, "major_reduction")
        evening = _max_status(evening, "technique_only")

    # High load alone never forces rest when deterministic recovery remains high.
    output = {
        "morning_training": _entry(
            morning, schedule["morning_strength"], "上午力量训练", rules, adjustments
        ),
        "evening_training": _entry(
            evening, schedule["evening_hip_hop"], "晚间 Hip-Hop", rules, adjustments
        ),
    }
    return {**output, "training_summary": build_training_summary(data, rules, output, signals)}


def build_training_summary(data, rules, output, signals=None):
    """Explain the final combined decision without exposing raw health values."""
    signals = signals or _domain_signals(data, rules)
    domains = []
    if signals["sleep_low"]:
        domains.append("睡眠不足或睡眠质量偏低")
    if signals["training_high"]:
        domains.append("近期训练负荷偏高")
    if signals["neural_low"]:
        domains.append("神经状态提示需要降低刺激")
    if signals["nutrition_low"]:
        domains.append("营养记录显示训练相关摄入仍需补足")

    morning = output["morning_training"]["status"]
    evening = output["evening_training"]["status"]
    active_training_pressure = any(signals[key] for key in ("sleep_low", "training_high", "neural_low"))
    if not domains:
        advice = "综合睡眠、训练、神经和营养情况，当前可按计划训练，并根据实时主观状态调整。"
        status = "normal"
    elif morning == "rest":
        advice = "综合信号偏向恢复优先，建议暂停高强度训练，以休息和状态观察为主。"
        status = "conservative"
    elif not active_training_pressure:
        advice = "综合营养记录与其它可用数据，训练安排暂可维持；训练前后优先补足营养。"
        status = "adjusted"
    elif signals["training_high"] and not (signals["sleep_low"] or signals["neural_low"]):
        advice = "近期训练负荷偏高，但当前恢复未触发明显降负荷条件；建议按计划完成，避免额外加量并保留恢复间歇。"
        status = "adjusted"
    else:
        advice = "综合" + "、".join(domains or ["当前恢复情况"]) + "，建议降低训练刺激，优先保留动作质量和恢复间歇。"
        status = "adjusted"
    if signals["nutrition_low"]:
        advice += "训练前后优先补充有记录依据的碳水化合物和蛋白质来源。"
    if not domains:
        domains = ["四类数据均未触发额外降负荷条件"]
    return {
        "status": status,
        "advice": advice,
        "drivers": domains[:4],
        "data_coverage": {
            "sleep": signals["sleep_available"],
            "training": signals["training_available"],
            "neural": signals["neural_available"],
            "nutrition": signals["nutrition_available"],
        },
    }
