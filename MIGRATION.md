# Migrating kiro-pure → codebuddy-pure

What this port changed, why, and what did not survive. Read this before comparing the two repos:
the directory names differ, but the methodology is the same.

## Why a separate repo

`kiro-pure` targets kiro-cli's agent JSON format. CodeBuddy has a different extension surface, and
its `PreToolUse` hook can ask the user a question natively. Trying to serve both runtimes from one
tree would have meant carrying two agent vocabularies and one permanently dead branch. The
methodology, scripts and templates are shared *ideas*, not shared files — so this repo starts clean
and keeps the lineage documented here instead.

## Concept mapping

| kiro-pure | codebuddy-pure | Notes |
|---|---|---|
| `contexts/workflow.md` | `.codebuddy/rules/workflow.md` | became a rule with `alwaysApply: true` |
| `contexts/preferences.md` | `.codebuddy/rules/preferences.md` | same |
| `contexts/rules/*.md` | `.codebuddy/rules/*.md` | frontmatter added; `alwaysApply` false for the on-demand ones |
| `contexts/tips/**` | `contexts/tips/**` | unchanged path; read on demand, registered in `INDEX.md` |
| `agents/kiro-lab.json.tmpl` | `.codebuddy/skills/pure/SKILL.md` | orchestrator prompt + routing table |
| `agents/kiro-lab.json.tmpl` `resources` | `rules/workflow.md` + `rules/preferences.md` as rules | CodeBuddy auto-loads rules; no `resources` list needed |
| `agents/reviewer.json.tmpl` + `-prompt.md` | `.codebuddy/agents/reviewer.md` | prompt kept nearly verbatim |
| `agents/html-generator.*` | `.codebuddy/agents/html-generator.md` | same |
| `agents/health-checker.*` | `.codebuddy/agents/health-checker.md` | same |
| `tools: ["read","write","shell",...]` | `tools: Read, Write, Bash, ...` | comma-separated; case differs per host |
| `toolsSettings.subagent.availableAgents` | implicit | CodeBuddy discovers `.codebuddy/agents/*` |
| `welcomeMessage` | — | dropped; a slash command is the equivalent entry point |
| trigger-word table | `.codebuddy/commands/*.md` **and** the same table in `workflow.md` | slash commands for explicit use, the table for fuzzy matching |
| `hooks.agentSpawn` | `SessionStart` → `additionalContext` | the digest is injected the same way |
| `hooks.preToolUse` | `PreToolUse` → `permissionDecision` | see below |
| `hooks.postToolUse` | `PostToolUse` | forwards to `agent-trace.py post` |
| `hooks.userPromptSubmit` | `UserPromptSubmit` | forwards to `agent-trace.py prompt` |
| `hooks.stop` | `Stop` | forwards to `agent-trace.py stop` |
| `KIRO_*` keys | `CBP_*` keys | mechanical rename, `config/paths.env` |
| `bin/kiro-*` | `bin/cbp-*` | `cbp-gate`, `cbp-doctor`, `cbp-audit`, `cbp-closeout`, `cbp-startup-hook.sh` |

## The one real deletion: `/dev/tty` approval

kiro-pure's gate had to open `/dev/tty` to make a human approve an L3 action, because its host had
no native "ask the user" primitive. That is why the repo carried a pty reader, an `approve`
subcommand bound to a one-shot gate id, an approval TTL, and pty-based tests (the most fragile code
in the tree — the last kiro commit was a fix for exactly this).

CodeBuddy's `PreToolUse` can return `permissionDecision: "ask"` and the host asks. So this port
**deletes** instead of adapting:

- `_tty_ask()` and the `approve` subcommand
- the approval store and `approval_ttl_sec`
- `tests/test_gate_audit.py::TtyPrompt` (pty), `test_apply_refuses_in_agent_or_without_tty`
- `bin/gate-install.py` (it patched rendered agent JSON to add hooks; `settings.json` is now the
  only registration point)

`cbp-gate` keeps `list`, `tail`, `stats`, `mode` — the review and audit surface. `apply` stays,
because it proposes rule changes from the log and still needs a human to confirm, which CodeBuddy
now does through the ordinary permission prompt.

Net: fewer moving parts than upstream, and the fragile part is gone rather than shimmed.

## Windows work

Upstream never ran on Windows: `import pwd` and `import fcntl` failed at import, so 12 of 24 tests
errored before executing anything. Fixed properly:

| Problem | Fix |
|---|---|
| `import pwd` (`action-gate.py`) | `_account_home()` / `_account_name()` fall back to `os.path.expanduser` / `getpass` |
| `/tmp/<user>-` default | `_tmp_prefix_default()` uses `%TEMP%` on Windows, keeps the POSIX form elsewhere |
| `import fcntl` (`agent-trace.py`) | `_lock_state_file()` uses `msvcrt.locking` on Windows |
| `signal.SIGALRM` / `setitimer` | `_arm_deadline()` / `_read_payload()` — the deadline bounds the stdin read on Windows |
| `while d != "/"` in `_check_roots` | loops until the parent stops changing (`C:\` never equals `/` — this hung forever) |
| `tmp.startswith("/")` | accepts `os.path.isabs()` too, so POSIX-style tests stay meaningful |
| `open("/dev/tty")` in tests | replaced with `sys.executable` and platform skips |

### The limitation that remains

The gate takes POSIX paths from the command string and compares them against roots produced by
`os.path.realpath`. On Windows those two never line up (`C:\Users\x` vs `/c/Users/x`), so **path**
rules under-match: `rm -rf /` classifies as L2/allow instead of L3. Textual rules still match.

Rather than pretend, the gate now detects this and:

- marks such decisions `would-deny` / `would-block` in the log instead of `deny` / `block`
- never blocks (so a mis-classification cannot silently fail *closed* and wedge the session)
- prints one warning per session, and `SessionStart` states it in the injected context

Enforcement needs a POSIX host or WSL. Making it work on Windows would mean rewriting the path
comparison to translate drives to `/c/...` and re-baselining ~20 expectations — a real project, not
a patch. It is scoped as follow-up work, not silently skipped.

## Test status

```
Linux/macOS (upstream behaviour)   118 tests, 0 skipped
Windows                            118 tests, 48 skipped, 0 failures
```

The 48 skipped on Windows are the suites whose expectations *are* POSIX path semantics, plus the two
pty tests that no longer have a subject. They are skipped with a reason string, not deleted, so they
keep guarding the POSIX path.

New here: `tests/test_hooks.py` (14 tests) pins the adapter layer — event names, tool vocabulary,
permission decisions, `settings.json` shape, and that every referenced hook script exists.
