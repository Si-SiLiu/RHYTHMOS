# Testing

## Sleep Regularity Engine 2.0

`tests/test_sleep_regularity.py` covers maturity gates, missing-data semantics,
unified score/status mapping, cross-midnight intervals, circular centers and
MAD, robust components and weights, outlier resistance, last-night reference
exclusion and signed deviations, SRI coverage/matching, and duplicate-date
selection. The existing Sleep card layout remains a UI regression contract.

## Training baseline coverage

`tests/test_training_baseline.py` covers missing/sync-error states, open-day
no-training, planned rest, real zero calories, multi-session accumulation,
deduplication, independent duration/calorie samples, median/IQR ranges,
maturity thresholds, seven-day load, fourteen-day missing-date distinction,
and comparison labels. The service is tested without Streamlit or external
network access.

## Local Coach coverage

Tests cover score bands, schedules, reductions, sleep/load combinations, missing
values, Confidence/completeness degradation, conflicting evidence, explicit
urgent-input fallback, output Schema, sanitized rationale, idempotent storage,
dry-run, selective Pipeline execution, history, Dashboard degradation, and the
report disclaimer.

Longitudinal evaluation tests additionally inject tampered JSON, missing safety
notices, insufficient date coverage, missing tables, and invalid configuration;
the evaluator fails closed and performs no writes.

Prospective protocol tests prove that pre-protocol history, future dates, and
late backfills are excluded; timely unique dates can pass and progress checks
remain read-only.

> Test strategy, commands, fixtures, and completion gates.
> Current totals are generated in [../project_state.json](../project_state.json).

## 统一命令

- 推荐使用项目虚拟环境。
- 完整命令为 .venv/bin/python -m unittest discover -s tests。
- 激活环境后可用 python -m unittest discover -s tests。
- 单文件可用 python -m unittest tests.test_module。
- 语法检查使用 python -m py_compile。
- 测试失败返回非零状态。
- 完成报告记录 Ran 数量。
- 当前测试数量不得手工写入本文。
- 使用 `scripts/update_project_state.py` 运行并记录完整结果。

## Cognitive Training practice coverage

`tests/test_cognitive_training.py` verifies the isolated 5-second practice shell for Visual Search, Memory Grid, Sequence Memory and N-back Lite: countdown exclusion, fixed entry-level stimuli, feedback rules, retry cleanup, formal-start cleanup, focus-loss reset, and the absence of practice calls to formal trial recording. It also verifies valid 1-back and 2-back practice sequences and preserves Target Focus and Go / No-Go protocol checks.

## 目录与命名

- 测试位于 tests。
- 文件命名 test_<module>.py。
- 类名以 Tests 结尾。
- 方法名以 test_ 开头。
- 一个测试描述一个行为。
- 回归测试名称体现缺陷场景。
- 共享 helper 保持测试内部可读。
- 不要把业务实现复制到测试。

## 隔离

- 测试不能依赖真实 Polar API。
- 测试不能读取真实 token。
- 测试不能修改真实 recovery.db。
- 测试不能依赖 Dashboard 已启动。
- 测试不能依赖执行顺序。
- 测试创建自己的临时目录。
- 测试结束关闭数据库连接。
- 测试清理临时资源。

## Fixture

- 使用虚构日期和数值。
- fixture 不包含真实账号。
- 最小 fixture 覆盖目标行为。
- 复杂 JSON 保留必要字段。
- CSV fixture 明确编码。
- 边界 fixture 标出单位。
- 同一 fixture 不承担过多场景。
- fixture 变化需检查测试含义。

## 数据库测试

- 测试空数据库自动建表。
- 测试所有表存在。
- 测试迁移缺列场景。
- 测试唯一键。
- 测试 upsert 更新。
- 测试 created_at 与 updated_at 语义。
- 测试 NULL 保存。
- 测试真实零值保存。

## OAuth 测试

- 测试缺少配置提示。
- 测试授权参数。
- 测试 scope 拼接。
- 测试 state 校验。
- 测试 callback 缺 code。
- 测试 Polar error 安全展示。
- 测试 token 保存结构。
- 不得断言真实 secret。

## Polar Client 测试

- 测试 Bearer header 但使用虚构 token。
- 测试 v3 URL。
- 测试 v4 URL。
- 测试日期参数。
- 测试 204 返回。
- 测试 JSON 返回。
- 测试 HTTP 错误。
- 测试 token refresh 分支。
- 测试瞬时 TLS/连接错误的有界 GET 重试。

## Scheduler 与锁测试

- 测试 06:00 plist、含中点路径、虚拟环境和无 secret 配置。
- 测试 manual、scheduled、catch_up 来源、当天去重与 Catch-Up 上限。
- 测试进程锁并发拒绝与崩溃后恢复。
- Pipeline 单元测试使用隔离测试锁，避免与正在接受治理检查的真实
  Pipeline 互相阻塞；生产并发锁始终保持启用。

## Fetch 测试

- 测试各 fetcher 被调用。
- 测试文件名。
- 测试列表计数。
- 测试字典计数。
- 测试 API error 安全保存。
- 测试命令参数。
- 测试日期范围。
- 不发真实网络请求。

## Import 测试

- 测试多种容器键。
- 测试日期提取。
- 测试 external_id 提取。
- 测试 durationMillis 转换。
- 测试 raw_json 保存。
- 测试重复导入更新。
- 测试缺关键键跳过。
- 测试各 Polar raw 表。

## Kubios 测试

- 测试 header aliases。
- 测试 UTF-8 BOM。
- 测试日期规范化。
- 测试 measurement_time。
- 测试 rmssd 解析。
- 测试 readiness 文本。
- 测试重复导入。
- 测试同步 daily metrics。

## Daily Metrics 测试

- 测试活动字段汇总。
- 测试多训练合计。
- 测试训练次数。
- 测试 duration 合计。
- 测试睡眠合并。
- 测试 Nightly 合并。
- 测试日期并集。
- 测试重复重建。

## Baseline 测试

- 测试正常 28 天。
- 测试恰好 7 天。
- 测试少于 7 天。
- 测试排除当天。
- 测试缺失 HRV。
- 测试低 HRV。
- 测试高静息心率。
- 测试 MAD 与 std 为零。

## Baseline 边界

- 测试 ISO duration。
- 测试负数过滤。
- 测试 NaN 过滤。
- 测试异常值处理。
- 测试 percent change 分母零。
- 测试 readiness 映射。
- 测试重复 upsert。
- 测试配置字段校验。

## Recovery 测试

- 测试 v0.1 负荷。
- 测试 v0.2 Kubios。
- 测试 v0.3 Polar。
- 测试 v1.0 baseline。
- 测试各方向。
- 测试 fallback。
- 测试推荐区间。
- 测试评分 0–100。

## Dashboard Data 测试

- 测试空数据库。
- 测试缺睡眠。
- 测试缺 HRV。
- 测试最新日期。
- 测试最近 7 天。
- 测试最近 30 天。
- 测试 duration 转换。
- 测试 baseline map。

## Dashboard 页面测试

- 可使用 Streamlit AppTest。
- 测试页面无 exception。
- 测试关键 subheader。
- 测试空状态。
- 测试评分版本显示。
- 测试解释区域。
- 测试图表有数据时渲染。
- 页面测试不修改数据库。

## Report 测试

- 测试指定日期。
- 测试默认最新日期。
- 测试缺失日期错误。
- 测试中文字段。
- 测试 duration 显示。
- 测试文件名。
- 测试保存目录。
- 测试 score_version。

## 解释层测试

- 测试 higher_is_better。
- 测试 lower_is_better。
- 测试 higher_is_load。
- 测试 within 为 neutral。
- 测试 insufficient 为 missing。
- 测试偏离强度排序。
- 测试空 latest。
- 测试消息不包含敏感内容。

## 覆盖原则

- 高风险共享逻辑需要更多覆盖。
- 数据库迁移必须覆盖。
- 外部 API 边界必须 mock。
- 纯展示细节不追求逐像素。
- 算法分支必须覆盖。
- 错误与缺失路径必须覆盖。
- 幂等任务必须覆盖重复执行。
- 测试数量不是唯一质量指标。

## 反模式

- 不使用 sleep 等待异步结果。
- 不访问公网。
- 不共享可变全局数据库。
- 不依赖真实日期 today 除非注入。
- 不只断言函数未报错。
- 不复制生产公式作为 expected。
- 不吞掉测试异常。
- 不因脆弱测试降低业务正确性。

## 回归流程

- 先复现失败。
- 新增失败测试。
- 确认测试在修复前失败。
- 实施最小修复。
- 运行目标测试。
- 运行相关模块测试。
- 运行全量测试。
- 更新 CHANGELOG Fixed。

## 完成门槛

- 所有测试通过。
- 没有意外 skip。
- 没有未处理 warning 影响未来兼容。
- 语法检查通过。
- 真实数据验证不泄露敏感值。
- CURRENT_STATE 更新测试数。
- 失败测试原因已解决。
- 无法运行的测试明确汇报。

## AI 协作治理测试

- `test_project_state.py` verifies the machine-readable state contract.
- `test_ai_collaboration.py` verifies the standard handoff section order.
- Handoff values must match `project_state.json`.
- Handoff placeholders and sensitive assignments are rejected.
- Authority files and labels must exist.
- Dashboard and report layers cannot import Polar clients.
- Recovery Engine cannot import Dashboard or Streamlit.
- `scripts/finalize_phase.py` is the final executable phase gate.
- Governance tests inspect artifacts and imports; they do not modify business
  data.

## AI Coach 设计契约测试

- 验证设计明确为未实现且 `model_version` 为 `unreleased`。
- 验证最小输入 allowlist 和 token、secret、raw payload denylist。
- 验证输出 schema、audit envelope 和独立版本字段。
- 验证 high、medium、low、very_low 的语言边界。
- 验证医疗禁止行为、紧急症状升级和确定性 fallback。
- 验证 ADR、ROADMAP 与权威设计文档一致。
- 未来运行测试必须全部使用合成数据和 mock provider，不访问公网。
- 未来回归必须证明 AI 无法写 Recovery、Baseline、Confidence 或 raw 表。

## AI Coach Machine-Readable Contract 测试

- 验证输入/输出根对象和嵌套对象全部拒绝 unknown fields。
- 验证 0–100、长度、枚举、日期、带时区时间和 digest 格式边界。
- 验证 user question 拒绝 email、phone 和 credential-like 文本。
- 验证输出拒绝 HTML、URL、control character 和 contract version drift。
- 验证错误只报告字段路径，不回显敏感 payload 值。
- 验证纯 validator 不导入 network、SQLite、Polar、Recovery 或 Streamlit。

## AI Coach Semantic Safety 与 Fallback 测试

- 验证 evidence fact id 必须来自输入 allowlist。
- 验证生成文本不得包含无依据数字、诊断或用药指令。
- 验证 medium/low/very_low 的 limitation 和 action 数量边界。
- 验证紧急症状必须升级到当地急救且不生成普通 action。
- 验证输入摘要使用至少 32-byte local key 的 HMAC-SHA256。
- 验证 invalid model output 自动替换为 schema-valid deterministic fallback。
- 验证 fallback 无 provider、network、database、OAuth、scoring 或 Dashboard 依赖。

## AI Coach Synthetic Safety Preflight

- 命令：`.venv/bin/python -m src.ai_coach_evaluation`。
- 每轮固定 200 个合成案例，覆盖 grounded、unknown evidence、numeric claim、
  medical directive、Confidence violation、urgent escalation 和 invalid schema。
- 至少连续运行三轮；当前预检总计 600 次评估。
- Critical expectation mismatch 必须为零，否则命令非零退出。
- 结果只包含 suite、category、run、pass/fail 和 case id 聚合，不含 payload。
- 这是本地 safety-layer preflight，不是未来 exact model/snapshot evaluation。

## AI Coach Cloud Call Approval Gate

- 验证 committed record 为 blocked、authorization false 且 provider fields 为空。
- 验证 blocked record 不允许 partial provider/model/endpoint/region 配置。
- 验证 future approved record 需要全部 controls、Product Owner 和 Chief Architect approved。
- 验证 evidence effective/expiry 使用 aware datetime 且过期立即 fail closed。
- 验证 endpoint 必须是无 credentials/query/fragment 的 HTTPS URL。
- 验证 configuration fingerprint 包含 provider decision 和 contract versions。
- 验证错误不输出 provider/endpoint，模块不读取 secret 或访问 network/database。

## AI Coach Outbound Context Builder

- 验证 source root/nested fields 使用 closed allowlist 且缺失 required field 失败。
- 验证调用方不能注入 `contract_versions`，版本只来自 authority。
- 验证 raw、token、exact HRV、exact sleep minutes 和未知字段失败。
- 验证 email、phone、credential-like question 被拒绝且错误不回显值。
- 验证深拷贝不修改或 alias source。
- 验证 blocked approval 在调用 builder 前停止；synthetic full approval 才能构建。
- 验证 context builder 不访问 provider、network、database、raw 或 engines。

## AI Coach Pre-Provider Readiness Gate

- 命令：`.venv/bin/python -m src.ai_coach_readiness`。
- `local_pre_provider_ready` 只聚合 contract/safety 与 200×3 local preflight。
- `runtime_ready` 额外要求 provider approval、matching model version、schema
  0.4.0、provider adapter 和 exact-model evaluation artifact。
- Exact-model artifact 必须匹配 suite/model/prompt/schema/safety versions 和全部阈值。
- 当前预期为 local true、runtime false；`--require-runtime` 在 blocked 时非零退出。
- 输出仅包含 boolean、version、aggregate counts 和 blocker codes。

## Today's Recovery Details

`tests/test_recovery_details.py` covers missing values remaining missing,
respiration zero exclusion, low-quality exclusion, baseline maturity gates,
RMSSD and resting-HR direction rules, bilateral respiration deviation,
conflicting signals, legacy/canonical quality normalization, confidence impact,
and separation of interpreted details from the raw table. The page reuses the
existing resolved recovery history and does not add a database table.

## Cognitive Training Studio

`tests/test_cognitive_training.py` covers finite d-prime correction, idempotent
session writes, quick/standard storage, interruption semantics, and strict
three-task plan ordering. Browser component checks should additionally cover
focus loss, visibility changes, touch, keyboard, and reduced-motion behavior.
# Alertness Probe checks

Verify 60-second daily and 180-second calibration durations, separated baseline groups, false starts below 100 ms, one response per trial, interruption exclusion, and browser timing. Test mobile touch and desktop Space input manually before release.
# Cognitive component browser tests

The Cognitive Training Studio browser suite executes real pointer, touch,
keyboard, focus, visibility, timer, duration, sequence-generation, and narrow
viewport behavior:

```bash
npm install
npx playwright install chromium
npm run test:cognitive-browser
```

Local Codex runtimes may provide Playwright and a system Chrome executable; CI
should install Chromium explicitly with the command above.
