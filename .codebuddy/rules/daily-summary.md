---
alwaysApply: false
description: "Daily Summary Rules"
---

# Daily Summary Rules

## Language Rule

- Triggered by `查看报告` → Chinese output
- Triggered by `check-summary` → English output
- Triggered by startup check → follow startup flow language

## Trigger Condition

On each conversation start, check if summary is needed for the last active Pure day.

**Detection method:**
1. Check mtime of recent session files in `$CBP_CLI_HOME/sessions/cli/`
2. If latest session date ≠ today → new day
3. Check if history file exists and is complete (`history/YYYY-MM/YYYY-MM-DD.md`)
4. If missing or stale → trigger summary

**Note:** "Last working day" = last active date from session files, not calendar yesterday. May span weekends/holidays.

**Mid-conversation trigger:** Not limited to trigger words and startup checks. Any explicit request to run daily summary (e.g. "regenerate summary", "check yesterday's summary") must first read this file then execute full flow.

**Completeness check:** Even if `.md` exists, verify:
1. Content covers all sessions of that day (compare session count vs topics)
2. If day involved log analysis, HTML report generated?
3. Email sent? (check for `📧` marker at end of history `.md`)
If any incomplete → continue execution.

## Content Filter (no exceptions)

Only include **technical/work-related** content in daily summary:

**Include:**
- Log analysis, test case results, root cause findings
- Workflow/tool improvements, rule changes, code commits
- Issue investigation, deployment activities
- Generated files (reports, configs, scripts)

**Exclude:**
- Personal conversations, learning discussions, casual chat
- Tool exploration/reading without actionable output
- Pure system internal optimization (tips restructure, workflow refactoring, etc.) — unless it produced a deployable artifact

**Principle:** Summary should read like a technical work log that you'd share with your team lead. If a topic wouldn't appear in a standup, don't include it.

**Skip marker (📭):** If a day has sessions but only non-technical content (interview prep, learning, casual chat), append a line to that day's history `.md`:
`- 📭 无技术内容，跳过每日报告（<reason>）`
`startup-check.py` detects 📭 → returns `NO_SUMMARY_NEEDED`, skips email/HTML checks. This prevents repeated "incomplete summary" nags on non-technical days.

## Execution Steps

1. Ask user: "Detected N sessions on YYYY-MM-DD. Run summary?"
2. After confirmation, run extraction script:
   ```bash
   python3 $CBP_ROOT/bin/daily-summary-extract.py YYYY-MM-DD
   ```
   This produces `$CBP_TMP/daily-summary-raw.json` (~20KB structured data vs 1MB+ raw session)
3. Read `$CBP_TMP/daily-summary-raw.json` — use this as sole source for summary generation
   - Do NOT read raw session .jsonl files directly (context waste)
   - The JSON contains: conversations (Q + A preview), tags, timestamps, stats
4. Generate summary from JSON and show preview
5. **If day involved log analysis** (check `tags_summary` for `log_analysis`): generate an HTML report by **delegating to the `html-generator` subagent** (see `rules/report-generation.md`):
   - Delegate with `type=daily` + the summary data (from `$CBP_TMP/daily-summary-raw.json`: log path, analysis process, key findings, root cause) + output language.
   - html-generator fills `daily-report.html` (short summary + collapsible detailed analysis), saves to `docs/reports/daily/daily-report-YYYY-MM-DD.html`, and returns the path + preview.
   - Do NOT hand-fill the template in the main context — that's the subagent's job (single dispatch point).
   - After the HTML is produced: execute sync per `rules/sync.md` (add card to Daily Summary section + month filter if new month).
6. After user confirmation:
   - Write to `history/YYYY-MM/YYYY-MM-DD.md`
   - Send email (subject format: `[Pure][Daily] YYYY-MM-DD — <topic summary>`):
     - `s-nail -s "[Pure][Daily] YYYY-MM-DD — <topic>" [-r "$CBP_MAIL_FROM"] -a <HTML report if any> "$CBP_USER_EMAIL"` (`-r` only if `CBP_MAIL_FROM` is set)
7. If user requests changes, adjust before sending

**Note:** Never send email before user confirmation. Always preview first, wait for "send" command.

**Email send verification (no exceptions):**
After sending:
1. Check s-nail exit code (0 = success)
2. Run `echo $?` to confirm
3. Success: output `✅ Email sent to $CBP_USER_EMAIL`
4. Failure: output `❌ Email send failed (exit code: X)`, offer retry
5. Record result in day's history `.md`, using the **dated marker format**
   (no exceptions — the date is mandatory even inside that day's own file):
   - Success: `- 📧 <YYYY-MM-DD> 日报邮件已发送 $CBP_USER_EMAIL ([Pure][Daily] <YYYY-MM-DD]), 附 <html filename>, 退出码0`
   - Failure: `- ❌ <YYYY-MM-DD> 日报邮件发送失败 (exit code: X)`
   - **Why dated**: a marker like bare `📧 日报邮件已发` is ambiguous — on 2026-10-09
     a 09-30 marker sitting in the 10-08 file was misread as "10-08 sent" when
     10-08 had never actually been emailed. Always state which report's email it is.
   - If the marker refers to a **different** day's email (backfill/catch-up),
     append `(非本日)` so it's never mistaken for the current file's status.

**Pre-send mandatory check (no exceptions):**
Before sending, verify:
1. Subject starts with `[Pure][Daily]` followed by date and topic summary
2. Body grouped by topic, not chronological
3. Using s-nail + `-a` attachment mode
4. Body ends with signature block

**Email subject format (all Pure emails, unified):**
- `[Pure][Daily] YYYY-MM-DD — <topic summary>`
- `[Pure][Monthly] YYYY-MM — <title>`
- `[Pure][Weekly] WXX — <title>`
- `[Pure][Nightly] <build> — N failures (L2: X, L3: Y)`
- `[Pure][Alert] <issue> — YYYY-MM-DD`

All subjects start with `[Pure]` for inbox rule filtering.

## Execution Style

- Start with one line only:
  - Chinese: "⏳ 正在生成昨日总结，请稍候..."
  - English: "⏳ Generating yesterday's summary, one moment..."
- No intermediate explanations or analysis printing
- Show final preview directly when done
- Keep conversation concise

---
> **Local overlay** — paths like `bin/…` are relative to the repo root; `$CBP_*` names resolve from `config/paths.env` / `config/local.env` at the repo root. If `contexts/local/rules/daily-summary.md` exists, read it as well: it adds or overrides install-specific steps (it wins on conflict). Keep this file generic; put personal/domain details there.
