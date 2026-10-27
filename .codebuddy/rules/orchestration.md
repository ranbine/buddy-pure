---
alwaysApply: false
description: "Orchestration — Delegation Chains & Graphs"
---

# Orchestration — Delegation Chains & Graphs

> Purpose: orchestrate multiple sub-agents (sequential `chain` / parallel `graph`).
>          Workflows are defined as tables in this file — no YAML, no extra dirs.
> Triggers: `orchestrate`, or whenever a
>           flow needs multiple agents to cooperate.

## Design principle (HOW vs WHAT)

- **Agent prompts define HOW**: how each sub-agent works (format, method, self-check) —
  lives in each agent's own prompt.
- **The tables in this file define WHAT**: what to do, in what order, how data flows.
- **The orchestrator (main agent) schedules AND consolidates**; how each stage is
  executed depends on what the session actually provides (see below).

## Execution contract (pick the first available path per stage)

1. **Native delegate tool** — if this session's tool list actually contains a
   delegate/subagent tool, use it (agent must be in pure.json
   `toolsSettings.subagent.availableAgents`). Listing `delegate` in agent.json does
   NOT guarantee the runtime exposes it — check the real tool list, don't assume.
2. **Process boundary** — otherwise `run-agent.sh <agent> "<task>"` (see
   `tips/tools/run-agent.md`, decision 2026-10-16). This is the sanctioned way to
   get the agent's own prompt + allowedTools sandbox + context isolation.
3. **Run the stage method directly** — only when 1/2 are unavailable (e.g. token/SSO
   expired): run the stage agent's underlying script in the main context
   (health-checker → `cbp-doctor.py`/`cbp-validate.py`) and say so explicitly.

- **Do NOT** start an *interactive* `cbp-cli chat --agent X` from a session.
  `run-agent.sh` (non-interactive, depth-guarded) is the only allowed process spawn.
- Ordering: independent stages may run together (≤4 at a time); `depends_on`
  stages run after their inputs.
- Fail-fast: if a stage errors, report and stop; no auto-retry.
- Treat each stage as isolated work: don't let one stage's assumptions leak into
  another; pass results explicitly (see Data flow).

## Delegation brief (every sub-agent call, user-set 2026-10-23)

Sub-agent time ≈ LLM turns × seconds per turn. Spawn costs ~1.5 s; a turn costs
7 s with a small context and 30+ s with a large one (2026-10-23 reviewer runs:
broad review 6 turns × 34 s = 205 s; scoped verification 6 turns × 7 s = 44 s).
So cut turns and context, not spawn count. Every task string uses these fields:

```
GOAL      one sentence: the deliverable and the verdict/format expected
INPUTS    exact files / line ranges / diff / commit — "read only these"
GIVEN     facts already established (test results, paths, prior findings) — authoritative, don't re-derive
DO        numbered steps, each a concrete command or check
DON'T     forbidden steps (re-exploring the repo, browsers/screenshots, cbp-cli, edits, writes outside the scratch prefix `CBP_TMP_PREFIX*`)
BUDGET    ≤ N tool calls, ~M min; stop and report what's left when reached
OUTPUT    contract (verdict/json/raw) + shape (table, numbered findings with severity)
```

Budgets by task type. `bin/agent-perf.py` flags `OVER_BUDGET` when a run's tool calls exceed the largest budget for that agent:

| Task type | Tool calls | `--timeout` |
|---|---|---|
| verify fixes / re-probe known cases | ≤ 6 | 240 s |
| code review of a scoped diff (reviewer) | ≤ 10 | 600 s |
| report from a complete brief (html-generator, edit) | ≤ 10 | 300 s |
| new page from a brief (html-generator) | ≤ 15 | 600 s |
| health check (health-checker) | ≤ 8 | 300 s |

Speed-ups, in order of payoff:
1. **Pre-compute in the main context**: run the tests / grep the relevant lines /
   trim the log first and put results under GIVEN — the agent judges, it doesn't collect.
2. **Iterate narrow**: first pass broad, follow-ups re-probe only the open items.
3. **Split independent work**: separate files/jobs → parallel agents, then merge.
4. Model choice (`--model`) only after `agent-perf.py` shows turn time is the bottleneck.

The BUDGET line is enforced: `run-agent.sh` reads `BUDGET: ≤ N tool calls` (or `--budget N`) and `bin/agent-trace.py` refuses tool call N+1 with "wrap up now", so an over-scoped agent returns partial results instead of timing out.

Measure: `python3 bin/agent-perf.py --runs --turns` (per run: wall, turns,
tools, s/turn, flags TIMEOUT / OVER_BUDGET / SLOW_TURN). Reviewed weekly.

## Data flow

- Pass data between stages explicitly: feed a stage's output into the next stage's
  instruction, or write artifacts to `$CBP_ROOT/tmp/orchestrate/<run>/` (only
  when something must hit disk).
- `input=previous` = use the previous step's output as context for this step's instruction.
- Preserve valuable final artifacts (reports → `$CBP_ROOT/docs/reports/`,
  records → history).

## Steps

1. Find the chain/graph by name in "Workflow definitions" below.
2. For each table row, execute the stage via the first available path in the
   Execution contract, with the row's instruction + `{task}` + upstream results.
   Independent rows can run together (≤4); `depends_on` rows run after their inputs.
3. Consolidate the last/terminal node's output for the user.
4. Preserve valuable artifacts (reports → docs/reports/, records → history).

---

## Workflow definitions

### chain: daily-report
Distill today's sessions → generate the daily HTML report.

| step | agent | input | output | instruction |
|------|-------|-------|--------|-------------|
| 1 | html-generator | — | daily.md | type=daily; data source: today's records in `$CBP_ROOT/history` |

> Reserved two-step chain (once a session-summarizer agent exists):
> `1 session-summarizer — summary.md (distill technical work)` →
> `2 html-generator previous daily.md (generate report)`

### graph: full-health
Run checkup + validate in parallel → consolidate into one health report.

| node | agent | depends_on | output | instruction |
|------|-------|-----------|--------|-------------|
| checkup | health-checker | — | checkup.md | Operational checkup (cbp-doctor F1): capacity/staleness/backlog |
| validate | health-checker | — | validate.md | Structural validation (validate-pure F2): refs/numbering/format |
| report | html-generator | checkup, validate | report.md | Read both results, consolidate into a health report HTML |

---

## Adding a workflow

Add a `### chain: <name>` or `### graph: <name>` section plus one table under
"Workflow definitions". Columns: chain uses `step/agent/input/output/instruction`;
graph uses `node/agent/depends_on/output/instruction`.

## Rules (red lines)

- The orchestrator consolidates but keeps stages isolated — don't blur one stage's
  work into another.
- **Never start an interactive `cbp-cli chat --agent`** from a session; process
  delegation goes through `run-agent.sh` only.
- ≤4 concurrent stages; fail-fast + report, no auto-retry.
- Preserve valuable artifacts to a permanent location (docs/reports/, history).

---
> **Local overlay** — paths like `bin/…` are relative to the repo root; `$CBP_*` names resolve from `config/paths.env` / `config/local.env` at the repo root. If `contexts/local/rules/orchestration.md` exists, read it as well: it adds or overrides install-specific steps (it wins on conflict). Keep this file generic; put personal/domain details there.
