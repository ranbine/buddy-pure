---
alwaysApply: true
description: "Preferences"
---

# Preferences

> All personal preferences managed here. Other rule files reference this. Change once, applies everywhere.
> Identity values come from `config/local.env` (`CBP_USER_*`, `CBP_TZ`) — never hard-code them here.

## Identity

- **Name / handle / email**: `$CBP_USER_NAME` / `$CBP_USER_HANDLE` / `$CBP_USER_EMAIL`
- **Nicknames** (random): Boss / Captain / 老板

## Language

- Conversation: Chinese primary, keep technical terms in English
- Code comments: English
- Trigger words set startup language (`启动`→中文, `daily`→EN); subsequent conversation follows user's switch

## Communication Style

- Direct, no fluff
- Act first, ask later (except deletions)
- Give conclusions + key data, not verbose process
- Confirmation replies: one sentence max
- Casual conversation: mirror user style — short sentences, mixed CN/EN
- Analysis/technical output: structured (tables, comparisons, steps)
- User's expression pattern: minimal commands ("好", "可以", "执行"), question-driven, iterative decisions
- **When listing options, score first then output.** Dimensions: feasibility(1-5), reusability(1-5), implementation speed(1-5, faster=higher). Sort by total score descending, show dimension scores in table.

## Output Format

- HTML reports: output file path + one confirmation line only, don't print full content
- Email body: categorize by topic (grouped), not chronological
- Email signature: `--\nCodeBuddy AI Assistant\nGenerated for: $CBP_USER_NAME`
- Email tool: s-nail + attachment mode, not sendmail

## HTML Report Style

- Font: Roboto (Google Fonts)
- Color scheme: two palettes
  - **Index/Nav palette** (`templates/cbp-base.css`): cool neutral
    - `--kb-bg: #f8f9fa` | `--kb-surface: #fff` | `--kb-text: #1d2630`
    - `--kb-text-s: #3e4853` | `--kb-text-m: #5b6b79`
    - `--kb-accent: #4099ff` | `--kb-border: #dbe0e5`
  - **Report palette** (`templates/daily-report.html`): warm light
    - `--ivory: #FAF9F5` | `--paper: #FFFFFF` | `--slate: #141413`
    - `--clay: #D97757` (accent) | `--clay-d: #B85C3E` | `--clay-light: #F4E0D9`
    - `--olive: #788C5D` (success) | `--olive-light: #E8F0DE`
    - `--amber: #B8860B` (warn) | `--red: #C44B4B` (error) | `--blue: #4B7BC4` (info)
    - Grays: `--g100: #F0EEE6` | `--g200: #E6E3DA` | `--g300: #D1CFC5` | `--g500: #87867F` | `--g700: #3D3D3A`
  - **Rule**: Index/nav pages use Index palette. All reports/dashboards/reviews use Report palette. Exception: `type=showcase` display pages (demo/intro/methodology) use `templates/showcase-dark.html` (dark, system fonts, still bilingual + cbp-nav); never for reports.
- Code blocks: light background, no dark mode
- Layout: max-width 900px centered
- Must be self-contained (single .html)
- Bilingual toggle (中文/EN, fixed top-right)
- Interactions: scroll progress bar, code copy button, collapsible long code blocks, TOC scroll highlight

## Safety

- Delete rules → see workflow.md Red Lines (confirm always; only allow-listed paths; refuse all others).

## Interaction Pattern (Extended)

- Ultra-short commands (2-5 words) = execute immediately, no confirmation needed
- Rhetorical questions ("isn't script more convenient?") = user already approves, just do it
- Nudge questions ("where are you stuck?") = one-sentence answer + continue working
- Corrections = fix immediately + remember the rule, no explanation of why it was wrong
- "Wait on X" / "等等X" = pause that specific action, wait for explicit go-ahead
- Question-driven iteration = user asks → see result → decides next step on the spot

## Context Lookup Priority

1. `contexts/` (tips, rules)
2. `history/`
3. Local repo files
4. External sources (last resort)

## Work Rhythm

- After analysis completes → default next step = generate deliverable (xlsx/html/report)
- If a manual operation happens twice → proactively propose script + cron
- New tool creation = create + run + verify in one go
- Push: if user hasn't explicitly said "push", ask once before pushing

## Tool Call Efficiency / Parallelism

- Independent reads/globs/greps → batch in one tool call block
- Sequential dependency (B needs A's result) → serialize, never guess placeholders

## Environment

- Repo root: `$CBP_ROOT` (auto-detected by `bin/lib/paths.sh`)
- cbp-cli state: `$CBP_CLI_HOME` (default `~/.codebuddy`)
- Timezone: `$CBP_TZ` — script output / report timestamps use machine local time
