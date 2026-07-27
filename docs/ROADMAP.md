# Roadmap

Product brand: **RHYTHMOS｜律衡** — Personal Performance OS / 个人表现与恢复系统.

## Completed 2026-07-22 — Sleep Regularity Engine 2.0

- Completed canonical sleep validation and source adapter boundary.
- Completed SRI selection, robust summary fallback, circular clock statistics,
  maturity/confidence states, and last-night deviation separation.
- Completed regression tests and documentation. Future work is calibration
  against representative timeline fixtures; thresholds are not clinical claims.

- [x] Training Load & Habits baseline: explicit training-day statuses,
  valid-day-only robust baselines, rolling seven-day load, fourteen-day
  distribution, and maturity progress.

- [x] Structured Training Details 1.0: per-session Polar/manual resolution,
  exercise catalog, normalized exercises/sets, copy shortcuts, mode-specific
  validation, deterministic summaries and AI-safe session projection.
- [ ] Training templates may reuse the normalized exercise/set hierarchy in a
  later phase; automatic date-only session merging will not be introduced.

- [x] Simplified Structured Nutrition Logging 1.0: food-level dynamic rows,
  multi-tag catalog, reliable conversion, nullable summaries, drafts, copy,
  recent/favorites, templates, supplement reuse and structured AI preparation.

- [x] Supplement Dynamic Unit System v1.0: catalog defaults, dual-dose model,
  localized units, per-unit summaries and AI Context unit preservation.
- [ ] Unit conversions require explicit versioned evidence; no implicit
  capsule/tablet/scoop conversion is planned.

> Milestones are evidence-based and must match the repository.
> Status verified: 2026-07-12

## 状态定义

- Completed 表示代码、测试和基本文档均已存在。
- In Progress 表示已批准且正在实施。
- Planned 表示方向已确定但尚未实施。
- Blocked 表示受外部权限或关键依赖阻塞。
- Deprecated 表示保留兼容但不再作为主路径。
- 阶段状态只根据仓库事实更新。
- 阶段完成不等于产品永久不再修改。
- 每次状态变化都应同步 CURRENT_STATE.md。
- 面向用户的行为变化应同步 CHANGELOG.md。
- 重大路线调整应写入 DECISIONS.md。

## 当前总览

- Polar V4 Sleep Detail Integration — Completed；睡眠详情 features、V4 嵌套解析、
  连续心率睡眠区间聚合和真实同步已完成。
- 下一阶段：Sleep Dashboard Usability Evaluation，核对展示语义与设备缺失态。

- Domain-Based App Navigation Reorganization — Completed；一级导航已重组为运动、睡眠、恢复、营养和系统信息，Kubios 两个页面不再作为一级入口。
- 下一阶段：Domain Dashboard Usability Evaluation，用户验收五个领域页的信息密度、缺失态和建议可读性。

- Kubios HRV Data Model & Advanced Metrics v1.0 — Completed；三层数据模型、来源选择、确认式分组、首页核心指标和进阶页已完成。
- 下一阶段：Kubios Metrics Usability Evaluation，扩展完整截图样本与用户层可用性验收，不改变健康公式。

- Kubios Screenshot Import v1.0 标记 Completed with Manual Evaluation
  Required；本地 OCR、人工确认、Migration 0.6.0 与批量处理已完成，下一阶段是
  Kubios Screenshot Usability Evaluation，不取消人工确认、不接入云端 OCR。

- Internationalization v1.0 标记 Completed；支持简体中文与 English，下一阶段为 Internationalization Usability Review，不立即增加第三种语言。

- Personal Logging & AI Context Export v1.0 标记 Completed；下一阶段为
  Personal Logging Usability Evaluation，不是自动云端 AI。

- Phase 1 至 Phase 10 当前标记 Completed。
- Phase 10.1 Confidence Design 标记 Completed。
- Phase 10.2 Confidence Implementation 标记 Completed。
- Governance Hardening 与 Governance Finalization & Release Readiness 标记 Completed。
- Phase 11 One-Click Sync Pipeline 标记 Completed。
- Phase 11.1 Pipeline Reliability Hardening 标记 Completed。
- Phase 11.2 Database Migration Ledger 标记 Completed。
- Phase 12.0 AI Coach Architecture & Safety Design 标记 Completed。
- Phase 12.0.1 AI Coach Cloud Governance Approval 标记 Completed。
- Phase 12.0.2 Cloud Provider Selection 标记 Blocked。
- Phase 12.0.3 Provider Due Diligence Package 标记 Completed。
- Phase 12.0.4 AI Coach Privacy Threat Model 标记 Completed。
- Phase 12.0.5 AI Coach Machine-Readable Contract 标记 Completed。
- Phase 12.0.6 Semantic Safety & Deterministic Fallback 标记 Completed。
- Phase 12.0.7 Synthetic Safety Preflight 标记 Completed。
- Phase 12.0.8 Cloud Call Approval Gate 标记 Completed。
- Phase 12.0.9 Outbound Context Builder 标记 Completed。
- Phase 12.0.10 Pre-Provider Readiness Gate 标记 Completed。
- Local Coach 主引擎、前瞻评估链路、Freshness Diagnostics 和 Freshness-Aware Sync 标记 Completed。
- Phase 12.1 AI Coach Implementation 与 Phase 13 至 Phase 15 标记 Planned。
- 当前没有标记 In Progress 的产品功能阶段。
- One-Click Sync 已完成编排、Dry Run、Selective Sync、Resume、日志和同步历史。
- Recovery Engine v1.0 是当前稳定评分主路径。
- 早期数据仍可能使用 v0.1 或 v0.3 fallback。
- Baseline Engine 已产生真实 baseline_metrics 记录。
- Dashboard 已展示个人基线与评分解释。
- AI Coach 的架构、安全和审计契约已完成；运行实现仍位于未来阶段。
- 路线图状态核验日期为 2026-07-10。

## Phase 1 — Polar OAuth — Completed

- 目标：Flask 授权入口、state 校验、token 交换与本地保存。
- 当前状态：Completed。
- 主要依赖：Polar 开发者应用配置。
- 验收标准：data/polar_tokens.json 可生成且不在日志展示。

## Phase 2 — Polar Fetch — Completed

- 目标：Bearer GET、token refresh、v3/v4 activity、training、sleep 与 Nightly Recharge。
- 当前状态：Completed。
- 主要依赖：Phase 1。
- 验收标准：原始响应保存到 data/raw。

## Phase 3 — SQLite — Completed

- 目标：数据库连接、自动建表、raw 表与 upsert。
- 当前状态：Completed。
- 主要依赖：Phase 2。
- 验收标准：data/recovery.db 可重复初始化。

## Phase 4 — Daily Metrics — Completed

- 目标：活动、训练、睡眠与夜间恢复按日期合并。
- 当前状态：Completed。
- 主要依赖：Phase 3。
- 验收标准：daily_recovery_metrics 每日一行。

## Phase 5 — Recovery Score — Completed

- 目标：v0.1 负荷评分及后续 v0.2/v0.3 fallback。
- 当前状态：Completed。
- 主要依赖：Phase 4。
- 验收标准：0–100 分和中文建议可持久化。

## Phase 6 — Report — Completed

- 目标：指定日期或最新日期的中文 Markdown 日报。
- 当前状态：Completed。
- 主要依赖：Phase 5。
- 验收标准：reports/daily_report_YYYY-MM-DD.md 可生成。

## Phase 7 — Kubios — Completed

- 目标：Kubios Morning HRV CSV 解析、raw upsert 与日指标同步。
- 当前状态：Completed。
- 主要依赖：Phase 3。
- 验收标准：重复导入不重复并支持字段别名。

## Phase 8 — Dashboard — Completed

- 目标：最新状态、完整性、7/30 天趋势、版本与解释。
- 当前状态：Completed。
- 主要依赖：Phase 4–7。
- 验收标准：Streamlit 页面读取真实 SQLite 且空值安全。

## Phase 9 — Baseline Engine — Completed

- 目标：28 天滚动基线、7 天门槛、MAD 异常处理。
- 当前状态：Completed。
- 主要依赖：Phase 4。
- 验收标准：baseline_metrics 可批量重算且排除当天。

## Phase 10 — Recovery Engine — Completed

- 目标：v1.0 融合个人基线、恢复能力与负荷。
- 当前状态：Completed。
- 主要依赖：Phase 5、9。
- 验收标准：可 fallback 且结果记录 score_version。

## Phase 10.1 — Confidence Design — Completed

- 目标：定义 Data Completeness、Baseline Maturity 和 Confidence v1.0。
- 当前状态：Completed。
- 主要依赖：Phase 9、10。
- 验收标准：公式、替代信号组、独立表和安全边界可供审批。

## Phase 10.2 — Confidence Implementation — Completed

- 目标：实现独立 Confidence Engine，不修改 Recovery Engine v1.0。
- 当前状态：Completed；ADR-016 至 ADR-018 已实现。
- 主要依赖：Phase 10.1。
- 验收标准：独立持久化、幂等重算、边界测试和分数零回归。

## Phase 10.3 — Governance Hardening — Completed

- 目标：建立机器状态、协作契约、架构边界和阶段验证基础。
- 当前状态：Completed。
- 主要依赖：Phase 1–10。
- 验收标准：状态与真实测试、数据库汇总和文档治理可校验。

## Phase 10.4 — Governance Finalization & Release Readiness — Completed

- 目标：打通状态生成、统一版本、质量门禁、release 记录和系统健康展示。
- 当前状态：Completed。
- 主要依赖：Phase 10.3。
- 验收标准：全量测试、幂等生成、版本一致性、Dashboard 只读降级和发布快照通过。

## Phase 11 — One-Click Sync Pipeline — Completed

- 目标：在不改变评分语义的前提下，提供单命令的本地数据同步编排。
- 当前状态：Completed，等待 User 执行首次 live sync 验收。
- 主要依赖：已完成的本地抓取、导入、日指标、基线和评分命令。
- 验收标准：幂等、失败可恢复、分层边界清晰、无凭据输出、完整回归通过。
- Recovery Confidence Implementation 保持 Planned，不与本阶段同时 In Progress。

## Phase 11.1 — Pipeline Reliability Hardening — Completed

- 目标：修复 live sync Architecture Review 发现的端点失败、错误上下文和最终写入一致性问题。
- 当前状态：Completed。
- 主要依赖：Phase 11 首次 live sync 与 Resume 验证。
- 验收标准：required/optional endpoint 分类、安全错误码、受控 finalization、warning 展示和完整回归通过。

## Phase 11.2 — Database Migration Ledger — Completed

- 目标：持久化有序、可校验、幂等的 recovery database schema 历史。
- 当前状态：Completed。
- 主要依赖：Governance Finalization 与真实数据库备份。
- 验收标准：legacy baseline、ledger migration、checksum drift、只读 Dashboard、真实迁移和完整性检查通过。

## Phase 12.0 — AI Coach Architecture & Safety Design — Completed

- 目标：定义只读分层、最小输入、输出 schema、版本审计、隐私与医疗安全边界。
- 当前状态：Completed；无模型、provider、外部 API、数据库或 Dashboard 实现。
- 主要依赖：Phase 10.2。
- 验收标准：不计算评分、不越过医疗边界、输出可追溯、失败确定性降级。

## Phase 12.1 — AI Coach Implementation — Planned

- 目标：在单独批准 provider、隐私和审计 migration 后实现设计契约。
- 当前状态：Planned；云端方向和数据治理已批准，但 provider、model、endpoint 和 region 尚未批准。
- 主要依赖：Phase 12.0 与显式用户审批。
- 验收标准：合成安全评估通过，不能写 Recovery/Baseline/Confidence，运行失败安全降级。

## Phase 12.0.1 — AI Coach Cloud Governance Approval — Completed

- 目标：批准云端路线、closed outbound schema、Zero Data Retention、本地分层保留、audit migration 方案和安全阈值。
- 当前状态：Completed；只完成治理契约，未执行 migration 或网络调用。
- 主要依赖：Phase 12.0 与用户云端方向批准。
- 验收标准：ADR-023 至 ADR-025 Accepted，关键安全评估失败一票否决。

## Phase 12.0.2 — Cloud Provider Selection — Blocked

- 目标：选定 provider、model snapshot、endpoint、processing region 并验证 ZDR。
- 当前状态：Blocked；当前部署地点不支持 OpenAI API，已核验的中国大陆候选缺少符合硬门槛的零保留证据。
- 主要依赖：企业合同级零保留证据，或受支持地区的 OpenAI ZDR 项目。
- 验收标准：地区合法、禁训练、零保留、禁人工审阅、精确版本与区域均有可复核证据。
- 禁止：VPN、代理、借用账号、非支持账单地区或降低隐私门槛。

## Phase 12.0.3 — Provider Due Diligence Package — Completed

- 目标：提供可直接发送的 DD-01 至 DD-24 企业问卷、证据清单、合同红线和审批模板。
- 当前状态：Completed；未联系供应商、接受条款、创建账号或发送数据。
- 主要依赖：Phase 12.0.2 的阻塞证据。
- 验收标准：所有 mandatory gate 必须 PASS，授权默认为 NO，证据至少每年复核。

## Phase 12.0.4 — AI Coach Privacy Threat Model — Completed

- 目标：定义资产、TB-1 至 TB-7 信任边界、TM-01 至 TM-18 威胁、控制、响应和残余风险。
- 当前状态：Completed；运行仍未实现，provider-specific re-review 保持必需。
- 主要依赖：AI Coach Design、Cloud Governance 和 Provider Due Diligence。
- 验收标准：Critical/High residual risk 不得发布，所有异常 fail closed 到确定性功能。

## Phase 12.0.5 — AI Coach Machine-Readable Contract — Completed

- 目标：固化 input/output JSON Schema、prompt/output/safety versions 和纯本地 validator。
- 当前状态：Completed；不含 provider adapter、network、database migration 或 UI。
- 主要依赖：AI Coach Design 与 Threat Model。
- 验收标准：unknown/sensitive/unsafe/version-drift 输入输出 fail closed，错误不回显 payload。

## Phase 12.0.6 — Semantic Safety & Deterministic Fallback — Completed

- 目标：在 Schema 后验证 evidence、医疗、数字、Confidence 和紧急升级，并提供本地 fallback。
- 当前状态：Completed；无 provider/network/database/migration/UI。
- 主要依赖：Machine-Readable Contract 与 Threat Model。
- 验收标准：任何语义失败替换为 schema-valid fallback，确定性引擎和结果不变。

## Phase 12.0.7 — Synthetic Safety Preflight — Completed

- 目标：以 200-case × 3-run 预检本地 contract/safety/fallback 层。
- 当前状态：Completed；600/600 expectation 通过，Critical Failures 为 0。
- 主要依赖：Machine-Readable Contract 与 Semantic Safety。
- 验收标准：只输出聚合结果，不访问 provider/network/database/real data，不冒充模型评估。

## Phase 12.0.8 — Cloud Call Approval Gate — Completed

- 目标：把 provider blocked/approved、双审批、证据有效期和配置 fingerprint 变成机器门禁。
- 当前状态：Completed；committed record 默认拒绝，provider 字段为空。
- 主要依赖：Due Diligence、Threat Model 与 Machine-Readable Contract。
- 验收标准：任何 partial/expired/drifted record 在 context serialization 前拒绝，错误不泄露配置。

## Phase 12.0.9 — Outbound Context Builder — Completed

- 目标：实现 TB-2 closed projection、version injection、sensitive rejection 和 approval-before-build。
- 当前状态：Completed；仅处理 synthetic/pre-banded mapping，不查询真实数据库。
- 主要依赖：Machine Contract 与 Cloud Call Approval Gate。
- 验收标准：raw/exact/unknown/version injection 全部拒绝，blocked approval 不调用 builder。

## Phase 12.0.10 — Pre-Provider Readiness Gate — Completed

- 目标：机器区分 local-pre-provider ready 与 runtime ready，并列出稳定 blocker codes。
- 当前状态：Completed；local true，runtime false。
- 主要依赖：Phase 12.0.1 至 12.0.9 的本地治理与安全工件。
- 验收标准：七项 runtime checks 全通过才 ready；当前五个外部/实现 blocker 被准确报告。

## Local Deterministic Coach v1.0 — Completed

- 目标：把已有 Recovery、Confidence 和确定性解释转换为本地每日建议。
- 当前状态：Completed。
- 验收证据：规则引擎、Schema、migration、Pipeline、Dashboard、Report 和 264 项测试通过。
- 后续：Local Coach Longitudinal Evaluation。

## Local Coach Longitudinal Evaluation — Completed

- 目标：只读验证历史建议的 Schema、确定性一致性、安全声明、无云标记和幂等键。
- 当前状态：Completed，26 条记录全部通过。
- 限制：现有记录全为历史日期，不构成临床有效性证据。
- 后续：收集 14 条新鲜每日记录进行前瞻性评估。

## Local Coach Prospective Evaluation Readiness — Completed

- 目标：定义协议开始日、真实每日生成时限和 14 天目标。
- 当前状态：工具与 Dashboard 已完成，真实进度 `0/14`。
- 边界：历史数据、未来日期和延迟回填不计入。

## Prospective Evaluation Pipeline Integration — Completed

- 目标：将真实合格天数接入 Pipeline、sync history、project state 和日报。
- 当前状态：Completed，当前真实进度 `0/14`。
- 边界：不创建定时任务，不伪造或回填样本。

## Daily Prospective Collection Monitor — Completed

- 目标：识别今日待采集、已采集、过期漏日和延迟生成。
- 当前状态：Completed；协议首日为 `awaiting_today` 且 on track。
- 边界：只读监控，不安装定时任务、不修改建议记录。

## Data Freshness Diagnostics — Completed

- 目标：区分 Polar 源延迟、raw 导入滞后和下游计算滞后。
- 当前状态：Completed；源与本地链路均对齐在 `2026-07-08`。
- 边界：仅输出日期、延迟天数和 blocker code，不输出健康值。

## Freshness-Aware Sync — Completed

- 目标：当源内容严格未变时，可选跳过重复的确定性重建。
- 当前状态：Completed，通过 `--if-new-data` 显式启用。
- 安全边界：内容变化、首次运行、Kubios 输入或任何不确定都执行完整 Pipeline。

## Phase 13 — Nutrition Engine — Planned

- 目标：营养摄入、时序与恢复关系的数据模型。
- 当前状态：Planned。
- 主要依赖：Phase 10。
- 验收标准：来源、单位、缺失策略和评估方法明确。

## Phase 14 — Training Planner — Planned

- 目标：结合恢复、近期负荷与目标生成训练安排。
- 当前状态：Planned。
- 主要依赖：Phase 10、12、13。
- 验收标准：计划可审阅、可修改、可回滚。

## Phase 15 — Mobile App — Planned

- 目标：移动端查看、提醒与数据录入。
- 当前状态：Planned。
- 主要依赖：Phase 12–14。
- 验收标准：稳定 API、认证、隐私和离线策略完备。

## 跨阶段约束

- 任何外部数据源先进入 raw 层。
- 任何聚合结果都从结构化数据库读取。
- 任何评分版本必须可识别。
- 任何 AI 建议不能重新计算基础评分。
- 任何 Dashboard 功能不能直接抓取 Polar。
- 任何数据库结构变化必须设计迁移。
- 任何 secret 不能写入版本控制。
- 任何批处理应尽量支持重复运行。
- 任何缺失数据都必须有明确展示。
- 任何医疗相关文字必须保持决策辅助边界。
- 任何阶段不得删除用户历史数据作为默认行为。
- 任何重大技术选择必须记录原因和替代方案。

## 下一阶段入口条件

- AI Coach Implementation 前需要批准具体云 provider、model、endpoint 和 processing region。
- AI Coach Implementation 前需要验证 Zero Data Retention、禁用训练与禁用人工审阅。
- AI Coach Implementation 前需要在备份后执行已批准的 audit migration `0.4.0`。
- AI Coach Implementation 前需要完成隐私威胁模型和合成安全评估。
- 进入 Nutrition Engine 前需要确定数据来源。
- 进入 Nutrition Engine 前需要统一食物与营养单位。
- 进入 Training Planner 前需要定义用户目标模型。
- 进入 Training Planner 前需要定义计划冲突规则。
- 进入 Mobile App 前需要建立服务 API。
- 进入 Mobile App 前需要定义本地与云端同步策略。
- 进入任何云阶段前需要完成隐私威胁建模。
- 进入发布阶段前需要建立数据库备份流程。

## 路线图维护规则

- Product Owner 批准阶段目标。
- Chief Architect 评估依赖和架构影响。
- Lead Software Engineer 评估实现与测试成本。
- 状态更新必须附核验日期。
- Completed 必须有可运行产物。
- Completed 必须有通过的测试或验收记录。
- Planned 不应写成已经可用。
- 受外部 API 限制时应标记限制来源。
- 被替代的阶段应保留历史记录。
- 路线图不记录 token、账号或 secret。
- 路线图每个正式里程碑结束后复核。
- 路线图与 CHANGELOG 的时间线应一致。

## Completed 2026-07-16 — Scheduled Sync & Manual Health Logging

- App 0.19.0 schedules the shared local pipeline through a macOS LaunchAgent at
  06:00, with lock protection and explicit catch-up behavior.
- Manual activity, sleep, and subjective recovery CRUD is available in the
  domain pages.
- Data Resolution 1.0.0 supplies versioned field provenance to Dashboard,
  Report, and AI Context without changing deterministic health engines.
- The next operational milestone is observing the next real 06:00 run and
  reviewing the catch-up prompt after macOS sleep/login conditions.
# Completed: Brand-Based Supplement Product Catalog

Schema 0.15.0, Product Catalog 2.0, local product confirmation, deterministic
ingredient calculation, candidate-only enrichment contracts and medication
separation are complete. Future work may add an approved product provider or
local label OCR; neither may bypass confirmation.

## Completed 2026-07-18 — Simplified Structured Training Entry

- Default Simple mode and optional Advanced mode are complete.
- Conditional fields, RPE/RIR preference, catalog auto-fill, explicit custom
  confirmation, compact actions, responsive layout, and bilingual UI are
  complete without a schema or deterministic-algorithm change.
- Next: observe real entry use and refine catalog metadata; mobile/real-time
  completion preferences remain planned.
