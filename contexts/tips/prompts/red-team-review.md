---
title: "Red Team Review — Pre-mortem for Plans & Designs"
category: prompts
verified_at: 2026-08-21
keywords:
  - prompting
  - ai
  - review
  - red
  - team
---

# Red Team Review — Pre-mortem for Plans & Designs

## When to Use
- Before implementing a major pipeline/workflow change
- Before committing to a new architecture decision
- When a plan "feels right" but hasn't been stress-tested

## Prompt Template

```
Before executing this plan, act as my red team. Your judgment is the weapon.

First, restate my plan in full to confirm you understand it. Then challenge it.

Assume 6 months from now, this plan has failed. Reverse-engineer the 3 most likely causes:
- Which unvalidated assumption did I treat as fact?
- Which failure mode did I never consider?
- Where was I overly optimistic to save effort?
- Is there a simpler way to achieve the same goal?
- Am I solving the right bottleneck? (Do I have measurement data, or am I guessing where "slow" is?)

For each cause, provide:
- Trigger condition (what makes it happen)
- Failure cost (what breaks, how badly)
- Minimum falsification experiment (smallest action to prove/disprove it early)

Final verdict (pick one):
- ✅ Proceed as-is
- ⚠️ Run experiment X first, then proceed
- 🔴 Rethink from scratch
```

## Usage Pattern

1. Write your plan/design in a few paragraphs
2. Paste the template above
3. Review the output — especially the "assumptions treated as fact" section
4. Record findings in `decisions/` if proceeding

## Example Scenarios

- "L2→L3 chain logic: L2 low confidence passes hypothesis to L3"
  → Red team might find: "What if L2 gives low on everything? L3 gets overloaded with noise"
  
- "Move nightly pipeline from forge A to forge B"
  → Red team might find: "Runner IP might change quarterly, breaking the shared NFS mount"

## Integration

- Can be piped into any LLM CLI for automated pre-mortem
- Or run interactively in Pure conversation before major decisions
- Output feeds directly into `decisions/YYYY-MM-DD-<slug>.md` under "Alternatives Considered"

---
> **Local overlay** — if `contexts/local/tips/prompts/red-team-review.md` exists, read it too (install-specific notes and evidence).
