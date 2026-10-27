---
title: "gen-agent-evolution.py — 按 agent 聚合演进记录 (L2)"
category: tools
verified_at: 2026-10-16
keywords:
  - agent
  - evolution
  - changelog
  - derived
  - aggregate
  - git-log
---

# gen-agent-evolution.py — 按 agent 聚合演进记录（L2 派生式）

> `bin/gen-agent-evolution.py` — 从 git log + decisions/ + workflow-patterns
> 自动聚合每个 agent 的演进史到 `contexts/agents-evolution/<agent>.md`。

## 理念（L2：派生而非手维护）

演进记录是**派生物**，不是手写文件——同 check-drift、测量/决策分离的「记录即生成、不靠记忆」哲学。
源头（commit / decision / pattern）本来就在写，脚本按 agent 聚合，**零新增手动负担**，源变重跑即新、不 drift。

对比其它记录视角（互补不重复）：
- README changelog = 全局时间线
- decisions/ = 为什么做某架构选择
- workflow-patterns = 行为纠偏模式
- **agent-evolution = 按主体聚合的变更史**（回答「reviewer 这半年怎么演进的」）

## 用法

```bash
gen-agent-evolution.py            # 重生成全部 agent
gen-agent-evolution.py reviewer   # 单个
gen-agent-evolution.py --dry-run  # 预览不写
```

输出：`contexts/agents-evolution/<agent>.md`（reviewer / html-generator / health-checker / pure）
每份含三节：Commits（date+subject 表）/ Decisions / Workflow Patterns。

## 匹配机制

agent → 关键词表（名字 + 别名 + 关联脚本名），对 commit subject+body / decision / pattern 做小写子串匹配。
- area != agent 1:1（commit 前缀 `fix(review)` → reviewer），故用关键词而非前缀精确匹配
- 宽匹配：宁多包勿漏（html-generator 经手所有报告 commit，数量本就大，属实情非误吞）
- 关键词表在脚本顶部 `AGENTS` dict，精度可随时调

## 触发（何时重跑）

- 某 agent 的能力/prompt/工具/关联脚本/把关规则变更并 commit 后
- 周回顾时批量刷新
- 约定 commit 用 `<type>(<area>):`，area 尽量含 agent 名/别名便于匹配

## 坑

- f-string 内不能含反斜杠（py<3.12）：escape 提到 f-string 外
- agents 模板在 `agents/`；输出写 `contexts/agents-evolution/`

## 验证

2026-10-16 建立：5 agent 全生成；reviewer 聚合出 14 commit + 3 decision + 2 pattern（9-29 转正→push gate→把关归 agent），全自动派生零手写。

---
> **Local overlay** — if `contexts/local/tips/tools/gen-agent-evolution.md` exists, read it too (install-specific notes and evidence).
