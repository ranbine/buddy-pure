"""Shared plumbing for the CodeBuddy hook shells.

CodeBuddy hands a hook a JSON event on stdin and reads a JSON decision back on stdout
(plus exit codes: 0 continue, 2 block). The framework's own scripts speak a slightly
different dialect, so every adapter in this directory funnels through here.

Contract kept deliberately small — anything that is not about translation lives in bin/.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # .codebuddy/hooks/<this file> -> repo root

# CodeBuddy tool names -> the vocabulary the gate policy is written in.
_TOOL_MAP = {
    "bash": "shell", "shell": "shell",
    "write": "write", "edit": "write", "multiedit": "write", "notebookedit": "write",
    "read": "read", "grep": "read", "glob": "read",
    "webfetch": "read", "websearch": "read",
    "task": "delegate", "agent": "delegate",
}


def read_event():
    """Parse the hook event. Never raise: a malformed event must not wedge the session."""
    try:
        raw = sys.stdin.read()
    except (OSError, UnicodeDecodeError):
        return {}
    try:
        ev = json.loads(raw) if raw.strip() else {}
    except ValueError:
        return {"_raw": raw}
    return ev if isinstance(ev, dict) else {}


def map_tool(name):
    """Translate a CodeBuddy tool name into the policy's vocabulary."""
    if not name:
        return ""
    n = str(name)
    if n.startswith("mcp__"):                       # mcp__server__tool -> @server/tool
        parts = n.split("__")
        if len(parts) >= 3:
            return "@%s/%s" % (parts[1], "__".join(parts[2:]))
    return _TOOL_MAP.get(n.lower(), n)


def emit(payload=None, exit_code=0):
    """Write a HookOutput JSON document and exit."""
    if payload is not None:
        sys.stdout.write(json.dumps(payload))
        sys.stdout.flush()
    raise SystemExit(exit_code)


def context(event_name, text):
    """additionalContext for SessionStart / UserPromptSubmit / PostToolUse."""
    return {"continue": True, "hookSpecificOutput": {"hookEventName": event_name, "additionalContext": text}}


def permission(decision, reason):
    """permissionDecision for PreToolUse: allow | deny | ask."""
    out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision}}
    if reason:
        out["hookSpecificOutput"]["permissionDecisionReason"] = reason
    return out


def _run(cmd, stdin_text=None, timeout=30):
    import subprocess
    try:
        p = subprocess.run(cmd, input=stdin_text, capture_output=True, text=True,
                           timeout=timeout, cwd=str(ROOT))
        return p.returncode, p.stdout, p.stderr
    except (OSError, subprocess.SubprocessError) as e:
        return 1, "", "%s: %s" % (type(e).__name__, e)


def run_script(args, stdin_text=None, timeout=30):
    """Run a Python entry point under the interpreter that is already running this hook."""
    return _run([sys.executable] + [str(a) for a in args], stdin_text, timeout)


def run_shell(script, stdin_text=None, timeout=45):
    """Run a bash entry point. CodeBuddy runs hooks in Git Bash on Windows too, so bash exists.

    Resolve bash from PATH first: on Windows ``$BASH`` is not reliably the Git Bash we want (it can
    point at wsl.exe), and the script itself is plain POSIX sh.
    """
    import shutil
    shell = shutil.which("bash") or os.environ.get("BASH") or "/bin/bash"
    return _run([shell, str(script)], stdin_text, timeout)


def warn(text):
    """Surface a message to the user without blocking."""
    return {"continue": True, "systemMessage": text}


def is_windows():
    return os.name == "nt"
