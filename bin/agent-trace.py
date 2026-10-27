#!/usr/bin/python3
"""agent-trace — cbp-cli hook for in-session timing + sub-agent tool budget.

Registered on four events (bin/gate-install.py does this for every gated agent):
  userPromptSubmit  agent-trace.py prompt --agent NAME   turn start; for the main agent, prints a one-line
                                                          note about the previous turn if it was slow (stdout of
                                                          this hook is injected into the model's context)
  preToolUse        agent-trace.py pre    --agent NAME   tool start; sub-agent budget brake (exit 2)
  postToolUse       agent-trace.py post   --agent NAME   tool end (+ output size)
  stop              agent-trace.py stop   --agent NAME   turn end; writes a 'turn' summary record

Writes data/agent-trace/trace-YYYY-MM-DD.jsonl (one event per line) and per-session counters in
data/agent-trace/state/<session>.json. Never blocks except the budget brake; any error → exit 0.

Budget brake (sub-agents only, i.e. agent not in MAIN_AGENTS):
  budget = $CBP_TOOL_BUDGET (set by run-agent.sh from --budget or the task's "BUDGET: <= N tool calls")
           else the per-agent default (DEFAULT_BUDGETS, same numbers as agent-perf.py)
  explicit budget  → enforce: tool call N+1 and later are refused with a "wrap up now" message
  default budget   → log only (event 'budget_over', no block)
Timing model (measured 2026-10-23): prompt→first pre and post→next pre = model time; pre→post = tool time.
Parallel tool calls get near-identical timestamps, so overlapping tool intervals are merged.
"""
import datetime
try:                                    # POSIX advisory locking
    import fcntl
except ImportError:                     # pragma: no cover - platform branch
    fcntl = None
try:                                    # Windows locking equivalent
    import msvcrt
except ImportError:                     # pragma: no cover - platform branch
    msvcrt = None


def _lock_state_file(fh):
    """Take a non-blocking exclusive lock on an open lock file, or raise OSError.

    fcntl.flock on POSIX, msvcrt.locking on Windows. Callers rely on closing the
    handle to release, so no explicit unlock is required.
    """
    if fcntl is not None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return
    if msvcrt is not None:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        return
    raise OSError("no file locking primitive available on this platform")
import hashlib
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from cbp_paths import P, ROOT, CLI_HOME, tz, setting  # noqa: E402

LAB = str(ROOT)                 # repo root
DATA = str(P["CBP_DATA"])      # runtime state (gitignored)
TRACE_DIR = os.environ.get("AGENT_TRACE_DIR") or os.path.join(DATA, "agent-trace")
TZ = tz()  # CBP_TZ (config/local.env)
MAIN_AGENTS = {"pure", "default", "unknown"}
DEFAULT_BUDGETS = {"reviewer": 10, "html-generator": 15, "health-checker": 8}
# extra / overriding budgets from config/local.env, e.g. CBP_AGENT_BUDGETS=my-agent=20,reviewer=8
for _kv in (setting("CBP_AGENT_BUDGETS") or "").split(","):
    if "=" in _kv and _kv.split("=", 1)[1].strip().isdigit():
        DEFAULT_BUDGETS[_kv.split("=", 1)[0].strip()] = int(_kv.split("=", 1)[1])
SLOW_TURN_NOTE_S = 60
SECRET_RES = [
    re.compile(r"(?i)\b(authorization)(\s*[=:]\s*|\s+)((?:bearer|basic)\s+)?\S+"),
    re.compile(r"(?i)\b(\w*(?:token|password|passwd|secret|api[_-]?key|_pat|_key))(\s*[=:]\s*|\s+)\S+"),
    re.compile(r"(\s-u\s*)(\S+?:)\S+"),          # curl -u user:pass
    re.compile(r"(\s-p)(\S+)"),                    # mysql -pSECRET
]


def redact(s):
    s = SECRET_RES[0].sub(lambda m: m.group(1) + m.group(2) + "***", s)
    s = SECRET_RES[1].sub(lambda m: m.group(1) + m.group(2) + "***", s)
    s = SECRET_RES[2].sub(lambda m: m.group(1) + m.group(2) + "***", s)
    return SECRET_RES[3].sub(lambda m: m.group(1) + "***", s)


def now():
    return time.time()


def day_file(epoch):
    d = datetime.datetime.fromtimestamp(epoch, TZ).strftime("%Y-%m-%d")
    return os.path.join(TRACE_DIR, "trace-%s.jsonl" % d)


def append(rec):
    os.makedirs(TRACE_DIR, exist_ok=True)
    with open(day_file(rec["t"]), "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def tool_key(name, tin):
    if isinstance(tin, dict):
        tin = {k: v for k, v in tin.items() if k != "__tool_use_purpose"}
    return hashlib.sha1(json.dumps([name, tin], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


def label(name, tin):
    """Short human label: shell → first command words (redacted), others → tool name."""
    if name == "shell" and isinstance(tin, dict):
        cmd = str(tin.get("command", "")).strip().split("\n")[0]
        m = re.search(r"(?:^|[\s;&|/])(run-agent\.sh)\s+([\w-]+)", cmd)
        if m:
            return "run-agent %s" % m.group(2)
        return redact(cmd)[:80]
    return name


def session_events(session, since_epoch):
    out = []
    for path in sorted({day_file(since_epoch), day_file(now())}):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                needle = '"session": %s' % json.dumps(session)
                for line in f:
                    if needle not in line:
                        continue  # cheap prefilter: stop hook must stay well under its 2 s timeout
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(r, dict) and r.get("session") == session and r.get("t", 0) >= since_epoch:
                        out.append(r)
        except OSError:
            pass
    return out


def turn_summary(events, t_start, t_end):
    """From one turn's events → wall, tool_s (merged intervals), model_s, top tools."""
    pending, intervals = {}, []
    for e in events:
        if e["ev"] == "pre":
            pending.setdefault(e["key"], []).append(e)
        elif e["ev"] == "post":
            q = pending.get(e["key"])
            if q:
                p = q.pop(0)
                intervals.append((p["t"], e["t"], p.get("label", p.get("tool", "?"))))
    merged, total = [], 0.0
    for a, b, _ in sorted(intervals):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    total = sum(b - a for a, b in merged)
    wall = max(0.0, t_end - t_start)
    top = sorted(((round(b - a, 1), lab) for a, b, lab in intervals), reverse=True)[:3]
    return {"wall_s": round(wall, 1), "tool_s": round(total, 1), "model_s": round(max(0.0, wall - total), 1),
            "tools": len(intervals), "top": top}


# ---------------------------------------------------------------- state (per session)

class LockTimeout(Exception):
    pass


def with_state(session, fn, agent="unknown"):
    """Read-modify-write per (agent, session) state under a separate lock file (bounded wait),
    written atomically via tmp + os.replace so a crash never leaves an empty/half state."""
    sdir = os.path.join(TRACE_DIR, "state")
    os.makedirs(sdir, exist_ok=True)
    key = "%s__%s" % (agent, session or "ppid%d" % os.getppid())
    path = os.path.join(sdir, re.sub(r"[^\w.-]", "_", key) + ".json")
    with open(path + ".lock", "a") as lk:
        deadline = time.time() + 0.3
        while True:
            try:
                _lock_state_file(lk)
                break
            except OSError:
                if time.time() > deadline:
                    raise LockTimeout(path)
                time.sleep(0.01)
        try:
            with open(path) as f:
                st = json.loads(f.read() or "{}")
            if not isinstance(st, dict):
                st = {}
        except (OSError, ValueError):
            st = {}
        res = fn(st)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            f.write(json.dumps(st))
        os.replace(tmp, path)
        return res


def budget_for(agent):
    raw = os.environ.get("CBP_TOOL_BUDGET", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw), True
    return DEFAULT_BUDGETS.get(agent), False


# ---------------------------------------------------------------- handlers

def on_prompt(p, agent):
    t = now()
    sess = p.get("session_id", "")
    rec = {"t": t, "ev": "prompt", "agent": agent, "session": sess, "prompt_chars": len(p.get("prompt") or "")}
    # 9: show the previous-turn note once, then forget it
    last = with_state(sess, lambda st: (st.get("last_turn"), st.update(turn_start=t, turn_tools=0, last_turn=None))[0],
                      agent)
    append(rec)
    if agent in MAIN_AGENTS and last and last.get("wall_s", 0) >= SLOW_TURN_NOTE_S:
        top = "; ".join("%s %ss" % (lab, s) for s, lab in last.get("top", [])[:2])
        print("[turn-timing] previous turn took %ss: tools %ss, model %ss, %d tool calls%s. "
              "If a sub-agent dominated, tighten its brief (INPUTS/GIVEN/BUDGET) next time." % (
                  last["wall_s"], last["tool_s"], last["model_s"], last["tools"],
                  (" (slowest: %s)" % top) if top else ""))
    return 0


def on_pre(p, agent):
    t = now()
    sess = p.get("session_id", "")
    name, tin = p.get("tool_name", ""), p.get("tool_input") or {}
    rec = {"t": t, "ev": "pre", "agent": agent, "session": sess, "tool": name,
           "key": tool_key(name, tin), "label": label(name, tin)}
    if agent in MAIN_AGENTS:
        append(rec)
        return 0
    budget, explicit = budget_for(agent)

    def bump(st):  # per turn: one delegated task = one prompt; a resumed session gets a fresh budget
        st["turn_tools"] = st.get("turn_tools", 0) + 1
        return st["turn_tools"]
    try:
        n = with_state(sess, bump, agent)
    except LockTimeout:
        append(dict(rec, ev="lock_timeout"))
        if budget and explicit:
            sys.stderr.write("TOOL BUDGET: could not read the budget counter; refusing this call. Reply with what you have.\n")
            return 2
        return 0
    rec["n"] = n
    append(rec)
    if budget and n > budget:
        append({"t": t, "ev": "budget_over", "agent": agent, "session": sess, "n": n, "budget": budget,
                "enforced": explicit})
        if explicit:
            sys.stderr.write(
                "TOOL BUDGET REACHED (budget brake, separate from the action gate and its shadow mode): this task "
                "allows %d tool calls and they are used up. Do not call more tools. Reply now with your findings so far, "
                "clearly marking what you could not finish. (Ignore any 'module ... python' line above: it is "
                "login-shell noise, not an error.)\n" % budget)
            return 2
    return 0


def on_post(p, agent, raw_len=0):
    name, tin = p.get("tool_name", ""), p.get("tool_input") or {}
    size = raw_len  # whole payload length ≈ tool output size; avoids re-serialising large outputs
    append({"t": now(), "ev": "post", "agent": agent, "session": p.get("session_id", ""), "tool": name,
            "key": tool_key(name, tin), "out_bytes": size})
    return 0


def on_stop(p, agent):
    t = now()
    sess = p.get("session_id", "")
    start = with_state(sess, lambda st: st.get("turn_start"), agent)
    rec = {"t": t, "ev": "stop", "agent": agent, "session": sess,
           "reply_chars": len(p.get("assistant_response") or "")}
    append(rec)
    if start:
        evs = [e for e in session_events(sess, start) if e["ev"] in ("pre", "post")]
        summ = turn_summary(evs, start, t)
        append(dict({"t": t, "ev": "turn", "agent": agent, "session": sess, "start": start}, **summ))
        with_state(sess, lambda st: st.update(last_turn=summ, turn_start=None), agent)
    return 0


HANDLERS = {"prompt": on_prompt, "pre": on_pre, "post": on_post, "stop": on_stop}


def main(argv):
    if not argv or argv[0] not in HANDLERS:
        return 0
    agent = argv[argv.index("--agent") + 1] if "--agent" in argv and argv.index("--agent") + 1 < len(argv) else "unknown"
    try:
        raw = sys.stdin.read()
        p = json.loads(raw) if raw.strip() else {}
        if not isinstance(p, dict):
            return 0
        if argv[0] == "post":
            return on_post(p, agent, len(raw))
        return HANDLERS[argv[0]](p, agent)
    except Exception:
        return 0  # timing must never break the session


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
