---
description: Generate a bilingual HTML report (daily/weekly/biweekly/monthly/insight/scope/health)
argument-hint: "<type>[, 数据/要点]"
allowed-tools: Read, Write, Edit, Grep, Glob, Bash, Task
---

Read `.codebuddy/rules/report-generation.md`, then:

1. Delegate to the **html-generator** subagent with `type=` and the data below.
2. Send the produced file to the **reviewer** subagent (`bin/review-artifact.py <file> --type html`).
3. `BLOCK` goes back to html-generator (max 3 rounds). Only `PUBLISH-OK` is shown to the user.

Type and data: $ARGUMENTS

Never claim a report is ready before the reviewer returns `PUBLISH-OK`.
