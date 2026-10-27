# Decisions Log

Record **why** a choice was made, not just what was done.

## Format

```markdown
# YYYY-MM-DD — <short title>

## Decision
<one sentence>

## Alternatives Considered
- A: <option> — <pros/cons>
- B: <option> — <pros/cons>

## Reason
<why this one won>

## Revisit If
<condition that would invalidate this decision>

## Outcome
- 复盘日期: YYYY-MM-DD (决策后 60 天)
- 实际结果: (空=待复盘 | 填写实际情况)
- 当前结论: 维持 / 推翻 / 调整
```

## When to Record
- Architecture/infra choices (where to deploy, which tool, which repo)
- Workflow design changes (rule structure, pipeline logic)
- Trade-off decisions (performance vs maintainability, scope vs time)

NOT needed for:
- Trivial file renames, typo fixes
- Obvious single-option choices
