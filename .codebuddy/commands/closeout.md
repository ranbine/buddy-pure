---
description: End-of-session closeout — archive, summary, pending items, and the gate's audit trail
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
---

Read `.codebuddy/rules/session-end.md` and `.codebuddy/rules/session-archive.md`, then run
`python3 bin/cbp-closeout.py` and report what it archived, what it left pending, and why.

Anything that still needs action goes into the pending queue rather than being dropped. $ARGUMENTS
