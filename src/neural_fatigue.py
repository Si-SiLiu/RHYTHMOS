"""Transparent, non-diagnostic neurocognitive fatigue trend calculation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Literal


ALGORITHM_VERSION = "neural-fatigue-v0.1"
COMPONENT_NAMES = ("cognitive", "recovery", "sleep", "training", "subjective")
MINIMUM_BASELINE_SAMPLES = 28
HARD_STALE_HOURS = 168.0


class NeuralFatigueInputError(ValueError):
    """Raised when a component violates the explicit domain contract."""


@dataclass(frozen=True)
class NeuralFatigueComponent:
    """One observed burden component on the shared 0--100 scale."""

    score: float
    observed_at: datetime
    baseline_sample_count: int
    source: str
    freshness_hours: float | None = None
    quality: float | None = None

    def __post_init__(self) -> None:
        score = _finite_number(self.score, "score")
        if not 0.0 <= score <= 100.0:
            raise NeuralFatigueInputError("score must be within 0..100")
        if not isinstance(self.observed_at, datetime) or self.observed_at.tzinfo is None:
            raise NeuralFatigueInputError("observed_at must be timezone-aware")
        if isinstance(self.baseline_sample_count, bool) or not isinstance(self.baseline_sample_count, int):
            raise NeuralFatigueInputError("baseline_sample_count must be an integer")
        if self.baseline_sample_count < 0:
            raise NeuralFatigueInputError("baseline_sample_count must be non-negative")
        if not isinstance(self.source, str) or not self.source.strip():
            raise NeuralFatigueInputError("source must be a non-empty string")
        if self.freshness_hours is not None and _finite_number(self.freshness_hours, "freshness_hours") < 0:
            raise NeuralFatigueInputError("freshness_hours must be non-negative")
        if self.quality is not None:
            quality = _finite_number(self.quality, "quality")
            if not 0.0 <= quality <= 1.0:
                raise NeuralFatigueInputError("quality must be within 0..1")


@dataclass(frozen=True)
class NeuralFatigueInputs:
    cognitive: NeuralFatigueComponent | None = None
    recovery: NeuralFatigueComponent | None = None
    sleep: NeuralFatigueComponent | None = None
    training: NeuralFatigueComponent | None = None
    subjective: NeuralFatigueComponent | None = None

    def items(self):
        return tuple((name, getattr(self, name)) for name in COMPONENT_NAMES)


@dataclass(frozen=True)
class NeuralFatigueResult:
    burden_score: float | None
    confidence: float
    status: Literal["available", "insufficient_data"]
    component_scores: dict[str, float]
    component_weights: dict[str, float]
    available_components: tuple[str, ...]
    missing_components: tuple[str, ...]
    reasons: tuple[str, ...]
    cautions: tuple[str, ...]
    algorithm_version: str
    computed_at: datetime


def calculate_neural_fatigue(inputs: NeuralFatigueInputs, *, computed_at: datetime) -> NeuralFatigueResult:
    """Calculate a deterministic personal trend indicator from valid inputs.

    At least two usable components are required, including cognitive, recovery,
    or sleep. Missing values never contribute a zero burden score.
    """
    _validate_computed_at(computed_at)
    usable: list[tuple[str, NeuralFatigueComponent, float]] = []
    missing: list[str] = []
    reasons: list[str] = []
    cautions = ["confidence_reflects_data_coverage_and_quality"]

    for name, component in inputs.items():
        if component is None:
            missing.append(name)
            reasons.append(f"component_{name}_missing")
            continue
        age = _freshness_hours(component, computed_at)
        if age > HARD_STALE_HOURS:
            missing.append(name)
            reasons.append(f"component_{name}_stale_excluded")
            cautions.append(f"component_{name}_is_stale")
            continue
        usable.append((name, component, age))
        reasons.append(f"component_{name}_available")

    names = tuple(name for name, _, _ in usable)
    minimum_met = len(usable) >= 2 and any(name in {"cognitive", "recovery", "sleep"} for name in names)
    if not minimum_met:
        reasons.append("minimum_data_condition_not_met")
        return NeuralFatigueResult(
            burden_score=None,
            confidence=0.0,
            status="insufficient_data",
            component_scores={name: component.score for name, component, _ in usable},
            component_weights={},
            available_components=names,
            missing_components=tuple(missing),
            reasons=tuple(reasons),
            cautions=tuple(_unique(cautions)),
            algorithm_version=ALGORITHM_VERSION,
            computed_at=computed_at,
        )

    weight = 1.0 / len(usable)
    scores = {name: component.score for name, component, _ in usable}
    weights = {name: weight for name, _, _ in usable}
    burden = sum(scores[name] * weights[name] for name in names)
    confidence = _confidence(usable)
    if any(component.baseline_sample_count < MINIMUM_BASELINE_SAMPLES for _, component, _ in usable):
        cautions.append("personal_baseline_samples_are_limited")
    if any(age > 24.0 for _, _, age in usable):
        cautions.append("some_component_data_is_not_recent")
    return NeuralFatigueResult(
        burden_score=round(burden, 6),
        confidence=round(confidence, 6),
        status="available",
        component_scores=scores,
        component_weights=weights,
        available_components=names,
        missing_components=tuple(missing),
        reasons=tuple(reasons),
        cautions=tuple(_unique(cautions)),
        algorithm_version=ALGORITHM_VERSION,
        computed_at=computed_at,
    )


def _confidence(usable: list[tuple[str, NeuralFatigueComponent, float]]) -> float:
    coverage = len(usable) / len(COMPONENT_NAMES)
    freshness = sum(max(0.2, 1.0 - age / HARD_STALE_HOURS) for _, _, age in usable) / len(usable)
    baseline = sum(min(component.baseline_sample_count / MINIMUM_BASELINE_SAMPLES, 1.0) for _, component, _ in usable) / len(usable)
    quality = sum(component.quality if component.quality is not None else 0.75 for _, component, _ in usable) / len(usable)
    return max(0.0, min(1.0, coverage * freshness * baseline * quality))


def _freshness_hours(component: NeuralFatigueComponent, computed_at: datetime) -> float:
    if component.observed_at > computed_at:
        raise NeuralFatigueInputError("observed_at must not be in the future")
    derived = (computed_at - component.observed_at).total_seconds() / 3600
    return component.freshness_hours if component.freshness_hours is not None else derived


def _validate_computed_at(value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise NeuralFatigueInputError("computed_at must be timezone-aware")


def _finite_number(value: object, name: str) -> float:
    if isinstance(value, bool):
        raise NeuralFatigueInputError(f"{name} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise NeuralFatigueInputError(f"{name} must be numeric") from exc
    if not isfinite(number):
        raise NeuralFatigueInputError(f"{name} must be finite")
    return number


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
