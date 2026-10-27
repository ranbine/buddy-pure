---
alwaysApply: true
description: "Pure Workflow Rules"
---

# Pure Workflow Rules

> Paths below are repo-relative. Their single source of truth is `config/paths.env`
> (e.g. `history/` = `$CBP_HISTORY`, `pending/` = `$CBP_PENDING`).

## Startup Check (Highest Priority)

Before the first reply in each new conversation, act on the **startup digest** (injected by agentSpawn hook `bin/cbp-startup-hook.sh`; it already ran steps 2–4's data collection — don't re-run; digest missing/FAILED → run the scripts manually):

1. Match user message to trigger words → read corresponding rules/ file, skip remaining checks
2. Digest `daily-summary: INCOMPLETE` → read `rules/daily-summary.md`
3. Digest `auth-check: FAILED` → notify user (hook runs it once per day; pass/skipped = silent)
4. Check `pending/` → process per `rules/pending-queue.md`
5. If Monday and no insight this week → remind
6. If Monday → remind weekly review per `rules/periodic-review.md`; even weeks add bi-weekly; 1st of month add monthly

Priority: trigger words > daily summary > auth-check > pending queue > insight reminder. Execute sequentially, don't throw multiple questions at once.

## Trigger Word Mapping

| Trigger | Rule File | Output Lang | Description |
|---------|-----------|-------------|-------------|
| `启动` | `rules/daily-flow.md` | 中文 | Daily flow |
| `daily` | `rules/daily-flow.md` | English | Daily flow |
| `查看报告` | `rules/daily-summary.md` | 中文 | Daily summary |
| `check-summary` | `rules/daily-summary.md` | English | Daily summary |
| `运行workflow` | this file | 中文 | Show workflow status |
| `insight` | `rules/insight.md` | English | Weekly insight |
| `生成报告` | `rules/report-generation.md` | 中文 | Delegate to html-generator (template dispatch) |
| `generate report` | `rules/report-generation.md` | English | Delegate to html-generator (template dispatch) |
| `体检` / `checkup` | `health-checker` (Function 1) | 中文 | Operational health (cbp-doctor) |
| `校验` / `validate` | `health-checker` (Function 2) | 中文 | Structural validation (validate-pure) |
| `健康检查` / `health check` | `health-checker` (both) | 中文 | Full health (checkup + validate) |
| `orchestrate` | `rules/orchestration.md` | — | Multi-agent YAML orchestration |
| `回顾` | `rules/periodic-review.md` | 中文 | Periodic review (auto-detect) |
| `review` | `rules/periodic-review.md` | English | Periodic review (auto-detect) |
| `周回顾` | `rules/periodic-review.md` | 中文 | Force weekly review |
| `weekly review` | `rules/periodic-review.md` | English | Force weekly review |
| `月回顾` | `rules/periodic-review.md` | 中文 | Force monthly review |
| `monthly review` | `rules/periodic-review.md` | English | Force monthly review |

**Language rule:** Trigger word determines output language. Chinese trigger → Chinese output, English trigger → English output. Subsequent conversation follows user's switch.

**Fuzzy matching rule:** If user message is not an exact trigger but contains key action words from the trigger table, treat it as that trigger but **state what you're doing in one sentence first** (gives user a chance to redirect). Exact trigger → execute silently. Fuzzy match → execute with one-line declaration. No match → don't trigger.

## Red Lines

- **All delete operations (files, data, post-archive removal) must inform user of exact content and wait for explicit confirmation.** Only exception: deleting *inside* your own scratch dirs (`CBP_TMP_PREFIX*`, `.tmp/<sub>`, `CBP_SCRATCH_DIRS/<sub>`) — never the scratch root itself.
- **Only paths under the allow-list may be proposed for deletion** (`CBP_DELETE_ALLOW` in `config/local.env`; default: the repo's runtime dirs from `config/paths.env`). All other paths: refuse deletion even if user requests.
- If the action gate is installed, these are enforced in code (`.codebuddy/rules/gate-policy.json`, `tips/tools/action-gate.md`); text and policy must stay in sync.
- **No verbal promises.** When user requests behavior change, write it into the rule file and commit immediately. Never say "I'll do this next time..." — written rule = guarantee, unwritten = not done.

## Analysis Execution Rules

→ See `rules/analysis-checklist.md` for mandatory reference bindings.
- Core: when entering an analysis/tool scenario, **read the bound md first**, execute per its steps.
- When creating new tips/ md, **must register** in `rules/analysis-checklist.md` trigger table.
- No unregistered md allowed — unbound md = dead doc.

## Discipline Patterns (纪律框架)

→ See `rules/discipline.md`
- 3-tier framework: **D-A** (Analysis) → **D-O** (Output) → **D-P** (Process)
- 进入分析场景 → 扫 Tier 1；准备输出 → 扫 Tier 2；执行多步流程 → 扫 Tier 3
- 每条挂来源 + 翻车实例；无实例的规则不收录

## Workflow Patterns (行为模式库)

→ See `rules/workflow-patterns.md`
- **When**: Same type of mistake happens 2× OR user corrects me
- **Action**: Check patterns file for existing match → if none, extract new pattern immediately
- **Self-audit trigger**: If workflow.md + preferences.md total exceeds 300 lines → flag for review next `启动`/`daily`

## General Behavior Rules

### Docs Sync (docs/ deployment)
→ See `rules/sync.md` for full flow and nav consistency rules.
- Core: generate HTML → copy to `docs/` → update index card → preview → user confirms → commit + push

### Decisions Log
When a non-trivial choice is made (architecture, workflow design, trade-off), write to `decisions/YYYY-MM-DD-<slug>.md` using the format in `decisions/README.md`. Record: decision, alternatives considered, reason, revisit condition. No user reminder needed.

### Conversation History
After completing a clear task, immediately append summary to `history/YYYY-MM/YYYY-MM-DD.md` (task description + key conclusions). No user reminder needed.

### Memory Dream (记忆整固)
→ See `rules/memory-dream.md` for full 4-phase process.
- Triggered in daily-flow Step 4.5 (every 7 days, user confirms before execution)
- Orient → Gather → Consolidate → Prune
- Core constraint: merge > create; relative dates → absolute; index ≤ hard limits

### Tool/Script Tips
After using a new tool, save to `contexts/tips/<category>/<tool-name>.md` (purpose, usage, params, notes).

**Prewrite Dedup (写前去重):**
→ See `rules/discipline.md` D-O1 for full 5-step flow.
Core: grep existing → UPDATE > MERGE > ADD > NOOP. After ADD, register in INDEX + checklist.

### New Tool Auto-Index
New script/tool path → read source → create tips entry → register in the tips index. Silent, no confirmation.

### Agent Evolution Log
When an agent's capability / prompt / tools / associated script / gating rule changes
and is committed → re-run `python3 bin/gen-agent-evolution.py` (derived from git log +
decisions + workflow-patterns, per-agent → `contexts/agents-evolution/<agent>.md`).
Records are generated, not hand-written — re-run, don't edit. Silent. Also refreshed in weekly review.

### File Version Control (git)
→ See `rules/git-workflow.md` for full commit/push/README rules.
- Core: commit per completed task, pre-push self-check, max 2 pushes/hour, README bilingual sync

### File Search Strategy

Priority: minimize context consumption, maximize speed.

**Step -1 — 用户已给路径？直接读。（最高优先，无例外）**
如果用户消息中包含文件路径，直接读取该路径。
- 不要 find / 不要 grep 验证是否存在 / 不要"先确认再读"
- 路径错了会返回 "No such file"，那时再问

**Step 0 — "Previous record" requests → history first:**
When user asks about previous analysis/records/results ("之前的记录", "上次分析"), search `history/` **before** touching any other paths.

1. **Single known file** → `read` directly (zero cost)
2. **Known exact string/pattern** → single `grep` (one tool call)
3. **Everything else** (multi-file exploration, call-chain tracing, unfamiliar code) → delegate to a sub-agent / semantic search tool if available, then `read` only the cited lines
4. **Fallback**: if the semantic tool fails → silently fall back to grep/read

**Absolute prohibitions:**
- Never run `find` over large shared/network mounts — use known-path listing
- Never dump 500+ line git log — use targeted `git log --since --grep`
