# Decision: startup-check exempts periodic-report days from daily-report requirement

- **Date**: 2026-10-19
- **Status**: Adopted

## Decision

Added `check_alt_report()` to `bin/startup-check.py`. When a day's history records
a periodic HTML deliverable (monthly-review / weekly-review / biweekly-review /
insight `.html`), the daily-report requirement is treated as satisfied
(`html_needed=False`, `html_report` not added to `missing`).

## Context

2026-10-16's actual deliverable was `monthly-review-2026-09.html` (+ email sent),
not a daily log-analysis report. The old hardcoded `html_needed=True` flagged the
day INCOMPLETE on every `启动`, a false positive that would recur on every
monthly/weekly review day.

## Alternatives Considered

- **B2: add 📭 skip marker to the day's history** — fastest, but semantically wrong
  (the day had real technical output, not a skip), and needs manual tagging every
  periodic-report day. Rejected.
- **A: generate a daily report wrapping the monthly work** — content would duplicate
  the already-sent monthly report; low value. Rejected.

## Reason

Root-cause fix at the detection layer — future periodic-report days auto-exempt,
no manual tagging. Narrow marker match (specific review/insight filenames + `.html`)
avoids over-triggering on ordinary daily reports.

## Revisit Condition

If a future report type is introduced whose filename doesn't match the marker list,
extend the `markers` tuple. Revisit if false-negatives appear (a genuine daily-report
day wrongly exempted).
