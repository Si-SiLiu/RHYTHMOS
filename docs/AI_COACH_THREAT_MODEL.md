# AI Coach Privacy and Security Threat Model

> Status: Design review complete; standard-retention runtime enabled
> Threat-model version: `1.0.0`  
> Review date: 2026-07-11

## Scope and Assumptions

This model covers the AI Coach path from read-only local facts through
context minimization, cloud inference, schema validation, local audit, and
Dashboard presentation. Polar collection, deterministic Recovery/Baseline/
Confidence calculations, and the cloud provider's internal platform are outside
the implementation trust boundary but are represented as dependencies.

Assumptions are fail-closed: the approval record fixes the OpenAI Responses
endpoint and `gpt-5.4`, tools are disabled, and only the closed minimum-necessary
schema leaves the device. The product owner accepted standard API retention.

## Protected Assets

- Local health aggregates and their inference-sensitive combinations.
- Recovery Score, recommendation, Confidence, missing groups, and versions.
- User question and any accidental identifiers it contains.
- Cloud API credential and project/account configuration.
- System prompt, output schema, safety policy, and evaluation artifacts.
- Audit response content, input digest, request id, and retention timestamps.
- Integrity of deterministic results and Dashboard presentation.
- User consent, deletion choice, and provider approval evidence.

## Trust Boundaries and Data Flow

```text
TB-1 Local SQLite (read-only)
  -> TB-2 allowlist context builder and identifier scrubber
  -> TB-3 outbound HTTPS adapter and project-scoped credential
  -> TB-4 approved standard-retention cloud inference endpoint
  -> TB-5 local schema/safety validator
  -> TB-6 local audit store with expiry
  -> TB-7 read-only Dashboard presentation
```

- `TB-1`: business data boundary; AI cannot write or migrate it.
- `TB-2`: privacy boundary; unknown fields and high-precision/history expansion fail.
- `TB-3`: secret and network boundary; logs never contain bodies or authorization headers.
- `TB-4`: external processor boundary; exact endpoint/model and retention-mode evidence is mandatory.
- `TB-5`: untrusted-output boundary; model text is data, never code or instructions.
- `TB-6`: sensitive local retention boundary; content and metadata have different expiry.
- `TB-7`: user interpretation boundary; AI text cannot masquerade as deterministic fact.

## Threat Register

Risk is rated before controls as Critical, High, Medium, or Low. A Critical or
High residual risk blocks runtime approval.

| ID | Threat and path | Inherent risk | Required controls | Target residual |
| --- | --- | --- | --- | --- |
| `TM-01` | Overbroad SQL/query exports raw or historical health data at TB-1→TB-2. | Critical | Dedicated read-only query, exact column projection, closed schema, unknown-field rejection, synthetic regression tests. | Low |
| `TM-02` | User question contains name, contact detail, account id, credential, or hidden identifier. | High | 1,000-character cap, local identifier/credential scrubber, deny on uncertain credential match, never persist verbatim. | Low |
| `TM-03` | Prompt injection in user text asks the model to reveal system prompt, alter score, or use tools. | High | Delimit user data, immutable system policy, no tools/files/search/MCP, output schema, injection evaluation suite. | Low |
| `TM-04` | Cloud credential leaks through repository, logs, exception, shell, or Dashboard. | Critical | Project-scoped environment secret, startup presence check without echo, header redaction, safe error codes, secret scanning and rotation runbook. | Low |
| `TM-05` | Request/response body appears in application, proxy, SDK, tracing, or provider logs. | Critical | Body logging disabled, no debug HTTP, approved standard-retention disclosure, stateless endpoint, integration log assertions, fail closed on configuration drift. | Medium |
| `TM-06` | Unsupported region, proxy, DNS override, redirect, or wrong endpoint bypasses provider approval. | Critical | Exact HTTPS origin allowlist, redirects disabled, TLS verification, deployment-region evidence, runtime config fingerprint, no user-supplied URL. | Low |
| `TM-07` | Provider silently changes alias, retention, region, subprocessor, or review policy. | High | Immutable model snapshot, annual/change-triggered due diligence, config expiry, startup approval check, kill switch. | Medium |
| `TM-08` | Model fabricates metrics, medical diagnosis, medication guidance, or unsafe training advice. | Critical | Strict evidence references, prohibited-content validator, Confidence language policy, safety notice, 200-case three-run gate, deterministic fallback. | Low |
| `TM-09` | Malformed or adversarial output injects Markdown links, HTML, script, control characters, or oversized content. | High | Strict JSON Schema, length limits, Unicode normalization, allowlisted Markdown/plain text renderer, HTML disabled, URL rejection. | Low |
| `TM-10` | Generated text is mistaken for or writes over deterministic score/recommendation. | Critical | Separate table and visual label, immutable source fields, no write dependency, database permission boundary, hash regression tests. | Low |
| `TM-11` | Audit store retains content after 90 days or metadata after 365 days. | High | Expiry columns, idempotent deletion job, startup overdue check, deletion tests, user-triggered deletion and proof event. | Low |
| `TM-12` | Audit response, digest, or request id enables linkage or inference across dates. | High | Random non-provider request id, keyed digest with rotating local key, minimum metadata, no cross-user identifiers, expiry enforcement. | Medium |
| `TM-13` | Backup, export, crash dump, Spotlight/indexer, or file permissions expose audit data. | High | Exclude from generic exports, restrictive file permissions, encrypted backup policy before runtime, no core dumps, documented secure deletion limits. | Medium |
| `TM-14` | Replay, retry, or concurrent request creates duplicate output or stale advice. | Medium | Idempotency key, analysis-date/input-digest uniqueness, bounded retry only before response, freshness label, transactional audit finalization. | Low |
| `TM-15` | Compromised dependency or SDK exfiltrates local files/environment. | Critical | Minimal pinned dependency, direct HTTPS client, dependency review/SBOM, no auto instrumentation, adapter process/file-access minimization. | Medium |
| `TM-16` | Safety or schema validator fails open due to exception or version mismatch. | Critical | Validator before display/persistence, explicit version match, exception-to-fallback, mutation/failure tests, no partial rendering. | Low |
| `TM-17` | Dashboard caches or exposes AI content to another local user/session. | High | Local single-user boundary, no shared cache, session isolation, audit access control, explicit clear/delete action, no URL query content. | Medium |
| `TM-18` | Consent or provider approval expires while runtime continues sending data. | Critical | Approval record with expiry, startup and per-request gate, kill switch default off, revalidation trigger, safe deterministic-only mode. | Low |

TM-18's provider approval record, expiry check, dual-review check,
HTTPS endpoint check, and configuration fingerprint are implemented in
`src/ai_coach_approval.py`. Integration before serialization remains mandatory
for any future adapter.

TB-2's provider-independent closed projection and approval-before-build path are
implemented in `src/ai_coach_context.py`. `src/ai_feedback.py` performs the
minimum-necessary database projection and persists only validated output.

## Mandatory Security Controls

### Prevent

- Default feature flag is off and cannot be enabled without a current approved
  provider configuration fingerprint.
- Context is built from named fields, reduced to approved bands, locally scrubbed,
  and validated with `additionalProperties=false` semantics.
- Network destination, model snapshot, project, endpoint, and region are fixed
  configuration—not user input.
- The adapter enforces an exact HTTPS origin allowlist and disables redirects.
- Provider features that add state or third parties remain disabled.
- AI components cannot import or call Recovery/Baseline/Confidence write paths,
  Polar OAuth/token paths, raw storage, tools, shell, or arbitrary filesystem APIs.

### Detect

- Synthetic canary values verify body/header redaction without using real secrets.
- Tests inspect logs, audit rows, and exceptions for forbidden fields and identifiers.
- Runtime records configuration fingerprint, schema/safety versions, status, and
  expiry—not request bodies.
- Startup detects expired approval, retention backlog, model/config mismatch, and
  unexpected audit schema; any detection disables cloud calls.

### Respond

- Kill switch immediately disables outbound calls while deterministic features remain available.
- On suspected exposure: stop calls, rotate provider credential, preserve only
  non-content incident metadata, identify affected audit ids/dates, delete where
  safe, notify the user/provider as required, and reauthorize before restart.
- Provider policy, incident, or subprocessor notice invalidates approval until review.
- Recovery, Baseline, Confidence, sync, reports, and Dashboard deterministic views
  must continue without AI.

## Privacy Properties

- **Data minimization:** only the closed outbound schema leaves the local boundary.
- **Purpose limitation:** cloud output explains existing deterministic facts only.
- **Unlinkability:** no account/device id or historical series; local linkage expires.
- **Transparency:** UI names AI text, model/prompt/safety versions, Confidence, and limitations.
- **Intervenability:** the user can disable AI and request local content deletion.
- **Retention limitation:** standard API retention is disclosed to the user; local content is stored per day and may be deleted locally.
- **Integrity:** model output cannot change source facts or execute instructions.

## Verification Requirements

Before runtime approval, tests must prove:

1. every `TM-01` through `TM-18` control has at least one synthetic positive and
   negative case;
2. all Critical paths fail closed in context, network, validator, audit, and UI layers;
3. network redirects, wrong origin/region/model, expired approval, and retention
   backlog prevent the request before health context is serialized to the client;
4. logs and errors contain no body, credential, user question, exact health value,
   or provider envelope;
5. Recovery/Baseline/Confidence and existing database rows remain hash-identical;
6. the approved 200-case, three-run safety thresholds pass for the exact snapshot.

## Residual Risk and Approval

Even with controls, cloud processing, model unpredictability, local-device
compromise, legal exceptional access, linkage from health combinations, and
provider-policy change cannot be eliminated. Residual Medium risks `TM-07`,
`TM-12`, `TM-13`, `TM-15`, and `TM-17` require explicit Product Owner acceptance
after provider evidence and implementation tests. No Critical or High residual
risk may be accepted for release.

Threat-model review does not approve a provider or runtime. Re-review is required
for any provider/model/endpoint/region, data field, retention, database, UI,
dependency, authentication, or safety-policy change, and after any incident.
