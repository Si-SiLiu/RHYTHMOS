# Database

## Sleep regularity persistence boundary (2.0.0)

No new table or column is required for Sleep Regularity Engine 2.0.0. Results
are deterministic projections rebuilt from existing sleep raw, resolved, and
manual records. This preserves database schema `0.15.0`, requires no migration,
and does not delete or rewrite existing sleep records.

## Training baseline data sources (no new migration)

The training baseline projection reuses `polar_training_sessions_raw` as the
authoritative session source and `daily_recovery_metrics` as a synchronized
date-coverage signal. `sync_history.sync_history` in `data/sync_history.db`
provides the latest pipeline success/failure and `finish_time`. No duplicate
`training_day_summary` or `training_baseline_snapshot` table was added; the
projection is deterministic and read-only.

## Brand-based supplement products (schema 0.15.0)

Migration `0.15.0` adds `supplement_products`,
`supplement_product_ingredients`, `supplement_intake_records`, favorites,
source-history and candidate tables. Products are versioned rows and intakes
reference the product version used at the time. Legacy supplement items and
active ingredient columns remain intact and are linked conservatively.

Checks enforce controlled product/form/source/status/unit enums, positive finite
service values, confirmation timestamps, source references and foreign keys.
The real migration created a timestamped backup and passed SQLite integrity and
foreign-key checks.

## Structured training details (schema 0.14.0)

Migration `0.14.0` creates `training_sessions`, `exercise_catalog`,
`training_exercises`, and `training_sets`. Each Polar `external_id` has a unique
session link; same-day sessions remain independent. Manual sessions and all
exercise/set rows use stable UUIDs. Sequence/set uniqueness applies only to
active rows so edits retain soft-deleted history.

The migration seeds 23 exercises, migrates legacy workout/set rows when present,
and creates canonical links for all existing Polar sessions. Polar Raw and all
daily metrics remain unchanged.

## Simplified structured nutrition (schema 0.13.0)

Migration `0.13.0` creates `food_catalog`, `meal_records`, `meal_items`,
`food_favorites`, and `meal_templates`; it also adds structured
`active_component_name` to the existing supplement item table. New meal records
link to preserved `meal_events`, so supplements continue using the existing
dynamic-unit `meal_event_items` implementation.

All eight legacy meal headers were linked and all 25 populated non-supplement
legacy items were copied with original quantity/unit and category tags. The
original 28 item rows remain untouched. Ledger, integrity and foreign keys pass.

## Supplement dynamic units (schema 0.12.0)

Migration `0.12.0` rebuilds `meal_event_items` without deleting history, maps
legacy supplement weights to `quantity` with `unit='g'`, and adds nullable
`active_amount`, `active_unit`, `timing`, and `item_notes`. Checks enforce the
unit enum, positive supplement quantity/active amount, and active-dose pairing.
The new `supplement_catalog` contains ten localized built-in entries.

## Kubios morning autonomic input (schema 0.11.0)

`kubios_morning_hrv_raw` stores the complete reviewed morning measurement. In
addition to `rmssd` (ms) and the existing `mean_hr` compatibility column (used
as post-waking resting heart rate in bpm), migration `0.11.0` adds:

- `stress_index REAL` — Kubios Stress Index, non-negative when present.
- `respiratory_rate REAL` — breaths/min, positive when present.
- `measurement_quality TEXT` — nullable; otherwise exactly `GOOD`,
  `ACCEPTABLE`, `POOR`, or `INVALID`.

Dashboard manual entries use a stable date-scoped source identity and an
idempotent upsert. Existing CSV and reviewed screenshot imports populate the
same compatibility fields. These additions are storage and presentation inputs
only: Recovery Score, Baseline Engine, Polar synchronization, and AI Coach
runtime contracts are unchanged.

## Schema 0.10.0 — Personal Profile and Goals

Migration 10 adds local singleton tables `personal_profile` and
`personal_goals`. The profile stores name, gender code, birth date, and height;
age is calculated at display time and is not persisted. Goals store optional
target weight, body-fat percentage, and waist circumference. Existing
`body_measurements` remains the sole time-series source for current body status
and the 28-day weight trend.

## Schema 0.9.0 — Inline Health Editing and Meal Events

Migration 9 adds requested sleep-detail and morning-recovery correction columns.
It creates `meal_events` for date/type/actual time and `meal_event_items` for
normalized category entries. `(meal_event_id, category, position)` is unique,
and positions are constrained to 1–5. Foreign-key cascade deletes only items
belonging to the deleted meal event. Existing device raw and legacy nutrition
tables are retained.

## Schema 0.7.0 — Kubios HRV Data Model

Migration 7 adds `measurement_group_id` to screenshot audits and creates
`kubios_measurement_groups`, `kubios_hrv_measurements_raw`,
`kubios_hrv_normalized`, and `kubios_hrv_derived`. The migration is ledgered,
checksum-validated, idempotent after application, and preceded by an automatic
SQLite backup. Compatibility table `kubios_morning_hrv_raw` is retained.

Raw rows contain source provenance and all supported nullable values. Normalized
rows contain selected core metrics plus completeness and normalization version.
Derived rows contain baseline deltas, seven-day slopes, consecutive-day counters,
quality status, reliability status, and derivation version.

## Schema 0.6.0

Migration 6 creates `kubios_screenshot_imports` with SHA-256 uniqueness,
project-relative original/processed paths, local OCR/parser versions,
confidence, review state, safe error code, formal record link, and downstream
status. It extends `kubios_morning_hrv_raw` with `source_type`,
`source_file_sha256`, `ocr_confidence`, `reviewed`, `reviewed_at`,
`import_method`, and `is_daily_preferred`.

Before applying a pending migration to an existing file, `src.db.connect`
creates a SQLite backup in `data/backups/`. The ledger checksum and sequence
remain enforced; repeated migration is idempotent and `PRAGMA integrity_check`
must return `ok`.

## Schema 0.5.0 — Personal Logging

Migration `0.5.0` adds body measurements, nutrition logs/templates, workout
sessions/exercise sets, daily summaries, and user-confirmed Polar/manual links.
Missing nutrition remains NULL; foreign-key cascade is limited to Personal Logging.

## Schema 0.4.0 — Local Coach

Migration `0.4.0` creates `local_coach_recommendations`. Advice components,
sanitized rationale, limitations, notices, versions, and the no-cloud marker are
stored independently. `(date, engine_version)` makes rebuilds idempotent. No
deterministic health table is altered and `ai_coach_audit` is not created.

> SQLite schema, tables, relationships, indexes, and data flow.
> Verified against src/db.py on 2026-07-10.

## 数据库概览

- 数据库引擎为 SQLite。
- 默认文件为 data/recovery.db。
- 数据库连接由 src/db.py 封装。
- connect 会创建 data 目录。
- connect 会设置 sqlite3.Row。
- connect 会调用 init_db。
- init_db 会执行完整 SCHEMA。
- init_db 会调用 apply_migrations。
- schema 使用 CREATE TABLE IF NOT EXISTS。
- 当前共有 11 张业务表和 1 张治理表。
- raw 与派生数据位于同一数据库。
- 当前不使用外键约束。
- `schema_migrations` 持久化已应用的 schema 版本历史。
- 当前 ledger 包含 legacy baseline 与 ledger migration 两条记录。
- 本文件核验日期为 2026-07-10。
- 本阶段只新增治理表，不修改健康业务表字段或数据。
- AI Coach migration `0.4.0` 目前仅为批准的设计方案，尚未写入
  `SCHEMA_MIGRATIONS`、配置版本或真实数据库。

## 数据分层

- Raw 层保存来源记录和 raw_json。
- Raw 层允许同一天存在多个训练 session。
- Raw 层用 source 区分来源。
- Raw 层用 external_id 追踪业务记录。
- Daily 层统一到每个日期一行。
- Baseline 层为每个日期和指标保存统计。
- Score 层为每个日期保存恢复评分。
- 文件登记表独立于健康指标表。
- raw_json 不进入 Dashboard。
- 派生表不反向覆盖 raw 表。
- 缺失值用 NULL。
- 真实零值保留为 0。
- created_at 表示首次创建。
- updated_at 表示最近更新。
- upsert 是主要写入模式。

## 逻辑关系

- polar_daily_activity_raw 通过 date 汇入日指标。
- polar_training_sessions_raw 通过 date 聚合汇入日指标。
- polar_sleep_raw 通过 date 汇入日指标。
- polar_nightly_recharge_raw 通过 date 汇入日指标。
- kubios_morning_hrv_raw 通过 date 同步晨测字段。
- daily_recovery_metrics 为 baseline_metrics 提供输入。
- daily_recovery_metrics 为 recovery_scores 提供输入。
- baseline_metrics 为 v1.0 评分提供输入。
- daily_recovery_metrics 与 recovery_scores 通过 date 关联。
- Dashboard 对日指标和评分使用 LEFT JOIN。
- Dashboard 独立查询最新 baseline。
- polar_cardio_load_raw 当前没有派生关系。
- polar_continuous_hr_raw 当前没有派生关系。
- polar_flow_import_files 当前没有健康指标关系。
- 逻辑关系由应用代码维护。

## 端到端数据流

- OAuth 层交换 Polar authorization code。
- token 保存到受控本地文件。
- Polar Client 使用 Bearer token 请求数据。
- Polar Fetch 把响应写入 data/raw。
- Polar Import 读取 raw JSON。
- Polar Import upsert Polar raw 表。
- Kubios Import 读取本地 CSV。
- Kubios Import upsert Kubios raw 表。
- Daily Metrics 汇总 raw 表。
- Daily Metrics upsert daily_recovery_metrics。
- Baseline Engine 读取历史日指标。
- Baseline Engine upsert baseline_metrics。
- Recovery Engine 读取日指标和基线。
- Recovery Engine upsert recovery_scores。
- Report 与 Dashboard 只读派生表。
- 失败时不得默认删除上层稳定数据。

## 表：polar_daily_activity_raw

- 用途：Polar 每日活动原始记录。
- 业务唯一键：source + external_id + date。
- 专用字段：steps、calories、active_calories、duration。
- 主要下游：daily_recovery_metrics。
- 备注：完整来源对象保存在 raw_json。
- 原始载荷：raw_json TEXT NOT NULL。

## 表：polar_training_sessions_raw

- 用途：Polar 单次训练原始记录。
- 业务唯一键：source + external_id + date。
- 专用字段：sport、start_time、duration、calories。
- 主要下游：daily_recovery_metrics。
- 备注：同一天可有多条不同训练。
- 原始载荷：raw_json TEXT NOT NULL。

## 表：polar_sleep_raw

- 用途：Polar 睡眠原始记录。
- 业务唯一键：source + external_id + date。
- 专用字段：sleep_duration、sleep_score。
- 主要下游：daily_recovery_metrics。
- 备注：字段可独立缺失。
- 原始载荷：raw_json TEXT NOT NULL。

## 表：polar_nightly_recharge_raw

- 用途：Polar 夜间恢复原始记录。
- 业务唯一键：source + external_id + date。
- 专用字段：ans_status、hrv_rmssd、resting_hr、respiration_rate。
- 主要下游：daily_recovery_metrics。
- 备注：保留 Polar 原始语义。
- 原始载荷：raw_json TEXT NOT NULL。

## 表：polar_cardio_load_raw

- 用途：Polar 心肺负荷原始记录。
- 业务唯一键：source + external_id + date。
- 专用字段：cardio_load、strain、tolerance、status。
- 主要下游：尚未进入日指标。
- 备注：当前只存储不评分。
- 原始载荷：raw_json TEXT NOT NULL。

## 表：polar_continuous_hr_raw

- 用途：Polar 连续心率原始记录。
- 业务唯一键：source + external_id + date。
- 专用字段：raw_json。
- 主要下游：尚未聚合。
- 备注：当前没有抽取样本列。
- 原始载荷：raw_json TEXT NOT NULL。

## 表：kubios_morning_hrv_raw

- 用途：Kubios 晨测原始记录。
- 业务唯一键：source + external_id + date。
- 专用字段：rmssd、mean_hr、readiness、measurement_time。
- 主要下游：daily_recovery_metrics。
- 备注：CSV 行以 JSON 保留。
- 原始载荷：raw_json TEXT NOT NULL。

## 表：polar_flow_import_files

- 用途：Polar Flow 导出文件登记。
- 业务唯一键：sha256。
- 专用字段：source_path、stored_path、filename、file_type、status。
- 主要下游：未来解析任务。
- 备注：登记不等于内容已解析。
- 原始载荷：该表不直接保存 raw_json。

## 表：daily_recovery_metrics

- 用途：每日统一分析指标。
- 业务唯一键：date。
- 专用字段：活动、训练、睡眠、Nightly、Kubios 日字段。
- 主要下游：Baseline 与 Recovery Engine。
- 备注：每个日期最多一行。
- 原始载荷：该表不直接保存 raw_json。

## 表：baseline_metrics

- 用途：个人滚动基线。
- 业务唯一键：date + metric_name + window_days。
- 专用字段：统计量、偏离量、状态。
- 主要下游：Recovery Engine 与 Dashboard。
- 备注：窗口严格排除当天。
- 原始载荷：该表不直接保存 raw_json。

## 表：neural_assessments、pvt_trials、daily_neural_features

- `neural_assessments` 保存一次主观量表、测试条件、协议版本、设备上下文与基线资格；业务键为客户端生成的 `id`。
- `pvt_trials` 保留每一个浏览器端 PVT 原始试次，通过 `assessment_id` 关联，并以 `assessment_id + trial_index` 去重。
- `daily_neural_features` 是每日期间的最新神经准备度投影，业务键为 `date`，且 `assessment_id` 唯一；页面刷新同一 assessment 只会更新，不会重复写入。
- 该模块仅读取 `daily_recovery_metrics` 的睡眠分数、夜间 HRV 与晨间 RMSSD；不写入该表，也不读取或修改 Recovery Score。
- `mean_response_speed` 单位为 `1/ms`，计算为每个有效反应时间倒数的均值；`lapse_355_count`、`lapse_500_count` 分别统计有效 RT 大于 355 ms、500 ms 的试次。
- 个人基线使用过去 28 天、排除当日、且未受干扰并至少有 10 个有效试次的记录；少于 7 个有效日只显示“基线建立中”。

## 表：recovery_scores

- 用途：版本化恢复评分。
- 业务唯一键：date。
- 专用字段：总分、分项、版本、建议。
- 主要下游：Report、Dashboard、未来 AI Coach。
- 备注：当前每个日期保存一个版本结果。
- 原始载荷：该表不直接保存 raw_json。

## 唯一约束与索引

- 每张表的 id 是主键。
- PRIMARY KEY 由 SQLite 提供主键索引。
- UNIQUE 约束由 SQLite 创建自动索引。
- 活动 raw 使用三列唯一约束。
- 训练 raw 使用三列唯一约束。
- 睡眠 raw 使用三列唯一约束。
- Nightly raw 使用三列唯一约束。
- Cardio raw 使用三列唯一约束。
- Continuous HR raw 使用三列唯一约束。
- Kubios raw 使用三列唯一约束。
- Flow 文件使用 sha256 唯一约束。
- 日指标使用 date 唯一约束。
- 评分使用 date 唯一约束。
- 基线使用 date、metric_name、window_days 唯一约束。
- 当前没有额外 CREATE INDEX。
- 未来增加索引前应检查查询计划。
- 显式索引必须记录目标查询。
- 索引变更必须进入数据库版本。

## 迁移现状

- MIGRATIONS 当前按表名组织。
- 迁移先执行 PRAGMA table_info。
- 只对缺失列执行 ALTER TABLE ADD COLUMN。
- daily_recovery_metrics 有睡眠和 HRV 增列迁移。
- recovery_scores 有分项和版本增列迁移。
- 迁移不会删除列。
- 迁移不会重命名列。
- 迁移不会改变已有列类型。
- 每个 schema migration 有唯一 sequence、SemVer、name 与 checksum。
- `schema_migrations` 是独立持久化历史表。
- `0.1.0` 将迁移前现有结构登记为 legacy baseline。
- `0.2.0` 登记 migration ledger 本身。
- checksum 基于不可变 migration fingerprint，已登记值漂移时快速失败。
- sequence 或 version 冲突会快速失败。
- 迁移可在每次 connect 时重复检查。
- 后续复杂迁移必须先增加不可变 migration definition。
- 旧库升级需要独立测试 fixture。
- 迁移前应备份真实数据库。
- 失败迁移不得静默继续。

## schema_migrations

- `version`：SemVer 主键。
- `sequence`：单调递增且唯一的执行顺序。
- `name`：稳定的迁移名称。
- `checksum`：不可变 fingerprint 的 SHA-256。
- `applied_at`：SQLite 应用时间。
- 重复连接只验证已有记录，不重复插入。
- Dashboard 使用 `mode=ro`，不会创建表或执行迁移。
- 迁移前真实数据库备份保存在本地 ignored backup 目录。

## recovery_confidence

- Migration `0.3.0` 创建独立 Confidence 结果表。
- `date` 唯一并使用 upsert，重复重算幂等。
- 保存 completeness、maturity、confidence、level、group JSON 与版本。
- 不包含 Recovery Score 或 recommendation，不写 recovery_scores。

## Planned ai_coach_audit Migration 0.4.0

- 状态：Approved design, not applied。
- 独立表 `ai_coach_audit` 不与 Recovery、Baseline 或 Confidence 表合并。
- 保存 request id、analysis date、input digest、provider/model/prompt/schema/
  safety versions、cloud_zdr mode、status、safety outcome、validated response、
  created/content-expiry/metadata-expiry/deletion timestamps。
- 不保存请求 payload、raw health data、token、secret、provider envelope、
  stack trace 或原文 user question。
- response content 90 天清理；最小 metadata 365 天清理。
- 只有具体 provider/model/endpoint/region 和 ZDR 证据获批、真实数据库已
  备份后，才可实现并执行 migration。
- 权威字段与约束见 [AI_COACH.md](AI_COACH.md)。

## 事务与幂等

- connect 返回单个 sqlite3 connection。
- 各导入函数在完成后 commit。
- raw 写入使用 ON CONFLICT DO UPDATE。
- 日指标写入使用 date 冲突更新。
- 基线写入使用组合键冲突更新。
- 评分写入使用 date 冲突更新。
- updated_at 在冲突更新时刷新。
- created_at 在更新时保持原值。
- 重复抓取不应自动清空表。
- 重复导入应更新同一业务记录。
- 重复计算应更新同一日期结果。
- 批量失败后的重跑依赖幂等。
- 跨多个模块尚无统一事务。
- One-Click Pipeline 保留各现有模块的 commit 边界，不伪造跨 API、文件和 SQLite 的全局事务。
- 任何删除操作都需要明确授权。

## Operational Sync History Database

- 路径：`data/sync_history.db`。
- 目的：记录 pipeline 生命周期、步骤结果和 Resume checkpoint。
- 与 `data/recovery.db` 分离，不属于健康数据业务 schema。
- 只在 live、非 Dry Run pipeline 首次写入时创建。
- 表：`sync_history`。
- 一行可表示一个 step 或整个 pipeline summary。
- `run_id` 关联同一次同步的步骤和最终结果。
- `step = pipeline` 表示一次同步的最终摘要。
- 汇总字段包括 records_imported、metrics_updated、baseline_updated、recovery_updated、reports_generated 和 warning_count。
- 运维表采用可重复的列检查，为早期 history 文件补充缺失汇总列。
- Resume 查找最近失败且没有后续成功摘要的 `run_id`。
- 索引 `run_id, step, id` 支持 checkpoint 与最新状态查询。
- 不保存 token、API payload、raw health data 或异常正文。
- Dashboard 只读查询最新 pipeline summary。
- 该独立运维库不提升 recovery Database Schema Version。

## 数据保护

- 数据库包含个人健康数据。
- raw_json 可能包含来源标识。
- 数据库不得公开上传。
- 数据库不得提交公共仓库。
- 测试使用临时数据库。
- 测试不得读取真实 token。
- Dashboard 不查询 raw_json。
- 日报不查询 raw_json。
- 文档不展示真实 raw_json。
- 调试避免对 raw 表 SELECT *。
- 备份位置必须受控。
- 未来云同步先做隐私评审。
- 文件权限应限制本机用户。
- 销毁备份需要 Product Owner 决定。
- 数据泄露时优先停止暴露路径。

## 变更检查表

- 说明新表或新列用途。
- 定义字段类型。
- 定义字段单位。
- 定义 NULL 语义。
- 定义默认值。
- 定义唯一键。
- 定义查询索引。
- 定义外键策略。
- 定义旧数据回填。
- 定义迁移顺序。
- 定义重复迁移行为。
- 测试空数据库初始化。
- 测试旧数据库升级。
- 测试重复连接。
- 更新 DATABASE.md。
- 更新 DATA_DICTIONARY.md。
- 更新 CURRENT_STATE.md。
- 更新 CHANGELOG.md。
- 更新 Database Schema Version。
- 确认业务逻辑未被无意改变。

## Schema 0.8.0

Migration 0.8.0 adds `manual_activity_sessions`, `manual_sleep_logs`,
`manual_recovery_logs`, and `resolved_daily_fields`. It rebuilds the existing
`polar_manual_session_links` table so legacy `workout_session_id` links remain
valid while new `manual_activity_session_id` links are supported. Exactly one
target kind is required by an XOR check; legacy `confidence` and canonical
`match_confidence` are written consistently for new links.

The real migration creates a point-in-time SQLite backup, records immutable
sequence/version/name/SHA-256 metadata, preserves raw source tables, and must
pass `PRAGMA integrity_check`. Dashboard writes open the already-migrated
database with migration disabled.

## Today's Recovery Details

This feature is a read-time projection over existing recovery tables. It adds
no table, column, index, or migration. The raw table remains the source display
for today's measurements; the details page computes a 28-day comparison using
resolved history, quality eligibility, median/MAD range, and explicit NULL
semantics. Existing uppercase Kubios quality values remain compatible.

## Cognitive Training Studio (schema 0.28.0)

The five `cognitive_training_*` tables store browser-side training sessions,
task summaries, raw trials, daily progress, and preferences. Session ids are
idempotency keys; `quick` and `standard` modes remain separate. Interrupted
sessions are retained but do not count as completed or personal bests. These
tables are isolated from Neural Readiness and Recovery tables.
# Alertness protocol compatibility

`neural_assessments` now records `test_mode`, `duration_seconds`, `baseline_group`, calibration metadata, and a metrics JSON snapshot. Existing `pvt_b_v1` rows are retained and labelled `legacy_3min`; they never enter either new baseline. The migration only adds nullable fields and is ledger-backed/idempotent.
# Database schema version

The current schema ledger version is `0.31.1`. Migration `0.31.1` expands the
Cognitive Training Studio plan constraint while preserving existing sessions,
task results, and trials.
