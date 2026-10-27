---
alwaysApply: false
description: "Session File Archive"
---

# Session File Archive

Merged into **`rules/periodic-review.md` → Weekly Review → Additional task — Session archive**.

Session `.jsonl`/`.json` files with mtime >15 days are archived into
`sessions/archive/sessions-YYYY-MM.tar.gz` during the weekly review
(inform user first, keep last-15-day files). See periodic-review for the command.

---
> **Local overlay** — paths like `bin/…` are relative to the repo root; `$CBP_*` names resolve from `config/paths.env` / `config/local.env` at the repo root. If `contexts/local/rules/session-archive.md` exists, read it as well: it adds or overrides install-specific steps (it wins on conflict). Keep this file generic; put personal/domain details there.
