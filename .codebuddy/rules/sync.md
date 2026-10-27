---
alwaysApply: false
description: "Pure Lab Sync (docs/ deployment)"
---

# Pure Lab Sync (docs/ deployment)

## Flow

After generating any HTML report (daily-report, review, dashboard, blog):

1. Copy HTML to `docs/`
2. Add/update card in `docs/index.html` under the correct **section grid** (Daily/Weekly/etc.) — insert at top in descending date order. This is separate from What's New.
3. **Update What's New section**: All report-generating scripts must call `bin/update-whats-new.py` at the end — no manual action needed. For manually deployed reports (hand-written HTML), Pure calls `python3 bin/update-whats-new.py --date MM-DD --tag Tag --title-zh "..." --title-en "..." --url "relative/path.html"`. Keep latest 3, descending.
4. **Pre-publish index check (mandatory gate, no exceptions):**
   Verify `docs/index.html` compliance before any commit. Fail = fix first, never push broken state.
   ```
   a. Card inserted?     → grep new report URL in index.html
   b. Display limits?    → count visible post-card (no hidden-card) per section:
                           blog ≤ 3, weekly ≤ 6, daily ≤ 6, tech ≤ 4
   c. No corrupted HTML? → grep 'hidden-card"="' index.html (must be 0)
   d. 🔴 What's New updated? → **separate region from the section grids (step a)**;
                           updating a section card does NOT update What's New.
                           Run `bin/update-whats-new.py` and verify the new URL
                           is inside the whats-new block. (Missed 2026-10-16:
                           section cards added, What's New forgotten — don't repeat.)
   e. Featured updated?  → if blog/monthly, verify hero featured bar
   ```
   If any check fails → fix before proceeding to step 5.
4.5. **Reviewer quality gate (mandatory, no exceptions):** run the `reviewer`
   subagent on the produced HTML (`review-artifact.py --type html --index
   docs/index.html`). Only a `PUBLISH-OK` verdict may proceed. `BLOCK` → fix (or
   send back to html-generator) and re-review; `NEEDS-HUMAN` → ask the user.
   This gate covers link/bilingual/structure/compliance/size + index-sync scoring
   (≥90 to publish), so it subsumes the manual index checks above for report files.
5. Start local preview (`python3 -m http.server 8080` in docs/) and inform user of URL
6. Wait for user confirmation before commit + push. Do not auto-push.
7. After confirmation, commit **from the repo root** (`$CBP_ROOT`; never from the cbp-cli state dir):
   ```bash
   cd $CBP_ROOT && git add docs/ && git commit && git push   # triggers Pages update
   ```

No user reminder needed — generate = deploy.

## Featured Auto-Update

When deploying a Blog or Monthly Review, `update-whats-new.py` automatically updates the hero featured-inline bar. No manual action needed.

- Triggered automatically when `--tag Blog` or `--tag Review`
- Can also be forced with `--featured` flag for any tag
- Updates: href, title (bilingual), date
- Template comment in index.html marks the editable section

## Editing Rule

When modifying docs/, edit locally first, user confirms satisfaction, then commit + push once. Don't push frequently.

## Card Style Rule (v2.0+, no exceptions)

All new post-cards must use `card-visual` + `card-body` structure:

```html
<a href="URL" class="post-card" data-type="TYPE" data-month="YYYY-MM">
    <div class="card-visual" data-type="TYPE">
        <span class="tag tag-TYPE">TAG</span>
        SVG_HERE
    </div>
    <div class="card-body">
        <h3>TITLE</h3>
        <p>DESC</p>
        <div class="meta"><span><span class="meta-dot" style="background:COLOR"></span>DATE</span><span>EXTRA</span></div>
    </div>
</a>
```

Type → animation rule:
- `blog`, `weekly`, `biweekly`: SVG with animation classes (`anim-spin`, `anim-dash`, `anim-float`, `anim-pulse`)
- `daily`, `report`, `tech`: SVG static (no animation classes)
- `learning`: keep old style (no card-visual)

SVG generation: use `bin/generate-card-svg.py --type TYPE --seed DATE` to auto-generate unique SVG.

Section display limits:
- `blog`: show latest 3 only, rest folded with "Show more reviews" button
- `weekly`: show latest 6, rest folded with "Show more reviews" button
- `biweekly`: included in weekly section grid, same 6-card limit applies
- `daily`: show latest 6, rest folded with "Show more dailies" button
- `tech`: show latest 4, rest folded with "Show more notes" button
- `report`: no limit
- `learning`: keep as-is

**Card insertion checklist (mandatory, every time):**
1. Insert new card at top of section grid (no `hidden-card` class)
2. Count total cards in that section WITHOUT `hidden-card` class
3. If count > section limit → add `hidden-card` to cards beyond the limit (from bottom up)
4. Never skip step 2-3, even when inserting a single card

Colors by type:
- daily: `#D97757` + `#B8860B`
- weekly: `#2ed8b6` + `#0d5c4d`
- biweekly: `#00bcd4` + `#006064`
- blog: `#673ab7` + `#9b59b6`
- report: `#4B7BC4`
- tech: `#ff5370`

## Nav Consistency (no exceptions)

- All HTML reports use `<link rel="stylesheet" href="../../cbp-base.css">` (relative to `docs/reports/<category>/`)
- All HTML reports must include `--kb-*` CSS variables in `:root` mapped from their own theme variables
- All HTML reports use the same `<nav class="cbp-nav">` block with: brand link `../../index.html`, lang buttons (中文/EN), theme toggle, back link
- Nav must NOT define its own `.cbp-nav` or `.nav-controls` CSS. All nav styling comes from `cbp-base.css`.
- Reports must include nav fallback CSS inline (for email attachment use)
- Before deploying, verify: `grep "../../cbp-base.css" <file>` — if missing, fix before commit

## Evolution Sidebar

- Located in `index.html` inside `.page-layout` wrapper, left of `.container`
- Auto-carousel: 5 versions (v0.1→v2.0), 4s interval, JS at bottom of index
- Includes "What Pure Lab Does" vertical list at bottom
- Sticky positioned, hidden on mobile (<900px)
- Keep until explicitly decided to remove

---
> **Local overlay** — paths like `bin/…` are relative to the repo root; `$CBP_*` names resolve from `config/paths.env` / `config/local.env` at the repo root. If `contexts/local/rules/sync.md` exists, read it as well: it adds or overrides install-specific steps (it wins on conflict). Keep this file generic; put personal/domain details there.
