# Quality Gate

## Simplified Structured Training Entry 1.0

- [x] Simple mode and RPE are session defaults; reruns preserve selection.
- [x] Seven measurement modes render only applicable fields.
- [x] RPE, RIR, or none never deletes or converts the other stored value.
- [x] Catalog metadata auto-fills; custom catalog writes require explicit choice.
- [x] Primary rows contain no more than four inputs plus the set label.
- [x] Batch copy is limited to 1–20 with unique UUIDs; deletes require confirmation.
- [x] Hidden fields, failed-save state, and Polar objective priority are preserved.
- [x] No schema, Recovery, Baseline, Confidence, summary, Polar, or cloud-AI change.
- [x] Bilingual coverage, 47 acceptance points, browser, SQLite, and regression pass.

Gate Result: **PASS**.

## Brand-Based Supplement Product Catalog 2.0

- [x] Default daily UI contains brand, product, quantity, unit and actions only.
- [x] Active ingredients remain in versioned product profiles and legacy columns.
- [x] Unconfirmed/stale/unit-mismatched products produce no ingredient totals.
- [x] Candidate search cannot bypass user confirmation or Provider Approval Gate.
- [x] Medication is separated; finasteride cannot enter supplement calculation.
- [x] Migration 0.15.0 is backed up, idempotent and integrity checked.
- [x] Recovery, Baseline, Confidence and Polar behavior remain unchanged.

Gate Result: **PASS** after focused and complete regression, i18n, SQLite and
browser verification.

## Structured Training Details 1.0

- [x] Each Polar session accepts independent manual exercise details.
- [x] Same-day sessions remain separate; exact external ID is unique.
- [x] Polar time, duration, heart rate, calories and distance are read-only.
- [x] Sport overrides retain the original Polar value and source marker.
- [x] Exercise/set CRUD, copy, ordering, draft/complete and soft-delete pass.
- [x] Strength, bodyweight, duration, cardio and dance rules are covered.
- [x] kg/lb conversion is versioned; bodyweight/assistance are not false volume.
- [x] AI exports summaries only; notes/raw details are excluded; no cloud AI runs.
- [x] Recovery, Baseline, Confidence, Daily Metrics and Polar logic are unchanged.

Gate Result: **PASS** after complete regression, i18n, SQLite and browser checks.

## Simplified Structured Nutrition Logging 1.0

- [x] Default input asks for food/beverage, quantity and controlled unit.
- [x] Category-first tables are absent from the default page.
- [x] Multi-tag catalog and unknown-food no-guess behavior are tested.
- [x] Draft, complete, edit, soft-delete, recent, copy, template and UUID paths pass.
- [x] Legacy headers/items/supplements are retained through migration 0.13.0.
- [x] Supplement dynamic units remain operational.
- [x] Deterministic health engines and Polar remain unchanged; no cloud AI is called.

Gate Result: **PASS** after 604-test regression, i18n, SQLite and browser checks.

## Supplement Dynamic Units 1.0

- [x] Unit enum and catalog validation are centralized.
- [x] Legacy gram records are preserved through migration.
- [x] Unlike units are not summed or converted.
- [x] Dashboard uses services instead of SQL.
- [x] Recovery, Baseline and Confidence formulas remain unchanged.
- [x] No cloud AI or credential access is introduced.
- [x] SQLite integrity is `ok`; the migration ledger contains schema 0.12.0 once.
- [x] Simplified Chinese, Traditional Chinese and English coverage passes with no direct page literals.
- [x] 589/589 tests pass, including migration, constraints, catalog, UI contract,
  summaries, AI Context and existing deterministic-engine regressions.
- [x] Browser smoke testing confirms fish oil → 粒, creatine → 克,
  allowed manual override, dynamic add/remove, and no persisted smoke-test row.

Gate Result: **PASS**.

## Polar V4 Sleep Detail Gate

- `/sleeps` detail requests use a one-day range and explicit sleep-result,
  sleep-evaluation, and sleep-score features.
- Continuous heart rate uses `/continuous-samples` with heart-rate-samples.
- Sleep aggregates are restricted to the recorded sleep interval; invalid or
  absent respiration remains missing.
- Raw responses are preserved before deterministic import and projection.
- Endpoint, parser, conversion, aggregation, and missing-value tests must pass.

## Domain-Based App Navigation Gate

- Top-level navigation contains exactly Exercise, Sleep, Recovery, Nutrition,
  and System Information.
- Kubios Screenshot Import and Kubios Advanced Metrics have no top-level links;
  underlying code and data are preserved.
- All domain queries open SQLite read-only and degrade safely when fields or
  tables are unavailable.
- Requested training fields are parsed from local Polar source records. Missing
  sleep-stage fields remain unavailable rather than becoming zero or estimates.
- Existing 28-day baselines and deterministic Local Coach outputs are reused;
  no health formula, engine version, cloud path, or database schema is changed.
- Chinese and English keys match, and the Streamlit literal coverage scan passes.

Gate Result: **PASS WITH CONDITIONS** after full regression and browser smoke
testing. The condition is source availability for detailed sleep-stage fields.

## Kubios HRV Data Model & Advanced Metrics v1.0 Gate

- Schema 0.7.0 created an automatic pre-migration backup and passed integrity,
  ledger, checksum, and idempotency checks.
- Recovery, Confidence, and Local Coach record serializations were unchanged by
  migration; all three engine versions and formulas remain unchanged.
- Source priority, review eligibility, explicit user selection, conflict handling,
  NULL behavior, confirmed groups, normalization, derivation, read-only queries,
  AI allowlisting, reports, i18n, and privacy boundaries are tested.
- Home displays exactly six configured core metrics; advanced fields stay on the
  dedicated page and outside default reports/AI export.
- Real local evaluation passes template detection and all 17 visible numeric
  fields across two fixtures. Formal import is intentionally blocked until the
  user supplies and confirms a complete date.

Gate Result: **PASS WITH CONDITIONS**. Implementation and regression validation
pass. The condition is user review/full-date completion before formal import,
plus broader full-screen and Results Summary sample coverage. This is engineering
validation, not medical or clinical validation.

## Kubios Real Screenshot Calibration v1.2 Gate

- Local OCR only; source and runtime contain no cloud OCR or API-key path.
- Original images are preserved and hashed; duplicate import is idempotent.
- Unconfirmed and failed recognition never writes formal Kubios health data.
- CSV conflicts require an explicit choice and configured priority is stable.
- Migration 0.6.0 is backed up, ledgered, idempotent, checksum-checked, and
  SQLite integrity is `ok`.
- Recovery, Baseline, Confidence and Local Coach formulas are unchanged.
- Screenshot paths and OCR text remain outside AI Context and ordinary logs.
- Chinese/English page coverage has zero direct visible literals.
- Three explicit templates use normalized regions, field-specific preprocessing,
  candidate voting, fixed units, and manual fallback.
- Auto-selection is enabled only for the two layouts calibrated from genuine
  anonymized samples; Results Summary remains manual pending a real sample.
- Two real cropped samples pass template detection and every visible supported
  numeric field. They are not import-ready without manual completion because a
  complete date or other mandatory fields are absent.

Gate Result: **PASS WITH CONDITIONS**. Offline implementation, two-sample real
calibration, visible-field recognition, mandatory completion, and regression
tests pass. Broader full-screen and Results Summary coverage remains limited.

This gate is required after every project phase. It verifies engineering and
governance readiness; it does not establish medical or clinical validity.

## Scope Compliance

- Confirm that changes stay within the approved phase scope.
- Confirm that no unapproved architecture, scoring, ingestion, OAuth, or data
  model change was introduced.
- Record any scope exception and its explicit approval.

## Security

- No secret, credential, token, or sensitive assignment is committed or logged.
- `.env`, token files, and `data/` are not included in release artifacts.
- Personal raw health records and raw payloads are not included in state,
  documentation, screenshots, or release notes.
- Tests use synthetic or aggregate-only values.

## Code Quality

- Responsibilities remain modular and dependency direction is preserved.
- There are no circular imports or duplicated core rules.
- Runtime configuration is not scattered across code or documentation.
- Types, missing values, errors, and friendly degradation are handled explicitly.

## Tests

- The complete unittest suite passes.
- New behavior and failure paths have tests.
- Boundary conditions and regression behavior are covered.
- A phase cannot pass while any required test fails.

## Internationalization Gate

- `zh-CN`, `zh-TW` and `en` resources load and expose identical keys.
- Language selection is immediate, persisted locally, and does not clear forms.
- Database values, internal enums, calculation results, AI Context JSON schema,
  and default CSV headers remain stable.
- Reports render in both languages and include complete safety language.
- Coverage scan passes with no direct primary-page display literals.
- No translation API, cloud AI, network call, or automatic upload is used.

Result for Internationalization v1.0: **PASS**. The complete suite passes,
coverage is complete for the primary pages, both report languages were
generated, language switching retained unsaved form text, and the signed macOS
App was rebuilt and launched locally.

## State Governance

- `project_state.json` is regenerated from the real test run and read-only
  database measurements.
- The generated region in `CURRENT_STATE.md` matches machine state.
- `CHANGELOG.md`, `ROADMAP.md`, and `HANDOFF.md` reflect the phase outcome.
- Repeated state generation is idempotent when measured facts are unchanged.

## Documentation

- Every affected specialist document is updated.
- Database changes update `DATABASE.md`; field changes update
  `DATA_DICTIONARY.md`.
- Model or scoring changes update `MODEL_CARD.md` and `RECOVERY_ENGINE.md`.
- Consequential decisions update `DECISIONS.md`.
- Unaffected specialist documents are not edited merely to create activity.

## Real Data Verification

- Verification uses the real local `recovery.db` in read-only mode when relevant.
- Only aggregate counts and non-sensitive dates are recorded.
- No personal health detail, raw payload, credential, or token is output.

## Release Readiness

- Version changes come from `config/versions.json` and satisfy version rules.
- Database migration impact is explicitly stated, including when there is none.
- Required manual user actions are listed.
- Open P0/P1 issues are reviewed and any release condition is explicit.
- A formal version snapshot exists in `releases/` when the phase forms a release.

## Approval

- Codex completes implementation and evidence-based verification.
- The User performs runtime and user-level acceptance.
- ChatGPT performs the Architecture Review.
- Approval duties do not allow a failed automated gate to be reported as passed.

## Gate Result

### Personal Logging & Manual Export Validation

- Personal writes use parameterized storage methods; missing nutrition stays NULL.
- Export is allowlisted, previewable, confirmation-gated, and local-only.
- Raw payloads, credentials, identifiers, paths, and notes are excluded.
- Recovery, Baseline, Confidence, Local Coach and cloud readiness remain unchanged.

- `PASS`: every required check passes and there are no release-blocking issues.
- `PASS WITH CONDITIONS`: automated checks pass, but named non-blocking conditions
  require user acceptance or architecture review.
- `FAIL`: a required check fails or a P0/P1 issue blocks the stated release scope.

## Pipeline Validation

### Local Coach validation

- Local Coach runs after Confidence and before Report.
- `--only local-coach`, dry-run, and resume preserve Pipeline semantics.
- Update counts are persisted without logging advice JSON or health details.
- Dashboard and reports degrade safely when the table or recommendation is absent.
- Cloud AI is not a Pipeline step and remains runtime-blocked.
- Longitudinal evaluation must have zero invalid/duplicate records and 100%
  Schema, deterministic-match, safety-notice, and no-cloud-marker rates.
- Prospective evaluation counts only post-protocol, non-future, timely generated
  unique dates; backfills cannot satisfy the 14-day target.
- `--if-new-data` may skip deterministic stages only after an unchanged tracked
  source snapshot, zero new raw rows, and zero pending Kubios CSV files.
- Any changed/missing snapshot or uncertain input must run the full pipeline.

- Full ordering invokes each existing layer exactly once unless a selective or
  resumed run intentionally skips it.
- Dry Run performs no database, report, state, or phase-document write.
- Selective Sync runs only the requested step and documented prerequisites.
- Resume continues the latest interrupted run without repeating completed steps.
- Every live step records start, finish, duration, success, step, and safe message.
- `sync_history` remains separate from the recovery business database.
- Logs and history contain no token, credential, raw payload, or health detail.
- Imported, metrics, baseline, recovery, report, and state counts appear in the
  final summary.
- Required endpoint failures stop the pipeline; optional capability failures are
  recorded as warnings and cannot be silently reported as a clean sync.
- Safe error codes are actionable without exposing response bodies or credentials.
- Finalization/history-write failures use the standard controlled failure summary.
- Dashboard changes are limited to the read-only System Status area.

## Database Migration Validation

- A verified local backup exists before real migration.
- Empty and legacy databases converge to the same ordered ledger.
- Existing business rows survive baseline registration.
- Repeated initialization does not duplicate migration records.
- Version, sequence, name, and checksum drift fail explicitly.
- `config/versions.json`, ledger latest version, project state, CURRENT_STATE,
  release note, DATABASE, and DATA_DICTIONARY agree.
- Dashboard and other read-only consumers cannot execute migrations.
- SQLite integrity check passes after real migration.

## Confidence Validation

- Empty, full, partial, no-training, alternative-source, invalid-value and
  boundary cases pass.
- Seven-day and full-window maturity behavior pass.
- Repeated rebuild is idempotent.
- Persisted version matches unified version source.
- Recovery rows are byte-for-byte unchanged before and after rebuild.
- Dashboard reads persisted Confidence and does not reimplement the formula.

## AI Coach Design Validation

- Design is explicitly non-runtime and `model_version` remains `unreleased`.
- Only allowlisted structured facts may enter future context; token, secret,
  raw JSON, raw payload, database files, and logs are denied.
- Output, prompt, model, safety policy, schema, and input digest are versioned.
- Confidence-aware language and medical, urgent-symptom, and injection boundaries
  are explicit and covered by contract tests.
- Provider choice, outbound fields, retention, audit migration, and evaluation
  thresholds require separate approval before implementation.
- Failure falls back to deterministic explanation and cannot alter Recovery,
  Baseline, Confidence, OAuth, raw data, or Dashboard state.

## AI Coach Cloud Governance Validation

- Outbound schema rejects unknown fields and excludes identity, raw payloads,
  exact timestamps, files, logs, secrets, and historical series.
- Named provider must prove Zero Data Retention, disabled training, and disabled
  human review before the first request.
- Local response content expires at 90 days; minimal metadata expires at 365
  days; verbatim user questions are not persisted.
- Migration `0.4.0` remains unexecuted until provider approval and verified backup.
- At least 200 synthetic cases pass three consecutive runs; critical security,
  immutability, schema, escalation, and fallback categories require 100%.
- Any critical failure blocks release regardless of aggregate evaluation score.

## Cloud Provider Selection Validation

- Deployment location is present in the provider's official supported-region list.
- ZDR is an account/project control or contractual term, not inferred from
  encryption or no-training language.
- Exact provider, model snapshot, endpoint, region, retention, review, and data-use controls are evidenced.
- Unsupported-region access, VPN, proxy, borrowed account, or billing-location workarounds are rejected.
- Missing evidence keeps the phase Blocked and prevents adapter, credential, migration, or live-call work.

## Provider Due Diligence Validation

- Questionnaire contains stable DD-01 through DD-24 identifiers.
- Every mandatory gate requires PASS; unknown, partial, or exception results block authorization.
- Binding evidence is distinguished from sales email and generic privacy claims.
- Review record defaults implementation authorization to NO and identifies exact snapshot and region.
- Evidence is revalidated before first use, at least annually, and after material changes.
- Procurement uses synthetic examples and stores no key, account ID, contract body, or real health data.

## AI Coach Threat Model Validation

- Protected assets and TB-1 through TB-7 boundaries cover local read, context,
  network, provider, validation, audit, and presentation.
- TM-01 through TM-18 each define inherent risk, required controls, and target residual risk.
- Context, destination, provider configuration, validation, audit, retention, and UI failures fail closed.
- Prevent, detect, and respond controls include redaction tests, kill switch, credential rotation, and deterministic continuity.
- Every threat receives synthetic positive/negative tests before runtime; Critical and High residual risks block release.
- Provider/model/endpoint/region, field, retention, UI, dependency, auth, safety-policy changes and incidents trigger re-review.

## AI Coach Contract Validation

- Prompt, output schema, and safety policy versions come from one machine-readable authority.
- Input and output schemas deny unknown root and nested fields.
- Sensitive user-question patterns, exact-value expansion, invalid ranges, unsafe markup/URLs, and version drift fail closed.
- Validation errors expose field paths but not rejected values.
- Validator has no network, database, provider, scoring, OAuth, or Dashboard dependency.
- Contract completion does not change `model_version`, execute migration, or authorize provider calls.

## AI Coach Semantic Safety and Fallback Validation

- Evidence references are a subset of identifiers derived from validated input.
- Unsupported numeric health claims, diagnostic certainty, medication directives,
  and strong recommendations under low confidence fail closed.
- Medium/low/very-low Confidence limitations and action bounds are enforced.
- Urgent-term matches require local emergency escalation and prohibit ordinary actions.
- Input digest uses HMAC-SHA256 with an explicit local key of at least 32 bytes.
- Invalid model output becomes schema-valid deterministic fallback with no model call.
- Safety and fallback modules cannot access provider, network, database, OAuth,
  scoring engines, raw data, or Dashboard.

## AI Coach Synthetic Preflight Validation

- Machine authority requires at least 200 synthetic cases and three consecutive runs.
- All eight categories have equal deterministic coverage and stable case ids.
- Critical expected pass/fallback behavior requires 100%; any mismatch fails the command.
- Aggregate output contains no prompt, model output, question, recommendation, or health value.
- Preflight has no provider, network, database, Polar, scoring, or Dashboard dependency.
- Local preflight success is not reported as exact-model safety evaluation success.

## AI Coach Cloud Call Approval Validation

- Committed approval record is blocked, authorization false, and contains no provider identity or endpoint.
- Approved state requires exact provider/model/HTTPS endpoint/region, all privacy controls, dual approval, and current evidence.
- Endpoint rejects HTTP, embedded credentials, query, and fragment configuration.
- Configuration fingerprint binds approval metadata to active contract versions.
- Missing, partial, expired, revoked, drifted, or malformed records fail before health-context serialization.
- Approval errors expose no record value and the gate has no network, database, or secret dependency.

## AI Coach Outbound Context Validation

- Source and every nested object use explicit fields; missing and unknown values fail closed.
- Contract versions are injected from authority and cannot be supplied by callers.
- Raw, token, historical series, exact metric expansion, and sensitive user questions are rejected.
- Builder returns a deep copy and does not mutate or alias source objects.
- Machine approval runs before provider-bound context construction.
- Context errors expose no rejected value and the module has no provider,
  network, database, raw, engine, OAuth, or Dashboard dependency.

## AI Coach Pre-Provider Readiness Validation

- Local pre-provider readiness and runtime readiness are separate booleans.
- Runtime requires all seven checks: contract/safety, local preflight, provider
  approval, matching released model version, audit migration, adapter, and exact-model evaluation.
- Exact-model artifact matches every contract version and approved numeric threshold.
- Missing or invalid artifact produces stable blocker codes and never a partial-ready state.
- `--require-runtime` exits nonzero while current provider approval is blocked.
- Readiness output contains no provider identity, endpoint, payload, credential, or health value.

## Reusable Quality Gate Template

```markdown
# Quality Gate — <Phase / Version>

- Date:
- Reviewer:
- Result: PASS | PASS WITH CONDITIONS | FAIL

## Scope Compliance
- [ ] Approved scope only
- [ ] No unapproved architecture change

## Security
- [ ] No secret or token exposure
- [ ] No `.env`, token file, `data/`, or personal raw health data in release artifacts

## Code Quality
- [ ] Module boundaries and dependency direction preserved
- [ ] No duplicated core logic or scattered runtime configuration
- [ ] Types, errors, and missing values handled

## Tests
- [ ] Full unittest suite passes
- [ ] New behavior, failure paths, boundaries, and regression covered

## State Governance
- [ ] project_state.json regenerated
- [ ] CURRENT_STATE.md generated region synchronized and idempotent
- [ ] CHANGELOG, ROADMAP, and HANDOFF updated

## Documentation
- [ ] Affected specialist documents updated
- [ ] Decisions and migrations documented when applicable

## Real Data Verification
- [ ] Real database checked read-only when relevant
- [ ] Only aggregate, non-sensitive evidence recorded

## Release Readiness
- [ ] Unified versions validated
- [ ] Migration, manual actions, and P0/P1 issues reviewed
- [ ] Release snapshot created when applicable

## Approval
- [ ] Codex implementation complete
- [ ] User runtime acceptance pending/completed
- [ ] ChatGPT Architecture Review pending/completed

## Pipeline Validation
- [ ] Dry Run made no database or governance writes
- [ ] Selective Sync and Resume passed
- [ ] History and logs contain safe lifecycle metadata only
- [ ] Existing engine and Dashboard analysis regression tests passed

## Conditions / Failed Checks
- Conditions:
- Failed Checks:
```

## Scheduled Sync & Manual Health Logging Gate

- [x] Default local schedule is 06:00 through a user-level macOS LaunchAgent.
- [x] Scheduler delegates to the shared pipeline and contains no duplicated
  Fetch, Import, scoring, reporting, or Cloud AI logic.
- [x] Full manual/scheduled/catch-up triggers share a crash-safe lock and
  canonical `trigger_type` history.
- [x] Catch-up is a user prompt, runs at most once per day, and is never started
  by a Streamlit rerun.
- [x] Manual activity, sleep, and recovery CRUD supports edit and confirmed
  deletion in both languages.
- [x] Polar wins overlapping measured fields; confirmed activity type is the
  only manual semantic override.
- [x] Kubios morning and Polar nightly measurements remain independent.
- [x] Dashboard, Report, and AI Context expose source/fallback/override metadata.
- [x] Raw rows are preserved and migration 0.8.0 is backed up, ledgered,
  idempotent, checksum-validated, and integrity-checked.
- [x] Recovery, Baseline, Confidence, and Local Coach algorithm versions remain
  1.0.0; Recovery/Confidence database hashes are unchanged.
- [x] No network AI, credentials in plist/log output, or notes in AI Context.

Gate Result: **PASS WITH CONDITIONS**. Implementation, synthetic conflict
verification, and local LaunchAgent runner checks pass. The conditions are the
next actual 06:00 observation and the macOS sleep/login scheduling caveat.
