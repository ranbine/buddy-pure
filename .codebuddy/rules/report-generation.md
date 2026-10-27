---
alwaysApply: false
description: "Report Generation — Delegation Stub"
---

# Report Generation — Delegation Stub

Triggers: `生成报告` / `generate report`
Also fires when a workflow step needs an HTML report (daily-summary, periodic-review).

## Rule: delegate to the `html-generator` subagent

Full report logic (template dispatch via `$CBP_ROOT/templates/style-registry.json`, placeholder
filling, preview, confirm/iterate, optional publish) lives in the **`html-generator`
subagent** (`agents/html-generator.json` → `html-generator-prompt.md`).
Do NOT duplicate it here.

When the trigger fires, or a workflow step needs a report:

1. **Delegate** to the `html-generator` subagent, passing:
   - `type` if known (daily / weekly / biweekly / monthly / insight / scope) — from the
     workflow context, pass it explicitly so no prompt is needed.
   - the report **data** (summary content, stats, findings, date/week range).
   - output language.
2. If no `type` is given by the user, the subagent will list available template
   styles (with the default) and let the user pick.
3. The subagent fills the matched template, produces a preview (local URL), and
   returns the file path + preview URL + one-line summary.
4. **Quality gate (mandatory, no exceptions) — the gate belongs to the `reviewer`
   AGENT, not to the main context.** Before showing the result to the user,
   **delegate to the `reviewer` subagent via a real process** —
   `run-agent.sh reviewer "<task + file + index>"` (see `tips/tools/run-agent.md`).
   - The main context must NOT substitute a direct `review-artifact.py` run for
     this. Running the script yourself is the gate's *lower bound* (mechanical
     checks); the reviewer **agent** adds the *upper bound* — judgement the
     script can't make (sparse/duplicated content, prose/translation accuracy,
     over-claiming, "50KB but thin" smells). The 2026-10-16 monthly bug
     (content double-filled + JS leaked, script said PUBLISH-OK) is exactly why
     the agent must do the gating, not a bare script call.
   - Inside the agent: it runs `review-artifact.py --type html --index
     docs/index.html` as its mechanical floor, then reasons on top, and returns
     `PUBLISH-OK` / `BLOCK (N issues)` / `NEEDS-HUMAN`.
   - **PUBLISH-OK** → proceed to step 5 (relay to user).
   - **BLOCK** → send the issue list back to `html-generator` to fix, then
     re-review. Loop until PUBLISH-OK (cap ~3 rounds). Do not surface a BLOCKed
     report as if it were ready.
   - **NEEDS-HUMAN** → relay the specific unresolved point to the user and ask,
     don't auto-publish.
   - This is the inter-agent chain: main → html-generator → reviewer → main.
   - **Fallback only on agent failure:** if `run-agent.sh reviewer` fails
     (token/SSO expired, timeout), fall back to a direct `review-artifact.py`
     run AND say so explicitly to the user ("agent gate unavailable, ran script
     floor only") — never silently downgrade the gate to a script.

   **Template vs creative (user-set 2026-09-30):**
   - **Template reports** (daily/weekly/monthly/insight/health — registered
     in `style-registry.json`): the first `PUBLISH-OK` version is publishable.
     Don't make the user re-review routine reports.
   - **Creative HTML** (slides, demos, one-off visualisations — NOT a registered
     type): iterate until the user says "satisfied". Even then reviewer runs only
     a **baseline check** (links/bilingual/structure) and returns `NEEDS-HUMAN` —
     never auto-publish. Publish = user satisfaction + baseline pass.
5. Relay the result (with the reviewer verdict) to the user. On the user's
   confirmation, publish; never auto-push.

## When NOT to delegate (handle in main context)

- The user only wants the raw text summary, not an HTML report.
- Trivial one-off tweaks to an already-generated file (just edit in place).
- Small, well-specified changes to an existing HTML (fix a style bug, tune an
  animation, reword a section, swap a class) — edit directly; a sub-agent
  round-trip costs minutes per step for a change that takes one edit.

## Delegation budget (no exceptions)

When delegating to `html-generator` (or any sub-agent via `run-agent.sh`) — use the
task template and per-type budgets in `rules/orchestration.md` → "Delegation brief". In addition:

1. **Scope the task in the prompt**: state the exact deliverable and what NOT to
   do — always include "verification = `review-artifact.py` only, no browser
   rendering/screenshots" and "facts in the brief are authoritative, don't
   re-explore them".
2. **Size the timeout to the task**, not a blanket max:
   edit existing file → `--timeout 300`; new page from a brief → `--timeout 600`.
   Hitting the timeout = the task was mis-scoped → split it or do it in the
   main context; don't just raise the limit.
3. **Tell the user before waiting**: one line with the agent, task and timeout,
   so a long wait is never a silent black box.

Source: a delegated page task re-explored the repo despite a complete brief
(timeout); a later pass finished its edit quickly, then spent most of its time
on a self-initiated headless-browser check until the timeout.
Pattern `P-DELEGATE-SCOPE`.

## Workflow integration

- **daily-summary flow**: when generating the daily HTML report, delegate with
  `type=daily` + the day's summary data.
- **periodic-review flow**: delegate with `type=weekly|biweekly|monthly` + review data.
- This centralizes all HTML generation in one subagent + one dispatch table.

---
> **Local overlay** — paths like `bin/…` are relative to the repo root; `$CBP_*` names resolve from `config/paths.env` / `config/local.env` at the repo root. If `contexts/local/rules/report-generation.md` exists, read it as well: it adds or overrides install-specific steps (it wins on conflict). Keep this file generic; put personal/domain details there.
