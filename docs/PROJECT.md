# RHYTHMOS｜律衡 — Project

**Personal Performance OS · 个人表现与恢复系统**

> Know your state. Shape your day.<br>
> 读懂状态，掌控节奏。

## Current product capability

The product includes a released Local Deterministic Coach that converts existing
Recovery and Confidence results into on-device daily direction. It is distinct
from the blocked Cloud AI Coach and does not send health data externally.

> Project: RHYTHMOS｜律衡（原 Daily Recovery Coach）
> Positioning: Personal Performance OS · 个人表现与恢复系统
> Goal: Collect → Analyze → Explain → Recommend.
> Status verified: 2026-07-10

## 项目身份

- 项目名称是 RHYTHMOS｜律衡。
- 项目定位是 Personal Performance OS · 个人表现与恢复系统。
- 一句话目标是 Collect → Analyze → Explain → Recommend.
- 项目服务对象首先是单用户本人。
- 项目以个人历史作为比较对象。
- 项目不提供人群排名。
- 项目不替代医生、教练或临床判断。
- 项目当前采用本地优先的数据策略。
- 项目当前以 Python 为主要实现语言。
- 项目当前以命令行任务和 Streamlit 页面作为主要入口。

## 问题定义

- 运动、睡眠和 HRV 数据分散在多个来源。
- 原始平台通常展示数据，但不统一解释跨来源变化。
- 固定阈值无法充分反映个体差异。
- 单日指标容易受到噪声和异常值影响。
- 训练负荷与恢复能力需要在同一天尺度上比较。
- 缺失数据不能导致整套评分停止。
- 用户需要知道分数为什么变化。
- 用户需要可追溯的原始数据与计算结果。
- 开发者需要稳定的数据层避免页面绑死外部 API。
- 长期系统需要可演进而不破坏历史结果。

## 产品承诺

- 收集层保存来源数据，不偷偷改变来源含义。
- 分析层将多来源记录统一到日粒度。
- 解释层公开评分版本和主要影响因素。
- 建议层输出训练强度方向，不输出医疗诊断。
- 同一输入和同一版本应得到相同结果。
- 缺失项会明确标记为暂无数据或数据不足。
- 所有敏感凭据仅保存在本地受控文件或环境变量。
- Dashboard 不直接调用 Polar；展示读取 SQLite，受控表单只写入专用手工表。
- 评分计算独立于展示层。
- 每个阶段必须通过自动测试后才能声明完成。

## 长期目标

- 建立稳定的个人健康与训练数据仓库。
- 形成跨 Polar 与 Kubios 的统一日指标。
- 形成长期可解释的个人滚动基线。
- 形成可版本化的 Recovery Engine。
- 引入数据完整性与置信度表达。
- 支持训练计划与恢复状态联动。
- 支持营养记录与恢复关联分析。
- 支持移动端每日查看和提醒。
- 支持可撤销、可审计的 AI Coach 建议。
- 保留本地部署与数据可迁移能力。
- 允许未来增加新的穿戴设备来源。
- 允许未来增加实验性模型而不覆盖稳定评分。
- 支持历史回放和版本间评分比较。
- 支持用户导出自己的标准化数据。
- 保持个人决策辅助而非医疗产品的边界。

## 当前版本口径

- 机器可读的当前版本和真实计数只维护在
  [project_state.json](../project_state.json)。
- 人类可读的当前能力、问题和下一目标只维护在
  [CURRENT_STATE.md](CURRENT_STATE.md)。
- 本文件只描述稳定的项目定位，不复制运行状态快照。

## 已完成能力

- Polar OAuth 授权流程已完成。
- OAuth state 校验已实现。
- Polar token 本地保存已实现。
- Polar access token 自动刷新已实现。
- Polar API v3 与 v4 请求封装已实现。
- 训练 sessions 抓取已实现。
- daily activity 抓取已实现。
- sleep 抓取已实现。
- Nightly Recharge 抓取已实现。
- cardio load 抓取已实现。
- continuous heart rate 抓取已实现。
- 原始 JSON 保存到 data/raw 已实现。
- Polar 原始数据 SQLite 导入已实现。
- Kubios Morning HRV CSV 导入已实现。
- 日粒度指标汇总已实现。
- Recovery Score 的历史 fallback 版本已保留。
- Recovery Engine v1.0 已接入个人基线。
- 中文 Markdown 日报已实现。
- Streamlit Dashboard 已实现。
- 评分可解释性展示已实现。
- 用户级 06:00 LaunchAgent、显式 Catch-Up 与跨触发锁已实现。
- 手工运动、睡眠、主观恢复 CRUD 与字段来源解析已实现。

## 当前真实数据状态

- 数据库记录数、评分版本分布、测试结果和已知问题会变化。
- 这些动态事实不在项目总览中复制。
- 请读取 [project_state.json](../project_state.json) 和
  [CURRENT_STATE.md](CURRENT_STATE.md)。
- 历史变化请读取 [CHANGELOG.md](CHANGELOG.md)。

## 核心用户流程

- 用户先通过 Flask OAuth 完成 Polar 授权。
- 抓取任务从 Polar API 获取选定日期范围。
- 抓取任务把响应保存为原始 JSON。
- 导入任务把原始 JSON upsert 到 raw 表。
- 日指标任务将 raw 表汇总成每天一行。
- 手工日志汇总与字段解析为展示、报告和 AI Context 提供来源标签。
- Kubios CSV 导入会同步晨测字段。
- Baseline Engine 为每个日期计算此前 28 天统计。
- Recovery Engine 读取日指标与同日基线。
- Recovery Engine 写入版本化评分。
- 日报任务读取指标与评分生成 Markdown。
- Dashboard 展示解析结果，并通过独立表单维护手工补充记录。
- 解释层根据基线状态说明有利因素和压力。
- 用户根据建议结合自身感受做最终决定。

## 非目标

- 当前不做医疗诊断。
- 当前不预测疾病。
- 当前不提供紧急健康建议。
- 当前不自动修改 Polar 账户数据。
- 当前不把 token 上传到第三方服务。
- 当前不执行无人确认的训练计划。
- 当前不以 AI 输出替代确定性评分。
- 当前不与其他用户进行恢复排名。
- 当前不承诺 Kubios 账户自动导出。
- 当前不保证所有 Polar 历史数据永久可取。
- 当前不把 Dashboard 作为写入数据库的管理后台。
- 当前不建立云端多租户系统。

## 设计原则

- 原始事实与派生结果分层保存。
- 外部 API 变化应被限制在客户端与导入层。
- 数据库是分析与展示之间的稳定契约。
- 日粒度是当前恢复分析的基础粒度。
- 基线必须排除被评估当天以避免泄漏。
- 异常值优先使用 median 与 MAD 稳健处理。
- 评分版本必须和结果一起持久化。
- 推荐文本由评分区间确定。
- 缺失数据允许部分计算。
- 配置应集中管理而不是散落硬编码。
- 写入任务应支持重复运行。
- 所有 upsert 必须有明确唯一键。
- 日志不得输出 secret 或 token。
- 测试覆盖应与风险和影响范围匹配。
- 文档必须随架构、版本和数据结构更新。

## 成功标准

- OAuth 成功后 token 文件可安全生成。
- 抓取失败时错误不泄露凭据。
- 相同原始数据重复导入不会制造重复业务记录。
- 日指标每个日期最多一行。
- 基线窗口严格不包含当天。
- 有效历史少于 7 天时不伪造可用基线。
- 评分始终落在 0 到 100。
- 评分结果包含 score_version。
- Dashboard 遇到空值不崩溃。
- 日报在缺失字段时仍可生成。
- 全量 unittest 保持通过。
- 文档中的现状能被代码或数据库验证。
- 任何新外部来源都有 raw 层。
- 任何新评分版本都保留 fallback 路径。
- 用户能追踪主要恢复压力来源。

## 未来方向

- Phase 12.0 已完成 AI Coach 架构与安全设计，但未实现运行模型。
- Phase 12.1 仅在 provider、隐私、审计 migration 和评估获批后实施。
- AI Coach 只消费已计算且 allowlisted 的结构化事实。
- Phase 13 将探索 Nutrition Engine。
- 营养数据应有独立 raw 与 normalized 层。
- Phase 14 将探索 Training Planner。
- 计划器必须读取恢复状态但不能改写评分。
- Phase 15 将探索 Mobile App。
- 移动端应通过稳定服务接口读取数据。
- 数据库 migration ledger、统一应用版本和端到端同步命令均已完成。
- 未来应增加备份和恢复手册。
- 未来应增加数据保留与删除策略。
- Recovery Confidence 已独立实现并持久化。
- 未来应增加来源质量监控。

## 维护责任

- Product Owner 决定产品优先级和验收。
- Chief Architect 维护架构、算法边界与路线图。
- Lead Software Engineer 负责实现、测试与迁移。
- 修改数据库时必须同步 DATABASE.md。
- 修改字段含义时必须同步 DATA_DICTIONARY.md。
- 修改评分时必须同步 RECOVERY_ENGINE.md。
- 完成阶段时必须同步 CURRENT_STATE.md。
- 发布行为变化时必须同步 CHANGELOG.md。
- 改变架构边界时必须记录 DECISIONS.md。
- 改变 API 使用方式时必须同步 API.md。
- 改变版本口径时必须同步 VERSIONING.md。
- 改变测试命令或策略时必须同步 TESTING.md。

## 验收清单

- 项目描述与实际代码一致。
- 版本说明不把历史快照写成当前事实。
- 所有路径使用仓库相对路径。
- 文档不包含访问令牌。
- 文档不包含客户端密钥。
- 文档不复制 raw_json 敏感内容。
- 当前模块清单与 src 目录一致。
- 当前测试数量与 unittest 输出一致。
- 当前数据库表清单与 SCHEMA 一致。
- 未来模块明确标记 Planned。
- 医疗边界有清晰声明。
- README 能导航到完整文档。
