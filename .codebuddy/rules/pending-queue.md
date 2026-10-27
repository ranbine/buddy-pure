---
alwaysApply: false
description: "Pending Task Queue"
---

# Pending Task Queue

Automation scripts (cron jobs) write reports to `pending/` when human attention is needed.

## Directory Structure

```
pending/
├── <timestamp>_<task-type>.md    # pending
└── done/
    └── <timestamp>_<task-type>.md  # processed
```

## Registered Automation Tasks

| Task | Trigger | Output File |
|------|---------|-------------|
| Monthly review draft | cron, 2nd of month | `monthly-review-YYYY-MM.md` |
| _(your automation)_ | _(trigger)_ | `YYYYMMDD_HHMM_<task-type>.md` |

## Processing Flow

1. On startup, scan `pending/` (exclude `done/`)
2. If files found, show summaries in chronological order
3. After user confirms processing, execute corresponding action (e.g. update local scope)
4. Move processed file to `done/`

**Note:** Pending report comes after daily summary, before insight reminder. If user is discussing another topic, don't interrupt — mention pending items after current topic concludes.

---
> **Local overlay** — paths like `bin/…` are relative to the repo root; `$CBP_*` names resolve from `config/paths.env` / `config/local.env` at the repo root. If `contexts/local/rules/pending-queue.md` exists, read it as well: it adds or overrides install-specific steps (it wins on conflict). Keep this file generic; put personal/domain details there.
