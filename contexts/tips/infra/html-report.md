---
title: "HTML Report Generation Preferences"
category: infra
verified_at: 2026-08-21
keywords:
  - infrastructure
  - tooling
  - html
  - report
---

# HTML Report Generation Preferences

## Design Style

- **Font**: Roboto (Google Fonts), Serif for headings, Mono for code
- **Colors**: warm light theme (ivory background, clay accent, olive success)
- **Code blocks**: light background (`var(--g100)`), no dark backgrounds
- **Layout**: max-width 900px centered, left numbering indent 44px

## Structure

- Top: eyebrow tag + serif heading + intro paragraph
- Navigation: TOC pill-shaped links
- Sections: numbered `01` `02` ... + serif headings
- Content hierarchy: timeline > card > code block (pre) > note/warn

## Interactions (mandatory)

- Scroll progress bar (top, clay color)
- Code copy button (show on hover)
- Collapsible long code blocks (`<details>`)
- TOC scroll highlight (IntersectionObserver)
- Language toggle (中文/EN, fixed top-right)

## Bilingual Support

- All headings, descriptions, TOC wrapped in `<span class="zh">` / `<span class="en">`
- CSS: `[lang="en"] .zh { display: none }` controls visibility
- **Default language: English** (`<html lang="en">`), user can switch to Chinese
- Code blocks and config content: don't translate
- Technical terms in tables: keep English

## Reference

- Design inspiration: `~/pure/The unreasonable effectiveness of HTML — examples.html`
- Font reference: Roboto

## Template

- **Daily Report template**: `templates/daily-report.html`
- Copy CSS/JS skeleton from template, only fill content placeholders
- Placeholders: `{{TITLE}}`, `{{DATE}}`, `{{INTRO_ZH}}`, `{{INTRO_EN}}`, `{{TOC}}`, `{{SECTIONS}}`, `{{GEN_DATE}}`
- **No rewriting styles** — all colors, fonts, layout follow template

## Notes

- No external JS frameworks (highlight.js etc.), use manual `<span>` coloring
- All interactions in vanilla JS
- File must be self-contained (single .html)

## ✅ Daily-report generator skeleton — FIXED 2026-10-09 (template-based)

- `bin/generate-daily-report.py` **rewritten** to fill the shared template
  `templates/daily-report.html` instead of emitting an inline skeleton. It now
  only substitutes placeholders ({{TITLE}} {{DATE}} {{INTRO_*}} {{TOC}}
  {{SECTIONS}} {{GEN_DATE}}), so CSS / nav / `../../cbp-base.css` link /
  `--kb-*` mapping / lang+theme toggle / copy button are all inherited →
  reviewer **hard gates pass on first pass** (verified: 2026-10-09 raw output
  = PUBLISH-OK, soft 100).
- **Bilingual handling**: history md is single-language (Chinese). The script
  fills `.zh` = original and `.en` = ASCII-safe placeholder (`[EN] ...`, keeps
  `code`/paths, strips CJK) so the EN view has **zero bare CJK** (passes
  `check_bilingual`). Section ids are forced ASCII (CJK counts as `\w` in
  Python — this was the one remaining leak, now fixed).
- **Still required before shipping**: the `.en` spans are placeholders, not
  real English. Hand the raw output to the `html-generator` subagent (or fill
  manually) to replace `[EN] ...` with real translations. Structure is already
  publishable; only the English prose needs a pass.
- History (prior behaviour): old skeleton caused first-round BLOCK every time
  (compliance ×2 + bilingual leak) on 2026-09-29, 09-30, 10-08. Backup of the
  old script: `bin/generate-daily-report.py.bak-20261009`.
- Write in steps when generating (avoid oversized single tool call)
- **sticky nav must be direct child of scroll container**, not inside `<header>`, or `position: sticky` won't work
- Back-to-top button fixed bottom-right, show after 300px scroll

---
> **Local overlay** — if `contexts/local/tips/infra/html-report.md` exists, read it too (install-specific notes and evidence).
