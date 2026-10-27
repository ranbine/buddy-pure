"""SessionStart -> startup digest.

The original framework injected its digest from an ``agentSpawn`` hook. CodeBuddy has no such
event; ``SessionStart`` is the equivalent, and it takes context through
``hookSpecificOutput.additionalContext``.

Kept non-blocking on purpose: a broken digest must never stop the user from starting work, so
every failure degrades into a one-line warning inside the context instead of an error exit.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _hooklib as h


def main():
    notes = []

    code, out, err = h.run_shell(h.ROOT / "bin" / "cbp-startup-hook.sh", timeout=45)
    digest = out.strip()
    if code != 0 or not digest:
        detail = (err or "").strip().splitlines()
        notes.append("startup digest: FAILED (exit %d)%s" % (code, (": " + detail[-1]) if detail else ""))
        notes.append("Read .codebuddy/rules/workflow.md and run its Startup Check manually.")
    else:
        notes.append(digest)

    if h.is_windows():
        notes.append(
            "action gate: RUNNING DEGRADED on Windows — decisions are recorded but nothing is blocked "
            "(POSIX path semantics unavailable). Use a POSIX host or WSL for enforcement.")

    h.emit(h.context("SessionStart", "\n\n".join(notes)))


if __name__ == "__main__":
    main()
