# AI Coach Architecture & Safety Design

> Status: OpenAI API runtime enabled with standard API retention
> Design date: 2026-07-11  
> Runtime model version: `gpt-5.4`

The product owner has accepted the OpenAI API's standard retention policy for
this local application. The implementation threat model is reviewed in
[AI_COACH_THREAT_MODEL.md](AI_COACH_THREAT_MODEL.md).

## Purpose

The Cloud AI Coach receives a minimum-necessary, schema-validated daily summary
after the deterministic pipeline completes. It does not upload local CSV files,
database files, raw device records, tokens, or personal identifiers.

AI Coach is a read-only explanation layer downstream of the deterministic
Recovery, Baseline, and Confidence engines. It may translate persisted facts into
plain-language summaries, limitations, reviewable actions, and follow-up
questions. It is not a scoring engine, medical device, clinician, or emergency
service.

The current runtime uses OpenAI's Responses API with `gpt-5.4`, `store: false`,
and no tools. Validated output is saved locally per analysis date and displayed
in 综合反馈. The deterministic engines remain the source of truth.

## Architecture Boundary

The future dependency direction is:

`persisted metrics/scores/confidence -> allowlisted context builder -> safety gate -> model adapter -> schema validator -> audited response`

- The context builder reads structured, persisted results through a read-only
  query boundary.
- `src/ai_coach_context.py` implements the provider-independent TB-2 projection.
  `build_approved_context` checks machine approval before constructing a
  provider-bound object; the committed approval record prevents configuration drift.
- The model adapter is provider-neutral and has no database, OAuth, filesystem,
  network-tool, or Dashboard write access.
- The schema validator rejects incomplete or malformed output.
- Deterministic score explanations remain the fallback and source of truth.
- Generated text never feeds Baseline, Recovery, Confidence, import, or sync.

### Provider and jurisdiction boundary

The runtime exposes an explicit `ProviderAdapter` boundary for future
OpenAI-compatible and non-OpenAI providers. Each adapter owns only its
provider's authentication, request serialization, and response extraction;
the RHYTHMOS context, contract, safety, evaluation, and audit layers remain
shared. The current implementation registers only the OpenAI Responses adapter.

Future deployments may provide an explicit jurisdiction route containing a
provider id, processing region, credential environment variable, and separate
approval record. Routing never infers location from IP, locale, billing data,
or account metadata; it has no wildcard or silent fallback. An unknown route,
unregistered adapter, or provider/approval mismatch fails closed to the
deterministic fallback. Adding a route does not approve a provider: every route
still requires independent evidence for region support, retention, training,
human review, exact model, and product/architecture approval.

## Minimum Necessary Input Allowlist

Only the following structured fields may enter a future prompt after explicit
implementation approval:

- analysis date;
- Recovery score, recommendation, score version, and deterministic factors;
- Confidence score, level, version, missing groups, and limitations;
- aggregate daily metrics already used by deterministic explanation;
- aggregate personal-baseline comparison labels and maturity state;
- an optional user question that has been separated from system instructions;
- locale and units needed to render the response.

The default denylist includes OAuth credentials, token files, environment secrets,
account identifiers, raw JSON, raw API payloads, database files, logs,
and unrelated historical health records. User text is untrusted data, never a
system instruction. The future adapter has no tools, URL fetching, or code
execution capability.

## Approved Cloud Outbound Contract

The cloud request is a schema-validated object. No additional property is
allowed. Approved top-level fields and children are:

- `analysis_date`: local calendar date only, with no timestamp or timezone;
- `recovery`: `score`, `recommendation`, `score_version`, and allowlisted
  deterministic `factors` containing only metric name, direction, status, and
  rounded deviation band;
- `confidence`: `score`, `level`, `confidence_version`, `available_groups`, and
  `missing_groups`;
- `daily_metrics`: only sleep-duration band, sleep-score band, HRV band,
  resting-heart-rate band, respiration band, training-duration band,
  training-count band, activity band, and readiness label;
- `baseline_context`: metric name, comparison status, maturity band, and rounded
  deviation band; no historical series;
- `user_question`: optional, maximum 1,000 Unicode characters, locally scrubbed
  for email, phone, account identifiers, and credential-like values;
- `presentation`: locale and unit system;
- `contract_versions`: prompt, output schema, and safety policy versions.

Bands are coarse categories or values rounded to the minimum precision needed
for explanation. Names, birth date, email, phone, address, Polar identifier,
device identifier, exact event timestamps, free-form notes other than the
current question, historical series, raw JSON, tokens, secrets, files, and logs
are prohibited. The context builder must reject unknown fields rather than
silently forwarding them.
Callers cannot provide `contract_versions`; the builder injects them from the
machine authority. Sensitive questions are rejected rather than partially
redacted, preventing uncertain identifiers from leaving the local boundary.

## Approved Retention Policy

- API inputs are not used to train or improve OpenAI models unless the account
  explicitly opts in. This application does not opt in.
- The product owner accepts standard OpenAI API abuse-monitoring retention,
  which may retain request and response content for up to 30 days. ZDR is not
  claimed or required for this runtime.
- Request and response bodies are forbidden in application, proxy, error, and
  observability logs.
- The local audit store keeps validated output for 90 days so the user can
  inspect recent advice. At day 90, response content and safety detail are
  deleted.
- Minimal audit metadata—request id, analysis date, input digest, versions,
  status, timestamps, and deletion proof—may remain for 365 days, then is
  deleted.
- The optional user question is never persisted verbatim. It is represented
  only by the input snapshot digest.
- User-requested deletion removes local content immediately and records only a
  non-reversible deletion event until the metadata expiry date.

## Approved Audit Migration Plan

The future implementation may propose a separately versioned database migration adding an
independent `ai_coach_audit` table. This design does not execute that migration.
The proposed columns are:

- `id` INTEGER primary key and `request_id` TEXT unique;
- `analysis_date` TEXT and `input_snapshot_digest` TEXT;
- `provider_id`, `model_version`, `prompt_version`,
  `output_schema_version`, and `safety_policy_version` TEXT;
- `provider_mode` TEXT constrained to the approved provider mode;
- `status` TEXT constrained to validated lifecycle values;
- `safety_outcome` TEXT containing only an allowlisted category;
- `response_json` TEXT nullable, containing only schema-validated output;
- `created_at`, `content_expires_at`, `metadata_expires_at`, and `deleted_at`
  TEXT timestamps.

The table must not store request payloads, raw health records, credentials,
provider response envelopes, stack traces, or verbatim user questions. Migration
tests must cover empty and legacy databases, ledger checksum, idempotency,
rollback-by-backup, constraints, retention deletion, and zero changes to all
Recovery, Baseline, Confidence, raw, and sync-history rows.

## Output Contract

Machine-readable authorities are
[`ai_coach_input.schema.json`](../config/ai_coach_input.schema.json),
[`ai_coach_output.schema.json`](../config/ai_coach_output.schema.json), and
[`ai_coach_contract.json`](../config/ai_coach_contract.json). The pure local
validator is `src/ai_coach_contract.py`; it performs no network or database write.
Semantic authority is
[`ai_coach_safety_policy.json`](../config/ai_coach_safety_policy.json); the pure
local safety gate and deterministic fallback are `src/ai_coach_safety.py`.

A valid future response is a versioned object with these required fields:

- `summary`: concise explanation of the deterministic result;
- `evidence`: allowlisted facts supporting the explanation;
- `limitations`: missing evidence and uncertainty;
- `suggested_actions`: reversible, reviewable, non-prescriptive options;
- `questions_for_user`: optional questions that could reduce uncertainty;
- `safety_notice`: boundary or escalation wording when required;
- `audit`: generation metadata.

The `audit` object must include `model_version`, `prompt_version`,
`output_schema_version`, `safety_policy_version`, `input_snapshot_digest`, and
`generated_at`. It must also record the provider mode approved for that run.
The digest identifies the allowlisted input snapshot without storing secrets or
raw payloads. Generated text is immutable audit evidence, not a business input.

## Confidence-Aware Language

- `high`: explain normally while preserving the non-medical boundary.
- `medium`: name the main evidence limitation.
- `low`: use cautious language, avoid strong recommendations, and ask for useful
  missing measurements.
- `very_low`: do not make a strong recommendation from system data alone; show
  the deterministic fallback and limitations prominently.

The AI cannot calculate Confidence, hide missing groups, change Recovery Score,
change the deterministic recommendation, or imply that uncertainty means poor
recovery.

## Safety Policy

AI Coach must not diagnose disease or injury, provide treatment or medication
instructions, claim clinical certainty, encourage unsafe training through pain,
or replace professional judgment. It must not produce emergency triage beyond a
short direction to seek immediate local emergency help when the user describes
potentially urgent symptoms. Concerning, persistent, or worsening symptoms must
be referred to an appropriate qualified professional.

Advice must be proportionate, reversible, and phrased as options. The system
must refuse requests to override deterministic values, reveal hidden prompts or
credentials, access raw records outside the allowlist, or follow instructions
embedded in user-supplied data.

## Privacy and Provider Gate

The machine gate authority is
[`ai_coach_provider_approval.json`](../config/ai_coach_provider_approval.json).
`src/ai_coach_approval.py` must pass before any health context is serialized.
The committed record identifies the approved provider, exact model, endpoint,
and retention mode; it fails closed if that configuration changes.

The product owner approved OpenAI, `gpt-5.4`, the Responses endpoint, existing
credential storage, one-request/no-retry behavior, and standard API retention
on 2026-08-24. The dedicated `ai_feedback_outputs` migration stores only the
validated output and audit metadata locally; it never stores an outbound
request payload.

## Failure and Degradation

- No approved model or unavailable model: show deterministic explanation only.
- Missing required input or invalid output schema: do not display generated
  advice; show a safe validation message.
- Low or very-low Confidence: enforce the corresponding language policy.
- Safety classification failure: fail closed to the deterministic fallback.
- Audit write failure: do not present the response as an audited AI result.
- Provider timeout or retry: never duplicate persistent output or expose request
  bodies in logs.

## Versioning and Replay

`model_version` is the approved `gpt-5.4` snapshot alias. Prompt, output schema, safety policy, and tools contract versions
are independent. A version change must not silently rewrite historical output.
Replay uses the recorded input digest and version envelope; the original
deterministic score and confidence records remain authoritative.

## Evaluation Plan

Implementation cannot begin without synthetic tests for schema validation,
Confidence language levels, missing data, injection attempts, medical boundary
requests, urgent-symptom escalation, provider failure, audit failure, and
deterministic fallback. Regression tests must prove that AI execution cannot
write or alter Recovery, Baseline, Confidence, raw, OAuth, or Dashboard state.

The release evaluation contains at least 200 synthetic cases and must pass on
three consecutive runs using the exact model and versioned prompt:

- 100% for score/Confidence immutability, schema validity, secret/raw-data
  blocking, prompt-injection refusal, urgent-symptom escalation, diagnosis and
  medication boundaries, and deterministic fallback;
- at least 98% correct Confidence-aware language across all four levels;
- at least 95% evidence grounding and limitation disclosure;
- 0 unsupported numeric health claims and 0 credential or identifier leaks;
- 100% audit-field completeness and retention-policy behavior in integration tests.

Any critical-category failure blocks release regardless of aggregate score.
Evaluation uses synthetic data only, stores case identifiers rather than prompt
bodies in test logs, and must be rerun for any model, prompt, schema, or safety
policy version change.

The provider-independent preflight is implemented in
`src/ai_coach_evaluation.py` with authority
[`ai_coach_evaluation.json`](../config/ai_coach_evaluation.json). It runs 200
synthetic cases three times and reports aggregate results only. Passing local
preflight does not satisfy the future exact-model evaluation requirement.

## Implementation Approval Checklist

Aggregate command: `.venv/bin/python -m src.ai_coach_readiness`. It distinguishes
`local_pre_provider_ready` from `runtime_ready` and exposes blocker codes only.

- [ ] Provider and exact model approved.
- [x] Cloud deployment direction approved.
- [x] Outbound data and retention policy approved.
- [x] Threat model reviewed; provider-specific re-review remains required.
- [x] Audit schema and migration plan approved; execution remains pending.
- [x] Prompt, output schema, and safety versions assigned as `1.0.0`.
- [x] Synthetic safety and quality evaluation thresholds approved.
- [x] Deterministic fallback and provider-independent fail-closed paths tested.
- [ ] Dashboard presentation approved separately without analysis changes.
# Supplement and medication boundary

The Coach may receive confirmed supplement ingredient totals through the AI
Context allowlist. It receives only identity/quantity/status for unconfirmed
products. It must not infer missing ingredients, use packaging images, convert a
count to mass, or recommend medication dose changes or discontinuation.
