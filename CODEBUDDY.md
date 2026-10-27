# Project memory — codebuddy-pure

A personal workflow framework for CodeBuddy Code. This file is the short version; the rules
themselves live in `.codebuddy/rules/` and the scripts in `bin/`.

## Conventions

- **Paths**: never hard-code. Every location is a key in `config/paths.env`, used as `$CBP_*` in
  shell and `P["CBP_*"]` in Python. Machine-specific values go in `config/local.env` (gitignored).
- **Shared vs personal**: shared files stay byte-identical across installs. Personal steps go in
  `contexts/local/` or `config/*.local.*`, never by editing a shared file.
- **No verbal promises**: when behaviour should change, write it into the rule file in the same
  turn. An unwritten rule is a rule that does not exist.

## Commands

```bash
python3 bin/cbp-doctor.py        # operational health
python3 bin/cbp-validate.py      # structural validation
bash bin/check-drift.sh          # drift against the contract baseline
python3 bin/cbp-gate stats       # what the gate would have blocked
python3 -m unittest discover -s tests
```

## Where things are

- `.codebuddy/rules/workflow.md` — startup check + trigger-word routing. Start here.
- `.codebuddy/rules/discipline.md` — the red lines. Read before anything destructive.
- `.codebuddy/rules/gate-policy.json` — the gate's policy template (placeholders filled from config).
- `contexts/tips/INDEX.md` — registry of methodology notes; an unregistered note is a dead document.
- `templates/style-registry.json` — report type → template.

## Known limitation

The action gate does not enforce on Windows (POSIX path semantics). It still classifies and logs.
Run it on a POSIX host or WSL when enforcement matters. `tests/` marks the affected suites
`POSIX-only` for the same reason.
