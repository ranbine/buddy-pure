---
alwaysApply: false
description: "Session End"
---

# Session End

Session-end is a named lifecycle flow (referenced by P-ATOMIC-FLOW, memory-dream layer diagram).

The full session-end self-check checklist + Correction Capture rule now lives in
**`rules/discipline.md` → "Session-End 自检清单"** (Tier 3 Process Discipline; number differs per install). Do not duplicate here.

On session close / when user signals end of conversation → run the **Session-End checklist**:
1. task done → write history  2. new script → verify  3. new tool/API → tips
4. unresolved → memory.md  5. rule change → consistency  6. correction → pattern  7. 2× mistake → extract now

Missing #1 or #4 = future-session context loss. Not optional.

---
> **Local overlay** — paths like `bin/…` are relative to the repo root; `$CBP_*` names resolve from `config/paths.env` / `config/local.env` at the repo root. If `contexts/local/rules/session-end.md` exists, read it as well: it adds or overrides install-specific steps (it wins on conflict). Keep this file generic; put personal/domain details there.
