# Local Deterministic Coach

Confirmed screenshot data can feed the existing daily metrics before a local
rebuild. OCR text and confidence never enter Local Coach, and OCR failures do
not produce advice. Local Coach now combines sleep, physical training, Neural
Readiness, and recorded nutrition when deciding the day's training adjustment.

## Boundary

Personal Logging and AI Context Export do not change Local Coach rules,
version, persisted recommendations, or its cloud boundary.

Local Coach Engine `1.0.0` is an on-device deterministic interpretation
sidecar. Its dependency direction is `Daily Metrics → Baseline → Recovery →
Confidence + Sleep/Training/Neural/Nutrition Context → Local Coach → Report /
Dashboard`.
It reads existing results and never recalculates Recovery Score, Recovery
Confidence, or Personal Baseline. It has no provider, network, credential,
API-key, or cloud-model dependency. Cloud AI remains a separate blocked path and
`model_version` remains `unreleased`.

## Rules and outputs

Rules are centralized in `config/local_coach_rules.json`; the output contract is
`config/local_coach_output.schema.json`. These transparent engineering rules
define score/confidence bands, completeness, sleep/load thresholds, fixed
training schedules, and adjustment percentages. They are not clinically validated.

Every output contains morning strength, evening Hip-Hop, a combined training
summary, sleep, hydration, nutrition, recovery, limitations, safety notices,
sanitized rationale, versions, historical freshness, and
`generated_without_cloud_ai=true`.

## Safety

Low confidence, low completeness, missing Recovery Score, or conflicting evidence
triggers conservative degradation. Missing Recovery Score prevents an intensity
conclusion. Only symptoms explicitly supplied by a future caller are eligible for
urgent-keyword handling. The engine does not infer symptoms from health metrics
and never provides diagnosis, medication, treatment plans, or precise intake doses.

## Commands

```bash
.venv/bin/python -m src.local_coach.engine
.venv/bin/python -m src.local_coach.engine --date YYYY-MM-DD
.venv/bin/python -m src.local_coach.engine --all
.venv/bin/python -m src.local_coach.engine --dry-run
.venv/bin/python -m src.sync_pipeline --only local-coach
```

CLI summaries contain aggregate counts and classifications only.

## Persistence and freshness

Migration `0.4.0` creates `local_coach_recommendations`, uniquely keyed by
`(date, engine_version)`. Upsert is idempotent and Dashboard access is read-only.
It does not create `ai_coach_audit` or change cloud runtime readiness. Advice
older than the configured freshness window is labeled historical.

> 本建议由本地确定性规则生成，不构成医疗诊断或治疗意见。

Dashboard and reports localize Local Coach presentation from stable status
codes. Stored recommendation JSON and deterministic rules are not translated
or recalculated. Both languages include the complete local-rule and medical
boundary statement; Local Coach is never labeled as Cloud AI Coach.

## Longitudinal evaluation

`python -m src.local_coach.evaluation --require-pass` performs a read-only
retrospective consistency gate. Thresholds live in
`config/local_coach_evaluation.json`. It reports aggregate Schema, deterministic
match, safety notice, no-cloud marker, uniqueness, coverage, status, and
transition results without emitting health values or advice JSON.

Fresh-data collection follows
[`LOCAL_COACH_PROSPECTIVE_EVALUATION.md`](LOCAL_COACH_PROSPECTIVE_EVALUATION.md).

Recorded nutrition and manual training summaries are read as context; missing
or incomplete records are reported as limitations and do not silently become
zero. A Neural Readiness result can reduce the next session when fatigue,
heaviness, slower-than-baseline responses, or repeated lapses cross the local
rules. Nutrition deficits influence fueling guidance and only contribute to
training reduction when combined with other recovery pressure.

After a local nutrition, physical-training, or Neural Readiness save/delete,
the affected date's recommendation is rebuilt synchronously when a recovery
score exists. Polar and sleep changes continue to rebuild through the normal
sync pipeline.
