# Phase / Version

> Sleep Regularity Engine 2.0 is implemented in `src/sleep_regularity.py` and
> consumed by `src/pages/1_Sleep.py` without changing the existing card layout.
> `src/sleep_adapters.py` provides the Polar canonical adapter and HealthKit
> extension boundary. The database schema remains unchanged; results are
> recomputed projections rather than persisted snapshots.

Simplified Structured Training Entry UI

- App Version: 0.31.0
- Current Phase: Simplified Structured Training Entry UI
- Phase Status: completed
- Recovery Engine Version: 1.0.0
- Baseline Engine Version: 1.0.0
- Confidence Engine Version: 1.0.0
- Database Schema Version: 0.26.0
- Schema Migration Count: 26
- Latest Schema Migration: 0.26.0
- Dashboard Version: 2.0.1
- Training Logging Version: 2.0.0
- Training Entry UI Version: 1.0.0
- Test Total: 801
- Test Passed: 801
- Test Failed: 0
- Test Success: true
- Baseline Record Count: 760
- Scored Day Count: 38
- Recovery v1 Day Count: 31
- Confidence Record Count: 38
- Latest Data Date: 2026-07-26

## Goal

Keep the existing Sleep UI unchanged while replacing the page-local sleep
regularity calculation with a versioned, device-independent algorithm.

## Status

Canonical sleep records, circular local-time statistics, robust summary
scoring, SRI selection, maturity/confidence states, separate last-night
deviation, Polar adapter coverage, and regression tests are complete.

## Files Changed

Added `src/sleep_regularity.py`, `src/sleep_adapters.py`, and
`tests/test_sleep_regularity.py`; updated the Sleep page binding, versions,
architecture, database boundary, data dictionary, testing policy, ADR,
changelog, roadmap, and release record.

## Version Changes

App 0.31.0; Sleep Regularity Engine 2.0.0; Dashboard 2.0.1; Training Logging
2.0.0; Training Entry UI 1.0.0.
Schema is 0.26.0. Recovery, Baseline, and Confidence remain 1.0.0.

## Database Migrations

None. `training_sessions`, `training_exercises`, and `training_sets` retain their
full schema. Custom catalog records use the existing table and service boundary.

## Tests

The focused Sleep Regularity suite passes 10/10 tests; the combined relevant
domain, documentation, version, release, and sleep suite passes 31/31. A full
workspace run remains affected by pre-existing database-ledger/state drift and
unrelated legacy test failures; no Sleep Regularity test fails.

## Current State Generation

The generator now records Training Entry UI version, Simple default mode,
conditional-field readiness, RPE/RIR preference support, and simplified-entry
readiness from the unified version source and tested implementation.

## System Status

Simple and RPE are the session defaults. Strength rows show load/unit/reps and
the chosen effort scale. Duration, distance/time, dance, and freeform use
conditional fields. Advanced and hidden values remain intact.

## Release Record

`releases/0.31.0.md` is the current local pre-1.0 release record.

## Real Data Verification

Browser smoke used an existing Polar session without saving test data. SQLite
integrity and foreign-key checks pass. Polar objective fields remained read-only.

## Documentation Updated

Sleep Engine, Architecture, Database, Data Dictionary, Recovery Engine,
Testing, Current State, Handoff, Roadmap, Changelog, AI Collaboration, ADR,
release note, and regression tests are updated.

## State Synchronization

`config/versions.json`, `project_state.json`, generated `CURRENT_STATE.md`, this
handoff, and the packaged App are synchronized.

## Known Issues

SRI calibration needs representative multi-day timeline fixtures; thresholds
remain product parameters and are not clinical standards. Existing upstream
respiration/Cardio Load and scheduled-run observations remain separate
monitoring items.

## Prioritized Issues

- P1: No cloud provider currently satisfies both deployment-region support and verified Zero Data Retention requirements.
- P2: Kubios calibration covers two complementary cropped layouts; complete full-screen and Results Summary usability coverage is still limited.
- P2: Some recent Polar respiration and Kubios metrics are missing.
- P2: Cardio Load remains unavailable in the latest sync and is surfaced as an optional endpoint warning.
- P2: The current Polar token predates the sports:read scope; a one-time Polar reauthorization is required before numeric sport IDs can resolve from the official catalog.
- P2: The next actual 06:00 LaunchAgent run is still pending observation.
- P3: A Git release tag cannot be created because this workspace is not a Git repository.

## Quality Gate Result

PASS. Conditional UI, preservation, localization, validation, privacy,
deterministic-engine regression, browser behavior, SQLite, and packaging pass.

## Architecture Decisions Needed

None blocking. ADR-039 fixes the complete-backend/simple-frontend boundary.

## Manual User Actions Required

No action is required. Users can select a session, add an action, and remain in
Simple mode; Advanced mode is available when professional fields are needed.

## Recommended Next Phase

Observe real training-entry use and refine catalog metadata without changing training or recovery algorithms.
