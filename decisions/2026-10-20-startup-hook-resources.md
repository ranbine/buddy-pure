# Decision: startup check via agentSpawn hook + resources

- **Date**: 2026-10-20
- **Status**: Adopted

## Decision
pure.json now (1) loads workflow.md + preferences.md as `resources`, (2) runs
`bin/cbp-startup-hook.sh` on `agentSpawn`, which executes startup-check.py and the
once-per-day cbp-auth-check and injects a compact "startup digest". The prompt tells
the agent to act on the digest and only fall back to manual reads if it is missing/FAILED.

## Alternatives
- Keep prompt-driven startup (model reads files + runs scripts): non-deterministic —
  auth-check was skipped in practice; costs tool calls every session.
- userPromptSubmit hook for trigger matching: deferred; trigger semantics need the model.

## Reason
Data collection is deterministic and fast (~0.35s); only the decision/interaction
part needs the model. Verified in a real non-interactive session: digest + both
resources present in context.

## Revisit
If cbp-cli hook semantics change, or hook latency exceeds ~2s.
Rollback: `archive/agents/pure.json.bak-2026-10-20`.
