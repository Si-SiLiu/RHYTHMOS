"""Deterministic, non-medical guidance from neural-fatigue observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping


ALGORITHM_VERSION = "neural-fatigue-guidance-v0.1"
BURDEN_LOWER_MAX = 35.0
BURDEN_MODERATE_MAX = 65.0
TREND_DELTA = 5.0
MIN_TREND_DAYS = 3
LOW_CONFIDENCE = 0.35
FULL_CONFIDENCE = 0.60
MAX_ACTIONS = 6
CATEGORIES = ("cognitive_work", "training", "recovery", "measurement")


class GuidanceDomainError(ValueError):
    """Raised when a guidance input does not meet the explicit contract."""


@dataclass(frozen=True)
class GuidanceInputs:
    current_result: Any
    current_snapshot_date: date
    history_summaries: tuple[Mapping[str, Any], ...]
    component_trends: Mapping[str, tuple[Mapping[str, Any], ...]]
    available_history_days: int
    requested_history_window: int
    computed_at: datetime


@dataclass(frozen=True)
class GuidanceAction:
    code: str
    category: str
    priority: int
    strength: str
    rationale_codes: tuple[str, ...]
    evidence_components: tuple[str, ...]
    evidence_dates: tuple[str, ...]
    caution_codes: tuple[str, ...]


@dataclass(frozen=True)
class GuidanceResult:
    status: str
    burden_band: str
    trend_direction: str
    confidence_band: str
    actions: tuple[GuidanceAction, ...]
    reasons: tuple[str, ...]
    cautions: tuple[str, ...]
    evidence_summary: Mapping[str, Any]
    algorithm_version: str
    computed_at: datetime


def calculate_guidance(inputs: GuidanceInputs) -> GuidanceResult:
    """Return transparent, stable suggestions without performing any I/O."""
    _validate(inputs)
    result = inputs.current_result
    rows = tuple(sorted(inputs.history_summaries, key=lambda row: str(row["snapshot_date"])))
    available = tuple(row for row in rows if row.get("status") == "available" and row.get("burden_score") is not None)
    burden_band = _burden_band(result.burden_score)
    direction, trend_dates, recent_average, prior_average = _trend(available)
    confidence_band = _confidence_band(result.confidence)
    evidence = {
        "history_window_days": inputs.requested_history_window,
        "available_history_days": len(available),
        "insufficient_history_days": sum(row.get("status") == "insufficient_data" for row in rows),
        "recent_average": recent_average,
        "prior_average": prior_average,
        "trend_dates": trend_dates,
        "component_trends": _component_summaries(inputs.component_trends),
    }
    missing = set(result.missing_components)
    stale = _stale_components(result.reasons)
    base_reasons = [f"burden_{burden_band}", f"trend_{direction}", f"confidence_{confidence_band}"]
    cautions = ["non_medical_personal_trend", "guidance_is_not_automatic"]
    actions: list[GuidanceAction] = []

    if result.status != "available" or result.confidence < LOW_CONFIDENCE:
        status = "insufficient_data"
        cautions.append("current_data_insufficient")
        actions.extend(_measurement_actions(missing, stale, len(available), result.confidence, trend_dates))
    else:
        status = "limited" if result.confidence < FULL_CONFIDENCE else "available"
        if status == "limited":
            cautions.append("confidence_limited")
        actions.extend(_measurement_actions(missing, stale, len(available), result.confidence, trend_dates))
        actions.extend(_cognitive_actions(burden_band, direction, result, trend_dates))
        actions.extend(_training_actions(burden_band, result, trend_dates))
        actions.extend(_recovery_actions(burden_band, direction, result, trend_dates))

    actions = _resolve_actions(actions)
    return GuidanceResult(
        status=status, burden_band=burden_band, trend_direction=direction,
        confidence_band=confidence_band, actions=tuple(actions), reasons=tuple(base_reasons),
        cautions=tuple(dict.fromkeys(cautions)), evidence_summary=evidence,
        algorithm_version=ALGORITHM_VERSION, computed_at=inputs.computed_at,
    )


def _measurement_actions(missing, stale, available_days, confidence, dates):
    actions = []
    priority = 1 if confidence < LOW_CONFIDENCE else 3
    if "cognitive" in missing:
        actions.append(_action("measure_cognitive", "measurement", priority, "light", ("cognitive_missing",), ("cognitive",), dates))
    if "recovery" in missing or "sleep" in missing:
        components = tuple(name for name in ("recovery", "sleep") if name in missing)
        actions.append(_action("measure_recovery_sleep", "measurement", priority, "light", ("recovery_or_sleep_missing",), components, dates))
    if available_days < MIN_TREND_DAYS:
        actions.append(_action("save_more_history", "measurement", priority, "light", ("history_insufficient",), (), dates))
    for component in sorted(stale):
        actions.append(_action(f"refresh_{component}", "measurement", priority, "light", ("component_stale",), (component,), dates))
    if confidence < LOW_CONFIDENCE and not actions:
        actions.append(_action("improve_data_coverage", "measurement", 1, "light", ("confidence_low",), (), dates))
    return actions


def _cognitive_actions(band, direction, result, dates):
    evidence = _evidence(result, ("cognitive", "recovery", "sleep"))
    cognitive_high = result.component_scores.get("cognitive", 0) >= BURDEN_MODERATE_MAX
    rationale = (f"burden_{band}", f"trend_{direction}") + (("cognitive_elevated",) if cognitive_high else ())
    if band == "lower":
        return [_action("cognitive_plan_high_focus", "cognitive_work", 2, "light", rationale, evidence, dates)]
    if band == "moderate":
        return [_action("cognitive_prioritize_and_split", "cognitive_work", 2, "moderate", rationale, evidence, dates)]
    return [_action("cognitive_defer_intense", "cognitive_work", 1, "strong", rationale, evidence, dates)]


def _training_actions(band, result, dates):
    scores = result.component_scores
    evidence = _evidence(result, ("training", "recovery", "sleep"))
    training_only = scores.get("training", 0) >= BURDEN_MODERATE_MAX and all(scores.get(name, 0) < BURDEN_MODERATE_MAX for name in ("cognitive", "recovery", "sleep"))
    if training_only:
        return [_action("training_context_limited", "training", 3, "light", ("training_only_elevated",), ("training",), dates, ("training_not_equivalent_to_neural_fatigue",))]
    if band == "lower" and all(scores.get(name, 0) < BURDEN_MODERATE_MAX for name in ("recovery", "sleep")):
        return [_action("training_maintain_plan", "training", 3, "light", ("burden_lower",), evidence, dates)]
    if band == "moderate":
        return [_action("training_reduce_complexity", "training", 2, "moderate", ("burden_moderate",), evidence, dates)]
    return [_action("training_reduce_intensity", "training", 1, "strong", ("burden_elevated_or_recovery_sleep",), evidence, dates)]


def _recovery_actions(band, direction, result, dates):
    evidence = _evidence(result, ("recovery", "sleep"))
    high = any(result.component_scores.get(name, 0) >= BURDEN_MODERATE_MAX for name in ("recovery", "sleep"))
    if not high and not (band == "elevated" and direction == "worsening"):
        return []
    priority = 1 if band == "elevated" and direction == "worsening" else 2
    return [_action("recovery_prioritize_sleep", "recovery", priority, "strong" if priority == 1 else "moderate", ("recovery_or_sleep_elevated", f"trend_{direction}"), evidence, dates)]


def _resolve_actions(actions):
    category_limit = {category: 0 for category in CATEGORIES}
    result = []
    seen = set()
    for action in sorted(actions, key=lambda item: (item.priority, CATEGORIES.index(item.category), item.code)):
        if action.code in seen or category_limit[action.category] >= 2 or len(result) >= MAX_ACTIONS:
            continue
        seen.add(action.code)
        category_limit[action.category] += 1
        result.append(action)
    return result


def _trend(rows):
    if len(rows) < MIN_TREND_DAYS:
        return "unavailable", tuple(row["snapshot_date"] for row in rows), None, None
    recent = rows[-3:]
    prior = rows[-6:-3]
    recent_average = sum(float(row["burden_score"]) for row in recent) / len(recent)
    if not prior:
        return "unavailable", tuple(row["snapshot_date"] for row in recent), recent_average, None
    prior_average = sum(float(row["burden_score"]) for row in prior) / len(prior)
    delta = recent_average - prior_average
    direction = "worsening" if delta >= TREND_DELTA else "improving" if delta <= -TREND_DELTA else "stable"
    return direction, tuple(row["snapshot_date"] for row in recent), recent_average, prior_average


def _component_summaries(component_trends):
    """Summarise available component observations without filling missing scores."""
    summaries = {}
    for name in ("cognitive", "recovery", "sleep", "training"):
        rows = tuple(component_trends.get(name, ()))
        scores = [float(row["score"]) for row in rows if row.get("score") is not None]
        summaries[name] = {
            "available_days": len(scores),
            "recent_average": sum(scores[-3:]) / len(scores[-3:]) if scores else None,
            "latest_date": rows[-1].get("snapshot_date") if rows else None,
        }
    return summaries


def _action(code, category, priority, strength, rationale, components, dates, cautions=()):
    return GuidanceAction(code, category, priority, strength, tuple(rationale), tuple(components), tuple(dates), tuple(cautions))


def _evidence(result, names):
    return tuple(name for name in names if name in result.component_scores)


def _burden_band(score):
    if score is None:
        return "unavailable"
    return "lower" if score < BURDEN_LOWER_MAX else "moderate" if score < BURDEN_MODERATE_MAX else "elevated"


def _confidence_band(confidence):
    return "low" if confidence < LOW_CONFIDENCE else "limited" if confidence < FULL_CONFIDENCE else "sufficient"


def _stale_components(reasons):
    return {reason.split("_")[1] for reason in reasons if reason.startswith("component_") and reason.endswith("_stale_excluded")}


def _validate(inputs):
    if not isinstance(inputs.current_snapshot_date, date) or not isinstance(inputs.computed_at, datetime) or inputs.computed_at.tzinfo is None:
        raise GuidanceDomainError("snapshot date and computed_at must be timezone-aware")
    if inputs.requested_history_window not in (7, 14, 30) or inputs.available_history_days < 0:
        raise GuidanceDomainError("history window must be 7, 14, or 30 days")
    if not 0 <= inputs.current_result.confidence <= 1:
        raise GuidanceDomainError("confidence must be within 0..1")
