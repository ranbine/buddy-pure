---
title: "Systematic Debugging"
category: analysis
verified_at: 2026-08-21
keywords:
  - debugging
  - methodology
  - root-cause
  - analysis
  - troubleshooting
---

# Systematic Debugging

> 来源：obra/superpowers systematic-debugging skill
> 用途：任何 bug/test failure/unexpected behavior，在提出 fix 前必须走这个流程

## Iron Law

```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
```

尤其要用在：
- 时间压力大时（急躁导致瞎猜）
- "就改一下试试"看起来很明显时
- 已经试了多个 fix 都没用时

## 四阶段流程

### Phase 1: Root Cause Investigation

1. **读错误信息** — 完整读 stack trace，不跳过。注意行号、文件路径、error code
2. **稳定复现** — 能每次触发吗？步骤是什么？不能复现 → 收集更多数据，不猜
3. **检查最近变更** — git diff, 新依赖, 配置变化, 环境差异
4. **多组件系统 → 在边界加诊断**:
   - 每个组件入口/出口加 log
   - 跑一次收集证据 → 定位断在哪层
5. **Trace Data Flow** — bad value 从哪来？一直向上追到源头。Fix at source, not symptom

### Phase 2: Pattern Analysis

1. 找 working example（同 codebase 里类似的能工作的代码）
2. 对照 reference 实现（完整读，不 skim）
3. 列出所有差异（别假设"这个不重要"）
4. 理清依赖和假设

### Phase 3: Hypothesis & Testing

1. 形成单一假设："我认为 X 是根因，因为 Y"
2. 做最小变更测试假设（一次只改一个变量）
3. 没用 → 形成新假设，不要在上面继续叠 fix

### Phase 4: Implementation

1. 先写 failing test
2. 实施单一 fix（修根因，不修表面）
3. 验证：test pass + 无 regression
4. **≥3 次 fix 失败 → STOP，质疑架构**（不是假设错了，是方向错了）

## Red Flags — 停下来回 Phase 1

- "先试试改 X 看看"
- "快速修一下，回头再查"
- "我不完全理解但可能有用"
- "同时改几个东西跑测试"
- "再试一个 fix"（已失败 2+ 次）
- 每个 fix 暴露新位置的新问题

## 常见借口 vs 现实

| 借口 | 现实 |
|------|------|
| "问题简单不需要流程" | 简单问题也有根因，流程对简单 bug 很快 |
| "紧急没时间走流程" | 系统化 debug 比瞎猜快 |
| "先改再查" | 第一个 fix 定调，一开始就要对 |
| "多改几处省时间" | 分不清哪个生效，还会引入新 bug |
| "3+ 次失败 → 再试一个" | 3+ 失败 = 架构问题，不是继续猜 |

## 对应到测试 log 分析

| Phase | 在 ST log 分析中的体现 |
|-------|----------------------|
| Phase 1 | 读 console.log error → 读 framework/simulator log → 读 pod status |
| Phase 2 | 找 pass 的同类 run 对比配置/版本/环境 |
| Phase 3 | "模拟器卡 initializing 是因为 X" → 验证 |
| Phase 4 | 修 confix/profile → rerun → 确认 pass |
| ≥3 fails | 不是你的配置问题 → 是工具版本/框架 bug |

---
> **Local overlay** — if `contexts/local/tips/analysis/systematic-debugging.md` exists, read it too (install-specific notes and evidence).
