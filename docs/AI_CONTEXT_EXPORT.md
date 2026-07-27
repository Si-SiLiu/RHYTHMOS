# AI Context Export v1.4

## Structured training summaries

`training_summary.sessions` contains completed session-level objective metrics
and deterministic exercise/set aggregates. It excludes Polar raw payloads,
exercise/set rows and every free-text note. AI cannot write Polar data or change
Recovery Score, and this phase invokes no cloud model.

## Structured meal summaries

`nutrition_summary.meals` exports completed meals as meal type, actual time,
food/identified counts, nullable nutrient totals and data completeness. It does
not export food rows, catalog IDs, brands, cooking methods or free-text notes.

## Structured supplements

`nutrition_summary.supplements` preserves brand, product, quantity, unit,
verification status and product kind. Only confirmed/verified products with an
exact serving-unit match include calculated active/nutrient ingredients.
Unconfirmed products never expose guessed ingredients. Notes, packaging images
and product source payloads remain excluded; medications cannot authorize dose
advice.

## Kubios projection

The default export contains the reviewed core Kubios projection, deterministic
baseline/trend fields, source type, completeness, and quality/reliability status.
Raw advanced fields are excluded unless the user enables advanced Kubios export
and completes both confirmation steps. Even then, OCR text, screenshots, file
paths, group IDs, raw JSON, secrets, and unrestricted health payloads remain
outside the allowlist. JSON, CSV, and Markdown previews use the same projection.

Kubios screenshot files, local paths, OCR text, audit rows and confidence values
are excluded from AI Context Export. Only downstream health fields that have
already been explicitly reviewed and imported can appear through the existing
allowlisted daily-metric schema.

AI Context Export creates a schema-validated, allowlisted local projection for
manual review. It supports JSON, Markdown, and summary CSV for 1, 7, 14, or 30
days. Preview/dry-run writes nothing; confirmed export writes only under
`exports/ai_context/` and never uploads.

Identity, identifiers, tokens, secrets, raw Polar payloads, raw time series,
database paths, explanation JSON, and free-form notes are excluded. Missing
values remain `null` and measured/estimated/missing status is explicit.

JSON uses a stable English schema and enum codes in every interface language;
`display_language` and `localized_summary` make presentation explicit.
Markdown follows `zh-CN`, `zh-TW` or `en`. CSV keeps stable English flattened headers by
default so language switching does not break downstream machine processing.

Resolved activity, sleep, and recovery metrics include `value`, `value_source`,
`is_fallback`, `is_manual_override`, and `data_date`. Manual values are never
labelled as device measurements. Kubios morning and Polar nightly fields remain
separate. Free-text notes continue to be excluded by the allowlist unless a
future separately approved contract adds them.
