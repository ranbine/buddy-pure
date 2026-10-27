---
title: "agent-perf"
category: tools
keywords:
  - subagent
  - latency
  - performance
  - delegation
  - run-agent
---

# agent-perf — 子 agent 耗时记录

> `bin/agent-perf.py`。不在 agent 内埋点，拼三份现成数据：
> 会话文件（`$CBP_CLI_HOME/sessions/cli/<id>.json(l)`：起止时间、LLM 轮数、按工具计数、工具输出体积）
> + gate 日志（session → agent，覆盖所有挂 gate 的 agent，含原生 delegate）
> + `$CBP_DATA/agent-runs.jsonl`（`run-agent.sh` 每次 spawn 写一行：timeout、exit/outcome、端到端耗时）。

```bash
agent-perf.py                      # 近 7 天按 agent 汇总：median/p90 耗时、轮数、s/turn、超时、被标记数
agent-perf.py --runs               # 逐次明细（wall_s / turns / tools / s/turn / out_kb / outcome / via / flags / task）
agent-perf.py --turns              # 每 agent 的 tool% / model% / 刹车次数 + 最慢轮次（需 agent-trace）
agent-perf.py --agent reviewer --days 30
agent-perf.py --write-weekly       # $CBP_DATA/agent-perf/YYYY-Www.json（周回顾对比上周）
```

- flags：`TIMEOUT`、`NO_CONTRACT`、`OVER_BUDGET`（工具调用数超该 agent 默认预算：reviewer 10 / html-generator 15 / health-checker 8；按需改 `BUDGETS`）、`SLOW_TURN`（> 20 s/轮）。
- `via`：`run-agent`（有 spawn 记录）/ `run-agent/resume`（续接会话，轮数是整个会话的，不算预算和 s/turn）/ `other`（原生 delegate）。
- join 规则：以每次 spawn 为主，选 20 s 内、cwd 相同、gate agent 不冲突的最近会话；`--session` 续接按会话 id 对上。主 agent 排除；坏文件跳过。时间按 `CBP_TZ` 显示。
- 经验值：spawn ≈ 1.5 s，空任务 6–8 s；耗时 ≈ 轮数 × 每轮秒数（小上下文 ~7 s，大上下文 30+ s）→ 提速靠收窄任务（INPUTS/GIVEN/BUDGET），不是省启动。
- `run-agent.sh` 用法错误（agent 不存在、深度保护）发生在 spawn 前，不记录。

## 会话内计时 + 预算刹车（`bin/agent-trace.py`）

hook：`userPromptSubmit` / `preToolUse` / `postToolUse` / `stop`，`gate-install.py install` 自动挂上（不设 matcher，所有工具都记）。

- 事件写 `$CBP_DATA/agent-trace/trace-YYYY-MM-DD.jsonl`；每轮在 stop 时写一条 `turn`：wall / tool_s（并行区间合并）/ model_s / 工具数 / 最慢 3 个工具。
- 主 agent：上一轮 ≥ 60 s 时，下一轮的 `userPromptSubmit` 往上下文注入一行 `[turn-timing] …`（只出现一次）。
- 预算刹车（仅子 agent）：`run-agent.sh --budget N`，或任务里的 `BUDGET: ≤ N tool calls`（取最后一行）→ `CBP_TOOL_BUDGET`。第 N+1 次工具调用起 exit 2 + "整理已有结果返回"，结果不会像 timeout 那样丢。每个 prompt 重新计数。没给预算 → 只记 `budget_over`，不拦。原生 delegate 拿不到预算，只记不拦。
- 刹车独立于 gate 的 shadow/enforce；但 `$CBP_DATA/agent-trace/` 只有在 gate enforce 时才防篡改。
- trace 里的命令已做凭据脱敏（Authorization / token / password / `-u user:pass` / `-pSECRET`），但仍属运行时数据，不要提交。

---
> **Local overlay** — if `contexts/local/tips/tools/agent-perf.md` exists, read it too (install-specific notes and evidence).
