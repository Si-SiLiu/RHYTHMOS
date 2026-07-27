# Personal Logging v1.0

Kubios Screenshot Import is a separate reviewed ingestion path. It does not
read personal notes, photo-library contents, nutrition logs or manual workout
records, and it does not alter Personal Logging storage semantics.

Personal Logging is a local-only input layer for body measurements, nutrition,
strength sets, Hip-Hop, juggling, other sessions, and subjective RPE/energy.
All writes pass through `src/personal_logging/storage.py`; missing nutrition is
stored as `NULL`, never invented as zero. Daily summaries are idempotent.

Polar sessions remain the physiological-load/time authority. Manual sessions
remain the exercise/set/weight/RPE authority. They are displayed in parallel
and are never automatically added together. Suggested links require explicit
user confirmation.

BMI 仅为一般性体重身高指标，不能单独判断健康或身体成分。

The Daily Log supports `zh-CN`, `zh-TW` and `en`. Meal and session selectors display
localized names while storage continues to use stable codes such as
`breakfast`, `strength`, and `hiphop`. Switching language does not clear form
state or alter stored rows.

Nutrition Logging 2.0 uses normalized `meal_events` and `meal_event_items`. It
supports breakfast, morning snack, lunch, afternoon snack, dinner, training
fuel, bedtime fuel, and free snack with actual meal time. Every allowed category
has positions 1–5; food name, quantity, and `g`/`ml` unit are validated locally.

Manual Health Logging 1.1.0 replaces separate forms with inline field
correction. Confirmed corrections preserve raw device records and provenance.
See `MANUAL_HEALTH_LOGGING.md`.
