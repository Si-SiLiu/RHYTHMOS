"""Structured input model for the local deterministic coach."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CoachInput:
    date: str
    recovery_score: int | None = None
    score_version: str | None = None
    recovery_capacity_score: float | None = None
    stress_load_score: float | None = None
    overall_confidence_score: int | None = None
    confidence_level: str | None = None
    data_completeness: int | None = None
    fallback_used: bool = False
    sleep_duration_hours: float | None = None
    sleep_score: float | None = None
    nightly_hrv_rmssd: float | None = None
    nightly_resting_hr: float | None = None
    respiration_rate: float | None = None
    morning_rmssd: float | None = None
    morning_mean_hr: float | None = None
    kubios_readiness: Any = None
    previous_training_duration_minutes: float | None = None
    previous_training_calories: float | None = None
    active_calories: float | None = None
    training_count: int | None = None
    current_training_duration_minutes: float | None = None
    current_training_session_rpe_load: float | None = None
    manual_training_session_count: int | None = None
    manual_training_duration_minutes: float | None = None
    manual_training_rpe_load: float | None = None
    nutrition_logged_meals: int | None = None
    nutrition_data_completeness: float | None = None
    nutrition_calories: float | None = None
    nutrition_protein_g: float | None = None
    nutrition_carbohydrate_g: float | None = None
    nutrition_water_ml: float | None = None
    nutrition_targets: dict[str, tuple[float, float | None]] = field(default_factory=dict)
    neural_available: bool = False
    neural_mental_fatigue: int | None = None
    neural_mental_clarity: int | None = None
    neural_physical_heaviness: int | None = None
    neural_baseline_status: str | None = None
    neural_confidence_level: str | None = None
    neural_lapse_355_count: int | None = None
    neural_slowest_20pct_rt_ms: float | None = None
    baseline_status: dict[str, str] = field(default_factory=dict)
    explanation_json: dict[str, Any] = field(default_factory=dict)
    freshness_days: int = 0
    is_historical: bool = False
