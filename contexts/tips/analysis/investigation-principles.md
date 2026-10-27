---
title: "Investigation Principles"
category: analysis
verified_at: 2026-08-21
keywords:
  - analysis
  - methodology
  - log
  - investigation
  - principles
---

# Investigation Principles

Failure analysis methodology. Read before diving into logs.

## Execution Order

### 1. PASS vs FAIL diff — always first

Find a passing run of the same case, diff against the failure. The divergence point = root cause location.

- Same case different build → code regression
- Same build different cluster → environment issue
- Same everything different time → timing/race condition

Don't theorize from error messages alone. Diff tells you WHERE to look.

### 2. Build timeline

Every event has a timestamp. Put them in order BEFORE analyzing.

```
trigger (before) → mechanism (during) → symptom (after)
```

Without timeline you're guessing causality. ISP events, alarms, pod restarts — all go on the same timeline.

### 3. Trace data flow

Symptom appears at the end. Cause is in the middle. Trace each layer:

```
source → transport → processing → destination
```

Find the break point: where "sent" ≠ "received". Don't skip intermediate layers.

### 4. Check external factors

Before deep-diving: is something else interfering?
- Node under maintenance / kernel panic recovery in progress
- Another test running on same cluster
- Cron job / certificate rotation / infra event

## Fault Patterns (from real TRs)

| Pattern | Frequency | What to check |
|---------|-----------|---------------|
| Value wrong, not event missing | 33% | Don't just check "did X happen" — check field values |
| Unhandled edge case | 23% | What unusual condition was active when crash happened? |
| Test issue (wrong assertion) | 27% | Which assumption is wrong? Need specific evidence |
| Cascading failure | — | TC1 leftover breaks TC2+. Check suite order dependency |

## Practical Rules

- **Don't stop at first error.** "Upgrade failed" is a symptom. Ask: which step → which component → which operation → why.
- **Error codes narrow the domain.** Connection refused ≠ TLS failure ≠ timeout. Read the code first.
- **Multi-instance: compare individually.** "2981 failures" could be 0+2981 across 2 pods. Check asymmetry.
- **Log coverage matters.** kubectl logs rotate. prev.txt only covers last container lifecycle. ADP tgz has wider window. If fault time < earliest log timestamp → log is lost.
- **Rerun judgment:** timing-sensitive (race condition) → rerun may pass. Deterministic (code bug, config error) → rerun will fail the same way.
