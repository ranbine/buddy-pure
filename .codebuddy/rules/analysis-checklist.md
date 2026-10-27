---
alwaysApply: false
description: "Tips 格式标准（2026-07-29 起生效）"
---


## Tips 格式标准（2026-07-29 起生效）

新建或改造 tips 文件必须遵循接口卡片格式：

```
# tool-name

> 用途：一句话
> 触发：什么场景该加载这个 tip

## [核心内容：认证/接口/判断标准等]
- 用表格，不用段落叙述

## 调用模板（如有）
- 一个最小可用示例

## 限制/坑
- 具体、可检查的约束列表

## 快速验证 / Fallback（如有）
```

**禁止**：
- 叙述性段落解释"为什么"（放 history 不放 tips）
- 重复示例（一个够用）
- 低频集成内容（拆到单独文件或删除）

## Trigger Table

| 触发场景 | Tips 文件 |
|----------|-----------|
| 排查故障 / 根因分析（先读原则再动手） | `tips/analysis/investigation-principles.md` |
| 调试卡住 / 连续 fix 失败 | `tips/analysis/systematic-debugging.md` |
| 重大决策前做 pre-mortem | `tips/prompts/red-team-review.md` |
| 写文案 / 去 AI 味 / 目标澄清 | `tips/thinking/de-ai-writing.md`, `tips/thinking/goal-clarity.md` |
| HTML 报告样式 | `tips/infra/html-report.md` |
| UI 动效 | `tips/design/ui-animation-rules.md` |
| Git 凭据 / 非交互操作 | `tips/infra/git.md` |
| 进入分析场景前（自检 D-A 纪律） | `rules/discipline.md` Tier 1 |
| 准备输出文件/交付物 | `rules/discipline.md` Tier 2 |
| 执行多步流程（daily-flow / sync / deploy） | `rules/discipline.md` Tier 3 |
| 部署 HTML 到 docs/（report / review / dashboard） | `rules/sync.md` |
| 生成报告/HTML（daily/weekly/monthly/insight）→ delegate html-generator | `rules/report-generation.md` |
| 多 agent 编排（chain 串行 / graph 并行 DAG）→ 定义见文件内表格 | `rules/orchestration.md` |
| 需以进程方式启动某个 subagent（无原生委托能力时的曲线救国 / 组合 agent 链） | `tips/tools/run-agent.md` |
| 动作被 gate 拦截 / 调整风险分层策略 / 审批 L3 / 安装或卸载 gate hook | `tips/tools/action-gate.md` |
| 子 agent 慢 / 超时 / 查耗时与轮数 / 设工具预算 | `tips/tools/agent-perf.md` + `rules/orchestration.md` Delegation brief |
| 给 agent/自动化新增有副作用的能力 / 设计放权、审批、shadow→enforce 流程 | `tips/thinking/progressive-authorization.md` |
| 编辑 rules/tips 后检查契约一致性 / 怀疑文件漂移 / 新 tip 是否注册 | `tips/tools/check-drift.md` |
| 某 agent 能力/规则/关联脚本变更 → 刷新该 agent 演进记录 / 查某 agent 怎么演进的 | `tips/tools/gen-agent-evolution.md` |
