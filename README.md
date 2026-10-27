# codebuddy-pure

A personal workflow framework for [CodeBuddy Code](https://www.codebuddy.cn/docs/cli/codebuddy-dir):
rules, discipline patterns, methodology notes, bilingual HTML report templates, three sub-agents,
and the scripts plus hooks that hold it together.

Ported from [`kiro-pure`](https://github.com/ranbine/lab) (built for kiro-cli). No machine-specific
paths: everything resolves relative to the repo root through `config/paths.env`.

## Layout

```
CODEBUDDY.md              # project memory: the short version of the rules
.codebuddy/
├── settings.json         # hook registration (5 lifecycle events)
├── settings.local.json   # your overrides, gitignored
├── rules/                # 17 rule files, auto-loaded with frontmatter control
├── agents/               # reviewer · html-generator · health-checker
├── skills/pure/          # the orchestrator skill
├── commands/             # /daily /report /insight /review /checkup /closeout
└── hooks/                # thin adapters: host JSON <-> framework scripts
bin/                      # 18 Python/bash scripts (stdlib only)
contexts/tips/            # 19 methodology notes, read on demand
templates/                # self-contained bilingual HTML + style-registry.json
config/                   # paths.env + gitignored local overrides
tests/                    # 118 unit tests
install.sh                # wire it up for this checkout
```

## Quick start

The framework works in place — CodeBuddy reads `.codebuddy/` from the project root.

```bash
cp config/local.env.example config/local.env    # fill in name / email / timezone
./install.sh                                    # checks hooks, paths, gates; no global changes
codebuddy                                        # then /checkup or /daily
```

Sanity checks:

```bash
python3 bin/cbp-doctor.py       # operational health
python3 bin/cbp-validate.py     # structural validation
bash bin/check-drift.sh         # contract drift vs baseline
python3 -m unittest discover -s tests
```

## How the pieces map to CodeBuddy

| Framework concept | CodeBuddy mechanism |
|---|---|
| rules | `.codebuddy/rules/*.md`, `alwaysApply` decides eager vs on-demand |
| sub-agents | `.codebuddy/agents/*.md` (YAML frontmatter + system prompt) |
| orchestrator | `.codebuddy/skills/pure/SKILL.md` |
| trigger words | `.codebuddy/commands/*.md` slash commands **and** the table in `rules/workflow.md` |
| startup digest | `SessionStart` hook → `hookSpecificOutput.additionalContext` |
| action gate | `PreToolUse` hook → `permissionDecision: allow \| deny \| ask` |
| turn timing | `UserPromptSubmit` / `PostToolUse` / `Stop` → `bin/agent-trace.py` |
| methodology notes | `contexts/tips/`, read only when a rule points at one |

## The action gate

`PreToolUse` classifies every tool call (DENY / L3 / L2 / L1 / L0) against
`.codebuddy/rules/gate-policy.json` and logs the decision:

- `DENY` → `permissionDecision: "deny"` — not approvable, the agent is told to stop.
- `L3` → `permissionDecision: "ask"` — **the host asks the user**; approval is the native one, so
  there is no `/dev/tty` reader, no `approve` CLI and no approval-TTL store in this port.
- everything else → `allow`, recorded for the audit trail.

Start in `shadow` mode (the default) and read the log before switching:

```bash
python3 bin/cbp-gate stats          # what would have been blocked
python3 bin/cbp-gate tail           # last decisions
python3 bin/gate-audit.py --days 7  # propose relax/tighten from the log
```

> **Windows caveat.** The gate compares POSIX-style paths from the command string with roots derived
> by `os.path.realpath`. On Windows those disagree, so path rules under-match: the gate runs, logs,
> and never blocks (textual rules still classify correctly, but nothing is enforced). The
> `SessionStart` hook says so out loud every session. Use a POSIX host or WSL if you want
> enforcement; `tests/` marks the affected suites `POSIX-only` for the same reason.

## Reports

One path only (`rules/report-generation.md`):

1. **html-generator** picks a template by `type` from `templates/style-registry.json`, fills it,
   writes a self-contained bilingual HTML file under `docs/<publish_dir>/`.
2. **reviewer** runs `bin/review-artifact.py <file> --type html` for the mechanical readings
   (links, zh/en pairing, structure, size, leftover placeholders) and returns
   `PUBLISH-OK` / `BLOCK (N issues)` / `NEEDS-HUMAN`.
3. Only a `PUBLISH-OK` file reaches the user. `BLOCK` loops back to html-generator, three rounds max.

`docs/` is gitignored: generated reports contain your own work data and are never published from
this repo.

## Personal vs shared

Shared files (scripts, generic rules, templates, tests) are meant to stay identical across installs.
Anything specific to you goes in gitignored files:

| File | Holds |
|---|---|
| `config/local.env` | identity, paths, timezone, gate allow-lists, budgets |
| `config/gate-policy.local.json` | personal gate rules and `mode` |
| `config/local.json` | summary tags, log patterns, agent keywords, closeout categories |
| `.codebuddy/settings.local.json` | per-checkout hook/permission overrides |

Rules and tips end with a *Local overlay* note: put your own steps in `contexts/local/rules/<name>.md`
or `contexts/local/tips/<path>` instead of editing the shared file.

## Path rule

Scripts never hard-code paths. Add a location as `KEY=relative/dir` in `config/paths.env`, then use
`$KEY` in shell or `P["KEY"]` in Python. Absolute values belong only in `config/local.env` or the
environment.

## Leak guard

`scripts/leak-check.sh` runs on every commit and push: absolute home paths, emails, private keys,
common token shapes. A private denylist (`$CBP_PURE_DENYLIST`, default
`~/.config/codebuddy-pure/denylist.txt`) adds your own org/host words without publishing them.

## License

MIT — see `LICENSE`. Original work by the same author; see `MIGRATION.md` for what changed.
