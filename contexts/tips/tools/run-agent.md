---
title: "run-agent.sh — 通用子代理进程调用器"
category: tools
verified_at: 2026-10-16
keywords:
  - agent
  - subagent
  - process
  - delegation
  - 曲线救国
  - cbp-cli
---

# run-agent.sh — 通用子代理进程调用器（曲线救国）

> `bin/run-agent.sh` — 以**独立进程**启动任意 Pure subagent，传任务字符串，返回 agent stdout。
> 当主上下文没有原生「委托 subagent」调度能力时，用进程边界实现等价委托。

## 方法论

| | 机制 |
|---|---|
| 原生委托 | 进程内切换 agent 上下文 |
| run-agent.sh（曲线救国） | 进程外起**同一份** `agents/<name>.json` 定义 |

两者加载完全相同的 agent 定义（prompt + allowedTools），结果等价。进程边界额外带来：
1. **上下文隔离** — 子进程独立 context window，不污染主 agent。
2. **返回契约** — 父进程只认 stdout（任务里要求结构化/verdict 输出，便于解析）。
3. **权限收敛** — agent 用自身 `allowedTools` 沙箱（如 reviewer 只有 read/shell/glob/grep，改不了被审产物）。
4. **可组合** — 「起 agent」成为标准动作，可拼 main→html-generator→reviewer→main 链。

## 用法

```bash
run-agent.sh <agent-name> <task...> [--contract c] [--session id] [--timeout N] [--budget N] [--out F] [--raw] [--quiet]
# 或结构化 stdin：
echo '{"task":"...","contract":"json|verdict|raw","session_id":"..."}' | run-agent.sh <agent> [flags]
```

- `<agent-name>`：**用名字**，不是 JSON 路径（传路径报 `failed to set agent: Internal error`）。
- `--contract`：输出形态 —— `verdict`(单 token) / `json`(单行 JSON) / `raw`(不约束，透传)。脚本据此给 agent 追加格式指令。
- `--session`：复用 CLI 原生会话（底层 `--resume-id`），多轮状态**不自建 Redis**。
- `--timeout`：秒，默认 180。超时 exit 124。
- `--out`：把提取后的结果 tee 到文件。
- `--raw`：强制 raw，不注入契约不提取，原样透传。
- `--quiet`：抑制 banner（banner 走 stderr）。

## 三条工程契约（v2 核心）

**输入契约**：两种模式。裸 args（向后兼容 analyze-log.sh 式）；或 stdin JSON（`task`/`contract`/`session_id`，适合流水线）。stdin 可选，无则退回 args。

**输出契约**：agent 被要求末尾吐 `RESULT=<payload>`。脚本用 `grep -o 'RESULT=.*'` **行内抠取**（CLI 常把叙述和 RESULT 拼同一行，故不能锚 `^`），只把 payload 送 stdout。无 RESULT 则回退末行 + exit 3。

**流分离**：stdout = 只有最终结果（给程序 parse）；stderr = 叙述 + `[tool]` 日志 + banner + 报错（给人调试）。CLI 本就把 `[tool]` 日志写 stderr，脚本再把 agent 叙述剥到 stderr，出菜口彻底干净。

## 运行记录

每次 spawn 由 EXIT trap 追加一行 `$CBP_DATA/agent-runs.jsonl`（agent / timeout_s / exit / outcome / wall_s / contract / task 前 200 字 / parent_session），不影响退出码；路径可用 `CBP_AGENT_RUNS_LOG` 覆盖。汇总看 `bin/agent-perf.py`。任务字符串按 `rules/orchestration.md` → Delegation brief 写。

## 工具预算

`--budget N`，或任务里一行 `BUDGET: ≤ N tool calls` → 导出 `CBP_TOOL_BUDGET`，由 `bin/agent-trace.py` 在第 N+1 次工具调用时拦下并要求子 agent 收尾返回。见 `tips/tools/agent-perf.md`。

## exit code

| code | 含义 |
|---|---|
| 0 | agent 跑完，契约命中 |
| 124 | 超时 → 调用方回退底层脚本 |
| 2 | 用法/guard 错（未知 agent、深度保护、坏 JSON、坏 contract） |
| 3 | 跑完但 agent 没遵守契约（无 RESULT=），已 best-effort 回退末行 |

## 示例

```bash
# verdict：stdout 纯 token
run-agent.sh reviewer "Review X against docs/index.html." --contract verdict --quiet
# → PUBLISH-OK

# json：stdout 可直接 json.load
run-agent.sh reviewer "Review X. Include verdict and score." --contract json --quiet
# → {"verdict":"PUBLISH-OK","score":100,...}

# stdin 结构化输入
echo '{"task":"Review X.","contract":"verdict"}' | run-agent.sh reviewer --quiet
```

## 底层实现要点

```bash
cbp-cli chat --agent <name> --no-interactive -a "<task>"
```

- **不要**加 `--trust-all-tools`：CLI 对非交互已注入信任，再加报 `cannot be used multiple times`。
- 存在性校验用路径 `$CBP_CLI_HOME/agents/<name>.json`（渲染后的 agent 只装在 cbp-cli 目录），但调用用名字。
- **CLI 流行为（实测）**：`[tool] Running:...` 等工具日志走 **stderr**；agent 的自然语言输出走 **stdout**，且叙述句尾常不换行就接 `RESULT=`（同一行）。故提取用 `grep -o 'RESULT=.*'` 不能锚 `^RESULT=`。
- **契约注入**：脚本据 `--contract` 给 task 追加「只输出一行 RESULT=... 不要叙述」指令；raw 模式不注入不提取。

## Guards

- **深度保护**：`CBP_AGENT_DEPTH`，默认 max=1。防 agent→run-agent→agent 递归。命中 exit 2。
- **agent 不存在**：exit 2 + 列出可用 agent。
- **超时**：exit 124，调用方应回退底层脚本（同 fastcontext→grep 回退策略）。

## 何时用 agent vs 直调脚本

```
需要「角色化判断 / 上下文隔离 / 权限收敛」?
  ├─ 是 → run-agent.sh（agent 补脚本之外的判断，如 reviewer 提醒译文准确性脚本查不了）
  └─ 否（纯机械、确定性校验） → 直调脚本（快、确定）
```
最佳形态：**agent 包脚本**——脚本保下限（机械检查），agent 补上限（角色判断）。

## 关系

- run-agent.sh 是通用版：任意 agent + verdict 契约 + 回退 + 深度保护。

## 验证

- 2026-10-16 v1 冒烟：未知 agent→exit 2+列表；深度保护→exit 2；真实 reviewer→PUBLISH-OK rc=0。
- 2026-10-16 v2 四模式全绿：
  - `--contract verdict` → stdout 纯 `PUBLISH-OK`，叙述/日志全在 stderr。
  - `--contract json` → stdout 合法 JSON，`python3 json.load` 直接解析成功。
  - stdin JSON 输入 → stdout 纯 token。
  - 裸模式（无 contract）→ raw 透传，叙述保留，向后兼容。

---
> **Local overlay** — if `contexts/local/tips/tools/run-agent.md` exists, read it too (install-specific notes and evidence).
