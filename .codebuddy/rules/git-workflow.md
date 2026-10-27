---
alwaysApply: false
description: "Git Workflow Rules"
---

# Git Workflow Rules

## Commit

After modifying files in the repo, run `git commit`.
- Commit message: short description of changes
- Scope: contexts/, bin/, agents/, config/, templates/, decisions/
- Don't commit every small change — once per completed task

## README Update

When adding features/tools/templates/triggers, must update `README.md`:
- Structure diagram + feature list + Changelog
- Before `git push`, confirm if commit requires README update. Never push then patch.
- Changelog format: current ISO week entries visible, previous weeks in `<details>`
- Bilingual sync: EN section and ZH section updated simultaneously

### Changelog Folding Rule

- **Show expanded**: latest 2 weeks only (current + previous)
- **Fold into `<details>`**: all older weeks (one `<details>` per week, summary = "Week N (date)")
- **Ultra-old (4+ weeks old)**: merge into single summary block (one-liner per week)
- **When**: every time a new week's changelog is added, fold the 3rd-oldest week
- **ZH section**: no detailed changelog — one line pointer to EN version

## Push Flow

Three separate stages — don't mix them:

| Stage | Owner | What |
|---|---|---|
| 1. Flow steps | main agent | README (structure + features + changelog, EN/ZH), docs/index card if a report. These are things to *do*, not review findings. |
| 2. Code review | `reviewer` agent via `run-agent.sh` | **Required when the change set touches `bin/`, `rules/`, `agents/`, `templates/`, `settings/`, `tests/`.** Reviewer reads the diff, runs the relevant tests, looks for logic holes / regressions; returns PASS / FIX (list). FIX → fix + re-review. Content-only changes skip this stage. |
| 3. Push gate | `review-artifact.py --type push` + reviewer routing | Confirms stages 1–2 are done + rate limit; decides push / batch / defer / block. Does **not** judge code correctness. |

## Pre-push Self-check (no exceptions)

Before push, must print:
```
✅/❌ README: [needs update? reason]
✅/❌ Code review: [PASS / skipped (content-only) / FIX pending]
✅/❌ docs/index: [needs new card?]
✅/❌ Bilingual sync: [involved?]
✅/❌ Rate limit: [N/2 pushes this hour]
```
If any ❌ incomplete, do not push. Fix first.

## Push Quality Gate (reviewer-driven, user-set 2026-09-30)

Not every change should push. The gate: **script measures, reviewer decides**.

### Flow

```
before push → review-artifact.py --type push (measuring tool: readings + suggestion)
            → reviewer agent decides routing (semantic judgment on top of readings)
            → main agent executes: push / batch / defer / block
```

Run: `python3 $CBP_ROOT/bin/review-artifact.py '<files or ->' --type push --subject '<msg>' --json`

### Routing (what pushes, what waits)

| routing | trigger | action |
|---------|---------|--------|
| **PUSH-NOW** | safety/correctness fix (security, token, revert, corrupt, leak) | push immediately, jump the queue |
| **PUSH** | new mechanism (touches bin/rules/agents/templates/settings), a complete template report, or ≥3 files | push once hard gates pass |
| **BATCH** | 1-2 files, content-only, no behaviour change (single tip, changelog line) | accumulate locally; push with the next PUSH-worthy change |
| **DEFER-TIME** | otherwise-pushable but rate window full (2/hour) | → **time queue**; auto-retry next window |
| **NEEDS-HUMAN** | change set contains a **creative** HTML (not a registered template) | human must say "satisfied"; only a baseline check runs |
| **BLOCK** | hard gate fail (README stale / index card missing) | → **quality queue**; fix then re-review |

### Two "next cycle" queues (never mixed)

- **time queue** (`settings/push-deferred-time.json`) — change already meets
  quality, only the clock is blocking. "Next cycle" = **next time window**.
  Auto-retried at each `启动` (startup-check `push_queue.ready_to_push`).
- **quality queue** (`settings/push-blocked-quality.json`) — change failed a
  gate or is still batching. "Next cycle" = **when quality is met**. Never
  auto-pushed; must re-pass the gate.

Manage with `bin/push-queue.py` (add/list/ready/pop/clear).

### Template vs creative HTML

- **template** (daily/weekly/monthly/insight/health — registered in
  `style-registry.json`): reviewer may green-light the first PUBLISH-OK version.
- **creative** (slides, one-off visualisations — not under any registered
  publish_dir): iterate until the human is satisfied; reviewer then runs only a
  baseline check (links/bilingual/structure) and returns NEEDS-HUMAN, never
  auto-publish.

## Rate Limit

- Max 2 pushes per hour
- Tracking: `settings/push-log.json` (optional; JSON list of push epochs, read by `push-queue.py` / `review-artifact.py` when present). If you keep it, write it from your pre-push hook only — never by hand (a manual append double-counts the push)
- When exceeded: keep commits local, prompt user
- Override: user says "continue" / "push" / "force" / "urgent"

## Post-Push Pipeline Feedback

After every `git push`, check the CI pipeline status (if the remote has CI) and report result to user:
- Success: one-line confirmation (commit SHA + "pipeline passed")
- Failure: report which job failed + link

Method: the forge's CLI/API (e.g. `gh run list -L1`, or GitLab `/pipelines?per_page=1`).
If no token available, inform user to check manually and provide the pipelines URL
(set `CBP_CI_URL` in `config/local.env`).

---
> **Local overlay** — paths like `bin/…` are relative to the repo root; `$CBP_*` names resolve from `config/paths.env` / `config/local.env` at the repo root. If `contexts/local/rules/git-workflow.md` exists, read it as well: it adds or overrides install-specific steps (it wins on conflict). Keep this file generic; put personal/domain details there.
