# Training Studio｜认知训练室

## 目标与边界

Training Studio 是 RHYTHMOS 的认知表现训练与趋势观察模块。它通过短时、结构化任务练习专注、警觉和工作记忆；成绩描述任务内表现与练习熟悉度，不代表智力水平、脑年龄或医学诊断。

`Daily Neural Check` 使用固定协议检测当日状态并进入 Neural Readiness 基线；`Training Studio` 使用可自适应难度的练习协议，成绩只进入训练档案、积分和训练进展，不写入 `neural_assessments`、`daily_neural_features` 或 `recovery_scores`。

## 第一阶段方案

- **Focus & Alertness**：Target Focus（目标专注）、Go/No-Go（反应抑制）、Visual Search（4×4 顺序视觉搜索）。
- **Working Memory**：Memory Grid（位置记忆）、Sequence Memory（数字顺序）、N-back Lite（1-back / 2-back）。

标准模式约 6–8 分钟，快速模式约 3–4 分钟。每次 session 先在浏览器完成三个任务，再一次性提交结果；`quick` 与 `standard` 分开统计。

## 5 秒交互练习

Visual Search、Memory Grid、Sequence Memory 与 N-back Lite 均在正式任务前提供独立的 3、2、1 倒计时和 5 秒交互练习。练习只教授操作，不用于能力评估：浏览器仅在内存中保留练习状态，绝不创建训练 session、trial、任务汇总或训练进展记录。进入正式任务前会清除全部练习计时器、事件监听器与临时刺激，并重新初始化正式任务。

- `visual_search_practice_v1`：3×3 数字盘，按 1 至 4 顺序点击。
- `memory_grid_practice_v1`：3×3 棋盘，观察两个非相邻位置后复现。
- `sequence_memory_practice_v1`：观察三个不重复图形的出现顺序后复现。
- `nback_lite_practice_v1`：快速模式教学 1-back，标准模式教学 2-back；每个预生成序列均含有效匹配刺激。

练习期间失焦或页面隐藏会放弃本轮练习并返回说明页，不会标记正式训练中断。

## 协议与指标

任务使用 `performance.now()`，保存设备、视口、输入方式、浏览器、操作系统和时区。每个任务保存 trial 原始记录与汇总：准确率、正确/错误/遗漏、RT 中位数/均值/CV、难度起止与协议版本。N-back 的 d-prime 使用 log-linear 修正，避免极端命中率产生无穷值。

自适应规则是按轮次的温和调整：准确率 ≥90% 且连续两轮稳定才升一级，75–89% 保持，低于 75% 降一级；单次最多变化两级，不因单个 trial 或单纯速度大幅加速。

## 数据结构

schema `0.28.0` 新增 `cognitive_training_sessions`、`cognitive_training_task_results`、`cognitive_training_trials`、`cognitive_training_progress` 和 `cognitive_training_preferences`。写入以 session id 幂等；刷新不会重复 session。中断记录保留但不进入个人最佳与稳定等级。

## 推荐与已知限制

推荐仅使用本地规则：近期较少的方案优先推荐；脑力疲劳 ≥8 时建议跳过；当日神经状态偏低时建议快速模式。用户始终可以忽略推荐。不同设备、输入方式、屏幕尺寸、训练模式和难度之间不能直接比较原始反应速度。

## 未来扩展（本阶段不实现）

认知控制与灵活性、信息处理速度、Stroop、Task Switching、Symbol Match、高级苏尔特方格、闪记、多模态 N-back、AI 个性化训练计划，以及训练效果与现实任务表现的验证。
