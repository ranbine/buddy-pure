#!/usr/bin/python3
"""gate-install — add/remove action-gate preToolUse hooks in pure agent configs.

  gate-install.py install [agent ...]   default: pure + all subagents listed in its toolsSettings
  gate-install.py remove  [agent ...]
  gate-install.py status  [agent ...]

Idempotent: hooks are tagged by command path; re-install replaces them.
Backs up each changed file to <agents>/.backup/<name>.json.<timestamp> first.
Only hooks for tools the agent actually has are added (matcher per tool).
"""
import datetime
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from cbp_paths import ROOT, CLI_HOME  # noqa: E402

AGENTS_DIR = os.path.join(str(CLI_HOME), "agents")   # rendered agents (install.sh)
GATE = os.path.join(str(ROOT), "bin/action-gate.py")
TRACE = os.path.join(os.path.dirname(GATE), "agent-trace.py")
TIMEOUT_MS = 3000
# timing/budget hooks on every tool (no matcher) + turn boundaries; see bin/agent-trace.py
TRACE_EVENTS = [("userPromptSubmit", "prompt"), ("preToolUse", "pre"), ("postToolUse", "post"), ("stop", "stop")]
GATED_BUILTIN = ["shell", "write", "delegate"]


def load(name):
    with open(os.path.join(AGENTS_DIR, name + ".json")) as f:
        return json.load(f)


def default_agents():
    main = load("pure")
    sub = (main.get("toolsSettings") or {}).get("subagent") or {}
    return ["pure"] + list(dict.fromkeys(sub.get("availableAgents", []) + sub.get("trustedAgents", [])))


def matchers_for(cfg):
    tools = cfg.get("tools") or []
    m = [t for t in GATED_BUILTIN if t in tools or "*" in tools]
    for t in tools:
        if t.startswith("@"):
            m.append(t if "/" in t else t)  # '@server' matches all its tools (verified)
    return m


def is_gate_hook(h):
    """Recognise our hooks by script basename, so a moved repo doesn't leave duplicates."""
    c = (h.get("command") or "") if isinstance(h, dict) else ""
    return bool(re.search(r"(^|[/\s])(action-gate|agent-trace)\.py(\s|$)", c))


def install(name):
    cfg = load(name)
    hooks = cfg.setdefault("hooks", {})
    for ev in list(hooks):
        if not isinstance(hooks[ev], list):
            raise SystemExit("%s: hooks.%s is not a list; fix the agent file by hand" % (name, ev))
    for ev in ["preToolUse"] + [e for e, _ in TRACE_EVENTS]:
        hooks[ev] = [h for h in hooks.get(ev, []) if not is_gate_hook(h)]
    new = [{"matcher": m, "command": "/usr/bin/python3 -I %s --agent %s" % (GATE, name), "timeout_ms": TIMEOUT_MS}
           for m in matchers_for(cfg)]
    hooks["preToolUse"] += new
    for ev, tag in TRACE_EVENTS:
        hooks[ev].append({"command": "/usr/bin/python3 -I %s %s --agent %s" % (TRACE, tag, name), "timeout_ms": 2000})
    for ev in list(hooks):
        if not hooks[ev]:
            hooks.pop(ev)
    save(name, cfg)
    return [h["matcher"] for h in new] + ["trace"]


def remove(name):
    cfg = load(name)
    hooks = cfg.get("hooks") or {}
    for ev in list(hooks):
        keep = [h for h in hooks[ev] if not is_gate_hook(h)]
        if keep:
            hooks[ev] = keep
        else:
            hooks.pop(ev)
    save(name, cfg)


def status(name):
    cfg = load(name)
    hooks = cfg.get("hooks") or {}
    out = [h.get("matcher") for h in hooks.get("preToolUse", []) if "action-gate.py" in (h.get("command") or "")]
    if any("agent-trace.py" in (h.get("command") or "") for hs in hooks.values() if isinstance(hs, list) for h in hs):
        out.append("trace")
    return out


def save(name, cfg):
    path = os.path.join(AGENTS_DIR, name + ".json")
    bdir = os.path.join(AGENTS_DIR, ".backup")
    os.makedirs(bdir, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(path, os.path.join(bdir, "%s.json.%s" % (name, ts)))
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.write("\n")
    with open(tmp) as f:
        json.load(f)  # validate before replacing
    os.replace(tmp, path)


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("install", "remove", "status"):
        print(__doc__)
        sys.exit(1)
    names = sys.argv[2:] or default_agents()
    for n in names:
        if sys.argv[1] == "install":
            print("%-16s installed: %s" % (n, ", ".join(install(n)) or "(no gated tools)"))
        elif sys.argv[1] == "remove":
            remove(n)
            print("%-16s removed" % n)
        else:
            print("%-16s %s" % (n, ", ".join(status(n)) or "-"))


if __name__ == "__main__":
    main()
