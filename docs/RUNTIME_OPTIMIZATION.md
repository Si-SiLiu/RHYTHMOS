# Runtime optimization — 2026-09-07

## Follow-up: batch history loading

Meal and training history services now read parent records and their children
in batches of at most 400 records. A meal-list call loads the food/OCR catalog
once. Training lists batch-load current Polar values, exercises and sets.
Single-record and batch paths share presentation assembly. Ordering, soft
deletion, unknown nutrients, legacy name resolution and Polar authority are
preserved. Each call reads fresh data; no cross-session health-data cache is
introduced.

Read-only measurements against the existing local database:

| History read | Before | After | SELECTs before / after |
| --- | ---: | ---: | ---: |
| 117 meals | 53.4 ms | 8.6 ms | 586 / 5 |
| 100 training sessions | 9.1 ms | 5.7 ms | 386 / 4 |

Both complete returned lists matched single-record loading field for field.
These measurements cover data loading, not complete page rendering. Additional
synthetic tests cover multiple batches, supplements, legacy food names, deleted
children, empty lists, limits, and current Polar source updates.

The existing pages, controls, scoring formulas, sync schedule and provider
behavior are preserved. Changes are limited to `src/db.py`, `src/baseline.py`
and `src/dashboard_launcher.py`, with regression tests and documentation.

## Changes

- Current database connections validate schema metadata and compatibility
  requirements with reads before deciding whether initialization is necessary.
  This removes repeated DDL and repair writes from ordinary page connections.
  Pending migrations still use the existing backup path; failures close the
  connection. No schema migration is introduced.
- Full baseline rebuilding normalizes one source series per metric and selects
  each historical window with binary search. It preserves current-day exclusion,
  primary measurement selection, latest-record behavior, formulas and per-day
  commits. Source series are discarded after the run.
- Launcher fingerprints include all component frontend directories, so PVT and
  calibration asset updates invalidate a stale local dashboard process too.

## Measurements and verification

Local synthetic benchmarks, not end-to-end application latency guarantees:

| Operation | Before | After |
| --- | ---: | ---: |
| Open/close 50 current database connections | 105 ms | 62 ms |
| Rebuild 365 days × 20 baseline metrics, in-memory SQLite | 272 ms | 106 ms |
| Source SELECTs in that baseline rebuild | 14,600 | 20 |

The focused regression command passed all 143 tests:

```sh
.venv/bin/python -m unittest tests.test_runtime_optimization tests.test_db tests.test_baseline tests.test_baseline_config tests.test_dashboard_launcher tests.test_recovery_score tests.test_recovery_score_v10 tests.test_database_version_consistency tests.test_sync_pipeline tests.test_dashboard_data tests.test_domain_dashboard tests.test_kubios_data_model
```

Full discovery ran 1,090 tests with 9 failures and 9 errors. Repeating the
existing suite with the original database connection and bulk-baseline
implementations restored in memory reproduced 9 failures and 9 errors across
1,085 existing tests (the five new regression tests were excluded from that
comparison). Outstanding failures include stale state/release/governance
documents, outdated UI and resume assertions, planner demo checks, a training
test import, and icon/LaunchAgent environment limitations. This is not a clean
repository-wide release gate.

The canonical `dist/RHYTHMOS.app` loads Python from this workspace. Reopening
the application activates the new source through the existing launcher. No
native compilation, replacement application, production migration, live sync,
or health-data cleanup was performed as part of this optimization.
