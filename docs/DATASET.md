# Dataset Documentation

## Scope

This document describes the local dataset used by RHYTHMOS｜律衡. It does
not publish the data itself. Machine-readable counts and coverage are generated
in [project_state.json](../project_state.json).

## Data sources

### Polar API v4 and v3 compatibility paths

The project stores locally fetched training sessions, activity, sleep, Nightly
Recharge, cardio load, and continuous heart-rate responses when authorized and
available. Account metadata may also be fetched but is not a recovery feature.

### Polar Flow export

Locally exported files can be collected and deduplicated by file hash. File
collection does not imply that every export type has been parsed into analysis
fields.

### Kubios CSV

Kubios Morning HRV rows can be imported from a local CSV. The importer supports
header aliases for date, measurement time, RMSSD, mean heart rate, and
readiness. Current availability is reflected by generated table counts.

## Data range

The generated state records:

- `earliest_data_date`.
- `latest_data_date`.
- `daily_metric_day_count`.
- Per-table record counts.

These values must not be copied manually into this document. Run:

```bash
.venv/bin/python scripts/update_project_state.py
```

## Current record counts

The canonical counts are `table_record_counts` in `project_state.json`.
Important summaries include baseline records, scored days, and Recovery v1
days. This document intentionally contains no mutable numeric snapshot.

## Granularity

| Dataset | Grain |
| --- | --- |
| Polar daily activity raw | Source activity record per date |
| Polar training raw | Training session |
| Polar sleep raw | Sleep result per date |
| Polar Nightly raw | Nightly recovery result per date |
| Polar cardio load raw | Source load record per date |
| Polar continuous HR raw | Source response per date or range |
| Kubios morning raw | Morning measurement |
| Daily recovery metrics | One row per date |
| Baseline metrics | One date, metric, and window |
| Recovery scores | One current score row per date |

## Raw and analysis relationships

```text
Polar/Kubios source
→ raw files
→ source-specific raw tables
→ daily_recovery_metrics
→ baseline_metrics
→ recovery_scores
```

Raw JSON preserves source evidence. Parsed raw columns support common queries.
Daily Metrics standardizes dates and aggregates training. Baselines and scores
are derived and version-dependent.

## Missing data

Missingness can arise from authorization, device wear, measurement behavior,
API retention, endpoint availability, export timing, parser support, or a true
absence of an event such as no training.

Null means unavailable or unknown. Zero means a recorded zero where valid.
Missing sleep, HRV, or training fields must not be silently imputed as favorable
recovery.

## Data quality issues

- Multiple external schemas and aliases require defensive parsing.
- Source values may change with vendor firmware or algorithms.
- Measurement windows differ across nighttime and morning sources.
- No-training days must be distinguished from unknown training data.
- Early dates lack mature rolling baselines.
- Outliers may be measurement artifacts or real events.
- Current data are dominated by one user and short coverage.

Operational issues and priorities are maintained in `project_state.json`.

## Deduplication

Polar and Kubios raw tables use source, external ID, and date uniqueness. Import
uses upsert so reprocessing updates the same business record. Daily metrics and
scores use date uniqueness. Baselines use date, metric name, and window.

Polar Flow files use SHA-256 uniqueness. A duplicate hash is not collected as a
new file.

## Time zones

Daily analysis uses `YYYY-MM-DD`. Source timestamps are retained as text where
available. Current code does not provide a complete cross-source timezone
normalization framework. Future multi-timezone use must define local-day
assignment, daylight-saving transitions, and travel handling before analysis.

## Unit standardization

- RMSSD: milliseconds.
- Heart rate: beats per minute.
- Activity and training energy: kilocalories.
- Steps: count.
- Raw durations: ISO 8601 when available.
- Baseline sleep duration: hours.
- Baseline training duration: minutes.

Field-level definitions belong to
[DATA_DICTIONARY.md](DATA_DICTIONARY.md).

## Update methods

- Polar data: explicit local fetch command.
- Polar raw import: explicit import command.
- Kubios: explicit CSV import.
- Daily metrics: rebuild command.
- Baselines and scores: deterministic rebuild commands.
- Project dataset summary: `scripts/update_project_state.py`.

There is no complete one-command data sync pipeline yet. Governance phase
finalization is separate from source-data synchronization.

## Privacy and local storage

The SQLite database, raw files, export files, and measurement CSVs contain
personal health and activity data. They remain local by default. Dashboard and
reports must not expose raw payloads or credentials.

## Repository exclusion rules

Do not commit or upload:

- `.env`.
- OAuth token files.
- The real SQLite database.
- Raw Polar JSON.
- Polar Flow exports.
- Kubios measurement CSVs.
- Reports containing personal details unless explicitly sanitized.

Tests must use fictional fixtures and temporary databases.

## Future dataset versioning

A future dataset release requires a versioned, de-identified export contract.
The version must identify schema, inclusion window, source types, transformation
code, exclusion rules, and checksums. Raw personal files must not be treated as
a publishable dataset.

Database Schema Version describes local structure; it is not automatically a
dataset release version. Research snapshots should record both schema and code
versions.

## Use limitations

The dataset cannot support clinical diagnosis or population inference. It is
currently suitable for local functionality testing, transparent N-of-1
exploration, and future hypothesis generation with explicit uncertainty.
