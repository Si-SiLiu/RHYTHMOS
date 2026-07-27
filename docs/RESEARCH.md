# Research Framework

## Research positioning

RHYTHMOS｜律衡 is a personal performance and recovery system and a
potential N-of-1 research instrument. It combines wearable, self-measurement,
and training data into reproducible daily features. It is not a clinically
validated model, medical device, diagnostic system, or population health
benchmark.

The research value is methodological: preserving raw evidence, defining daily
metrics, comparing each user with their own history, versioning deterministic
algorithms, and making missing data visible.

## Potential research questions

- Does an individual's rolling HRV baseline improve interpretation compared
  with a fixed RMSSD threshold?
- Are deviations in sleep and resting heart rate associated with subsequent
  subjective fatigue?
- Does training load above personal history predict lower next-day recovery
  scores within this individual?
- How stable are conclusions across 7-, 14-, 28-, and 42-day windows?
- Do Polar Nightly signals and Kubios morning signals agree on direction?
- How often does incomplete data materially change a recommendation?
- Can Confidence metadata reduce overinterpretation of sparse days?
- Does a recommendation correlate with later training adherence or perceived
  readiness?

These are research questions, not established claims.

## Testable hypotheses

Examples of hypotheses that could be preregistered before analysis:

1. Days with RMSSD below the individual's prior 28-day median are followed by
   higher subjective fatigue than within-baseline days.
2. Resting heart rate above the personal baseline is associated with lower
   self-reported readiness on the same morning.
3. Recovery Score computed with mature baselines has better within-person
   agreement with subjective readiness than fallback scores.
4. Confidence level moderates score reliability: high-confidence days have
   stronger agreement with subjective outcomes than low-confidence days.
5. Polar and Kubios RMSSD deviations agree in direction more often than chance
   when measurements occur under comparable conditions.

Every hypothesis requires a defined outcome, time window, exclusion rule,
analysis plan, and minimum observation count before results are inspected.

## Current data sources

- Polar AccessLink v3/v4 responses.
- Polar Flow export files collected locally.
- Kubios Morning HRV CSV imports when provided.
- Derived daily metrics in SQLite.
- Rolling baseline records.
- Versioned Recovery Engine outputs.

Current machine-readable counts and date coverage are maintained only in
[project_state.json](../project_state.json). Dataset structure and provenance
are documented in [DATASET.md](DATASET.md).

## Data limitations

- The current dataset primarily represents one user.
- Measurement conditions may vary by day.
- Wearable algorithms and firmware are external and may change.
- Polar and Kubios signals may use different sampling windows.
- Missing data are not random in all circumstances.
- Training, illness, travel, alcohol, stress, and nutrition confounders may be
  unrecorded.
- Subjective readiness and symptom labels are not yet captured systematically.
- The observation period is short for seasonal inference.
- Current data cannot support population generalization.
- No clinical reference standard is available.

## Baseline Engine research value

The Baseline Engine enables transparent within-person comparisons. It excludes
the target day, uses a configurable rolling window, requires a minimum history,
and stores mean, median, standard deviation, MAD, percent change, and robust
z-score. These properties support replay and sensitivity analysis.

Research should compare window sizes and outlier policies rather than assume the
default 28-day window is optimal. A baseline status is a statistical description
of personal history, not evidence of disease.

## Recovery Engine verifiability

Recovery Engine v1.0 is deterministic. Inputs, direction, weights, fallback,
score version, and recommendation thresholds are documented in
[RECOVERY_ENGINE.md](RECOVERY_ENGINE.md) and [MODEL_CARD.md](MODEL_CARD.md).

The same version and inputs should reproduce the same score. Historical replay
must retain the version source and configuration used. Reproducibility does not
establish predictive validity.

## Future experiment designs

### Prospective observational study

Collect daily subjective readiness before viewing the system score. Compare
within-person associations among raw signals, baseline deviations, Recovery
Score, Confidence, and next-day outcomes.

### Window sensitivity study

Replay the same dates with multiple baseline windows. Compare status changes,
score stability, and missing-baseline rates without selecting the best window
after seeing outcomes.

### Source agreement study

On mornings with both Polar and Kubios measurements, compare signed deviations,
rank correlation, absolute differences, and disagreement cases. Align
measurement timing before interpretation.

### Recommendation utility study

Record whether the user follows the recommendation and later reports benefit,
neutral effect, or harm. This requires careful avoidance of circular labels.

## Candidate validation metrics

- Spearman correlation with prospective subjective readiness.
- Mean absolute error against a predefined subjective scale.
- Calibration by Confidence level.
- Recommendation agreement rate.
- Directional agreement for Polar versus Kubios signals.
- Missing-group frequency.
- Baseline availability rate.
- Score test-retest stability under unchanged inputs.
- Sensitivity to baseline window and outlier policy.
- False reassurance and excessive caution review counts.

Metrics must be selected before evaluating a hypothesis. Statistical
significance alone is insufficient; effect size and uncertainty are required.

## Comparing with Polar and Kubios scores

Comparison should preserve each vendor's intended meaning. The project should
not treat Polar sleep or Nightly Recharge scores, Kubios readiness, and
RHYTHMOS｜律衡 as interchangeable labels.

A defensible comparison plan would:

1. Align dates and measurement windows.
2. Record vendor score availability.
3. Compare rank and direction, not only absolute values.
4. Stratify by project Confidence level.
5. Review disagreement days qualitatively.
6. Avoid declaring one system correct without an external outcome.

## N-of-1 design

The initial research unit is one person over time. Analysis should use
within-person centering, account for autocorrelation, preserve temporal order,
and avoid random train/test splits that leak future data. Prospective labels and
blocked time-series validation are preferred.

The user should be able to pause collection, inspect records, correct import
errors, and exclude predefined invalid measurements without deleting raw
evidence.

## Multi-user ethics and privacy

Any future multi-user study would require a separate protocol covering informed
consent, lawful data processing, withdrawal, minimization, de-identification,
access control, retention, incident response, and ethical review appropriate to
the jurisdiction and institution.

Local single-user data must not be uploaded or pooled merely because a research
question is interesting. Consent to use a product is not consent to participate
in research.

## Medical boundary

RMSSD, resting heart rate, respiration, sleep, and load can vary for many
reasons. This project does not diagnose infection, overtraining syndrome,
cardiac disease, sleep disorders, or any other condition. Concerning symptoms
require appropriate professional evaluation independent of the score.

## Potential publication directions

- A transparent architecture for local-first personal recovery analytics.
- Reproducibility of robust rolling baselines in an N-of-1 setting.
- Agreement between wearable nighttime and morning spot HRV measurements.
- Confidence-aware communication of incomplete personal health data.
- A case study of deterministic scoring plus constrained AI explanation.

These are possible directions, not claims of novelty or publishability.

## Reproducibility requirements

- Pin algorithm and configuration versions.
- Preserve raw source records locally.
- Record code revision for each analysis.
- Exclude the target day from its baseline.
- Define missing and invalid values before analysis.
- Preserve temporal train/validation separation.
- Record every transformation and unit conversion.
- Export aggregate results without personal identifiers.
- Report null findings and limitations.
- Never claim clinical validation without an appropriate study.
