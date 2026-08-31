"""Minimal mapping adapters for the neural-fatigue domain contract.

Adapters accept already-read records. They deliberately do not open databases,
write results, or recreate existing recovery, sleep, or cognitive algorithms.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from math import isfinite

from .neural_fatigue import NeuralFatigueComponent, NeuralFatigueInputs


def adapt_inputs(*, cognitive: Mapping | None = None, recovery: Mapping | None = None,
                 sleep: Mapping | None = None, training: Mapping | None = None,
                 subjective: Mapping | None = None) -> NeuralFatigueInputs:
    """Convert optional existing query/domain records without inventing data."""
    return NeuralFatigueInputs(
        cognitive=adapt_cognitive(cognitive),
        recovery=adapt_recovery(recovery),
        sleep=adapt_sleep(sleep),
        training=adapt_training(training),
        subjective=adapt_subjective(subjective),
    )


def adapt_cognitive(record: Mapping | None) -> NeuralFatigueComponent | None:
    """Use slower median response and lower accuracy against personal baselines."""
    if not record or not record.get("completed", True):
        return None
    reaction = _number(record.get("median_rt_ms"))
    accuracy = _number(record.get("accuracy"))
    reaction_baseline = _number(record.get("baseline_median_rt_ms"))
    accuracy_baseline = _number(record.get("baseline_accuracy"))
    deviations = []
    if reaction is not None and reaction_baseline and reaction_baseline > 0:
        deviations.append(_bounded((reaction / reaction_baseline - 1.0) / 0.20 * 100.0))
    if accuracy is not None and accuracy_baseline is not None:
        deviations.append(_bounded((accuracy_baseline - accuracy) / 0.20 * 100.0))
    if not deviations:
        return None
    return _component(record, sum(deviations) / len(deviations), "cognitive_training")


def adapt_recovery(record: Mapping | None) -> NeuralFatigueComponent | None:
    """Invert the existing 0--100 recovery score; do not alter its algorithm."""
    score = _number(record.get("recovery_score")) if record else None
    return _component(record, 100.0 - score, "recovery_scores") if score is not None else None


def adapt_sleep(record: Mapping | None) -> NeuralFatigueComponent | None:
    """Invert the existing 0--100 sleep score; no fixed medical threshold."""
    score = _number(record.get("sleep_score")) if record else None
    return _component(record, 100.0 - score, "daily_recovery_metrics.sleep_score") if score is not None else None


def adapt_training(record: Mapping | None) -> NeuralFatigueComponent | None:
    """Map a positive personal load deviation to observed training burden."""
    if not record:
        return None
    deviation = _number(record.get("percent_difference"))
    if deviation is None:
        return None
    return _component(record, _bounded(max(deviation, 0.0) / 50.0 * 100.0), "training_baseline")


def adapt_subjective(record: Mapping | None) -> NeuralFatigueComponent | None:
    """Reserved for a future explicit subjective input; no field exists in v0.1."""
    return None


def _component(record: Mapping, burden: float, default_source: str) -> NeuralFatigueComponent | None:
    observed_at = record.get("observed_at")
    if not isinstance(observed_at, datetime) or observed_at.tzinfo is None:
        return None
    baseline_count = record.get("baseline_sample_count")
    if isinstance(baseline_count, bool) or not isinstance(baseline_count, int) or baseline_count < 0:
        return None
    freshness = _number(record.get("freshness_hours"))
    quality = _number(record.get("quality"))
    if freshness is not None and freshness < 0:
        return None
    if quality is not None and not 0.0 <= quality <= 1.0:
        return None
    return NeuralFatigueComponent(
        score=round(_bounded(burden), 6),
        observed_at=observed_at,
        baseline_sample_count=baseline_count,
        source=str(record.get("source") or default_source),
        freshness_hours=freshness,
        quality=quality,
    )


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _bounded(value: float) -> float:
    return max(0.0, min(100.0, float(value)))
