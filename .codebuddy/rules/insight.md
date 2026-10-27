---
alwaysApply: false
description: "Insight Generation Rules"
---

# Insight Generation Rules

## Trigger

- Monday startup check: if no insight this week → remind
- Manual: user says `insight`

## Auto Stats Collection

Before writing insight, run these to populate stats:

```bash
# Run from the repo root; paths.sh exports CBP_ROOT (the git root) and CBP_ISSUE_KEY_RE
. bin/lib/paths.sh

# Commits this week
git -C "$CBP_ROOT" log --since="last monday" --until="next monday" --oneline | wc -l

# TRs mentioned in this week's history
grep -ohP "${CBP_ISSUE_KEY_RE:-\b[A-Z][A-Z0-9]+-[0-9]{3,}\b}" history/$(date +%Y-%m)/*.md | sort -u

# HTML reports generated
find history/$(date +%Y-%m)/ -name "*.html" -newer history/$(date +%Y-%m)/$(date -d "last monday" +%Y-%m-%d).md 2>/dev/null | wc -l

# Active days (from history md files)
find history/$(date +%Y-%m)/ -name "????-??-??.md" -newer history/$(date +%Y-%m)/$(date -d "last monday" +%Y-%m-%d).md 2>/dev/null | wc -l

# Rule changes
git -C "$CBP_ROOT" log --since="last monday" --oneline -- .codebuddy/rules/ .codebuddy/rules/workflow.md | wc -l
```

Inject results into `## Week Stats` section automatically.

## Template Structure

```markdown
# Insight — YYYY-MM-DD (Week XX: MM-DD → MM-DD)

## Friction Points

1. **Title**
   - Evidence: what happened
   - Root cause: why
   - Fix: what was done (or suggestion)
   - Status: ✅ Resolved / ⚠️ Open / 💡 Suggestion

## Improvements Implemented This Week

| Item | Type | File |
|------|------|------|
| ... | New/Enhancement/Rule/Fix/Architecture | path |

## Week Stats

- Active days: N
- Git commits: N (auto)
- TRs filed/linked: N — list (auto)
- HTML reports: N (auto)
- Rule changes: N (auto)
- [Manual additions as needed]

## Patterns Observed

- **Pattern name**: explanation (1-2 sentences, evidence-based)

## Open Action Items

- [ ] item (carry forward unresolved from last insight)
- [ ] new items from this week

## Recommendation

1-2 sentences: what to focus on next week and why.
```

## Friction Point Collection Criteria

### Sources
- Session history (`history/YYYY-MM/*.md`)
- Current week's conversations (retrospective scan)
- Workflow execution self-check (see below)

### What counts as friction

1. **Flow execution failure** — 固定流程（daily-flow, daily-summary, insight等）未完整执行、遗漏步骤、需要用户提醒才补齐
2. **Trigger miss** — 约定好的 md 规则未及时触发（如：周一没提醒 insight、完成任务没写 history、启动没问总结）
3. **Blocking issue** — 阻碍了预期目标的事件（工具报错、环境问题、权限等）
4. **Time sink** — 花了 >15 分钟解决的意外问题（非用户主动探索性任务）
5. **Workaround needed** — 工具/流程缺陷导致需要绕路解决
6. **Repeat occurrence** — 同类问题重复出现（上次已 fix 但又发生）
7. **Interaction inefficiency** — 从 chat 记录中发现的交互优化点：
   - 用户多次追问才得到完整答案（说明首次输出不够）
   - 用户反复用相同模式提问（可抽象为触发词/快捷指令）
   - 多轮对话才收敛到正确方向（可优化为一步到位的 workflow）
   - 用户手动指定的参数/路径可以自动推断
   - 输出格式需要用户多次要求调整（说明 preferences 未覆盖）

### Exclusions
- 用户主动的探索性分析/学习任务
- 正常复杂度的技术调查（如 log 分析本身）
- 用户中途改变需求导致的返工

### Self-check questions (each insight generation)
- 本周 daily-flow 是否每次都完整执行？哪些步骤被跳过？
- 完成任务后是否每次都写了 history？
- 触发词响应是否正确读取了对应 rules？
- 有没有"用户纠正我"的场景？（每次被纠正 = 1 个 friction）

## Friction Point Lifecycle

- Each friction point from previous insight with status ⚠️ must be checked in next insight
- If resolved → note in "Improvements" table
- If still open after 2 weeks → escalate to "Open Action Items" with priority tag

### Accepted Trade-off Revisit

When a friction is marked "⚠️ Accepted trade-off" (not fixed, consciously tolerated):
- Must include `revisit_date: YYYY-MM-DD` (default: 4 weeks from now)
- Format in md: `- **Status**: ⚠️ Accepted trade-off (revisit: YYYY-MM-DD)`
- On revisit date (checked during insight generation): re-evaluate if still reasonable
  - Still valid → extend revisit by 4 weeks
  - No longer valid → convert to actionable fix
  - Friction disappeared → remove
- Prevents "accepted" from becoming "forgotten"

## Save Path

`history/YYYY-MM/insight-YYYY-MM-DD.md`

## Post-Insight Follow-up (生成后立即执行)

### Step 1: 💡 Suggestion → Action
- 将所有 status 为 💡 的 friction point 转化为具体可执行 action
- 如需创建文件（tips/rules），当场创建或加入 pending queue

### Step 2: ⚠️ Open → memory.md
- 将 ⚠️ Open 项写入 `contexts/memory.md` 的"本周焦点"区域
- 确保下次 session 启动时可见

### Step 3: 邮件通知
- 发送 insight 摘要邮件到 `$CBP_USER_EMAIL`
- Subject: `[Insight] W{week} Friction {count} | Action {count}`
- Body: friction 列表（标题+状态）+ open action items + recommendation
- 使用 s-nail，同 daily-summary 邮件规则

### Step 4: Pure Lab docs 部署
- 生成 insight HTML 版本到 `docs/reports/insight/insight-YYYY-MM-DD.html`
- 更新 `docs/index.html` 卡片
- git commit + push（遵守 push rate limit）
- 注：积累 4 期后额外生成趋势对比图

---
> **Local overlay** — paths like `bin/…` are relative to the repo root; `$CBP_*` names resolve from `config/paths.env` / `config/local.env` at the repo root. If `contexts/local/rules/insight.md` exists, read it as well: it adds or overrides install-specific steps (it wins on conflict). Keep this file generic; put personal/domain details there.
