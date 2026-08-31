# Data Dictionary

## Canonical sleep regularity fields

- `CanonicalSleepRecord.sleep_date`: local sleep date.
- `sleep_start` / `sleep_end`: timezone-aware local datetimes; cross-midnight
  intervals are allowed.
- `actual_sleep_duration`: minutes of actual sleep; missing is never zero.
- `sleep_segments`: optional `asleep`, `awake`, or `unknown` timeline segments.
- `algorithm_type`: `sri_timeline`, `summary_composite`,
  `insufficient_data`, or `unavailable`.
- `maturity_status`: `collecting`, `provisional`, `reliable`, or `stable`.
- `regularity_status`: output of `map_score_to_status()`.
- `calculation_version`: `2.0.0` for the current sleep regularity algorithm.

## Training baseline projection fields

`src.training_baseline.build_training_baseline_view` returns `TrainingDay`
style dictionaries with `date`, `status`, `session_count`,
`total_duration_minutes`, `total_training_calories_kcal`, `last_synced_at`,
`sync_status`, `is_day_complete`, `is_planned_rest_day`,
`data_completeness`, `comparison_allowed`, and independent duration/calorie
completeness flags. `training_duration` and `training_calories` use separate
valid-day counts; `NULL` is never converted to zero.

## `training_sessions` (Schema 0.14.0)

- `polar_external_id`: nullable, unique exact link to Polar Raw.
- `polar_sport_type`: immutable original device type.
- `resolved_sport_type` and source: displayed type and `manual_override` audit.
- Objective fields are Polar-authoritative when linked; manual-only otherwise.
- `status`: `draft` or `completed`; `deleted_at` implements soft deletion.

## `training_exercises` and `training_sets`

- Exercises have UUID, session FK, catalog/custom identity, order, category,
  measurement mode, muscle, equipment, laterality, proficiency and notes.
- Sets have UUID, active set number, type, load/unit, repetitions, duration,
  distance, resistance, incline, RPE/RIR, rest, side, completion and notes.
- Load units are `kg`, `lb`, `bodyweight`, `assisted_kg`, `none`.
- Set numbers and exercise sequence are unique among non-deleted siblings.

## `exercise_catalog`

Bilingual canonical actions define category, movement pattern, muscles,
equipment, measurement mode and unilateral default. Custom actions remain local
to a session unless explicitly added in a future catalog workflow.

## `meal_records` and `meal_items` (Schema 0.13.0)

- Meals use unique UUID, date/type/time, draft/completed status, source and soft deletion.
- `legacy_meal_event_id` preserves old rows and the existing supplement system.
- Items preserve raw `quantity + unit`; quantity is positive and unit enumerated.
- Normalized weight/volume and eight nutrient fields are nullable and never guessed.
- Multi-tag classification uses JSON; unknown food remains unclassified.

## `food_catalog`, `food_favorites`, `meal_templates`

- Catalog rows store bilingual names, aliases, unit rules, tags, explicit serving
  conversion, nullable nutrition, source and quality.
- Favorites reference catalog rows. Templates preserve food and supplement payloads.

## 表：personal_profile（Schema 0.10.0）

- 用途：在本机保存单一用户的姓名、性别代码、生日和身高。
- 主键：固定为 `id = 1`，重复保存执行更新，不产生重复资料。
- 年龄：不落库；每次展示时根据 `birth_date` 与当前日期计算。

## 表：personal_goals（Schema 0.10.0）

- 用途：保存可选的目标体重、目标体脂和目标腰围。
- 主键：固定为 `id = 1`，所有目标允许保持 `NULL`。
- 边界：体重不超过 500 kg，体脂不超过 100%，腰围不超过 300 cm。

## 表：body_measurements（个人信息页复用）

- 用途：保存按日期记录的身高、体重、体脂和腰围。
- 展示：最新记录用于“身体状态”，最近 28 天记录用于体重趋势。

## 表：meal_events（Schema 0.9.0）

- 用途：保存一次实际餐次事件。
- 字段：date、meal_type、actual_meal_time、notes、审计时间戳。
- 餐次：早餐、上午加餐、午餐、下午加餐、晚餐、训练补给、睡前补给、自由加餐。

## 表：meal_event_items（Schema 0.12.0）

- 用途：保存餐次内按分类排列的具体种类、剂量和单位。
- 分类：碳水、蛋白质、脂肪、蔬菜、水果、乳制品、坚果、补剂、水分、咖啡因、酒精。
- 补剂字段：item_name、quantity、unit、可选成对字段 active_amount / active_unit、timing、item_notes。
- 补剂约束：quantity 大于 0；单位来自统一枚举；有效成分剂量与单位同时为空或同时存在。
- 删除：随所属 meal_event 外键级联删除。

## 表：supplement_catalog（Schema 0.12.0）

- 用途：保存补剂中英文名称、默认单位、允许单位与激活状态。
- 内置 10 条记录，canonical_name 唯一。

## Kubios HRV Data Model 1.0 fields

- Raw identity/provenance: `date`, `measurement_time`, `measurement_group_id`,
  `source_type`, `source_file_sha256`, `import_method`, `parser_version`,
  `reviewed`, `ocr_confidence`, `selected_as_primary`, `selection_reason`,
  `source_priority`, `raw_json`.
- Raw measurements: `mean_rr_ms`, `mean_hr_bpm`, `rmssd_ms`, `sdnn_ms`,
  `poincare_sd1_ms`, `poincare_sd2_ms`, `stress_index`,
  `respiratory_rate_bpm`, `lf_power_ms2`, `hf_power_ms2`, `lf_power_nu`,
  `hf_power_nu`, `lf_hf_ratio`, `readiness_percent`, `pns_index`, `sns_index`,
  `physiological_age`, `measurement_quality`, `mood_code`, `recovery_status`,
  `artefact_correction_percent`, `measurement_duration_seconds`.
- Normalized governance: `source_raw_table`, `source_raw_id`,
  `core_data_completeness`, `normalization_version`.
- Derived: eight baseline comparison fields, five seven-day trend fields, three
  consecutive-day counters, `data_quality_status`,
  `source_reliability_status`, and `derivation_version`.

All unavailable measurement values are SQL `NULL`; zero is never substituted.
Percent fields are stored in display-percent units, time in ISO text, duration in
seconds, heart rate/respiration in per-minute units, and power in ms².

## kubios_screenshot_imports

- `file_sha256`: duplicate-safe content identity; unique.
- `original_relative_path`, `processed_relative_path`: local project-relative
  paths, never network locations.
- `import_status`: stable code such as `review_required`,
  `needs_manual_input`, `parsing_failed`, `imported`, or `skipped_existing`.
- `ocr_engine`, `ocr_engine_version`, `parser_version`: reproducibility facts.
- `ocr_text_summary`: field-name summary only; never complete OCR text.
- `overall_ocr_confidence`: recognition confidence, not health confidence.
- `reviewed`, `reviewed_at`, `imported_record_id`: explicit review audit.
- `downstream_updated`: whether the selected local rebuild completed.

## kubios_morning_hrv_raw additions

`source_type` and `import_method` use stable English codes. Screenshot records
use `screenshot_ocr`, `reviewed = 1`, and their file hash. CSV is the default
daily source unless `is_daily_preferred` records an explicit user override.

> Canonical meanings, units, sources, and missing-value rules.
> Verified against the current schema and algorithms on 2026-07-10.

## 字典使用规则

Schema `0.5.0` adds cm, kg, percent, kcal, g, ml, mg, minutes, seconds, metres,
0–10 RPE/energy/soreness and non-negative RIR. Unentered values are NULL;
measured zero remains 0.

- 字段名称以数据库列名为准。
- 来源字段先保留原始语义。
- 单位在导入或分析边界统一。
- NULL 表示未知或未提供。
- 零表示已知的零。
- NULL 与零不得互换。
- 文本枚举应记录来源映射。
- raw_json 是审计字段。
- raw_json 不是 Dashboard 字段。
- 字段改名必须提供迁移。
- 字段语义变化必须更新版本。
- 评分字段变化同步 Recovery Engine 文档。
- 来源变化同步 API 文档。
- 示例不得包含真实敏感载荷。
- 字典核验日期为 2026-07-10。

## 字段：date

- 单位或格式：YYYY-MM-DD。
- 来源：Polar、Kubios 或日聚合。
- 意义：记录所属自然日，也是跨派生表逻辑关联键。
- 缺失处理：缺失时 raw 导入通常跳过该记录。

## 字段：source

- 单位或格式：枚举文本。
- 来源：导入模块。
- 意义：标识数据来源，例如 polar 或 kubios。
- 缺失处理：raw 表必填。

## 字段：external_id

- 单位或格式：来源标识文本。
- 来源：外部记录或稳定派生。
- 意义：在同一来源内识别业务记录。
- 缺失处理：缺失且无法派生时跳过。

## 字段：raw_json

- 单位或格式：JSON 文本。
- 来源：原始 API 或 CSV 行。
- 意义：审计、重放和未来字段修复。
- 缺失处理：raw 表必填但禁止直接展示。

## 字段：steps

- 单位或格式：步。
- 来源：Polar daily activity。
- 意义：当天步数，属于活动负荷输入。
- 缺失处理：NULL 表示没有来源数据，0 表示来源记录为零。

## 字段：calories

- 单位或格式：kcal。
- 来源：Polar daily activity。
- 意义：当天总热量字段，当前用于报告与展示。
- 缺失处理：缺失保留 NULL。

## 字段：active_calories

- 单位或格式：kcal。
- 来源：Polar daily activity。
- 意义：活动相关热量，是活动负荷输入。
- 缺失处理：缺失时可使用其他可用负荷项。

## 字段：activity_duration

- 单位或格式：ISO 8601 duration。
- 来源：Polar daily activity。
- 意义：当天活动时长。
- 缺失处理：缺失保留 NULL，展示时转小时。

## 字段：training_count

- 单位或格式：次。
- 来源：训练 sessions 聚合。
- 意义：当天训练记录数量。
- 缺失处理：无训练日期默认 0。

## 字段：training_duration

- 单位或格式：ISO 8601；基线转分钟。
- 来源：训练 sessions 聚合。
- 意义：当天全部训练持续时间，是训练负荷输入。
- 缺失处理：无训练可为 NULL，聚合按 0 秒处理。

## 字段：training_calories

- 单位或格式：kcal。
- 来源：训练 sessions 聚合。
- 意义：当天训练消耗，是训练负荷输入。
- 缺失处理：无训练默认 0。

## 字段：sport

- 单位或格式：Polar 枚举文本。
- 来源：Polar training session。
- 意义：单次训练项目类型。
- 缺失处理：缺失允许 NULL。

## 字段：start_time

- 单位或格式：ISO 日期时间文本。
- 来源：Polar training session。
- 意义：单次训练开始时间。
- 缺失处理：缺失时保留 NULL。

## 字段：sleep_duration

- 单位或格式：ISO 8601；基线转小时。
- 来源：Polar sleep。
- 意义：当天睡眠时长，用于恢复能力。
- 缺失处理：缺失时 readiness 分项可部分计算。

## 字段：sleep_score

- 单位或格式：通常 0–100。
- 来源：Polar sleep。
- 意义：Polar 睡眠质量评分。
- 缺失处理：缺失时不参与可用恢复分项。

## 字段：ans_status

- 单位或格式：Polar 状态文本。
- 来源：Nightly Recharge。
- 意义：自主神经系统恢复状态原始分类。
- 缺失处理：当前不直接进入评分。

## 字段：nightly_hrv_rmssd

- 单位或格式：ms。
- 来源：Polar Nightly Recharge。
- 意义：夜间 RMSSD 恢复信号。
- 缺失处理：缺失时可使用 morning_rmssd。

## 字段：nightly_resting_hr

- 单位或格式：bpm。
- 来源：Polar Nightly Recharge。
- 意义：夜间平均或静息心率信号。
- 缺失处理：缺失时可使用 morning_mean_hr。

## 字段：respiration_rate

- 单位或格式：来源数值。
- 来源：Polar Nightly Recharge。
- 意义：夜间呼吸频率恢复信号。
- 缺失处理：缺失不阻塞其他评分项。

## 字段：morning_rmssd

- 单位或格式：ms。
- 来源：Kubios Morning HRV CSV。
- 意义：晨测 RMSSD，是个人基线恢复能力输入。
- 缺失处理：没有 CSV 时保持 NULL。

## 字段：morning_mean_hr

- 单位或格式：bpm。
- 来源：Kubios Morning HRV CSV。
- 意义：晨测平均心率。
- 缺失处理：缺失时可使用 nightly_resting_hr。

## 字段：kubios_readiness

- 单位或格式：文本或数值字符串。
- 来源：Kubios Morning HRV CSV。
- 意义：Kubios readiness 状态或分值。
- 缺失处理：不可解析时 baseline 视为缺失。

## 字段：measurement_time

- 单位或格式：ISO 日期时间或时间文本。
- 来源：Kubios CSV。
- 意义：晨测发生时间并可参与 external_id。
- 缺失处理：缺失时 external_id 可回退 date。

## 字段：cardio_load

- 单位或格式：Polar 数值。
- 来源：Polar cardio load。
- 意义：Polar 心肺负荷原始指标。
- 缺失处理：当前未进入 daily metrics。

## 字段：strain

- 单位或格式：Polar 数值。
- 来源：Polar cardio load。
- 意义：近期短期负荷概念。
- 缺失处理：当前仅 raw 表保存。

## 字段：tolerance

- 单位或格式：Polar 数值。
- 来源：Polar cardio load。
- 意义：较长期负荷耐受概念。
- 缺失处理：当前仅 raw 表保存。

## 字段：recovery_score

- 单位或格式：0–100 整数。
- 来源：Recovery Engine。
- 意义：当天综合恢复评分。
- 缺失处理：recovery_scores 中必填。

## 字段：activity_load_score

- 单位或格式：0–100 整数。
- 来源：Recovery Engine。
- 意义：活动负荷分项，越高表示负荷越高。
- 缺失处理：必填，可使用 fallback。

## 字段：training_load_score

- 单位或格式：0–100 整数。
- 来源：Recovery Engine。
- 意义：训练负荷分项，越高表示负荷越高。
- 缺失处理：必填，可使用 fallback。

## 字段：hrv_score

- 单位或格式：0–100 整数。
- 来源：Recovery Engine。
- 意义：HRV 恢复能力分项，越高越有利。
- 缺失处理：无可用 HRV 时为 NULL。

## 字段：morning_hr_score

- 单位或格式：0–100 整数。
- 来源：Recovery Engine。
- 意义：心率与呼吸方向分项，越高越有利。
- 缺失处理：无可用心率时为 NULL。

## 字段：readiness_score

- 单位或格式：0–100 整数。
- 来源：Recovery Engine。
- 意义：睡眠、时长和 readiness 聚合分项。
- 缺失处理：无可用输入时为 NULL。

## 字段：score_version

- 单位或格式：版本文本。
- 来源：Recovery Engine。
- 意义：解释该行评分使用的算法路径。
- 缺失处理：必填。

## 字段：recommendation

- 单位或格式：中文枚举文本。
- 来源：Recovery Engine。
- 意义：与恢复分数区间对应的训练建议。
- 缺失处理：必填。

## 字段：window_days

- 单位或格式：天。
- 来源：Baseline config。
- 意义：滚动历史窗口长度。
- 缺失处理：baseline_metrics 中必填，默认 28。

## 字段：valid_days

- 单位或格式：天数。
- 来源：Baseline Engine。
- 意义：异常处理后参与统计的有效历史值数量。
- 缺失处理：少于 7 时 insufficient_data。

## 字段：metric_name

- 单位或格式：字段标识文本。
- 来源：Baseline config。
- 意义：被计算基线的指标名称。
- 缺失处理：与 date、window_days 组成唯一键。

## 字段：mean_value

- 单位或格式：指标自身单位。
- 来源：Baseline Engine。
- 意义：有效历史值均值。
- 缺失处理：没有历史值时 NULL。

## 字段：median_value

- 单位或格式：指标自身单位。
- 来源：Baseline Engine。
- 意义：有效历史值中位数，主要个人基准。
- 缺失处理：没有历史值时 NULL。

## 字段：std_value

- 单位或格式：指标自身单位。
- 来源：Baseline Engine。
- 意义：总体标准差。
- 缺失处理：全部相同可为 0。

## 字段：mad_value

- 单位或格式：指标自身单位。
- 来源：Baseline Engine。
- 意义：中位绝对偏差。
- 缺失处理：全部相同可为 0。

## 字段：min_value

- 单位或格式：指标自身单位。
- 来源：Baseline Engine。
- 意义：窗口有效值最小值。
- 缺失处理：没有历史值时 NULL。

## 字段：max_value

- 单位或格式：指标自身单位。
- 来源：Baseline Engine。
- 意义：窗口有效值最大值。
- 缺失处理：没有历史值时 NULL。

## 字段：latest_value

- 单位或格式：指标自身单位。
- 来源：Baseline Engine。
- 意义：被评估日期当天值。
- 缺失处理：当天缺失时 NULL。

## 字段：percent_change

- 单位或格式：百分比。
- 来源：Baseline Engine。
- 意义：当天值相对中位数变化。
- 缺失处理：中位数为 0 或缺失时 NULL。

## 字段：z_score

- 单位或格式：标准差倍数。
- 来源：Baseline Engine。
- 意义：当天值相对均值的标准 z 分数。
- 缺失处理：std 为 0 时特殊处理。

## 字段：robust_z_score

- 单位或格式：稳健标准分。
- 来源：Baseline Engine。
- 意义：基于 median 与 MAD 的偏离。
- 缺失处理：MAD 为 0 时特殊处理。

## 字段：status

- 单位或格式：枚举文本。
- 来源：Baseline Engine。
- 意义：insufficient、below、within 或 above baseline。
- 缺失处理：数据不足时明确 insufficient_data。

## 字段：created_at

- 单位或格式：SQLite timestamp。
- 来源：数据库默认值。
- 意义：记录首次创建时间。
- 缺失处理：必填默认 CURRENT_TIMESTAMP。

## 字段：updated_at

- 单位或格式：SQLite timestamp。
- 来源：upsert 逻辑。
- 意义：记录最近更新时间。
- 缺失处理：必填默认 CURRENT_TIMESTAMP。

## Baseline 状态枚举

- insufficient_data 表示有效历史少于最低门槛或当天缺失。
- below_baseline 表示当天值显著低于个人历史。
- within_baseline 表示当天值位于个人常见范围。
- above_baseline 表示当天值显著高于个人历史。
- 状态方向不等于好坏。
- HRV below 通常解释为恢复压力。
- 静息心率 above 通常解释为恢复压力。
- 训练负荷 above 通常解释为恢复压力。
- 负荷 below 可解释为相对较轻。
- 状态优先由 robust z-score 分类。
- robust z 不可用时可用 z-score。
- 标准分不可用时可参考 percent change。
- 状态只针对指定 window_days。
- 当前默认 window_days 为 28。
- 状态不能用于人群比较。

## Recommendation 枚举

- 正常训练对应 recovery_score 80–100。
- 适度训练对应 recovery_score 60–79。
- 减量训练对应 recovery_score 40–59。
- 恢复优先对应 recovery_score 0–39。
- 建议由确定性评分区间生成。
- 建议不是医疗结论。
- 建议不考虑未录入伤病。
- 建议不替代用户主观感受。
- 建议文本变化需要评审。
- 区间变化属于评分行为变化。
- 未来 AI Coach 可解释建议。
- 未来 AI Coach 不能覆盖原建议事实。

## 指标方向

- nightly_hrv_rmssd：higher_is_better。
- morning_rmssd：higher_is_better。
- nightly_resting_hr：lower_is_better。
- morning_mean_hr：lower_is_better。
- respiration_rate：lower_is_better。
- sleep_score：higher_is_better。
- sleep_duration：higher_is_better。
- kubios_readiness：higher_is_better。
- steps：higher_is_load。
- active_calories：higher_is_load。
- training_duration：higher_is_load。
- training_calories：higher_is_load。
- 方向只用于当前个人基线模型。
- 方向改变必须产生算法评审。
- 单项偏离不能独立诊断恢复状态。

## 单位转换

- ISO 8601 duration 由公共解析函数转换。
- sleep_duration 在 baseline 中转小时。
- training_duration 在 baseline 中转分钟。
- activity_duration 展示时可转小时。
- 数字字符串可以转换为秒。
- 无法解析的 duration 视为缺失。
- 负 duration 不应作为有效输入。
- RMSSD 使用毫秒。
- 心率使用 bpm。
- 热量使用 kcal。
- 步数使用整数步。
- 百分比变化以中位数为分母。
- 中位数为零时 percent_change 为 NULL。
- 展示单位不应改变数据库原值。
- 未来时区字段需单独定义。

## sync_history Operational Fields

- `id`：SQLite 自增主键。
- `run_id`：一次同步的随机关联标识；不是用户或设备标识。
- `start_time` / `finish_time`：带时区 ISO 时间。
- `duration`：步骤或 pipeline 的 wall-clock 秒数，REAL。
- `success`：0/1 布尔结果。
- `step`：token、fetch、import、metrics、baseline、recovery、report、governance 或 pipeline。
- `message`：受控状态文本，只记录完成、停止步骤和异常类型。
- `records_imported`：本次新增 raw 记录净数，不等于处理或 upsert 总数。
- `metrics_updated`：Daily Metrics upsert 的日期记录数。
- `baseline_updated`：现有 Baseline Engine 返回的处理记录数。
- `recovery_updated`：现有 Recovery Engine upsert 的评分记录数。
- `reports_generated`：生成的 Markdown report 文件数。
- `warning_count`：能力型 endpoint 失败等非阻断警告数量。
- 这些字段属于独立运维历史，不是恢复指标或医疗数据字段。

## schema_migrations Governance Fields

- `version`：数据库 schema SemVer，TEXT 主键。
- `sequence`：迁移顺序，INTEGER 且唯一。
- `name`：不可变迁移名称。
- `checksum`：迁移 fingerprint 的 SHA-256 十六进制字符串。
- `applied_at`：SQLite CURRENT_TIMESTAMP，记录首次登记时间。
- 该表不保存健康指标、账号、token 或 raw payload。

## recovery_confidence Fields

- `date`：Confidence 目标日期，唯一。
- `data_completeness_score`：当天六组信号覆盖度，0–100。
- `baseline_maturity_score`：个人历史成熟度，0–100。
- `confidence_score`：55% completeness + 45% maturity，0–100。
- `confidence_level`：high、medium、low、very_low。
- `group_scores_json`：每组 completeness 与 maturity 明细。
- `available_groups_json` / `missing_groups_json`：可用与完全缺失组。
- `confidence_version`：统一 Confidence Engine SemVer。

## Planned ai_coach_audit Fields

这些字段属于未执行的未来 Cloud AI audit migration 设计，不是当前数据库事实。Local Coach migration `0.4.0` 不包含这些字段：

- `request_id`：本地生成的唯一请求标识，不是 provider account id。
- `analysis_date`：解释对应的本地日期。
- `input_snapshot_digest`：closed outbound object 的不可逆摘要。
- `provider_id` / `model_version`：获批 provider 与精确模型标识。
- `prompt_version` / `output_schema_version` / `safety_policy_version`：独立契约版本。
- `provider_mode`：当前为 `cloud_standard_retention`；如未来获批 ZDR，可切换为 `cloud_zdr`。
- `status`：allowlisted request lifecycle 状态。
- `safety_outcome`：allowlisted 安全分类，不含原始 prompt。
- `response_json`：nullable，仅保存验证后的输出 schema，90 天过期。
- `created_at` / `content_expires_at` / `metadata_expires_at` / `deleted_at`：保留与删除审计时间。

## Manual health and resolution fields

- `manual_activity_sessions`: local activity context, measured-field fallbacks,
  confirmed semantic type correction, optional Polar link, and timestamps.
- `manual_sleep_logs`: local sleep timing/duration fallback plus subjective
  quality, awakenings, nap, and optional notes. It has no device sleep-stage,
  score, HRV, respiration, or heart-rate columns.
- `manual_recovery_logs`: 1–10 subjective recovery/fatigue/soreness/energy/
  motivation/stress, pain presence/location, optional notes, and timestamps.
- `resolved_daily_fields.resolved_value_json`: JSON representation of one
  canonical value; `NULL` semantics remain explicit.
- `value_source`: `polar`, `kubios`, `manual`, `estimated`, or `missing`.
- `is_fallback`: true only when a lower-priority permitted source filled a gap.
- `is_manual_override`: true only for a confirmed activity-type correction.
- `resolution_reason` and `resolution_version`: deterministic audit explanation
  and policy version.

## Today Recovery Details Derived Fields

The details layer is a read-time projection and adds no database columns or
tables. It reads `daily_recovery_metrics`/resolved recovery fields together
with `kubios_morning_hrv_raw` history. Its internal quality vocabulary is
`excellent`, `good`, `average`, `poor`, `unusable`, and `missing`; legacy raw
values remain readable and are normalized only at the analysis boundary.
`NULL`, non-finite values, and respiration rate `0` remain missing and are
excluded from the 28-day baseline. Only `excellent` and `good` records are
eligible baseline samples.
# Supplement product fields (schema 0.15.0)

- `supplement_products`: versioned brand/product identity, barcode, region,
  dosage form, `product_kind`, serving definition, formula/label version,
  provenance, verification and supersession.
- `supplement_product_ingredients`: product-scoped ingredient name,
  amount/unit per serving, role, source, confidence and confirmation.
- `supplement_intake_records`: meal-scoped product reference or custom
  brand/product, positive quantity, controlled unit, intake time and source.
- `supplement_product_candidates`: source-bearing, non-authoritative search/OCR
  result with explicit pending/confirmed/rejected/deferred status.

## Neural Readiness MVP fields

- `neural_assessments.id`: client-generated assessment/session identifier. The
  same identifier is an idempotency key for a refreshed completed test.
- Four subjective scores (`mental_fatigue`, `mental_clarity`,
  `task_motivation`, `physical_heaviness`) are integers from 0 to 10; they are
  personal observations, not diagnostic values.
- `pvt_trials.reaction_time_ms`: browser `performance.now()` response minus
  stimulus time in milliseconds. RT below 100 ms and pre-stimulus input are
  stored as false starts and are not valid trials.
- `mean_response_speed`: mean of `1 / reaction_time_ms` across valid trials,
  expressed in `1/ms`; it is not a recovery score.
- `lapse_355_count` and `lapse_500_count`: valid trials with RT strictly above
  355 ms and 500 ms respectively.
- `valid_for_baseline`: false for interrupted sessions and sessions with fewer
  than 10 valid trials. Baselines use a 28-day window that excludes today.
- `baseline_deviations_json`: per-metric personal median, absolute/percent
  deviation and z-score. It does not modify `baseline_metrics`.

## Cognitive Training Studio fields

- `cognitive_training_sessions.training_plan`: `focus_alertness` or
  `working_memory`; `session_mode` is `quick` or `standard`.
- `cognitive_training_task_results`: one row per ordered task, with protocol,
  difficulty start/end, accuracy, score and nullable RT summaries.
- `cognitive_training_trials`: raw browser trial payload and response; missing
  values remain `NULL`, never a synthetic zero.
- `cognitive_training_progress`: daily participation projection; trend
  consumers must filter by plan, mode, protocol and comparable difficulty.
- `sensitivity_d_prime`: finite N-back sensitivity using log-linear correction;
  extreme hit or false-alarm rates never produce infinity.
# Alertness Probe fields

`test_mode`: `daily_short`, `weekly_calibration`, or `legacy_3min`. `mean_response_speed` is the mean of `1 / RT_ms`, in **1/ms** (higher is faster). `fastest_20pct_rt_ms` and `slowest_20pct_rt_ms` are short-protocol summaries; lapse counts remain auxiliary.
