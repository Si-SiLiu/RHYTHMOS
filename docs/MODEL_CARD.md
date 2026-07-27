# Model Card: Recovery Engine

## Kubios HRV Data Model 1.0

This release is a deterministic data-processing model, not a predictive medical
model. It retains reviewed fields, selects a transparent primary source, and
computes reproducible baseline/trend summaries. It does not diagnose disease,
equate LF/HF with an exact autonomic balance, or treat physiological age as true
health age. Recovery, Confidence, and Local Coach model versions are unchanged.

## Kubios Screenshot OCR clarification

macOS Vision text recognition is a local operating-system capability, not the
unreleased RHYTHMOS｜律衡 AI model. OCR confidence describes text
recognition only; it is never interpreted as recovery confidence, physiology,
diagnosis, or treatment. Human review is mandatory before import. Cloud AI
Runtime remains false and AI Model remains unreleased.

Personal Logging and AI Context Export introduce no AI model. `model_version`
remains `unreleased`; exported files are user-reviewed context, not model output.

## Model Name

RHYTHMOS｜律衡 Recovery Engine.

## Version

The current implemented version is read from
[config/versions.json](../config/versions.json). Historical database rows may
contain legacy labels such as `v0.1` or `v0.3`.

## Model type

Deterministic rules and personal rolling baselines. It is not a trained machine
learning model.

## Intended Use

- Personal training decision support.
- Daily review of activity, training, sleep, HRV, and heart-rate evidence.
- Reproducible explanation of load and recovery signals relative to personal
  history.
- Local experimentation and N-of-1 research with appropriate limitations.

## Out-of-Scope Use

- Medical diagnosis or treatment.
- Emergency triage.
- Population screening or ranking.
- Employment, insurance, or eligibility decisions.
- Autonomous training prescriptions without user review.
- Evaluation of children, patients, or other populations without dedicated
  validation and governance.

## Inputs

Current daily inputs can include:

- Steps.
- Active calories.
- Training duration and calories.
- Polar nightly RMSSD.
- Kubios morning RMSSD.
- Nightly resting heart rate.
- Morning mean heart rate.
- Respiration rate.
- Sleep duration and sleep score.
- Kubios readiness.
- Personal baseline statistics for the target date.

Field units and missing semantics are defined in
[DATA_DICTIONARY.md](DATA_DICTIONARY.md).

## Outputs

- `recovery_score`, integer 0–100.
- Activity load score, integer 0–100.
- Training load score, integer 0–100.
- Optional HRV, heart-rate, and readiness component scores.
- Recovery Engine version.
- One of four Chinese recommendation labels.

## Personal Baseline

The default baseline uses the preceding 28 days and excludes the target day.
At least seven valid historical values are required for a usable metric
baseline. Median, MAD, and robust z-score reduce sensitivity to outliers.

Personal baseline means comparison with the same person's recent history. It
does not imply normality relative to a clinical or population reference.

## Recovery Capacity

Recovery Capacity combines available HRV, heart-rate, respiration, sleep, and
readiness components. Higher HRV and sleep signals are treated as favorable;
higher resting heart rate and respiration are treated as pressure relative to
personal history.

These directional rules are training heuristics, not disease classifiers.

## Stress Load

Stress Load combines activity and training measures. More steps, active
calories, training duration, or training calories relative to personal history
increase load. High load is not inherently harmful; it contributes pressure to
the same-day decision-support result.

## Confidence

Confidence is implemented as a separate deterministic sidecar documented in
[CONFIDENCE_ENGINE.md](CONFIDENCE_ENGINE.md). It does not alter Recovery Engine output.

## Data Completeness

The Confidence Engine persists explicit completeness and baseline maturity
scores. Missing data lowers confidence rather than Recovery Score.

## Fallback Logic

- Usable personal baselines select the current baseline-driven path.
- Kubios morning data can select the legacy v0.2 fallback when baseline support
  is unavailable.
- Polar recovery data can select the legacy v0.3 fallback.
- Activity and training alone can select v0.1.

Fallback preserves daily availability but changes the evidence basis. Consumers
must read the stored score version.

## Missing Data Handling

- Missing component values are skipped when partial calculation is supported.
- Missing values are not automatically converted to favorable signals.
- Zero and null remain distinct.
- Insufficient baseline history triggers fallback rather than invented history.
- A complete absence of recovery signals may reduce the calculation to load
  pressure.

## Known Limitations

- Current evidence is primarily from one user.
- Baseline and weighting choices are heuristic.
- No prospective subjective outcome is integrated.
- No clinical reference standard has been used.
- Missingness may be informative.
- Vendor algorithms and source semantics can change.
- Day-level aggregation hides within-day variation.
- Fallback versions are not directly equivalent to baseline-driven results.
- The model does not account for all illness, stress, nutrition, medication,
  travel, or environmental factors.

Current operational issues are maintained in
[project_state.json](../project_state.json), not duplicated here.

## Bias and Generalization Limits

The current system is tailored to one individual's available devices, habits,
measurement schedule, and history. It cannot be assumed to generalize across
age, sex, fitness, disease, medication, device, culture, or training modality.

Personalization reduces some between-person bias but does not remove device
bias, missing-data bias, behavioral feedback, or temporal confounding.

## Safety Boundary

- The engine cannot diagnose a condition.
- It must not override pain, symptoms, or professional guidance.
- It must expose version and missing-data context.
- AI Coach cannot calculate or modify the score.
- AI Coach architecture and safety are designed but no runtime model or provider
  is implemented; `model_version` remains `unreleased`.
- Future AI input is limited to allowlisted structured facts and fails closed to
  deterministic explanation. See [AI_COACH.md](AI_COACH.md).
- Sensitive source records remain local by default.
- Unexpected or concerning symptoms require independent professional review.

## Medical Disclaimer

RHYTHMOS｜律衡 is not a medical device. Changes in RMSSD, heart rate,
respiration, sleep, or activity are nonspecific and must not be interpreted as
diagnosis of illness or injury.

## Versioning

The canonical Recovery Engine version is maintained in
[config/versions.json](../config/versions.json). Semantic changes to inputs,
directions, weights, fallback, baseline rules, or recommendation thresholds
require a new engine version and documented replay.

## Validation Status

- Unit and integration tests verify deterministic software behavior.
- Real local rows verify that the pipeline can produce stored results.
- The algorithm has not undergone prospective clinical validation.
- Predictive validity, calibration, and outcome benefit are unknown.
- Confidence deterministic behavior, persistence, and Recovery zero-regression are tested.

Passing software tests demonstrates implementation consistency, not health
validity.

## Monitoring Plan

- Track missing signal groups.
- Track fallback version frequency.
- Track baseline valid-day maturity.
- Detect unexpected score distribution shifts after version changes.
- Review disagreement with prospective subjective readiness.
- Record vendor API or firmware changes.
- Re-run historical fixtures before changing defaults.
- Preserve versioned handoffs and changelog entries.

## Future Improvements

- Evaluate independent Confidence and Data Completeness against prospective outcomes.
- Add prospective subjective outcomes.
- Establish migration versioning and historical replay tooling.
- Evaluate baseline-window sensitivity.
- Compare Polar and Kubios signal agreement.
- Add cautious, confidence-aware AI explanation after deterministic inputs are
  stable.
