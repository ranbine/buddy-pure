"""Shared body for the three timing hooks (prompt / post / stop).

``bin/agent-trace.py`` already exposes exactly the four phases kiro needed; CodeBuddy's event
names map onto them one-to-one, so these hooks only forward the raw event and the agent name.
Timing must never break a session: any failure is swallowed and the call is allowed.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _hooklib as h


def forward(phase):
    try:
        raw = sys.stdin.read()
    except (OSError, UnicodeDecodeError):
        raw = ""
    agent = os.environ.get("CODEBUDDY_AGENT_NAME") or "pure"
    code, out, err = h.run_script([h.ROOT / "bin" / "agent-trace.py", phase, "--agent", agent],
                                  stdin_text=raw, timeout=20)
    if code == 2:                                   # sub-agent tool budget brake
        sys.stderr.write(err or out or "tool budget exhausted — wrap up now")
        raise SystemExit(2)
    if out.strip():                                 # e.g. the slow-turn note for main
        h.emit(h.context(_EVENT, out.strip()))
    h.emit({"continue": True})


_EVENT = "PostToolUse"
