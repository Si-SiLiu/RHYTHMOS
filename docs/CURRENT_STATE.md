# Current State

Current product brand: **RHYTHMOS｜律衡** — Personal Performance OS / 个人表现与恢复系统.

> Machine-readable authority: [../project_state.json](../project_state.json)
> Version authority: [../config/versions.json](../config/versions.json)
> Generator: `.venv/bin/python scripts/update_project_state.py`

The region between the markers below is generated. Do not maintain test counts,
database counts, versions, dates, or priorities by hand.

## Sleep Regularity Engine 2.0

Implemented in `src/sleep_regularity.py` with canonical records, SRI/summary
selection, circular local-time statistics, maturity states, and separate
last-night deviation. The existing Sleep UI remains unchanged in structure.

## Today's Recovery Details Engine 1.0.0

Implemented below the raw recovery table. It uses the resolved current
measurement plus the existing 28-day median/MAD baseline contract, excludes
the current date from comparison history, requires excellent/good quality for
baseline samples, and returns explicit maturity/confidence states instead of a
new unvalidated 0–100 score. No database schema change was made.

<!-- AUTO_STATE_START -->
## Automated Project State

- App Version: 0.31.0
- Current Phase: Simplified Structured Training Entry UI
- Phase Status: completed
- Recovery Engine Version: 1.0.0
- Baseline Engine Version: 1.0.0
- Confidence Engine Version: 1.0.0
- Local Coach Engine Version: 1.0.0
- Personal Logging Version: 1.1.0
- Nutrition Logging Engine Version: 5.0.0
- Food Catalog Version: 1.0.0
- Training Logging Version: 2.0.0
- Exercise Catalog Version: 1.0.0
- Training Entry UI Version: 1.0.0
- Training Entry Default Mode: simple
- Conditional Training Fields Ready: true
- RPE RIR Preference Supported: true
- Simplified Training Entry Ready: true
- Structured Training Ready: true
- Training Session Count: 60
- Training Exercise Count: 0
- Training Set Count: 0
- Latest Training Detail Date: none
- Supplement Unit System Version: 1.0.0
- Supplement Catalog Version: 2.0.0
- Supplement Product Enrichment Version: 1.0.0
- Brand Based Supplement Logging Ready: false
- Supplement Product Count: 20
- Verified Supplement Product Count: 0
- Unverified Supplement Product Count: 19
- Supplement Ingredient Count: 0
- Latest Supplement Product Update: 2026-07-22 14:24:21
- Supplement Enrichment Runtime Status: provider_blocked
- Supplement Dynamic Units Ready: true
- Supplement Catalog Count: 10
- Simple Nutrition Input Ready: true
- Food Catalog Count: 18
- Meal Record Count: 38
- Meal Item Count: 98
- Meal Template Count: 4
- Latest Meal Date: 2026-07-26
- Manual Logging Engine Version: 1.1.0
- Data Resolution Version: 1.1.0
- Scheduler Version: 1.1.0
- Scheduled Sync Enabled: true
- Scheduled Sync Time: 23:00
- LaunchAgent Installed: true
- Latest Scheduled Sync At: 2026-07-26T14:02:02+08:00
- Latest Scheduled Sync Success: false
- Manual Activity Count: 15
- Manual Sleep Count: 1
- Manual Recovery Count: 10
- Resolved Field Count: 2623
- Manual Logging Ready: true
- Data Resolution Ready: true
- AI Context Export Version: 1.4.0
- i18n Engine Version: 1.0.0
- Kubios Screenshot Import Version: 1.2.0
- Kubios Data Model Version: 1.1.0
- Database Schema Version: 0.28.0
- Schema Migration Count: 28
- Latest Schema Migration: 0.28.0
- Dashboard Version: 2.0.1
- Supported Languages: zh-CN, zh-TW, en
- Default Language: zh-CN
- Current Language: zh-CN
- Translation Key Count: 1355
- Translation Coverage: 100%
- Language Setting Ready: true
- Kubios Screenshot Count: 1
- Kubios Screenshot Imported Count: 0
- Kubios Screenshot Review Pending Count: 1
- Latest Kubios Screenshot Import Date: 2026-07-15 06:06:31
- Local OCR Ready: true
- Real Kubios Screenshot Verified: true
- Kubios Raw Measurement Count: 0
- Kubios Normalized Count: 0
- Kubios Derived Count: 0
- Latest Kubios Measurement Date: none
- Kubios Core Metrics Ready: false
- Kubios Advanced Metrics Ready: false
- Test Total: 801
- Test Passed: 801
- Test Failed: 0
- Test Success: true
- Baseline Record Count: 760
- Scored Day Count: 38
- Recovery v1 Day Count: 31
- Confidence Record Count: 38
- Local Coach Record Count: 38
- Latest Local Coach Date: 2026-07-26
- Local Coach Ready: true
- Cloud AI Runtime Ready: false
- Body Measurement Count: 18
- Nutrition Log Count: 0
- Workout Session Count: 0
- Exercise Set Count: 0
- AI Context Export Count: 0
- Latest Body Measurement Date: 2026-07-26
- Latest Nutrition Log Date: none
- Latest Manual Workout Date: none
- Manual ChatGPT Sync Ready: true
- Automatic Cloud Sync Ready: false
- Prospective Eligible Days: 9
- Prospective Target Days: 14
- Prospective Remaining Days: 5
- Prospective Evaluation Status: collecting
- Prospective Evaluation Ready: false
- Daily Collection Status: attention_required
- Daily Collection On Track: false
- Today Collection Completed: true
- Current Collection Streak Days: 1
- Overdue Collection Days: 6
- Latest Source Data Date: 2026-07-26
- Source Data Lag Days: 0
- Database Aligned With Source: true
- Today Source Data Available: true
- Prospective Collection Blocker: none
- Latest Data Date: 2026-07-26
- Next Goal: Observe real training-entry use and refine catalog metadata without changing training or recovery algorithms.
- Updated At: 2026-07-26T15:44:00+08:00

### Prioritized Issues

| Priority | Description | Status | Owner | Target Phase |
| --- | --- | --- | --- | --- |
| P1 | No cloud provider currently satisfies both deployment-region support and verified Zero Data Retention requirements. | blocked | Product Owner / Chief Architect | Phase 12.1 AI Coach Implementation |
| P2 | Kubios calibration covers two complementary cropped layouts; complete full-screen and Results Summary usability coverage is still limited. | planned | Product Owner / Codex | Kubios Metrics Usability Evaluation |
| P2 | Some recent Polar respiration and Kubios metrics are missing. | monitoring | Product Owner | Data Quality |
| P2 | Cardio Load remains unavailable in the latest sync and is surfaced as an optional endpoint warning. | monitoring | Chief Architect | Recovery Inputs Review |
| P2 | The current Polar token predates the sports:read scope; a one-time Polar reauthorization is required before numeric sport IDs can resolve from the official catalog. | external_constraint | Product Owner | Polar Sport Catalog Authorization |
| P2 | The next actual 06:00 LaunchAgent run is still pending observation. | monitoring | Product Owner / Codex | Daily Scheduling Operations |
| P3 | A Git release tag cannot be created because this workspace is not a Git repository. | external_constraint | Codex | Future Git repository setup |
<!-- AUTO_STATE_END -->

## Current problem background

Scheduled Sync & Manual Health Logging adds an installed user LaunchAgent for
local 06:00, explicit catch-up controls, one cross-trigger Pipeline lock,
manual activity/sleep/recovery CRUD, and versioned field-level provenance.
Polar remains authoritative for overlapping measured fields; confirmed manual
activity type is the only semantic override. Dashboard, Report, and AI Context
now consume the shared resolution policy. Subjective fields do not enter the
existing deterministic health algorithms.

Internationalization v1.0 adds a local display layer for `zh-CN`, `zh-TW` and
`en`.
Dashboard, Daily Log, deterministic interpretation, reports, and AI Context
Markdown use one translation interface and saved local preference. Internal
codes, health database schema, Recovery, Baseline, Confidence, Local Coach,
Polar OAuth/API, cloud readiness, and stored results are unchanged.

Local Deterministic Coach v1.0 is now the released on-device advice path. It
reads Recovery, Confidence, Baseline, and deterministic explanations without
recalculating them, persists schema-validated advice in an independent table,
and feeds the Dashboard and matching-date Markdown report. Migration `0.4.0`
belongs to Local Coach; it does not create the future Cloud AI audit table or
change Cloud AI runtime readiness. The latest local record is historical and the
Dashboard labels it accordingly.

Project Governance Hardening formalizes one runtime state source and removes the
need to copy mutable numbers across documents. The update script derives tests
from unittest, counts from read-only SQLite queries, and versions from
`config/versions.json`.

One-Click Sync Pipeline composes the existing local stages into one safe,
selective, and resumable command. It adds operational logs and a separate sync
history store without changing the recovery database schema or engine behavior.
Reliability Hardening distinguishes required endpoint failures from optional
capability warnings, adds safe error codes, and controls final history failures.
Database Migration Ledger now persists ordered SemVer migrations and checksums;
the existing schema is registered without changing health business tables.
Recovery Confidence is now an independent deterministic sidecar with persisted
completeness, maturity, score, level, group details, and its own version. AI
Coach architecture and safety are designed as a future read-only sidecar, but no
runtime model, provider adapter, outbound transfer, database migration, or UI
exists. Cloud direction, closed outbound schema, Zero Data Retention policy,
90/365-day local retention, audit migration plan, and safety thresholds are approved.
Official provider selection is blocked because no reviewed candidate currently
satisfies both deployment-region support and verified Zero Data Retention.
The provider due-diligence package now supplies DD-01 through DD-24, binding
evidence requirements, contract red lines, a default-NO approval record, and
annual revalidation rules for safely resolving that external blocker.
The privacy threat model now covers TB-1 through TB-7, TM-01 through TM-18,
prevent/detect/respond controls, incident handling, and residual-risk rules;
provider-specific review remains required before runtime.
Machine-readable input/output JSON Schemas and prompt/output/safety contract
versions `1.0.0` now have a pure fail-closed local validator. This component has
no provider, network, database, scoring, OAuth, or Dashboard dependency.
The semantic safety gate now rejects ungrounded evidence, unsupported numbers,
diagnosis/medication directives, Confidence-language violations, and missed
urgent escalation; unsafe output becomes a local deterministic fallback.
The local synthetic preflight now runs 200 cases across eight categories for
three consecutive runs. Its latest aggregate result is 600/600 expected outcomes
with zero critical failures; it is not an exact-provider model evaluation.
The machine provider-approval record is committed in blocked/default-deny state.
Its pure local gate rejects partial, expired, drifted, non-HTTPS, single-review,
or control-incomplete approval before future health-context serialization.
The TB-2 outbound context builder now performs explicit field projection,
authority-only version injection, sensitive-question rejection, and deep-copy
isolation. Its approved entry point checks authorization before construction.
The aggregate readiness gate reports local pre-provider readiness true and
runtime readiness false, with provider approval, released model version, audit
migration, provider adapter, and exact-model evaluation as explicit blockers.

## Architecture context

The current product pipeline is:

- External data enters raw files and raw tables.
- Manual records enter dedicated tables and never overwrite raw device rows.
- Daily Metrics creates the daily analysis contract.
- Field Resolution applies canonical per-field priority and provenance.
- Baseline Engine computes personal rolling history.
- The versioned Recovery Engine produces deterministic scores.
- Confidence Engine is an implemented independent sidecar.
- Future AI Coach may consume allowlisted structured results read-only and must
  fail closed to deterministic explanations.
- Dashboard forms write only dedicated manual-log/link tables; displayed fields,
  reports, and AI Context consume resolved results.
- One-Click Sync orchestrates existing layers without owning their business logic.

Detailed boundaries are maintained in [ARCHITECTURE.md](ARCHITECTURE.md).
Current scoring semantics are maintained in
[RECOVERY_ENGINE.md](RECOVERY_ENGINE.md).

## Risks

- Kubios Screenshot Import has one real screenshot verification, while broader
  full-screen and Results Summary layout coverage remains limited.
- OCR confidence is recognition confidence only and every result requires
  explicit user review before formal import.
- Missing sleep or Kubios data reduces evidence coverage.
- Current validation is based primarily on one user's local history.
- AI Coach design is not an implemented or clinically validated model.
- OpenAI API is unsupported from the current deployment location; reviewed
  China-mainland candidates lack verified Zero Data Retention evidence.
- A passing test suite cannot establish clinical validity.
- Local health data and raw payloads must remain private.

Current issue priority, ownership, status, and target phase are generated in the
automatic region from `project_state.json`.

## Next-stage implementation considerations

Before AI Coach implementation:

1. Obtain enterprise contractual ZDR evidence from a China-mainland provider,
   or establish an eligible project in an officially supported region.
2. Verify exact provider/model/endpoint/region, disabled training and human review.
3. Back up the database and assign a new migration version above schema `0.8.0`.
4. Assign prompt, output schema, safety policy, and model versions.
5. Execute the approved privacy threat model and synthetic safety evaluation.
6. Keep Recovery, Baseline, Confidence, OAuth, raw data, and Dashboard analysis unchanged.

## Training Load & Habits baseline

The Training dashboard now uses `src.training_baseline` v1.0.0. It separates
sync/no-training/missing states, builds duration and calorie baselines from
valid training days only, and exposes seven-day load, fourteen-day distribution
and maturity progress. This is a read-only projection over the existing
`polar_training_sessions_raw` and `daily_recovery_metrics` tables; schema
version remains 0.15.0.

The current machine next goal is generated above. Long-term sequence belongs to
[ROADMAP.md](ROADMAP.md); decisions belong to
[DECISIONS.md](DECISIONS.md).

## Maintenance rule

Codex updates the human narrative when context changes. The script alone updates
the automatic region. A phase cannot close until state generation, full tests,
documentation consistency, handoff verification, and architecture checks pass.
# Alertness Probe (v1)

The former daily 3-minute PVT is replaced by a fixed 60-second Alertness Probe. A voluntary 180-second calibration protocol remains available; short, calibration, and legacy three-minute data are isolated by protocol and test mode.
