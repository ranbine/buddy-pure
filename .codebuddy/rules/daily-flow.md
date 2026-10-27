---
alwaysApply: false
description: "Daily Flow"
---

# Daily Flow

## Chinese Version (trigger: `启动`)

When user says `启动`, execute these steps:

### 0. Run Startup Script (first, before anything else)
```bash
python3 bin/startup-check.py
```
All subsequent steps read from this JSON output. No manual checks needed.

### 1. Greeting (lively + nickname)
- Random nickname from `preferences.md` (Identity → Nicknames)
- Print current time (from `calendar.weekday_zh` + `today`)
- Calculate time since last session ended
- Calculate last session duration

### 2. Automation Status
- Read `pending.files` — filter for entries produced by your watchers/cron jobs
- Has changes: print summary (count, latest item)
- No changes: "风平浪静 ✓"

### 3. Daily Summary Check
- Read `summary_zh` directly. If `status == "INCOMPLETE"`, ask whether to execute.
- **Red line:** If INCOMPLETE, must report it. No silent pass.

### 4. Pending Queue / Reminders
- Read `pending` — report non-scope pending items (if any)
- Read `archive` — if `stale_count > 0`, mention archive suggestion
- Read `push_queue` — if `ready_to_push` non-empty, offer to push the ready
  time-queue changes (rate window freed); if `quality_count > 0`, remind that
  N change(s) are blocked on quality (need fix + re-review). Empty → say nothing.
- Read `calendar.reminders` — output corresponding reminders:
  - `weekly_review` → "本周回顾待执行"
  - `biweekly_review` → "双周回顾待执行"
  - `monthly_review` → "月度回顾待执行"
  - `insight_reminder` → "本周尚无 insight，建议执行"

### 4.5 Knowledge Base Health Check (Monday only)
- If today is Monday: run the **Checkup** (operational health) by delegating to
  the `health-checker` subagent (Function 1 → `cbp-doctor.py`). Weekly scan of
  backlog/expiry (pending, sessions, dream, decision revisit, capacity).
- All pass → `🏥 知识库体检 ✓`（一行，不展开）
- Has warnings → `⚠️ 体检 N 个 warning`（列出）
- Has errors → `🚨 体检 N 个 error`（列出 + 建议修复）
- (Structural validation runs event-driven after edits, per `rules/discipline.md`,
  not here.)

### 4.6 Memory Dream Check
- Check `.dream-last` mtime (create if not exists)
- If >= 7 days old AND history/ has >= 5 new days since then:
  - Output: `🧹 记忆整固待执行（上次：YYYY-MM-DD，积压 N 天日记），执行？`
  - Wait for user confirmation before running
  - See `rules/memory-dream.md` for full 4-phase process

### 5. Learning Path Reminder
- Read `contexts/learning-path.md`
- Count completed (☑) vs total items in current phase
- If unread items: print progress + recommend next item + file path
- If current phase all done: congratulate + remind action item
- If all phases done: skip silently

**Overdue escalation (no exceptions):**
- Calculate overdue = today - phase target date
- If overdue > 14 days: output in **red** (🚨) + cannot be dismissed without user explicitly saying "跳过" or "skip"
  - Format: `🚨 学习超期 {N} 天（Phase {X}）— 建议今天投入 1h。跳过请说"skip"`
  - This line prints BEFORE the normal progress line, not after
- If overdue 7-14 days: output in amber (⚠️), normal reminder
- If overdue < 7 days: normal reminder

### 6. Welcome Message Refresh (silent, end of flow)
- Run `python3 bin/gen-welcome.py` at the end of the startup flow.
- It regenerates the pure agent `welcomeMessage` from current capabilities
  (sub-agents + workflow triggers) and writes it back into `agents/pure.json`
  **only if capabilities changed** (fingerprint compare vs `data/welcome-snapshot.json`).
- Purpose: next time the agent is opened, the CLI shows an up-to-date "what I can
  do now" greeting. New/removed sub-agent or trigger → welcome auto-updates.
- Silent: only mention it if it actually updated (one line, e.g. "🔄 welcome 已更新").
  Unchanged → say nothing.

---

### Output Examples

Incomplete summary + pending + Monday reminders:
```
👋 早上好 Captain！现在是 2026-07-06（周一）。
距离上次对话已过去 14 小时，上次 session 持续了 52 分钟。

📋 Scope：3 个 scope diff 待处理（v107, Li Molback）
⏳ 2026-07-04（2 session）不完整：缺 邮件，是否执行？
📦 1 个 session 文件超 15 天，建议归档
🔔 本周回顾待执行 | 本周尚无 insight

📚 学习进度：Phase 2 — 1/5 完成
   下一篇：claude-code/41-parallel-tasks.md（Parallel tasks）
```

All clear (Friday, no reminders):
```
👋 Hey 老板，现在是 2026-07-03（周五）。
距离上次对话已过去 16 小时，上次 session 持续了 7.7 小时。

📋 Scope：风平浪静 ✓
⏳ 无需补总结 ✓

📚 学习进度：Phase 2 — 0/5 完成
   下一篇：claude-code/27-skills-in-practice.md（Skills 实战）
```

Do not treat `启动` as a regular request.

---

## Auth Token Check (optional)

If `CBP_AUTH_RECORD` is set in `config/local.env` (file whose mtime = last login):
- Older than `CBP_AUTH_WARN_DAYS` (default 77): `🔑 token 即将过期（还剩 X 天），请重新登录`
- Older than `CBP_AUTH_EXPIRE_DAYS` (default 84): `⚠️ token 已过期，依赖它的工具不可用`

---

## English Version (trigger: `daily`)

Same 5 steps. Use `summary_en`, `pending.summary_en`, `archive.summary_en` from script. All output in English.

### Output Examples

Monday with reminders:
```
👋 Morning Boss! It's 2026-07-06 (Monday).
Last session ended 14h ago, lasted 52 min.

📋 Scope: 3 scope diffs pending (v107, Li Molback)
⏳ 2026-07-04 (2 sessions) incomplete: missing email. Run?
📦 1 session file older than 15 days, suggest archive
🔔 Weekly review due | No insight this week

📚 Learning: Phase 2 — 1/5 done
   Next: claude-code/41-parallel-tasks.md (Parallel Tasks)
```

All clear:
```
👋 Hey Captain, it's 2026-07-03 (Friday).
Last session ended 16h ago, lasted 7.7h.

📋 Scope: All quiet ✓
⏳ Summary complete ✓

📚 Learning: Phase 2 — 0/5 done
   Next: claude-code/27-skills-in-practice.md (Skills in Practice)
```

Do not treat `daily` as a regular greeting — it is the daily flow trigger.

---
> **Local overlay** — paths like `bin/…` are relative to the repo root; `$CBP_*` names resolve from `config/paths.env` / `config/local.env` at the repo root. If `contexts/local/rules/daily-flow.md` exists, read it as well: it adds or overrides install-specific steps (it wins on conflict). Keep this file generic; put personal/domain details there.
