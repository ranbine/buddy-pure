---
title: "action-gate"
category: tools
keywords:
  - gate
  - preToolUse
  - hook
  - approval
  - L3
---

# action-gate（动作审核 hook）

> preToolUse hook + 策略文件 + 审批日志。按风险分层拦截 agent 的写操作，先 shadow 观察、再 enforce。

| 文件 | 作用 |
|---|---|
| `bin/action-gate.py` | hook 主体（stdlib，Python ≥ 3.9，deadline 1.5s） |
| `bin/cbp-gate` | 用户 CLI：`approve <gate_id>` / `list` / `tail [N]` / `stats [--days D]` / `mode [shadow\|enforce]` / `apply` |
| `bin/gate-audit.py` | 周审计：日志 → `$CBP_DATA/gate/proposals/<date>.{json,md}`（relax = L2 高频 → 新 L1 规则；tighten = L2 中的危险模式 → 新 L3 规则；L3/DENY 样本按当前策略重放）；从不改策略 |
| `bin/gate-install.py` | `install` / `remove` / `status`；默认 pure + 其 toolsSettings 里的所有子 agent；改前备份到 `$CBP_CLI_HOME/agents/.backup/` |
| `.codebuddy/rules/gate-policy.json` | 策略模板（受保护，agent 不能改） |
| `$CBP_DATA/gate/decisions-YYYY-MM.jsonl` | 判定日志；`approvals/` 一次性审批 |
| `tests/test_action_gate.py` | `python3 -m unittest discover -s tests -p 'test_action_gate.py'` |

## 安装

```bash
./install.sh                         # 渲染 agents → $CBP_CLI_HOME/agents
python3 bin/gate-install.py install  # 挂 gate + trace hook（install.sh 重新渲染后要再跑一次）
python3 bin/gate-install.py status
python3 bin/cbp-gate stats          # shadow 期看误报
```

## 用户信息与个人规则：两个本地文件

共享的部分只有代码和 `.codebuddy/rules/gate-policy.json`（模板），可直接分享或公开。属于个人或站点的内容只放在两个 gitignored 文件里，它们都在 `config/` 下，受 gate 保护，agent 不能改：

| 文件 | 放什么 |
|---|---|
| `config/local.env` | 身份和路径：邮箱、scratch 目录、tmp 前缀、可删除目录、gated agents、时区、agent 预算 |
| `config/gate-policy.local.json` | 个人规则：内部 MCP server 的写工具、信任的内部 CLI、`mode`；`cbp-gate mode` 和 `cbp-gate apply` 只写这个文件 |

overlay 的格式见 `config/gate-policy.local.example.json`：
- `rules`：放在模板规则之前，同一层级时报告 overlay 里的规则 id。
- `rule_overrides`：按 id 修改模板规则的字段。
- 未知的 key、未知的 rule id、和模板重复的 id、修改 id → 加载失败（fail-closed）。

换一台机器或分享给别人时，只需重写这两个文件，代码和模板不用动。

安全约束（reviewer 2026-10-26）：
- hook 用 `/usr/bin/python3 -I` 启动（由 gate-install 写入），`PYTHONPATH` 和用户 site-packages 不生效；配置值里的 `~` 按 passwd 的 home 展开。
- hook 只从文件读配置，**忽略环境变量**：`CBP_ROOT` / `CBP_DELETE_ALLOW` / `GATE_POLICY` 等即使设了也不生效，`HOME` 取自 passwd。原因：agent 能影响环境变量，例如 `.env` 经启动脚本导出。测试或特殊部署时，把 `--policy` / `--policy-local` / `--data` 写在 hook 命令行里（agent 配置受保护）。
- `rule_overrides` 只能改 `tool / cmd / unless_cmd / unless_tool / wpath_match / argv_any / note`，不能改 `level`；DENY 规则和 builtin 规则不能被 override。不过改 `tool` / `cmd` 仍然可以缩小某条 L3 规则的匹配范围，甚至可以让它永远匹配不到、等于关掉。这只在 overlay 文件受保护、只由用户编辑的前提下才可以接受。
- `mode` 必须是 shadow 或 enforce，`l2_default` 必须是 allow 或 block，`approval_ttl_sec` 必须是 1–3600 的整数。不符合时加载失败（fail-closed），避免拼写错误让 gate 悄悄退回 shadow。
- `cbp-gate mode` 和 `cbp-gate apply` 在 agent 上下文里会拒绝执行。

## 策略模板与占位符

`gate-policy.json` 不写任何本机路径或身份，`{{KEY}}` 在 `load_policy()` 时展开（`bin/action-gate.py: policy_vars()`）：

| 占位符 | 来源（`config/local.env` / 环境变量） | 默认 |
|---|---|---|
| `{{CBP_ROOT}}` `{{CBP_DATA}}` `{{CLI_HOME}}` | `config/paths.env` / `CBP_CLI_HOME` | 仓库根 / `data` / `~/.codebuddy` |
| `{{TMP_PREFIX}}` | `CBP_TMP_PREFIX` | `/tmp/<login>-` |
| `{{CBP_TMP}}` | `CBP_TMP`（`paths.env`） | `.tmp` |
| `{{SCRATCH_DIRS}}`（列表） | `CBP_SCRATCH_DIRS`（`:` 分隔） | 空 |
| `{{SELF_EMAILS}}`（列表） | `CBP_SELF_EMAILS`，否则 `CBP_USER_EMAIL` | — |
| `{{GATED_AGENTS}}` / `{{GATED_AGENTS_RE}}` | `CBP_GATED_AGENTS` | pure, reviewer, html-generator, health-checker |
| `{{DELETE_OK_RE}}` | `CBP_DELETE_ALLOW` + scratch + tmp 前缀 | 未设 allow-list 时 = `paths.env` 里的运行时目录 |

- 列表占位符必须单独作为一个数组元素，展开时拼接进数组。
- 未知占位符、或 allow-list 配得过宽 → 加载失败。`CBP_SCRATCH_DIRS` 不能是 `/`、`$HOME`、仓库根、`~/.codebuddy` 或它们的上级；`CBP_DELETE_ALLOW` 可以是 `$HOME`（这里的删除仍是 L3，需要审批），但不能是 `/` 或 `$HOME` 的上级；`CBP_TMP_PREFIX` 不是 `/tmp/<name>-` 形式）→ 加载失败 → enforce 下全部阻止（fail-closed）。
- allow-list 按路径前缀匹配（`^` 锚定），路径里只是"包含"某目录不算在内。
- `cbp-gate apply` 写入 `config/gate-policy.local.json`，写之前把本机路径换回 `{{CBP_ROOT}}` / `{{CLI_HOME}}` / `{{HOME}}`（正则字段用 `*_RE`），策略文件始终可公开。
- 用 `GATE_DATA` / `GATE_POLICY` 改了位置时，`protected_paths` 不会跟着变，需要自己把新位置加进去。

## cbp-cli preToolUse 行为（实测于 2.26）

- stdin：`{"hook_event_name","cwd","session_id","tool_name","tool_input"}`；MCP 工具名 `@server/tool`；`tool_input` 含 `__tool_use_purpose`（gate 忽略）
- exit 2 → 阻止，stderr 回模型；**exit 1 / 超时 → 放行**（所以脚本自己 fail-closed）
- matcher：`shell` / `write` / `@server` / `@server/*` / `@server/tool` 均可；同一工具多个 hook 全部执行
- hook 先于 CLI 权限确认执行

## 层级

DENY（不可审批：agent 调 `cbp-gate` 除 list/tail/stats、改 gate/策略/agent 配置/`config/`、删 allow-list 外路径）> L3（阻止，可 `cbp-gate approve`：无法解析的命令、cd 到未知目录后的相对路径修改、调用未挂 gate 的 agent、`--push` 类脚本、git push / 破坏性 git、k8s 写、未识别为只读的 MCP 工具、给非自己发邮件）> L0（只读）> L1（自有路径写、本地 git、自有脚本、给自己发邮件、scratch 内删除）> L2（其余，按 `l2_default` 放行 + 记录）。

MCP：`l0-mcp-read` 放行 `get_/search_/list_/check_/show_` 前缀；其余一律 `l3-mcp-write-default`。`l3-example-mcp-write` 是按 server 精细化的示例，换成你自己的 server 名和写工具。

shell 解析：引号感知的注释/heredoc；拆 `; && || |`、`$( )`、反引号；剥 `{ } if/then/do` 等关键字和 wrapper（nice/stdbuf/setsid/timeout/xargs/env/flock…）；展开 `bash -c`、`eval`、`ssh host cmd`、`find -exec`；喂给 shell 的 heredoc 按 shell 再拆，喂给 python 等的 body 按内容判（rmtree / push / 受保护路径）；跟踪 `cd`。复合命令取最高段。

## 常用

```bash
cbp-gate stats                  # L3/DENY by rule、L2 top commands
cbp-gate list                   # 最近 24h 被拦（shadow 下为"会被拦"）的动作
cbp-gate approve e6141cd7       # enforce 下放行一次（默认 10 分钟，参数绑定）
cbp-gate mode enforce           # shadow → enforce
cbp-gate apply <date> P01 P03   # 只能在真终端：逐条 y/N + 输入 apply；只增不改，先备份
python3 bin/gate-install.py remove   # 紧急卸载
```

## 注意

- 防误操作护栏，不是沙箱：变量路径、混淆写法可绕过字符串匹配。
- 凭据文件（`.ssh/`、`.netrc`、`.env`、`*.token`、`*.key`）只拦写，读不拦。
- `cbp-gate approve` 只能在真终端：检测到 `CBP_*` 环境变量或 cbp-cli 祖先进程即拒绝，且需在 `/dev/tty` 回输 gate_id。
- action_id = sha256(tool, 参数去掉 `__tool_use_purpose`, cwd)。
- shadow 下 hook 自身错误放行（记 `verdict:error`）；enforce 下错误 = 阻止。
- `$CBP_DATA/gate/` 是运行时日志，含真实命令和路径，已在 `.gitignore`，不要提交。

## 其他 hook 事件（实测于 2.26）

| 事件 | 触发时机 | stdin 关键字段 | stdout 进模型？ | 能拦？ |
|---|---|---|---|---|
| `userPromptSubmit` | 每轮用户消息后、LLM 前 | `prompt`, `session_id`, `cwd` | ✅ 作为 context 注入 | 未测 |
| `preToolUse` | 工具执行前 | `tool_name`, `tool_input` | ❌（仅 exit 2 时 stderr 回模型） | ✅ exit 2 |
| `postToolUse` | 工具执行后 | 另含 `tool_response` | ❌ | ❌（工具已执行） |
| `stop` | 本轮最终回复后 | `assistant_response` | — | — |
| `agentSpawn` | 会话启动 | — | ✅ | — |

并行工具调用时 pre/post 时间戳会挤在一起（hook 串行补跑），只能算整段，不能拆单个工具。

---
> **Local overlay** — if `contexts/local/tips/tools/action-gate.md` exists, read it too (install-specific notes and evidence).
