# RHYTHMOS｜律衡

**Personal Performance OS · 个人表现与恢复系统**

> Know your state. Shape your day.
> 读懂状态，掌控节奏。

RHYTHMOS（律衡）是一套面向高表现生活人群的个人表现与恢复系统。它通过整合睡眠、心率变异性、静息心率、训练负荷、主观疲劳及生活行为等数据，帮助用户理解当前状态，并为当天的训练、工作与恢复安排提供参考。

RHYTHMOS is a personal performance and recovery system designed for high-performing individuals. It integrates sleep, heart rate variability, resting heart rate, training load, subjective fatigue, and lifestyle data to help users understand their current state and make better decisions about training, work, and recovery.

The app sidebar has six top-level sections:
**Training**, **Sleep**, **Recovery**, **Nutrition**, **My Profile**, and **Settings**.
The former Kubios Screenshot Import and Kubios Advanced Metrics entries are no
longer top-level navigation items; their local implementation and stored data
remain preserved for compatibility.

Structured Training Details 2.0 links each Polar session to independent manual
exercise and set details without overwriting Polar time, heart rate, calories,
distance or raw sport data. It supports manual-only sessions, sport overrides,
strength/bodyweight/duration/cardio/dance modes, RPE/RIR/rest, copy shortcuts and
deterministic summaries. See [Training Logging](docs/TRAINING_LOGGING.md) and
[Exercise Catalog](docs/EXERCISE_CATALOG.md).

Training Entry UI 1.0 defaults to Simple mode: strength sets show only load,
unit, repetitions, and the selected RPE/RIR preference. Advanced fields remain
available conditionally and are never deleted when hidden. Catalog actions fill
metadata automatically; custom actions enter the global library only after
explicit confirmation.

Kubios HRV Data Model 1.0 adds local raw/normalized/derived storage, reviewed
source selection, six core Dashboard metrics, and a dedicated **Kubios Advanced
Metrics** page. Missing values remain unavailable rather than estimated. See
[Kubios Data Model](docs/KUBIOS_DATA_MODEL.md) and
[Kubios Metrics Guide](docs/KUBIOS_METRICS_GUIDE.md).

Training uses a per-session structured editor for exercises and sets, while
Sleep retains its historical record view and supported correction workflow.
Recovery records post-waking RMSSD, resting heart rate, stress index,
respiratory rate, and measurement quality. Confirmed corrections preserve the
original Polar/Kubios raw row and field provenance. Nutrition records eight
meal-event types, actual meal time, and structured food details. System
Information contains versions, data freshness, integrity, scheduled-sync
configuration, catch-up controls, and test status.

Local-first recovery analytics with Polar ingestion, deterministic scoring,
Confidence, and an on-device deterministic Daily Coach.

## Setup

```bash
cd '/Users/liuxi/Documents/Daily·Recovery·Coach'
.venv/bin/python -m pip install -r requirements.txt
```

Create `.env` from `.env.example` and keep real credentials only in `.env`:

```bash
POLAR_CLIENT_ID=your-client-id
POLAR_CLIENT_SECRET=your-client-secret
POLAR_REDIRECT_URI=http://localhost:5000/oauth2_callback
FLASK_SECRET_KEY=replace-with-a-local-random-secret
```

## Run

```bash
source .venv/bin/activate
python src/polar_oauth.py
```

Open `http://127.0.0.1:5000`.

## Language / 语言

Use the sidebar language selector to switch immediately between 简体中文、繁體中文
and English. The preference is saved locally and reused by Dashboard, Daily Log,
Markdown reports, and AI Context Markdown. Health data, internal enum codes,
CSV headers, and calculation results do not change. See
[Internationalization](docs/INTERNATIONALIZATION.md).

## Simple nutrition logging

Nutrition defaults to one searchable food/beverage row. Record the food, raw
quantity, controlled unit and actual meal time; add rows only when needed.
Optional details, drafts, recent foods, favorites, meal copy and templates are
available without carbohydrate/protein/fat category entry. Unknown foods save
without guessed nutrition. Supplements record brand, product, quantity and unit;
effective ingredients come from confirmed versioned product profiles rather
than repeated daily manual entry.

## Double-click Dashboard on macOS

### Application icon

The canonical RHYTHMOS｜律衡 icon source is `assets/app_icon.png` (the approved
blue symbol). The former wordmark is preserved at
`assets/app_icon_daily_recovery_coach_legacy.png`. Rebuild all optimized PNG
and macOS ICNS assets offline with:

```bash
.venv/bin/python scripts/build_app_icon.py
.venv/bin/python scripts/build_macos_app.py
```

To replace the icon later, preserve the current source, put a new square
RGB/RGBA PNG at `assets/app_icon.png`, rerun both commands, and verify the
Dashboard and Finder icon before release.

The native startup page uses the transparent `assets/startup_splash.png` brand
art. Its WebKit page uses the system `prefers-color-scheme` setting, so the
surrounding background and loading text follow macOS Light/Dark mode.

Build the local app bundle once:

```bash
.venv/bin/python scripts/build_macos_app.py
```

Then double-click `dist/RHYTHMOS.app`. Its Finder display name is
RHYTHMOS｜律衡. The previous `dist/Daily Recovery Coach.app` bundle is retained
as a legacy rollback artifact until existing launch paths and shortcuts have
been manually verified. It opens a native macOS
window containing the local Streamlit App. The local service
binds to loopback only; repeated launches reuse a matching runtime, while a
code/locale/version change safely restarts an owned stale service. Structured
Pipeline and Dashboard logs stay under `logs/`; LaunchAgent standard streams
stay local under `~/Library/Logs/Daily Recovery Coach/` for LaunchAgent
compatibility.

Use `⌘M` to minimize, `⌘W` to close the current Dashboard window, and `⌘Q` to quit the app.

## Scheduled Polar sync

Install the idempotent user LaunchAgent after reviewing a dry run:

```bash
.venv/bin/python scripts/install_daily_sync_launch_agent.py --dry-run
.venv/bin/python scripts/install_daily_sync_launch_agent.py
.venv/bin/python scripts/run_scheduled_sync.py --dry-run
```

The LaunchAgent runs in the Mac's system time zone every two hours until 22:00.
Scheduled runs refresh Polar activity data (including activity and total
consumption); training data is refreshed on the four-hour cadence. No scheduled
refresh runs after 23:00. Sleep data is refreshed only by the post-recovery-save
sync, not by the periodic job. Manual, scheduled, and catch-up triggers share
one pipeline and one crash-safe lock. See [Scheduled Polar Sync](docs/DAILY_SCHEDULED_SYNC.md).

## Local Deterministic Coach

## Daily Log and manual ChatGPT context

The legacy Daily Log implementation remains available internally for body and
manual-training compatibility, while the top-level domain pages own inline
health correction and normalized meal-event logging. AI Context previews
a local JSON/Markdown/CSV package and writes only after confirmation. Nothing is
uploaded and no API key is accepted. See
[Manual Health Logging](docs/MANUAL_HEALTH_LOGGING.md) and
[Data Source Resolution](docs/DATA_SOURCE_RESOLUTION.md).

Generate local advice without any cloud AI call:

```bash
.venv/bin/python -m src.local_coach.engine
.venv/bin/python -m src.local_coach.engine --all
.venv/bin/python -m src.local_coach.engine --dry-run
.venv/bin/python -m src.sync_pipeline --only local-coach
.venv/bin/python -m src.local_coach.evaluation --require-pass
.venv/bin/python -m src.local_coach.prospective
.venv/bin/python -m src.local_coach.collection
.venv/bin/python -m src.data_freshness
.venv/bin/python -m src.sync_pipeline --if-new-data
```

The pipeline runs Local Coach after Confidence and before Report. The Dashboard
at `http://localhost:8501/` labels local advice and Cloud AI status separately.
See [Local Coach](docs/LOCAL_COACH.md).

## Fetch Polar data

After OAuth succeeds and `data/polar_tokens.json` exists:

```bash
source .venv/bin/activate
python src/polar_fetch.py
```

Fetched raw JSON files are saved under `data/raw/`:

- `polar_user_account.json`
- `polar_training_sessions.json`
- `polar_daily_activity.json`

Useful options:

```bash
python src/polar_fetch.py --from 2026-07-01 --to 2026-07-10
python src/polar_fetch.py --activity-steps --activity-zones
python src/polar_fetch.py --exercise-samples --exercise-zones --exercise-route
```

If user account info reports a consent error, visit `https://account.polar.com`
and accept required Polar consents. Training sessions and daily activity are
still fetched independently when those endpoints are available.

## Baseline Engine

Baseline Engine builds personal rolling baselines from `daily_recovery_metrics`.
It compares each day only with the user's own recent history, not with population
thresholds. The default rolling window is 28 days, and at least 7 valid historical
days are required before a metric is marked usable.

The baseline configuration lives in `config/baseline_config.json`. It currently
covers HRV, resting heart rate, respiration rate, Kubios readiness, sleep,
activity calories, training duration, training calories, and steps. Duration
metrics are converted to consistent numeric units before calculation.

Run the baseline rebuild:

```bash
source .venv/bin/activate
python src/baseline.py
```

The results are stored in the `baseline_metrics` table in `data/recovery.db`.
These values are training decision support only and are not medical diagnosis.

## Recovery Engine

The current Recovery Engine uses personal rolling baselines when enough history is
available. HRV, sleep, readiness, resting heart rate, activity load, and training
load are scored against the user's own 28-day baseline. If a metric does not yet
have at least 7 valid historical days, the score falls back to the earlier static
rules so daily scoring can continue.

Runtime component versions are never maintained in this README. Read the unified
version source as described in [View current versions](#view-current-versions).

Rebuild recovery scores:

```bash
source .venv/bin/activate
python src/recovery_score.py
```

This command also refreshes `baseline_metrics` before writing `recovery_scores`.

## Score Explanation

The Dashboard includes a deterministic score explanation for the latest day. It
separates personal-baseline changes into favorable factors, recovery pressure,
and data gaps. Explanations use only values already stored in SQLite and do not
change the Recovery Engine formula or call an AI service.

Start the Dashboard:

```bash
source .venv/bin/activate
streamlit run src/dashboard.py
```

## Recovery Confidence

Recovery Confidence independently measures current-day data completeness and
personal-baseline maturity. It does not change Recovery Score or recommendation.

```bash
.venv/bin/python src/recovery_confidence.py
```

Results are stored in `recovery_confidence` and displayed read-only in Dashboard.

The page includes a read-only System Status area. It reads generated project
state, the unified version source, and the existing SQLite query layer; it does
not run tests or access credentials.

## Update project state

After implementation and an initial full test run, regenerate machine and human
state together:

```bash
.venv/bin/python scripts/update_project_state.py
```

The command runs the complete unittest suite, reads aggregate SQLite facts in
read-only mode, updates `project_state.json`, and replaces only the marked
generated region of `docs/CURRENT_STATE.md`. If measured facts are unchanged,
repeated execution is byte-stable.

## One Click Sync

After completing the existing Polar OAuth flow once, run the entire local daily
pipeline with one command:

```bash
.venv/bin/python src/sync_pipeline.py
```

It checks/refreshes authorization, fetches supported Polar datasets, imports raw
data and optional Kubios CSV files, rebuilds Daily Metrics, Baseline and Recovery,
rebuilds independent Confidence, generates the latest report, and refreshes governed project state. The existing
engine formulas and Dashboard analysis are unchanged.

Safe validation without database or report writes:

```bash
.venv/bin/python src/sync_pipeline.py --dry-run
```

Run one step or resume the latest interrupted run:

```bash
.venv/bin/python src/sync_pipeline.py --only fetch
.venv/bin/python src/sync_pipeline.py --only report
.venv/bin/python src/sync_pipeline.py --only recovery
.venv/bin/python src/sync_pipeline.py --resume
```

Lifecycle logs are written to `logs/sync.log`. Resume checkpoints and Dashboard
Last Sync facts use the separate `data/sync_history.db`; `recovery.db` schema is
not changed. See [Sync Pipeline](docs/SYNC_PIPELINE.md) for step and safety rules.

Core Polar endpoint failures stop the run with a safe error code. Sleep dates are
expanded through Polar V4 detail features, and continuous heart rate is fetched
from `/continuous-samples` for sleep-window aggregation. Cardio Load remains an
optional capability endpoint and appears as a warning when unavailable.

## View current versions

`config/versions.json` is the only runtime authority for application, engine,
schema, Dashboard, and future model versions:

```bash
.venv/bin/python -m json.tool config/versions.json
```

Do not copy current version values into this README or Dashboard source.

Inspect the applied database migration ledger without reading health tables:

```bash
sqlite3 data/recovery.db \
  "SELECT sequence, version, name, applied_at FROM schema_migrations ORDER BY sequence;"
```

Dashboard connections use SQLite read-only mode and never initialize or migrate
the database.

## Release and quality records

- [Release records](releases/README.md) contain immutable version snapshots.
- [Changelog](docs/CHANGELOG.md) contains continuous history.
- [Quality Gate](docs/QUALITY_GATE.md) defines phase and release acceptance.

## Project Documentation

The `docs/` directory is the engineering source of truth for the project:

- [Machine-readable project state](project_state.json): versions, verified test result, real database counts, known issues, and next goal.
- [Project](docs/PROJECT.md): product positioning, goals, current capabilities, and direction.
- [Roadmap](docs/ROADMAP.md): completed and planned milestone status.
- [Current State](docs/CURRENT_STATE.md): verified versions, tests, modules, issues, and next goal.
- [Architecture](docs/ARCHITECTURE.md): system layers, data flow, module ownership, and dependency rules.
- [AI Collaboration](docs/AI_COLLABORATION.md): responsibilities of the Product Owner, Chief Architect, and Lead Software Engineer.
- [Decisions](docs/DECISIONS.md): architecture decision records and pending decisions.
- [Changelog](docs/CHANGELOG.md): Added, Changed, Fixed, and Tests history.
- [Database](docs/DATABASE.md): SQLite tables, relations, constraints, migrations, and data flow.
- [Data Dictionary](docs/DATA_DICTIONARY.md): field meanings, units, sources, and missing-value rules.
- [Recovery Engine](docs/RECOVERY_ENGINE.md): versioned fallback and personal-baseline scoring design.
- [Confidence Engine](docs/CONFIDENCE_ENGINE.md): proposed Data Completeness, Baseline Maturity, and confidence design.
- [AI Coach Design](docs/AI_COACH.md): non-runtime architecture, privacy, safety, audit, and implementation approval contract.
- [Cloud Provider Evaluation](docs/CLOUD_PROVIDER_EVALUATION.md): dated provider evidence, blocked decision, conditional configuration, and compliant unblocking paths.
- [Provider Due Diligence](docs/PROVIDER_DUE_DILIGENCE.md): enterprise questionnaire, evidence bundle, contract red lines, and approval record.
- [AI Coach Threat Model](docs/AI_COACH_THREAT_MODEL.md): assets, trust boundaries, threat register, controls, response, and residual risk.
- [AI Coach input schema](config/ai_coach_input.schema.json) and [output schema](config/ai_coach_output.schema.json): machine-readable deny-unknown contracts.
- [AI Coach safety policy](config/ai_coach_safety_policy.json): semantic boundaries and deterministic fallback reason codes.
- [AI Coach evaluation policy](config/ai_coach_evaluation.json): local 200-case, three-run preflight thresholds.
- [AI Coach provider approval](config/ai_coach_provider_approval.json): machine-readable blocked-by-default cloud-call gate.
- `src/ai_coach_context.py`: provider-independent, approval-before-build outbound context projection.
- `python -m src.ai_coach_readiness`: aggregate local-pre-provider and runtime readiness gate.
- [Coding Standard](docs/CODING_STANDARD.md): Python, configuration, security, SQL, and module standards.
- [Testing](docs/TESTING.md): unittest commands, test design, fixtures, and completion gates.
- [API and Interfaces](docs/API.md): Polar, Kubios, SQLite, Dashboard, and future AI contracts.
- [Versioning](docs/VERSIONING.md): app, scoring, database, Dashboard, and model version rules.
- [Quality Gate](docs/QUALITY_GATE.md): reusable phase completion and release-readiness checks.
- [Release records](releases/README.md): formal version snapshots and their relationship to the changelog and handoff.
- [Sync Pipeline](docs/SYNC_PIPELINE.md): one-click ordering, Dry Run, Selective Sync, Resume, logging, and history.
- [Current phase handoff](docs/HANDOFF.md): standardized, machine-verified delivery summary.
- [Cognitive Training Studio](docs/COGNITIVE_TRAINING_STUDIO.md): isolated browser-based cognitive practice, protocols, data boundaries, and limitations.

Update `docs/CHANGELOG.md` after every completed development phase. Generate the
automatic region of `docs/CURRENT_STATE.md` with the state script, and update the
relevant specialist document whenever its contract changes.

Rebuild and validate machine/human project state after every completed phase:

```bash
.venv/bin/python scripts/update_project_state.py
```

This command runs the complete unittest suite, reads non-sensitive SQLite
counts, updates `project_state.json`, and synchronizes `docs/CURRENT_STATE.md`.
It never reads credential or token files.

Verify collaboration artifacts and architecture boundaries:

```bash
.venv/bin/python scripts/verify_ai_collaboration.py
```

Run the complete phase gate after Codex updates the handoff:

```bash
.venv/bin/python scripts/finalize_phase.py
```

## Test

```bash
source .venv/bin/activate
python -m unittest discover -s tests
```
# Alertness Probe update

Daily Neural Check now uses a 60-second **Alertness Probe｜警觉性反应** (`alertness_probe_v1`). The retained 3-minute **Calibration PVT｜警觉性校准测试** (`pvt_calibration_3min_v1`) has a separate baseline. Results support personal longitudinal trends only; the short form is not equivalent to laboratory PVT and does not provide medical or driving-safety judgments.
