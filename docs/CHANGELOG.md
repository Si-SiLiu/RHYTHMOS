# Changelog

## Unreleased — Cognitive Training Studio MVP

- Added browser-based Focus & Alertness and Working Memory training plans with
  quick/standard modes, raw trial retention, conservative adaptive difficulty,
  interruption handling, and separate Progress Lab views.
- Added schema `0.28.0` for isolated cognitive-training sessions, task results,
  trials, progress, and preferences. Training never writes Neural Readiness or
  Recovery tables.
- Added isolated 5-second interactive practice flows for Visual Search, Memory
  Grid, Sequence Memory and N-back Lite. Practice uses dedicated protocol
  identifiers, never enters formal trial or progress records, and teaches
  1-back or 2-back according to the selected mode.

## Unreleased — Neural Readiness MVP

- Added the Neural Readiness page with four 0–10 subjective-state scales, a
  browser-timed 25-second practice and 180-second PVT-B protocol.
- Added schema `0.27.0` for idempotent assessment sessions, every raw PVT
  trial, and an independent daily neural projection. Recovery Engine and Polar
  synchronization remain unchanged.
- Added a 28-day, same-person baseline that excludes today and interrupted
  runs, along with a transparent confidence level and integrated read-only
  sleep/HRV context.

## Unreleased — Branding

### Branding

- Renamed Daily Recovery Coach to RHYTHMOS｜律衡.
- Added the positioning statement “Personal Performance OS · 个人表现与恢复系统”.
- Added the bilingual tagline “Know your state. Shape your day. / 读懂状态，掌控节奏。”
- Updated application UI, documentation, reports, and demo descriptions.
- Preserved historical references to the former product name and compatibility identifiers.
- Added Traditional Chinese (`zh-TW`) locale support across the UI, reports, and AI Context display language.

## Unreleased — Training plan and prescription layer

- Added nullable training program, day template, module block, and exercise prescription tables.
- Added a collapsed weekly plan overview without changing the existing training page order.
- Added plan-to-actual metrics and read-only historical plan snapshots.

## Unreleased — Training Load & Habits baseline

- Replaced the training baseline's zero/negative-delta ambiguity with an
  explicit status model and independent duration/calorie validity.
- Added typical training-day median/IQR ranges, rolling seven-day load,
  fourteen-day distribution, maturity progress, and collapsed raw data.

## 0.29.0 — Sleep Regularity Engine 2.0.0

- Replaced the page-local standard-deviation sleep regularity formula with the
  device-independent `SleepRegularityService`.
- Added validated canonical sleep records, circular clock statistics, robust
  summary scoring, timeline SRI selection, maturity/confidence states, and
  separate last-night schedule deviation.
- Preserved the existing sleep card count, layout, dimensions, styling, and
  navigation. Missing data no longer renders as `0 / 100`.

## 0.26.0

- Added schema 0.14.0 normalized training sessions, exercises and sets.
- Added 23-action bilingual Exercise Catalog 1.0 and Training Logging 1.0.
- Added per-session Polar-linked/manual detail editing, sport overrides, copy
  shortcuts and strength/bodyweight/time/cardio/dance validation.
- Added deterministic training summaries and AI Context Export 1.3 session data.
- Preserved Polar Raw priority and left Recovery/Baseline/Confidence unchanged.

## 0.25.0

- Replaced category-first default nutrition input with dynamic food/beverage rows.
- Added schema 0.13.0, nine-food multi-tag catalog, twelve food units, reliable
  normalization, nullable nutrient summaries, drafts, copy and templates.
- Preserved legacy meals and reused supplement dynamic units.

## 0.24.0

- Added Recovery history.
- Replaced the supplement gram-only form with catalog-driven units, optional
  active dose, timing, notes and add/remove controls.
- Added schema 0.12.0, Nutrition 3.0.0, AI Context 1.1.0 and unit-safe summaries.

## 0.23.0

- Expanded the Kubios morning recovery input and display with Stress Index,
  respiratory rate, and localized measurement quality.
- Added idempotent schema migration `0.11.0` and validated manual/raw import
  persistence for the three new fields.
- Kept Recovery Score `1.0.0`, Baseline Engine `1.0.0`, Polar API/sync core, and
  AI Coach runtime unchanged.

> Keep a Changelog style.
> The project has a local pre-1.0 release snapshot; no Git tag exists because
> this workspace is not a Git repository.

## 格式说明

- 本文件遵循 Keep a Changelog 的 Added、Changed、Fixed、Tests 分类。
- 日期使用 YYYY-MM-DD。
- Unreleased 记录已完成但尚未发布标签的变化。
- 正式版本快照保存在 releases/；Git tag 需在未来 Git 仓库中建立。
- 历史条目根据当前仓库演进整理。
- 安全修复应增加 Security 分类。
- 破坏性变化必须明确标记 Breaking。
- 纯内部重构如果不改变行为可放 Changed。
- 测试数量以全量运行输出为准。
- 不得在变更记录中写 token、secret 或 raw 数据。

## Unreleased

- Weekly training plans now support per-day sport types and action lifecycle management with name, sets, reps, load, notes, and deletion.

### Added

- Added Today's Recovery Details Engine 1.0.0 below the raw recovery table.
- Added interpretable RMSSD, resting-HR, stress-index, and respiration cards
  with personal median/range, signed percentage deviation, maturity, factors,
  conditional advice, and quality-aware confidence.
- Added regression tests for invalid/missing/low-quality data, direction rules,
  bilateral respiration, conflicting signals, and legacy record reads.

### Changed

- Recovery page version 2.0.0 / app version 0.30.0. The legacy 0–100 Recovery
  Score remains unchanged and is not used to fabricate a new daily detail score.
- Raw “今日恢复数据”, interpreted “今日恢复详情”, and long-term “个人恢复基线”
  remain separate page responsibilities.

## 0.22.0 — Personal Information & Body Goals — 2026-07-17

### Added

- Added a top-level Personal Information page with basic information, latest
  body status, and a 28-day weight trend.
- Added local profile and target forms with explicit Save Personal Information,
  Save Body Data, and Save Targets actions.
- Added schema 0.10.0 singleton tables for personal profile and optional body
  targets; age is calculated from date of birth and is never persisted.

### Changed

- App 0.22.0, Dashboard 1.3.0, Personal Logging 1.1.0, and Database Schema
  0.10.0. Existing body measurements remain the body-status trend source.
- Left-aligned all labels and values in the Personal Information basic and body
  status summaries.
- Centered the selected value in the Personal Information gender dropdown.

### Tests

- Added age-boundary, singleton upsert, goal validation, latest-body selection,
  navigation, localization, and migration coverage.

### Fixed

- Replaced the Recovery Canvas data editor with the shared centered HTML table,
  removing header icon offsets while retaining edits in an explicit form.
- Combined Nutrition's quantity and unit columns into a single gram-based dosage
  column and removed the redundant visible unit selector.
- Replaced the Nutrition Canvas editor with centered native input rows and
  centered the meal date/time labels and displayed values.

## 0.20.0 — Inline Health Editing & Meal Event Logging — 2026-07-16

### Added

- Historical exercise and sleep record tables.
- Eight normalized meal-event types with actual meal time and at most five
  items per allowed food/supply category.
- Migration 0.9.0 with editable sleep detail fields, manual morning recovery
  values, `meal_events`, and `meal_event_items`.

### Changed

- Removed the separate manual exercise and sleep panels. Current records now
  use double-click inline editing with an explicit save action.
- Recovery now exposes only measurement time, post-waking RMSSD, and
  post-waking resting heart rate; the subjective recovery panel is removed.
- Confirmed inline corrections override the corresponding displayed field while
  preserving device raw rows and provenance.
- App 0.20.0, Dashboard 1.1.0, Schema 0.9.0, Nutrition Logging 2.0.0,
  Manual Logging 1.1.0, and Data Resolution 1.1.0.

### Tests

- Added normalized meal CRUD, unit/category contracts, five-item enforcement,
  sleep/recovery correction, raw preservation, and migration coverage.

### Changed

- Replaced the former mixed Recovery Dashboard navigation with five domain-first
  top-level sections: Exercise, Sleep, Recovery, Nutrition, and System Information.
- Removed Kubios Screenshot Import, Kubios Advanced Metrics, and the legacy Daily
  Log from top-level navigation while preserving their implementation and data.
- Exercise now exposes the requested Polar session fields plus personal training
  baselines and deterministic guidance. Sleep and Recovery expose their requested
  fields, baselines, explicit missing states, and existing Local Coach guidance.
- Polar V4 Sleep synchronization now expands each available date with the
  `sleep-result`, `sleep-evaluation`, and `sleep-score` features. The import layer
  parses sleep span, asleep duration, deep/REM phases, and Nightly Recharge
  interval fields, while sleep-window continuous heart-rate samples provide
  average and minimum sleeping heart rate.
- Continuous heart rate now uses the documented V4 `/continuous-samples` endpoint
  with `heart-rate-samples`, selecting the most complete device stream per day.

### Tests

- Added read-only domain projection and exact-navigation tests. Bilingual coverage
  remains complete with no direct visible literals in Streamlit pages.
- Added Polar V4 detail-fetch, nested-import, interval-conversion, and
  sleep-window heart-rate aggregation coverage.

## 0.19.0 — Scheduled Sync & Manual Health Logging — 2026-07-16

### Added

- User-level macOS LaunchAgent scheduling at 06:00 local time, idempotent
  install/uninstall tools, trigger-aware history, explicit catch-up controls,
  and crash-safe cross-process locking.
- Manual activity, sleep, and subjective recovery CRUD in the three domain
  pages with bilingual validation and delete confirmation.
- Versioned canonical-field policies, provenance persistence, and source labels
  in Dashboard, Markdown Report, and AI Context.
- Migration 0.8.0 for manual health logs, confirmed Polar/manual links, and
  recomputable resolved fields.

### Changed

- App 0.19.0, Dashboard 1.0.0, Schema 0.8.0, Scheduler 1.0.0, Manual Logging
  Engine 1.0.0, Data Resolution 1.0.0, and Nutrition Logging Engine 1.0.0.
- The pipeline order now includes `manual-summary` before metrics and
  `resolution` after metrics. Selective maintenance runs do not suppress a
  later full daily sync.

### Fixed

- LaunchAgent startup now avoids macOS protected-folder initialization limits
  while still executing the project virtual environment and runner; standard
  streams remain local under the user Library logs directory.
- Polar GET reads use bounded retry for transient TLS/network, 429, and common
  5xx failures.
- The macOS App runtime state includes a code/locale/version fingerprint, so a
  rebuilt App no longer reuses an incompatible stale Streamlit process.

### Security

- Scheduled sync remains local and never invokes Cloud AI. The generated plist
  contains no environment variables or credentials. Notes remain excluded from
  AI Context by default, and raw source records remain unchanged.

### Tests

- Added scheduler, lock recovery, catch-up, trigger provenance, CRUD,
  field-priority, semantic separation, migration, Dashboard, Report, AI Context,
  and unchanged Recovery/Confidence regression coverage.

## 0.18.0 — Kubios HRV Data Model & Advanced Metrics v1.0 — 2026-07-15

### Added

- Versioned raw, normalized, and derived Kubios tables with source provenance,
  completeness, baseline comparisons, trends, and consecutive-day counters.
- Confirmation-only grouping for two complementary screenshots and deterministic
  CSV > reviewed screenshot > manual source selection.
- Six home core metrics, a bilingual advanced metrics page, allowlisted AI
  Context projection, core report section, and metric/data-model guides.

### Changed

- App 0.18.0, Database Schema 0.7.0, Dashboard 0.9.0, and Kubios Data Model
  1.0.0. Screenshot Import remains 1.2.0; health engines remain 1.0.0.

### Security

- Missing values remain `NULL`; formal screenshot import remains review- and
  confirmation-gated. Advanced AI export requires two confirmations and excludes
  OCR text, images, paths, raw JSON, and secrets.

### Tests

- Added 46 dedicated data-model tests covering more than 35 requested categories.
- Two local real screenshot fixtures pass 100% template detection and exact match
  across 17 visible numeric fields, but remain non-importable without a full date.

## 0.17.2 — Kubios Real Screenshot Calibration v1.2 — 2026-07-15

### Added

- Two user-approved, cropped, anonymized genuine Kubios fixtures with reviewed
  offline ground truth and aggregate-only evaluation evidence.
- Real-sample normalized ROI calibration for Readiness Summary and HRV
  Parameters, including Stress Index support in the visible details crop.

### Fixed

- Accept valid sanitized portrait crops with aspect ratios above the former
  full-phone-only limit.
- Replace placeholder anchors and regions with labels and coordinates observed
  in genuine screenshots; incomplete dates and complementary sections remain
  manual rather than being guessed or merged automatically.

### Tests

- Real sample template detection is 100%; all visible supported numeric fields
  match reviewed ground truth. Both samples still need manual completion of the
  formal import fields, which is an expected safety outcome.

## 0.17.1 — Kubios Template-Based Screenshot Parser v1.1 — 2026-07-15

### Added

- Three explicit screenshot templates with normalized field regions, local
  template detection, image quality checks, and confirmed local calibration.
- Six preprocessing candidates per field, character allowlists, fixed units,
  deterministic candidate voting, disagreement handling, and evaluation tools.
- Side-by-side region highlighting, quick manual mode, candidate consistency,
  and high-confidence prefill controls; final confirmation remains mandatory.

### Security

- No cloud OCR, network dependency, automatic health-data write, original-image
  deletion, CSV priority reduction, or recovery-formula change.

### Tests

- Synthetic fixtures pass their template and field expectations. No anonymized
  genuine screenshot is present, so no real-world accuracy is claimed.

## 0.17.0 — Kubios Screenshot Import v1.0 — 2026-07-15

### Added

- Local macOS Vision OCR Adapter, deterministic image preprocessing, Kubios
  field parser, confidence bands, per-image review, batch handling and audit.
- Migration 0.6.0 with automatic pre-migration backup, screenshot audit table,
  reviewed source metadata and persistent daily-source preference.
- Bilingual Streamlit upload/review page and `--only kubios-screenshot` sync.

### Security

- No network OCR, API key, automatic upload, complete OCR logging, Cloud AI
  call, or unconfirmed formal health-data write.
- Screenshot files remain outside AI Context and deletion requires confirmation.

### Tests

- Synthetic Vision OCR finds all required fields. Real screenshot validation
  remains a named manual action and is not claimed complete.

## 0.16.0 — Internationalization v1.0 — 2026-07-15

### Added

- Extensible local i18n engine, Simplified Chinese and English resources,
  preference storage, display formatters, localized navigation, and coverage scanner.
- Bilingual Dashboard, Daily Log, reports, deterministic Local Coach
  presentation, and AI Context Markdown.

### Changed

- App advanced to `0.16.0`, Dashboard to `0.7.0`, and i18n Engine to `1.0.0`.
- AI Context JSON adds stable `display_language` and `localized_summary`; CSV
  and internal enum schemas remain language-independent.
- Recovery, Baseline, Confidence, Local Coach, Polar, database schema, cloud
  runtime, and model behavior are unchanged.

### Tests

- Added 43 i18n tests; complete suite passes 378/378.
- Direct Streamlit user-visible literal coverage reports zero violations.

## 0.15.1 — App Icon Integration — 2026-07-15

### Added

- Canonical icon source, optimized 16–1024px PNG assets, and macOS ICNS.
- Offline idempotent icon builder and resource/fallback/application tests.
- Streamlit favicon, compact Dashboard brand mark, and signed Finder App icon.

### Changed

- App version advanced to `0.15.1`; Dashboard presentation advanced to `0.6.1`.
- Recovery, Baseline, Confidence, Local Coach, schema, cloud runtime, and model are unchanged.

## 0.15.0 — Personal Logging & AI Context Export — 2026-07-15

### Added

- Local body, nutrition, strength, Hip-Hop, juggling, session-link, template,
  and daily-summary storage through Migration `0.5.0`.
- Daily Log forms, Dashboard trends, and report summaries.
- Allowlisted JSON/Markdown/CSV manual export with Preview, dry-run, explicit
  confirmation, and no network path.

### Security

- Raw payloads, credentials, identifiers, database paths, and free-form notes
  are excluded; automatic cloud synchronization remains false.

### Added

- Project-local macOS app bundle builder for double-click Dashboard access.
- Loopback-only detached Dashboard launcher with duplicate-process reuse,
  bounded port fallback, safe error codes, and local logs.
- Launcher and app-bundle structure tests.

### Fixed

- Finder launch now uses native macOS URL opening and an ad-hoc local app
  signature instead of relying on Python browser discovery.
- Replaced the browser-only shell bundle with a native AppKit/WebKit window;
  launch failures now appear as a visible macOS alert.

## 0.14.6 — Freshness-Aware Sync — 2026-07-12

### Added

- Opt-in `--if-new-data` mode with tracked source-file snapshot comparison.
- Safe no-data step history and accurate Governance result wording.
- Tests for snapshot scope, unchanged short circuit, changed full run, and incompatible modes.

### Changed

- Ordinary sync, dry-run, resume, and selective behavior remain unchanged.

## 0.14.5 — Data Freshness Diagnostics — 2026-07-12

### Added

- Aggregate-only source/raw/metrics/Recovery/Confidence/Local Coach date diagnostics.
- Dashboard `0.5.3` freshness cards and explicit lag blocker explanation.
- Machine state source date, lag, alignment, availability, and blocker fields.

### Tests

- Seven source-alignment and local-stage lag tests; full suite expanded to 294.

## 0.14.4 — Daily Prospective Collection Monitor — 2026-07-12

### Added

- Read-only daily collection operations CLI with today, streak, gap, and late-generation status.
- Dashboard `0.5.2` daily collection cards and attention warning.
- Machine governance fields for current daily collection health.

### Tests

- Seven date-boundary tests; full suite expanded to 287 tests.

## 0.14.3 — Prospective Evaluation Pipeline Integration — 2026-07-12

### Added

- Prospective eligible-day count in Local Coach Pipeline results and sync history.
- Machine project state fields for eligible, target, remaining, status, and readiness.
- Governance and Markdown report progress summaries.

### Tests

- Full suite expanded to 280 tests with history and report progress regressions.

## 0.14.2 — Local Coach Prospective Evaluation Readiness — 2026-07-12

### Added

- Versioned 14-day prospective collection protocol and read-only progress CLI.
- Dashboard `0.5.1` progress indicator showing genuine eligible days.
- Seven tests for protocol dates, timely generation, backfill exclusion, future exclusion, and read-only behavior.

### Security

- No historical record is relabeled as fresh and no prospective sample is fabricated.

## 0.14.1 — Local Coach Longitudinal Evaluation — 2026-07-12

### Added

- Read-only longitudinal evaluation CLI and centralized evaluation authority.
- Aggregate coverage, consistency, safety, no-cloud, uniqueness, status, and transition checks.
- Seven failure-path tests and a non-sensitive real-data evaluation record.

### Changed

- App patch version advanced to `0.14.1`; runtime engine, schema, Dashboard, and model versions are unchanged.

## 0.14.0 — Local Deterministic Coach v1.0 — 2026-07-12

### Added

- On-device deterministic training, sleep, recovery, hydration, and directional nutrition advice.
- Schema-validated output, safety fallback, sanitized rationale, CLI, migration `0.4.0`, and idempotent storage.
- Pipeline `local-coach` step, Dashboard advice area, report section, and historical labeling.

### Security

- No provider, API key, outbound request, raw-health logging, or Cloud AI runtime was introduced.
- Recovery, Baseline, and Confidence formulas remain unchanged; `ai_coach_audit` was not created.

### Tests

- Full suite passes 264/264 tests.

## Unreleased — AI Coach Architecture & Safety Design

### Added

- Provider-neutral AI Coach architecture and safety authority document.
- Minimum-input allowlist, output schema, audit envelope, Confidence-aware
  language, medical boundary, injection defense, and deterministic fallback.
- ADR-020 through ADR-022 and design consistency tests.

### Changed

- ADR-005 is accepted as an architecture guardrail.
- Roadmap separates completed design from unapproved runtime implementation.
- API, architecture, versioning, testing, quality, and model documentation now
  point to the same non-runtime contract.

### Security

- No external provider, outbound health-data transfer, runtime model, database
  migration, or Dashboard feature is authorized by this design phase.

### Tests

- Added contract checks for allowlisted input, audit fields, Confidence levels,
  medical boundaries, deterministic fallback, ADRs, and roadmap status.

## Unreleased — AI Coach Cloud Governance Approval

### Added

- Closed cloud outbound schema and explicit identity/raw/history denylist.
- Zero Data Retention provider requirement and 90/365-day local retention tiers.
- Proposed `ai_coach_audit` migration `0.4.0` without executing it.
- Safety release gate with at least 200 synthetic cases across three runs.
- ADR-023 through ADR-025 and cloud-governance contract tests.

### Security

- Any critical safety failure blocks release; runtime requests remain disabled
  until provider, model, endpoint, region, and ZDR evidence are approved.

## Unreleased — Cloud Provider Selection Evidence Review

### Added

- Official-source comparison of OpenAI, Alibaba Model Studio, Baidu Qianfan, and Tencent Hunyuan/TokenHub.
- Conditional OpenAI configuration for a future supported-region, ZDR-approved organization.
- Contract-evidence and supported-region unblocking paths plus prohibited workarounds.
- ADR-026 and provider-evaluation consistency tests.

### Security

- Selection remains Blocked: no current candidate satisfies every location,
  zero-retention, no-training, and no-human-review gate with verifiable evidence.

## Unreleased — Provider Due Diligence Package

### Added

- Versioned DD-01 through DD-24 provider questionnaire and request template.
- Binding evidence bundle, conjunctive acceptance matrix, contract red lines,
  review record, annual revalidation, and safe-handling rules.
- ADR-027 and due-diligence contract tests.

### Security

- Implementation authorization defaults to NO; unknown, partial, exception, or
  expired evidence cannot pass the provider gate.

## Unreleased — AI Coach Privacy Threat Model

### Added

- Protected-asset inventory and TB-1 through TB-7 trust boundaries.
- TM-01 through TM-18 threat register covering minimization, injection, secrets,
  routing, provider drift, unsafe output, audit retention, dependencies, and consent expiry.
- Prevent/detect/respond controls, incident sequence, residual-risk policy, and verification requirements.
- ADR-028 and threat-model contract tests.

### Security

- Critical or High residual risk cannot be accepted for release; failures disable
  cloud calls while deterministic Recovery functions remain available.

## Unreleased — AI Coach Machine-Readable Contract

### Added

- Version authority for prompt, output schema, and safety policy `1.0.0`.
- Closed input and output JSON Schemas with no additional properties.
- Pure standard-library validator for range, enum, format, sensitive-text,
  unsafe-output, digest, timestamp, and version checks.
- ADR-029 and ten synthetic contract tests.

### Security

- Validation fails closed without echoing rejected values and has no network,
  database, scoring, OAuth, provider, or Dashboard dependency.

## Unreleased — AI Coach Semantic Safety & Deterministic Fallback

### Added

- Version-aligned machine-readable semantic safety policy.
- Evidence grounding, numeric-claim, diagnosis, medication, Confidence-language,
  strong-recommendation, and urgent-escalation gates.
- HMAC-SHA256 input digest and schema-valid deterministic fallback.
- ADR-030 and ten synthetic semantic/fallback tests.

### Security

- Invalid or unsafe model output is discarded and replaced locally; it is never
  partially displayed, persisted as valid AI output, or fed to deterministic engines.

## Unreleased — AI Coach Synthetic Safety Preflight

### Added

- Machine-readable evaluation thresholds and suite version `1.0.0`.
- Deterministic 200-case generator across eight safety categories.
- Three-run aggregate preflight command with critical mismatch blocking.
- ADR-031 and eight evaluation-harness tests.

### Tests

- Local preflight completed 600/600 expected pass/fallback evaluations with zero
  critical failures; this is explicitly not an exact-model evaluation.

## Unreleased — AI Coach Cloud Call Approval Gate

### Added

- Machine-readable provider approval record with blocked default and no provider fields.
- Pure local gate for exact provider/model/HTTPS endpoint/region, six privacy
  controls, dual approval, aware evidence dates, and configuration fingerprint.
- ADR-032 and ten approval-gate tests.

### Security

- Missing, partial, expired, revoked, drifted, or malformed approval fails before
  health-context serialization with a constant non-sensitive error.

## Unreleased — AI Coach Outbound Context Builder

### Added

- Provider-independent TB-2 closed projection with authoritative version injection.
- Approval-before-build entry point and deep-copy isolation.
- Raw, token, exact-metric, unknown-field, and sensitive-question rejection.
- ADR-033 and ten context-builder tests.

### Security

- Committed blocked approval stops before context construction; errors never echo
  rejected source values.

## Unreleased — AI Coach Pre-Provider Readiness Gate

### Added

- Aggregate readiness module and CLI separating local preparation from runtime release.
- Seven runtime checks and five current stable blocker codes.
- Strict exact-model evaluation artifact validation against contract versions and thresholds.
- ADR-034 and eight readiness tests.

### Security

- Current result is local-ready/runtime-blocked; aggregate output excludes provider,
  endpoint, payload, credential, and health values.

## 0.13.0 — 2026-07-10 — Recovery Confidence Implementation

### Added

- Deterministic Confidence Engine with six weighted signal groups.
- Data Completeness, Baseline Maturity, 55/45 Confidence, and four levels.
- Independent `recovery_confidence` table via migration `0.3.0`.
- Unified Confidence Engine version and One-Click Pipeline step.
- Read-only Dashboard Confidence area.

### Changed

- ADR-016 through ADR-018 move from Proposed to Completed.
- Dashboard version advances for persisted Confidence display.

### Fixed

- Missing evidence is now quantified independently instead of remaining implicit.

### Tests

- Added empty/full/partial/alternative/no-training/maturity/boundary/upsert tests.
- Verified real Recovery rows remain byte-for-byte unchanged after Confidence rebuild.

## 0.12.0 — 2026-07-10 — Database Migration Ledger

### Added

- Persistent `schema_migrations` governance table with sequence, SemVer, name,
  SHA-256 checksum, and applied timestamp.
- Immutable legacy baseline and ledger migration definitions.
- Real database backup and post-migration integrity verification.
- Project-state migration count and latest-ledger-version facts.

### Changed

- Database Schema Version advances to the ledger-backed version.
- Dashboard Data now opens existing SQLite files with `mode=ro` and cannot run migrations.
- State generation rejects config/ledger database-version drift.

### Fixed

- Database versions are no longer configuration-only assertions.
- Dashboard connections no longer call the write-side database initializer.

### Tests

- Added empty/legacy database, idempotency, checksum drift, business-row
  preservation, and true read-only Dashboard connection tests.

## 0.11.1 — 2026-07-10 — Pipeline Reliability Hardening

### Added

- Structured per-endpoint fetch status with required and optional classifications.
- Safe public pipeline error codes and allowlisted recovery instructions.
- Sync-history and Dashboard warning counts.

### Changed

- Core endpoint HTTP failures now stop Fetch and create a resumable failure.
- Continuous HR and Cardio Load unavailability now produces explicit warnings.
- Final pipeline history writes run inside controlled finalization handling.

### Fixed

- A sync can no longer appear clean when capability endpoints returned HTTP errors.
- RuntimeError-only failures now provide safe, actionable error codes.
- Final history failures now produce a standard pipeline failure summary.

### Tests

- Added structured fetch, required failure, optional warning, safe error, and
  finalization-failure regression tests.

### Latest Local Pipeline Sync

<!-- PIPELINE_RELIABILITY_SYNC_START -->
- Last validated live sync: 2026-07-10T20:35:27+08:00
- Result: success with 2 optional endpoint warnings
- Records Imported: 0
- Metrics Updated: 26
- Baselines Updated: 312
- Recovery Scores Updated: 26
- Reports Generated: 1
<!-- PIPELINE_RELIABILITY_SYNC_END -->

## 0.11.0 — 2026-07-10 — One-Click Sync Pipeline

### Added

- Single-command pipeline with token, fetch, import, metrics, baseline,
  recovery, report, and governance steps.
- Dry Run, Selective Sync, and checkpoint-based Resume.
- Safe lifecycle logging under `logs/`.
- Independent SQLite sync history with per-step and pipeline summaries.
- Dashboard System Status fields for Last Sync, Duration, Success, and Records Imported.
- Pipeline architecture, operations, and safety documentation.

### Changed

- App and Dashboard versions advance for the new orchestration and read-only status contract.
- Phase completion now includes Pipeline Validation in the Quality Gate.
- ROADMAP assigns Phase 11 to One-Click Sync and keeps AI Coach planned.

### Fixed

- Daily operation no longer requires users to manually invoke every local stage.
- Interrupted full runs can continue without repeating completed steps.
- Fixed direct-script governance imports and Resume summary aggregation after the
  first live sync exposed both orchestration edge cases.

### Tests

- Added pipeline ordering, logger, resume, Dry Run, Selective Sync, operational
  document marker, and last-sync status tests.
- Existing engine, API, import, report, and Dashboard analysis regressions remain required.

### Latest Local Pipeline Sync

<!-- PIPELINE_SYNC_START -->
- Last Pipeline Sync: 2026-07-16T16:10:03+08:00
- Result: completed through report generation
- Records Imported: 0
- Metrics Updated: 27
- Baselines Updated: 540
- Recovery Scores Updated: 27
- Reports Generated: 1
- Endpoint Warnings: 2
- Confidence Updated: 27
- Local Coach Records Updated: 27
- Prospective Eligible Days: 1 / 14
<!-- PIPELINE_SYNC_END -->

## 0.10.0 — 2026-07-10 — Governance Finalization & Release Readiness

### Added

- Automatic CURRENT_STATE generation from `project_state.json`.
- Numeric test result fields and explicit `test_success`.
- Unified version source in `config/versions.json`.
- `docs/QUALITY_GATE.md` and a reusable quality-gate template.
- Versioned release record system under `releases/`.
- Read-only Dashboard System Status and health classification.

### Changed

- Project-state test semantics now use counts instead of a boolean passed field.
- Version governance now derives runtime displays from one source.
- Phase completion workflow includes state regeneration, release records, and
  quality-gate review.
- HANDOFF contract includes version, synchronization, release, and gate results.

### Fixed

- Replaced the pending AUTO_STATE placeholder with generated state.
- Removed ambiguity from the old boolean `test_passed` value.
- Resolved unreleased/unversioned drift between state and version authority.

### Tests

- Added current-state idempotency, missing-marker, system-health, version,
  release-document, quality-gate, and documentation-consistency coverage.
- Full measured totals remain machine-generated in project state.

## 2026-07-10 — Documentation Governance

### Added

- 建立 docs/ 工程文档体系。
- 记录真实 v1.0 与 Baseline 状态。
- 为未来协作定义维护规则。
### Changed

- README 增加文档索引。
### Fixed

- 纠正旧状态快照与当前仓库事实的差异。
### Tests

- 文档链接、行数与业务文件零修改检查。

## 2026-07-10 — Score Explanation

### Added

- 新增确定性评分解释模块。
- Dashboard 增加有利因素、压力与缺口。
### Changed

- Dashboard 改为读取全部最新基线。
### Fixed

- 修复 Streamlit 测试环境导入路径。
- 更新已弃用图表宽度参数。
### Tests

- 新增解释测试，测试总数达到 96。

## 2026-07-10 — Recovery Engine v1.0

### Added

- 个人基线驱动评分。
- 保留 v0.1/v0.2/v0.3 fallback。
### Changed

- 评分重建前刷新 baseline。
### Fixed

- 修复历史不足时的版本选择。
### Tests

- 新增 v1.0 方向和重建测试。

## 2026-07-10 — Baseline Engine

### Added

- baseline_metrics 表。
- 28 天窗口、7 天门槛、MAD、批量重算。
- Dashboard 个人基线区域。
### Changed

- 配置集中到 baseline_config.json。
### Fixed

- 处理 MAD=0、std=0、ISO duration 和无效数值。
### Tests

- 新增 baseline 与配置测试。

## 2026-07-10 — Streamlit Dashboard

### Added

- 最新状态、完整性、7/30 天趋势、评分版本。
### Changed

- 查询 SQL 移到 dashboard_data。
### Fixed

- 缺失睡眠与 HRV 时显示暂无数据。
### Tests

- 新增空库、缺失值和 duration 测试。

## 2026-07-10 — Polar API Expansion

### Added

- Polar v4 training、sleep、Nightly Recharge、cardio load、continuous HR。
### Changed

- 客户端支持 v3/v4 base URL 与 refresh。
### Fixed

- 修复训练数据抓取路径和 scope。
### Tests

- 新增 API 客户端与抓取测试。

## 2026-07-10 — Kubios Import

### Added

- CSV 字段别名识别、raw upsert、日指标同步。
### Changed

- 支持 UTF-8 BOM 与中英文日期列名。
### Fixed

- 无效数字和缺少 date 提供安全处理。
### Tests

- 新增 fixture 与重复导入测试。

## 2026-07-10 — Daily Recovery Report

### Added

- 指定日期和最新日期 Markdown 报告。
### Changed

- 报告包含评分版本。
### Fixed

- 缺失字段使用安全显示。
### Tests

- 新增渲染与保存测试。

## 2026-07-10 — Recovery Score v0.x

### Added

- 负荷评分、Kubios v0.2、Polar 夜间 v0.3。
### Changed

- recommendation 细分为四档。
### Fixed

- 缺失输入采用 fallback。
### Tests

- 新增各版本边界测试。

## 2026-07-10 — Daily Metrics

### Added

- activity、training、sleep、nightly 按日期合并。
### Changed

- duration 统一聚合为 ISO 8601。
### Fixed

- 重复日期采用 upsert。
### Tests

- 新增汇总和重复运行测试。

## 2026-07-10 — SQLite Raw Import

### Added

- raw 表、结构化字段、时间戳和唯一键。
### Changed

- Polar JSON 导入支持多种容器键。
### Fixed

- 修复 external_id 和日期兼容映射。
### Tests

- 新增数据库与导入测试。

## 2026-07-10 — Polar OAuth and Fetch

### Added

- OAuth、token 文件、Bearer GET、raw JSON 保存。
### Changed

- 成功 scope 扩展到当前数据权限。
### Fixed

- 修复 invalid_scope 与 token 过期处理。
### Tests

- 新增 OAuth、client 和 fetch 测试。

## Unreleased

### Added

- 工程文档体系。
- 项目、路线图、当前状态与架构文档。
- 数据库、数据字典和 Recovery Engine 文档。
- 协作、编码、测试、API 与版本规范。
- 机器可读的 `project_state.json` 状态契约。
- 从代码、SQLite 和 unittest 生成状态的更新脚本。
- 项目状态 schema、计数、一致性和敏感字段测试。
- 标准化且机器可验证的 `docs/HANDOFF.md`。
- AI 协作、架构边界和权威来源验证器。
- 单命令阶段收尾脚本。
- Recovery Confidence 与 Data Completeness 设计文档。
- Proposed ADR-016 至 ADR-018。
- Confidence Design 与 Implementation 路线图阶段。

### Changed

- README 增加 Project Documentation 导航。
- 文档改为权威来源加交叉链接，不再追求固定行数。
- CURRENT_STATE 使用机器可校验的稳定标记块。
- AI 协作增加阶段完成门槛和标准交接摘要。
- 标准交接由文档约定升级为可执行验证契约。
- 架构图增加独立 Confidence Engine 旁路，不改变 Recovery Engine。

### Fixed

- 文档现状以代码和数据库核验结果为准。
- 删除多个文档中的动态测试与数据库计数副本。

### Tests

- 不修改业务代码，因此继续运行现有测试确认零回归。
- 检查每份文档不是空文件。
- 检查文档链接目标存在。
- 验证 project_state 与真实数据库和 CURRENT_STATE 一致。
- 验证交接章节、动态数字、敏感字段和跨层 import 禁令。

## 维护规则

- 每次合并面向用户的能力时更新 Added。
- 每次改变已有行为时更新 Changed。
- 每次修复可复现缺陷时更新 Fixed。
- 每次测试数量或策略变化时更新 Tests。
- 安全修复使用独立 Security 分类。
- 不兼容变化明确标记 Breaking。
- 正式发布标题使用版本号和发布日期。
- 未发布但已完成的变化保留在 Unreleased。
- 发布后将 Unreleased 条目移动到对应版本。
- 历史条目保留原始版本语境，不用当前状态覆盖。
- Recovery Engine 变化必须写明 score_version。
- 数据库变化必须写明 schema migration 影响。
- Dashboard 变化必须说明是否影响数据读取契约。
- 文档变化不应冒充业务功能变化。
- 任何条目不得包含 token、secret 或 raw_json 敏感内容。
# 0.28.0 — 2026-07-18

- Added default Simple and optional Advanced structured-training entry modes.
- Added measurement-mode conditional fields and RPE/RIR/none preference.
- Added catalog auto-fill and confirmed custom exercise library saves.
- Moved batch, history, reorder, copy, and confirmed deletes into compact actions.
- Preserved schema 0.15.0 and all deterministic engine and Polar boundaries.

# 0.27.0 — 2026-07-18

- Replaced repeated daily active-ingredient input with brand/product intake.
- Added versioned supplement products, ingredients, intakes, favorites, sources
  and candidates through schema migration 0.15.0.
- Added confirmed-only ingredient calculation, provider-gated candidate
  enrichment and medication separation.
- Preserved legacy supplement rows/active fields and unchanged deterministic
  Recovery, Baseline, Confidence and Polar behavior.
# Alertness Probe v1

- Replaced the daily 3-minute PVT with the fixed 60-second Alertness Probe.
- Retained a voluntary 3-minute Calibration PVT with an independent baseline and legacy-data compatibility.
