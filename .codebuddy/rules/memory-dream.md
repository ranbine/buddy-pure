---
alwaysApply: false
description: "Memory Dream (记忆整固)"
---

# Memory Dream (记忆整固)

> 自动整理记忆系统，防止 tips/rules/history 腐化。
> 灵感来源：Claude Code v2.1.88 autoDream 模块。

## 触发条件（三重门控）

按顺序检查，任一步 fail 即退出：

1. **时间门**：距上次 dream >= 7 天（检查 `.dream-last` mtime）
2. **增量门**：`history/` 中有 >= 5 天的新日记（自上次 dream 后）
3. **当前任务门**：用户不在执行紧急分析/debug 中（`启动`/`daily` 流程中触发，不打断工作）

## 触发方式

- 在 `daily-flow` Step 4 后追加检查
- 满足条件时输出提醒：`🧹 记忆整固待执行（上次：YYYY-MM-DD，积压 N 天日记），执行？`
- 用户确认后执行（不自动执行，因为耗 context）
- 执行完毕后 `touch .dream-last`

## 4 阶段 Prompt

### Phase 1 — Orient（定向）

目标：搞清楚"已经有什么"，避免重复创建。

```
1. ls contexts/tips/ — 列出所有主题文件
2. 读 workflow.md 和 preferences.md — 当前规则全貌
3. 读 rules/workflow-patterns.md — 当前行为模式
4. skim 最近 7 天 history — 知道这周做了什么
```

### Phase 2 — Gather（收集新信号）

优先级：日记 > 过时规则 > tips 缺口

```
1. 从 history/ 近 7 天提取：
   - 新发现的工具/API/路径（tips 候选）
   - 重复出现的 pattern（workflow-patterns 候选）
   - 新的 known issue 关联（knowledge 候选）
2. 检查 workflow-patterns.md — 有没有应该升级为 rules 的 pattern（confidence >= 0.95，出现 3+ 次）
3. 检查 tips/ 文件 — 有没有内容明显过时的（引用了已下线的工具/旧路径）
```

### Pattern Evolution Rules (自动升级判断)

扫描 `workflow-patterns.md` 中每条 pattern：

| 条件 | 动作 |
|------|------|
| confidence >= 1.0 **且** violation count >= 3 | 🔴 **强制升级** — 写入对应 rules/ 文件或 workflow.md |
| confidence >= 0.95 **且** Learned From 日期 > 30 天前 | 🟡 **建议升级** — 输出候选，等用户确认 |
| confidence < 0.8 **且** 最后 Learned From > 60 天前 | 🟡 **建议归档** — 标记为低活跃 |

升级动作：
- 从 patterns 中删除该条
- 在目标 rules/ 文件（或 workflow.md 对应 section）中加入等效规则
- 记录升级来源：`Promoted from: P-XXX (YYYY-MM-DD)`

**不自动执行升级**，只输出候选列表。人工确认后才改文件。

### Phase 3 — Consolidate（整合）

规则：**合并优先于新建。**

```
0. 检查 .observations.jsonl — 跳过 sha256 未变的文件（已在上次 closeout 处理过）
1. 新信号合并到已有 tips 文件 — 不创建新文件除非主题完全不存在
2. 相对日期转绝对日期 — "今天"/"昨天"/"本周" → 具体日期
3. 删除矛盾旧事实 — 如果新证据推翻了旧结论，更新旧文件
4. 高 confidence pattern 升级 — 从 workflow-patterns.md 提取到对应 rules/ 文件
5. 已完成/不再相关的 pending 项 → 标记完成或删除
```

File Observation 用法：
```python
from cbp_closeout import is_observed
if is_observed("contexts/tips/tools/env-access.md"):
    # 文件内容未变，跳过处理
    pass
```

### Phase 4 — Prune & Index（修剪 + 索引）

硬约束：
- `workflow.md` + `preferences.md` 总计 ≤ 300 行
- `workflow-patterns.md` ≤ 50 条 pattern
- 单个 tips/ 文件 ≤ 5KB
- 每条 pattern 一行描述 ≤ 150 字符（索引用途）

```
1. 检查 workflow.md 行数 — 超标则标记低频规则为"可移出"候选
2. 检查 workflow-patterns.md 条数 — 超标则合并相似 pattern 或归档低 confidence 条目
3. 清理 history/ — 超过 30 天的日记中，已提炼到 tips/knowledge 的内容可压缩为一行摘要
4. 输出 diff 摘要：新增了什么、删除了什么、修改了什么
```

## 安全约束

- **不删除任何文件** — 只修改内容或标记为归档候选
- **不修改 workflow.md 的 Red Lines 段落** — 红线规则永不自动变更
- **所有修改输出 diff** — 便于人工审阅
- **涉及删除规则/pattern 时列出原文** — 用户确认后才真正删

## 输出格式

```
🧹 Memory Dream 完成（耗时 X 分钟）

📥 整合：
  - tips/tools/xxx.md：新增 Y 段落（来源：7/20 日记）
  - workflow-patterns.md：新增 P008（来源：7/18-7/22 重复出现）

🗑️ 清理：
  - workflow-patterns.md：P003 合并入 P001（重复）
  - tips/xxx.md：删除过时段落（失效的旧路径）

📊 健康度：
  - workflow.md: 105 行 ✅ (< 250)
  - patterns: 7 条 ✅ (< 50)
  - tips/ 最大文件: 3.2KB ✅ (< 5KB)
```

## 与现有机制的关系

```
session-end.md（采集层）
    → 写 history + 捕获纠正 → workflow-patterns.md
        → Memory Dream（整合层，每 7 天）
            → 从 history + patterns → 精炼到 tips/rules/knowledge
                → periodic-review（分析层，周/月）
                    → 只读分析，输出趋势洞察
```

三层各司其职：采集 → 整合 → 分析。Dream 填补"原始记录到结构化记忆"这一环。

---
> **Local overlay** — paths like `bin/…` are relative to the repo root; `$CBP_*` names resolve from `config/paths.env` / `config/local.env` at the repo root. If `contexts/local/rules/memory-dream.md` exists, read it as well: it adds or overrides install-specific steps (it wins on conflict). Keep this file generic; put personal/domain details there.
