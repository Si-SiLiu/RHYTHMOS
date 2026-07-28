# Training Engine

## Training Load & Habits baseline v1.0.0

The training projection is implemented by `src.training_baseline` and exposed
through `get_training_baseline_view` / `build_training_baseline_view`. It reads
`polar_training_sessions_raw` without converting missing fields to zero and
uses `sync_history` plus `daily_recovery_metrics` to classify data coverage.

Typical training-day baselines use the median and inclusive IQR of valid
training dates in a 28-day window. Duration and calories have independent
valid-day counts. Maturity is `collecting` below 5 valid days, `provisional`
at 5, `reliable` at 10, and `stable` at 20. Rolling seven-day load and a
fourteen-day distribution are separate from single-day comparison.

Polar training calories are analysis-only and are not added to Polar daily
total calories a second time.

## Training plan layer

Schema `0.26.0` adds nullable plan relationships around the existing actual
training tables: `training_programs`, `training_day_templates`,
`training_blocks`, and `training_prescriptions`. Polar sessions and legacy
manual sessions remain valid without a plan link. Plan rows represent intent;
session exercises and sets represent actual completion. HPRS adjustments are
stored as immutable prescription snapshots so the original plan remains
auditable. Each weekly day template also stores its selected sport type, while
prescriptions support the per-day action lifecycle and structured fields for
sets, reps, load, and notes.
