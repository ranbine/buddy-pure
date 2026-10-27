---
name: pure
description: Personal workflow orchestrator — daily flow, report generation, periodic reviews, session closeout, and the action gate. Use when the user says 启动/daily, 生成报告/generate report, insight, 回顾/review, 体检/checkup, 校验/validate, orchestrate, or asks what the workflow status is. Also load when a session opens with a startup digest and the user acts on it.
allowed-tools: Read, Write, Edit, Grep, Glob, Bash, Task
---

# Pure — workflow orchestrator

Single entry point for this personal workflow framework. The rules live in
`.codebuddy/rules/` (auto-loaded only where `alwaysApply: true`); everything else is read on demand.

## Startup (highest priority)

A `SessionStart` hook injects a **startup digest** as additional context. When it is present:

1. Do not re-run the collection scripts — the digest already holds daily-summary, pending-queue,
   push-queue and auth-check results.
2. Work the digest top-down, one step at a time. Never ask two questions at once.
3. If the digest is missing or says `FAILED`, read `.codebuddy/rules/workflow.md` and execute its
   Startup Check manually.

## Routing

`.codebuddy/rules/workflow.md` holds the trigger-word table. Read it before routing a fuzzy
request; exact triggers map to:

| Trigger | Action |
|---|---|
| `启动` / `daily` | read `.codebuddy/rules/daily-flow.md` |
| `生成报告` / `generate report` | delegate to the **html-generator** subagent, then **reviewer** |
| `insight` | read `.codebuddy/rules/insight.md` |
| `回顾` / `review` | read `.codebuddy/rules/periodic-review.md` |
| `体检` / `校验` / `checkup` | delegate to the **health-checker** subagent |
| `orchestrate` | read `.codebuddy/rules/orchestration.md` |

The trigger word decides the output language: Chinese trigger → Chinese answer, English → English.

## Report pipeline

Never publish a report that the reviewer has not passed.

1. **html-generator** — picks a template from `templates/style-registry.json` by `type`
   (`daily`, `weekly`, `biweekly`, `monthly`, `insight`, `scope`, `health`, `showcase`), fills it,
   writes a self-contained bilingual HTML file under `docs/<publish_dir>/`.
2. **reviewer** — runs `bin/review-artifact.py <file> --type html` for the mechanical readings, then
   returns `PUBLISH-OK` / `BLOCK (N issues)` / `NEEDS-HUMAN`.
3. `BLOCK` goes back to html-generator (three rounds maximum); only a `PUBLISH-OK` file is shown.

## Methods

Deeper methodology lives in `contexts/tips/` — read the specific file when the situation calls for
it rather than loading all of them:

- `tips/analysis/investigation-principles.md`, `tips/analysis/systematic-debugging.md`
- `tips/thinking/progressive-authorization.md` (the gate's tier → observe → replay → enforce loop)
- `tips/thinking/de-ai-writing.md`, `tips/thinking/goal-clarity.md`
- `tips/infra/git.md`, `tips/infra/html-report.md`

`contexts/tips/INDEX.md` is the registry; `bin/check-drift.sh` flags unregistered files.

## Hard rules

Read `.codebuddy/rules/discipline.md` before any destructive action. The short version:

- Deleting anything outside the configured scratch/allow lists is refused, even on request.
- Tell the user the exact content before a delete and wait for confirmation.
- No verbal promises: a behaviour change goes into a rule file in the same turn, or it did not happen.

## Paths

Never hard-code a path. Every location is a key in `config/paths.env`, readable as `$CBP_*` in shell
and `P["CBP_*"]` in Python. Machine-specific values belong in `config/local.env` (gitignored).
