---
title: "check-drift.sh — 契约文件一致性检测"
category: tools
verified_at: 2026-10-16
keywords:
  - drift
  - content-hash
  - consistency
  - registry
  - baseline
  - git-hash-object
---

# check-drift.sh — content-hash 契约一致性检测

> `bin/check-drift.sh` — 对 contexts/ 关键契约文件存 content-hash 基线，
> 检测偏离（改/删/新增未注册），并在 tips/ 变动时提示同步两个注册表。

## 本地衍化来源（非外部迁移）

一次会话里连续三次手动同步注册表（run-agent.sh→script-output-index+checklist；
新 tip→checklist；review-artifact.py→README），还靠 pre-push hook 兜底才没漏 README。
drift 在眼前发生三次 → 把 hook 那条孤立的 README 检查，泛化成跨 contexts/ 的 content-hash drift 检测。
纯本地工具，零外部依赖（git hash-object + shell）。

## 理论

- hash = 文件指纹：同内容同 hash，改一字节 hash 全变。存 64 字符即存"状态快照"，不存文件本身。
- drift = 当前 hash vs 基线逐项比。精髓不是"报告变了"，而是"每次偏离都成为必须显式确认的事件"——
  把隐性漂移变成显性决策（和 run-agent 的"隐性→显性契约"同一方法论）。
- 复用 `git hash-object`（git 的 blob SHA），指纹与 git 一致，不自己算。
- 和 git 的区别：git 管"字节版本历史"；check-drift 管"此刻注册表与现实是否自洽"（跨文件一致性，git 不管）。

## 追踪范围

`.codebuddy/rules/*.md` + `contexts/tips/**/*.md` + `workflow.md` + `preferences.md`
（含两个注册表：script-output-index.md、analysis-checklist.md）。约 73 文件。
不含 notes/history（噪音大）。

## 用法

```bash
check-drift.sh            # 检测 vs 基线，报 drift（exit 1=有 drift）
check-drift.sh --init     # 首次建基线
check-drift.sh --accept   # 接受当前状态为新基线（确认改动是对的）
check-drift.sh --quiet    # 机器输出：只 drift 行 + exit code
```

- baseline 存 `contexts/.drift-baseline`（入 git，作为单人团队基线，本身有版本）。
- drift 类型：MODIFIED（改了）/ DELETED（删了，引用悬空）/ UNTRACKED（新增，可能没注册）。
- 跨文件联动：任一 tips/ 变动 → 提示检查两个注册表（治"新 tip 没注册 / 改 tip 没同步 checklist"）。

## exit code

| code | 含义 |
|---|---|
| 0 | 无 drift（或 init/accept 成功） |
| 1 | 检测到 drift |
| 2 | 无基线 / 用法错 |

## 工作流接入建议

- 编辑 rules/tips 后手动跑一次 `check-drift.sh`，确认 drift 都是预期的 → `--accept`。
- 可挂进 discipline D-O8（编辑后结构校验）或 pre-push，和 validate-pure 并列。

## 验证

2026-10-16 建立：init 73 文件；clean→no drift；改 tips→MODIFIED+联动提示+exit1；revert→clean。

---
> **Local overlay** — if `contexts/local/tips/tools/check-drift.md` exists, read it too (install-specific notes and evidence).
