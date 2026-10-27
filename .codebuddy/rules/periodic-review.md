---
alwaysApply: false
description: "Periodic Review Rules"
---

# Periodic Review Rules

## Cycles & Output

| Cycle | Trigger | Content | Format | Save Path |
|-------|---------|---------|--------|-----------|
| Weekly | Monday startup check | Growth points, new capabilities, solved problem patterns | `.md` + short HTML | `history/YYYY-MM/weekly-review-WXX.md` + `.html` |
| Bi-weekly | Even-week Monday | Compare past 2 weeks: capability evolution, reuse rate, efficiency | HTML report | `history/YYYY-MM/biweekly-review-WXX.html` |
| Monthly | 1st of month | Aggregate month, merge weekly reviews, deep capability analysis | Full blog HTML (web-view) | `history/YYYY-MM/monthly-review-YYYY-MM.html` |

## Trigger Methods

### Auto Reminder (startup check)
- Monday startup: check if weekly review needed → remind user
- Even-week Monday: additionally remind bi-weekly
- 1st of month: remind monthly review
- User can execute or skip

### Manual Triggers
| Trigger | Action | Language |
|---------|--------|----------|
| `回顾` / `review` | Execute current cycle review (auto-detect week/biweek/month) | Follow trigger |
| `周回顾` / `weekly review` | Force weekly | Follow trigger |
| `月回顾` / `monthly review` | Force monthly | Follow trigger |

## Content Specifications

> **HTML generation**: delegate the actual HTML rendering to the `html-generator`
> subagent (see `rules/report-generation.md`), passing `type=weekly|biweekly|monthly`
> + the review data + language. The template/section details below are the *content
> spec* to hand the subagent — don't hand-fill templates in the main context.

### Weekly Review
- Data source: all `history/YYYY-MM/YYYY-MM-DD.md` from current week
- **Section ordering rule**: Sections are ordered by time-spent proportion of the week. The activity that consumed the most time comes first (e.g., if log analysis dominated → Analysis section leads; if tool development dominated → Tooling leads). Title/subtitle should reflect the primary activity.
- **Pure System Changelog (fixed section, always present)**:
  - Baseline: previous week's review timestamp → current review timestamp
  - Content:
    1. **New components**: file path + LOC + purpose (table)
    2. **Modified components**: file + diff stat + rationale (table)
    3. **Evolution logic**: 2-3 driving forces behind this week's changes (bullet list)
    4. **New theories/principles**: theory + source evidence + impact (table)
  - Data source: `git log --since/--until` + `git diff --stat` + `git status` for uncommitted
  - Position: after Workflow section, before Decisions (second-to-last)
- **Template**: `templates/daily-report.html` — use `<header class="hero">` variant + stats grid (see commented blocks in template)
- Extract: new capabilities, problem patterns, tool/rule changes, key decisions
- Keep concise, 5-10 bullet points
- Save HTML to: `docs/reports/reviews/weekly-review-WXX.html`
- **After save**: Execute sync per `rules/sync.md`.
- **Additional task — Session archive**: Check `sessions/cli/` for `.jsonl`/`.json` files with mtime >15 days. Inform user first ("About to archive X files (YYYY-MM month)"), wait for confirmation, then archive into `sessions/archive/sessions-YYYY-MM.tar.gz` (merge if same-month archive exists). Keep last-15-day files untouched.
  ```bash
  mkdir -p sessions/archive
  find sessions/cli -maxdepth 1 \( -name "*.jsonl" -o -name "*.json" \) -mtime +15 | \
    tar -czf sessions/archive/sessions-YYYY-MM.tar.gz -T - --remove-files
  ```
- **Auto-pattern review**: Check `knowledge/auto_*.json` — list count. If >3 new since last review, remind user to review them (confirm/refine/delete).

- **Sub-agent performance** — `python3 bin/agent-perf.py --days 7 --runs --turns --write-weekly` (turns = model vs tool split + brake hits) → `$CBP_DATA/agent-perf/YYYY-Www.json`. In the review: per-agent median wall / turns / s-per-turn vs last week's file, list flagged runs (TIMEOUT / OVER_BUDGET / SLOW_TURN) with the likely cause (brief missing INPUTS/GIVEN/BUDGET, re-exploration, oversized context) and one concrete fix each (brief change, pre-compute step, split). Recurring cause twice → workflow pattern.
- **Gate audit** — script counts, reviewer judges, user applies. Kept separate from Memory Dream (permission changes must not share a diff with knowledge edits).
  1. `python3 bin/gate-audit.py --days 7` → `$CBP_DATA/gate/proposals/<date>.{json,md}` (never edits the policy).
  2. If proposals > 0: `run-agent.sh reviewer` with the `.md` — per proposal ACCEPT / REJECT + one-line reason (does the key ever touch shared systems? are the samples representative?). Also flag likely false positives in the L3/DENY section.
  3. Show the user: proposals + reviewer verdicts + L3/DENY false-positive candidates + L2 share / errors / latency. One line per item.
  4. User runs `cbp-gate apply <date> [P01 ...]` in their own terminal (agent is DENY on this). (`apply` writes `config/gate-policy.local.json`.)
  5. While mode = shadow: also give an enforce-readiness call (false-positive DENY = 0 and L3 hits all intended → suggest `cbp-gate mode enforce`).

### Bi-weekly Review
- Data source: last two weekly reviews
- **Template**: `templates/biweekly-review.html` — use cmp-table + trend-bars + evolution table (see placeholders in template)
- Compare: efficiency changes, old vs new capabilities, reuse patterns
- Save HTML to: `docs/reports/reviews/biweekly-review-WXX.html`
- **After save**: Execute sync per `rules/sync.md`.

### Monthly Review
- Data source: all weekly + bi-weekly + daily summaries + raw session records
- **Auto-generation (cron, every 2nd of month 03:00)**:
  - an LLM CLI generates the draft (bring your own script)
  - Saved to `history/YYYY-MM/monthly-review-YYYY-MM.html` + `docs/reports/reviews/`
  - Creates `pending/monthly-review-YYYY-MM.md` with `action: REVIEW`
- **Pure review (next startup)**:
  When pending monthly review found, Pure performs automated QA:
  1. **Link check**: verify all `href` paths exist in `docs/`
  2. **Data accuracy**: cross-check stats (active_days, TRs) against actual `history/*.md`
  3. **Architecture**: verify directory tree matches real `` structure
  4. **No fabrication**: grep generated content for file paths — confirm they exist
  5. **Insights quality**: flag any generic statements without concrete examples
  6. **Language & expression**:
     - Chinese: natural, not machine-translated (no "进行了...的操作" stiff patterns)
     - English: concise, technical, no filler ("leverage", "utilize" → use simpler words)
     - Bilingual parity: zh and en convey same meaning, not literal translation
     - Match user's style: direct, no fluff, conclusions first
     - Technical terms keep English in both languages (e.g. "L3 分析" not "第三层分析")
  7. Output: "月报审查完成：N 个问题。[问题列表]。修正后发布？"
- **User action**: confirm → Pure fixes issues + sends email. Or user says "重新生成" → re-run with feedback.
- **Same mechanism applies to auto-generated weekly reviews.**
- **Insight Trend Report (auto-generated with monthly review):**
  - Generate `docs/reports/insight/insight-trend-WXX-WXX.html` covering the month's insights
  - Content: friction count stacked bar + category heatmap + timeline overview + observations
  - **Add card to `docs/index.html` Tech Notes section** (trend reports only, not single insights)
  - Link in monthly blog's "Further Reading" section
  - No separate trigger needed — monthly review = trend report
- **Style: narrative blog** (not technical checklist)
  - First-person Pure perspective, sharing growth story
  - Shareable with colleagues, fun but not frivolous
- **Writing principles:**
  - Narrative must have real technical substance (code blocks, log paths, commands, architecture trees)
  - Each phase: what happened → technical output → key decisions/insights
  - Avoid pure sentiment or anthropomorphic rhetoric stacking, tone is composed
  - Architecture explanation is important: include directory tree (`` structure) + Mermaid diagrams
  - Core Insights section: distill 3-5 reusable methodologies (not feelings)
- **Structure reference:**
  - Hero → TL;DR stats → Chronological by week (1-2 cards each, with code blocks) → Architecture diagram → Core Insights → Advice for Colleagues → Further Reading → History links
  - **Advice**: 3-5 reusable tips from this month's practice, targeting Pure users
  - **Further Reading**: related tool docs, internal resources, external articles
  - Reference template: `history/2026-06/blog-cbp-growth-story-webview.html`
- **Technical specs:**
  - **Template file**: `templates/monthly-review.html` — copy CSS/JS skeleton, only fill `{{CONTENT}}` etc.
  - Placeholders: `{{TITLE_ZH}}`, `{{TITLE_EN}}`, `{{SUBTITLE_ZH}}`, `{{SUBTITLE_EN}}`, `{{DATE_RANGE}}`, `{{READ_TIME}}`, `{{CONTENT}}`, `{{GEN_DATE}}`
  - **No rewriting styles** — all colors, fonts, layout follow template
  - Web-view style (Hero + Tailwind + Font Awesome + Mermaid)
  - Mermaid colors: Gradient Able palette (`#4099ff` / `#2ed8b6` / `#673ab7` / `#ff5370` / `#ffb64d`)
  - **Mermaid best practices:**
    - Use `classDef` for unified styles, nodes reference via `:::className`, no inline `style`
    - Short IDs (alpha only), display text separated from ID (`A([Display Text]):::class`)
    - Avoid special chars/emoji in subgraph labels
    - Ensure nodes and edges correct first, then add styling
    - Reduce crossings: avoid multiple lines merging into same intermediate node
    - Short edge labels (1-2 words)
    - Use `<pre class="mermaid">` tag (not `<div>`)
    - Complex diagrams: split into multiple sub-diagrams, not one crammed chart
  - Font Awesome CDN: `cdnjs.cloudflare.com` (`cdn.staticfile.org` unreachable)
  - Tailwind CSS CDN: same `cdnjs.cloudflare.com`
  - Bilingual toggle: `data-zh` / `data-en` attribute pattern
  - **Default language: English** (page loads with `switchLang('en')`, `<html lang="en">`, EN button active)
  - **Chinese in code blocks also needs bilingual**: use `<span data-zh="..." data-en="...">` inside code-blocks
  - Dark/light mode toggle
  - body: no `transition: all` (causes scroll jank), only transition background/color

- **History navigation section**: at blog bottom, list all previous monthly/weekly blog links
- Save path: `history/YYYY-MM/monthly-review-YYYY-MM.html`

## Monthly Blog History Link Format

```html
<section id="history">
  <h2>📚 Previous Reviews</h2>
  <ul>
    <li><a href="monthly-review-2026-05.html">2026-05 Monthly Review</a></li>
    ...
  </ul>
</section>
```

- Auto-scan `history/` for all `monthly-review-*.html` and `biweekly-review-*.html`
- Sort by date descending

## Email

- Weekly: no email, file only
- Bi-weekly: optional email (ask user)
- Monthly: after generation:
  1. Copy HTML to `docs/` and `git add + commit + push` (triggers static Pages deploy, if configured)
  2. Wait for deployment (pipeline pass)
  3. Ask user if send email
  4. Subject: `[Pure][Monthly] YYYY-MM — <title>`
  5. Body includes **Pages online link**, attachment includes HTML
  6. Pages URL: `$CBP_PAGES_URL/<filename>.html` (set in `config/local.env`)

---
> **Local overlay** — paths like `bin/…` are relative to the repo root; `$CBP_*` names resolve from `config/paths.env` / `config/local.env` at the repo root. If `contexts/local/rules/periodic-review.md` exists, read it as well: it adds or overrides install-specific steps (it wins on conflict). Keep this file generic; put personal/domain details there.
