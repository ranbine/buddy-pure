#!/usr/bin/python3
"""agent-perf — where does sub-agent time go? Per-run trace + per-agent summary.

  agent-perf.py [--days 7] [--agent NAME] [--runs] [--json] [--write-weekly]

Joins three existing sources (no new instrumentation inside the agents):
  $CBP_CLI_HOME/sessions/cli/<id>.json(l)   created/updated time, LLM turns, tool calls by name, tool output size
  data/gate/decisions-*.jsonl         session -> agent name (every gate-hooked agent, incl. native delegate)
  data/agent-runs.jsonl               run-agent.sh spawns: timeout given, exit/outcome, end-to-end wall
Main-agent sessions (pure) are excluded.

Per run: wall_s, turns, tool_uses (by tool), s_per_turn, tool_out_kb (≈ context growth), outcome,
and flags: TIMEOUT / OVER_BUDGET (tool calls > budget) / SLOW_TURN (> 20 s/turn) / NO_CONTRACT.
Budgets come from .codebuddy/rules/orchestration.md "Delegation brief" (kept in BUDGETS below).
--write-weekly writes data/agent-perf/YYYY-Www.json for trend comparison in the weekly review.
"""
import argparse
import ast
import collections
import datetime
import glob
import json
import os
import re
import statistics
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from cbp_paths import P, ROOT, CLI_HOME, tz, setting  # noqa: E402

LAB = str(ROOT)                 # repo root
DATA = str(P["CBP_DATA"])      # runtime state (gitignored)
SESS_DIR = os.environ.get("AGENT_PERF_SESSIONS") or os.path.join(str(CLI_HOME), "sessions/cli")
GATE_DIR = os.environ.get("GATE_DATA") or os.path.join(DATA, "gate")
RUNS_LOG = os.environ.get("CBP_AGENT_RUNS_LOG") or os.path.join(DATA, "agent-runs.jsonl")
OUT_DIR = os.path.join(DATA, "agent-perf")
TRACE_DIR = os.environ.get("AGENT_TRACE_DIR") or os.path.join(DATA, "agent-trace")
TZ = tz()  # CBP_TZ (config/local.env)
MAIN_AGENTS = {"pure", "default", "unknown"}
# tool-call budget per agent = the largest per-task-type budget for that agent in
# orchestration.md "Delegation brief" (used only for the OVER_BUDGET flag)
BUDGETS = {"reviewer": 10, "html-generator": 15, "health-checker": 8}
# extra / overriding budgets from config/local.env, e.g. CBP_AGENT_BUDGETS=my-agent=20,reviewer=8
for _kv in (setting("CBP_AGENT_BUDGETS") or "").split(","):
    if "=" in _kv and _kv.split("=", 1)[1].strip().isdigit():
        BUDGETS[_kv.split("=", 1)[0].strip()] = int(_kv.split("=", 1)[1])
SLOW_TURN_S = 20
JOIN_WINDOW_S = 20


def _ts(s):
    """ISO timestamp (Z or ±HH:MM, any fraction length, naive = UTC) → aware datetime.
    Python 3.9 fromisoformat only accepts 3- or 6-digit fractions, so normalise to 6."""
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    m = re.match(r"^(.*?T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(.*)$", s)
    if m:
        s = m.group(1) + ("." + m.group(2)[:6].ljust(6, "0") if m.group(2) else "") + m.group(3)
    d = datetime.datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)


def _data(d):
    """Decode an event's 'data' field (python-repr or JSON string) to a dict; {} on anything odd."""
    if not isinstance(d, dict):
        return {}
    v = d.get("data")
    if isinstance(v, str):
        try:
            v = ast.literal_eval(v)
        except (ValueError, SyntaxError, MemoryError, RecursionError, TypeError):
            try:
                v = json.loads(v)
            except ValueError:
                return {}
    return v if isinstance(v, dict) else {}


def session_stats(sid):
    """Return dict for one session or None (never raises: odd files are skipped)."""
    try:
        return _session_stats(sid)
    except Exception:
        return None


def _session_stats(sid):
    mp = os.path.join(SESS_DIR, sid + ".json")
    jp = os.path.join(SESS_DIR, sid + ".jsonl")
    try:
        with open(mp, encoding="utf-8", errors="replace") as f:
            meta = json.load(f)
        c, u = _ts(meta["created_at"]), _ts(meta["updated_at"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    turns, tools, out_bytes = 0, collections.Counter(), 0
    try:
        with open(jp, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(ev, dict):
                    continue
                kind = ev.get("kind")
                if kind == "AssistantMessage":
                    turns += 1
                    content = _data(ev).get("content", []) or []
                    for item in content if isinstance(content, list) else []:
                        if isinstance(item, dict) and item.get("kind") == "toolUse":
                            name = _data(item).get("name", "?")
                            tools[name] += 1
                elif kind == "ToolResults":
                    out_bytes += len(line)
    except OSError:
        pass
    return {"session": sid, "created": c, "updated": u, "wall_s": round((u - c).total_seconds(), 1),
            "turns": turns, "tools": dict(tools), "tool_uses": sum(tools.values()),
            "tool_out_kb": round(out_bytes / 1024, 1), "cwd": meta.get("cwd", ""),
            "title": (meta.get("title") or "")[:80]}


def gate_agents(since):
    m = {}
    for fn in glob.glob(os.path.join(GATE_DIR, "decisions-*.jsonl")):
        try:
            f = open(fn, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(r, dict):
                    continue
                s = r.get("session")
                if s and r.get("agent"):
                    m.setdefault(s, r["agent"])
    return m


def load_runs(since):
    out = []
    try:
        with open(RUNS_LOG, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(r, dict) or not r.get("agent"):
                    continue
                try:
                    r["start_epoch"] = float(r.get("start_epoch", 0))
                except (TypeError, ValueError):
                    continue
                if r["start_epoch"] >= since.timestamp():
                    out.append(r)
    except OSError:
        pass
    return out


def collect(days, agent_filter=None):
    since = datetime.datetime.now(TZ) - datetime.timedelta(days=days)
    g = gate_agents(since)
    runs = load_runs(since)
    stats = {}
    for mp in glob.glob(os.path.join(SESS_DIR, "*.json")):
        sid = os.path.basename(mp)[:-5]
        try:
            if os.path.getmtime(mp) < since.timestamp():
                continue
        except OSError:
            continue
        st = session_stats(sid)
        if st:
            stats[sid] = st
    # resumed runs reuse an older session: attach by id, time from the run itself
    for r in runs:
        if r.get("resume") and r["resume"] not in stats:
            st = session_stats(r["resume"])
            if st:
                stats[r["resume"]] = st
    # run-centric join over ALL candidate (run, session) pairs: same cwd, created within the window,
    # gate agent (if any) == run agent. Assign gate-confirmed pairs first, then gate-less ones,
    # closest in time first within each tier; resume -> that exact session.
    owner, taken = {}, set()
    for i, r in enumerate(runs):
        if r.get("resume") and r["resume"] in stats and r["resume"] not in owner:
            owner[r["resume"]] = i
            taken.add(i)
    cands = []
    for i, r in enumerate(runs):
        if i in taken or r.get("resume"):
            continue
        for sid, st in stats.items():
            if sid in owner or g.get(sid, r["agent"]) != r["agent"]:
                continue
            if r.get("cwd") and st["cwd"] and r["cwd"] != st["cwd"]:
                continue
            dt = st["created"].timestamp() - r["start_epoch"]
            if 0 <= dt <= JOIN_WINDOW_S:
                cands.append((0 if sid in g else 1, dt, i, sid))
    for _tier, _dt, i, sid in sorted(cands):
        if i in taken or sid in owner:
            continue
        owner[sid] = i
        taken.add(i)
    rows, used = [], set(owner.values())
    for sid, st in stats.items():
        run = runs[owner[sid]] if sid in owner else {}
        agent = g.get(sid) or run.get("agent")
        if st["created"] < since and not run:
            continue
        if not agent or agent in MAIN_AGENTS or (agent_filter and agent != agent_filter):
            continue
        rows.append(_row(st, agent, run))
    for i, r in enumerate(runs):  # spawns with no session (e.g. timed out before the CLI wrote one)
        if i in used or (agent_filter and r["agent"] != agent_filter):
            continue
        rows.append({"ts": _fmt_epoch(r["start_epoch"]), "epoch": r["start_epoch"], "agent": r["agent"],
                     "session": "", "wall_s": r.get("wall_s"), "e2e_s": r.get("wall_s"), "turns": None,
                     "tool_uses": None, "tools": {}, "tool_out_kb": None, "s_per_turn": None,
                     "outcome": r.get("outcome"), "timeout_s": r.get("timeout_s"), "task": r.get("task", ""),
                     "via": "run-agent", "flags": _flags(r["agent"], None, None, r.get("outcome"))})
    rows.sort(key=lambda x: x["epoch"])
    return rows


def _fmt_epoch(e):
    return datetime.datetime.fromtimestamp(e, TZ).isoformat(timespec="seconds")


def _flags(agent, tool_uses, spt, outcome):
    f = []
    if outcome == "timeout":
        f.append("TIMEOUT")
    if outcome == "no-contract":
        f.append("NO_CONTRACT")
    if tool_uses is not None and tool_uses > BUDGETS.get(agent, 15):
        f.append("OVER_BUDGET")
    if spt is not None and spt > SLOW_TURN_S:
        f.append("SLOW_TURN")
    return f


def _row(st, agent, run):
    # via=other: native delegate, or a run-agent spawn from before data/agent-runs.jsonl existed
    # resumed session: created->updated spans idle time, so use the run's own wall clock
    wall = run["wall_s"] if run.get("resume") and run.get("wall_s") is not None else st["wall_s"]
    epoch = run["start_epoch"] if run.get("resume") else st["created"].timestamp()
    spt = round(wall / st["turns"], 1) if st["turns"] and not run.get("resume") else None
    outcome = run.get("outcome") or ("ok" if st["turns"] else "?")
    # for a resumed session turns/tool_uses cover the whole session (no per-event timestamps),
    # so budget and s/turn flags are not computed for it
    tool_budget = None if run.get("resume") else st["tool_uses"]
    return {"ts": _fmt_epoch(epoch), "epoch": epoch, "agent": agent,
            "session": st["session"], "wall_s": wall, "e2e_s": run.get("wall_s"),
            "turns": st["turns"], "tool_uses": st["tool_uses"], "tools": st["tools"],
            "tool_out_kb": st["tool_out_kb"], "s_per_turn": spt, "outcome": outcome,
            "timeout_s": run.get("timeout_s"), "task": (run.get("task") or st["title"])[:80],
            "via": ("run-agent/resume" if run.get("resume") else "run-agent") if run else "other",
            "flags": _flags(agent, tool_budget, spt, outcome)}


def summarize(rows):
    by = collections.defaultdict(list)
    for r in rows:
        by[r["agent"]].append(r)
    out = {}
    for a, rs in sorted(by.items()):
        w = [r["wall_s"] for r in rs if r["wall_s"] is not None]
        t = [r["turns"] for r in rs if r["turns"]]
        s = [r["s_per_turn"] for r in rs if r["s_per_turn"]]
        tools = collections.Counter()
        for r in rs:
            tools.update(r["tools"])
        r1 = lambda v: None if v is None else round(v, 1)  # noqa: E731
        out[a] = {"runs": len(rs), "median_wall_s": r1(statistics.median(w)) if w else None,
                  "p90_wall_s": r1(sorted(w)[int(len(w) * .9)]) if w else None,
                  "median_turns": r1(statistics.median(t)) if t else None,
                  "median_s_per_turn": r1(statistics.median(s)) if s else None,
                  "timeouts": sum(1 for r in rs if r["outcome"] == "timeout"),
                  "flagged": sum(1 for r in rs if r["flags"]),
                  "top_tools": tools.most_common(5)}
    return out


def load_turns(days, agent_filter=None):
    """Per-turn records written by bin/agent-trace.py (stop hook): wall / tool / model seconds."""
    since = time.time() - days * 86400
    out, brakes = [], collections.Counter()
    for fn in sorted(glob.glob(os.path.join(TRACE_DIR, "trace-*.jsonl"))):
        with open(fn, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(r, dict) or r.get("t", 0) < since:
                    continue
                if agent_filter and r.get("agent") != agent_filter:
                    continue
                if r.get("ev") == "turn":
                    out.append(r)
                elif r.get("ev") == "budget_over" and r.get("enforced"):
                    brakes[r.get("session")] += 1
    for r in out:
        r["braked"] = brakes.get(r.get("session"), 0)
    return out


def print_turns(turns):
    print("\nturns (from hooks): %d" % len(turns))
    by = collections.defaultdict(list)
    for t in turns:
        by[t["agent"]].append(t)
    print("%-15s %5s %7s %7s %7s %6s" % ("agent", "turns", "med_s", "tool%", "model%", "brakes"))
    for a, ts in sorted(by.items()):
        w = sum(t["wall_s"] for t in ts) or 1
        print("%-15s %5d %7.1f %6.0f%% %6.0f%% %6d" % (a, len(ts), statistics.median(t["wall_s"] for t in ts),
              100 * sum(t["tool_s"] for t in ts) / w, 100 * sum(t["model_s"] for t in ts) / w,
              sum(1 for t in ts if t["braked"])))
    slow = sorted(turns, key=lambda t: -t["wall_s"])[:8]
    if slow:
        print("\nslowest turns:")
    for t in slow:
        top = "; ".join("%s %ss" % (lab[:40], sec) for sec, lab in t.get("top", [])[:2])
        print("  %s %-14s wall %6.1fs  tool %6.1fs  model %6.1fs  calls %3d  %s" % (
            datetime.datetime.fromtimestamp(t["t"], TZ).strftime("%m-%d %H:%M"), t["agent"], t["wall_s"],
            t["tool_s"], t["model_s"], t["tools"], top))


def fmt(v, w=5):
    return ("%*s" % (w, "-")) if v is None else ("%*s" % (w, v))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--agent")
    ap.add_argument("--runs", action="store_true", help="print per-run table")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--write-weekly", action="store_true")
    ap.add_argument("--turns", action="store_true", help="per-turn model vs tool time from the trace hooks")
    a = ap.parse_args()
    rows = collect(a.days, a.agent)
    summ = summarize(rows)
    turns = load_turns(a.days, a.agent)
    doc = {"generated": datetime.datetime.now(TZ).isoformat(timespec="seconds"), "days": a.days,
           "summary": summ, "runs": rows, "turns": turns}
    if a.write_weekly:
        os.makedirs(OUT_DIR, exist_ok=True)
        y, w, _ = datetime.date.today().isocalendar()
        p = os.path.join(OUT_DIR, "%d-W%02d.json" % (y, w))
        with open(p, "w") as f:
            json.dump(doc, f, indent=1, ensure_ascii=False)
        print("wrote %s" % p, file=sys.stderr)
    if a.json:
        print(json.dumps(doc, ensure_ascii=False))
        return
    print("sub-agent runs, last %d days: %d" % (a.days, len(rows)))
    print("%-15s %4s %7s %7s %6s %7s %4s %5s" % ("agent", "runs", "med_s", "p90_s", "turns", "s/turn", "T/O", "flag"))
    for ag, s in summ.items():
        print("%-15s %4d %7s %7s %6s %7s %4d %5d   %s" % (
            ag, s["runs"], fmt(s["median_wall_s"]), fmt(s["p90_wall_s"]), fmt(s["median_turns"]),
            fmt(s["median_s_per_turn"]), s["timeouts"], s["flagged"],
            ", ".join("%s×%d" % kv for kv in s["top_tools"])))
    if a.runs or a.agent:
        print("\n%-19s %-14s %6s %5s %5s %6s %7s %-8s %-9s %s" % (
            "start", "agent", "wall_s", "turns", "tools", "s/turn", "out_kb", "outcome", "via", "flags | task"))
        for r in rows:
            print("%-19s %-14s %6s %5s %5s %6s %7s %-8s %-9s %s | %s" % (
                r["ts"][:19].replace("T", " "), r["agent"], fmt(r["wall_s"], 6), fmt(r["turns"]),
                fmt(r["tool_uses"]), fmt(r["s_per_turn"], 6), fmt(r["tool_out_kb"], 7), r["outcome"],
                r["via"], ",".join(r["flags"]) or "-", r["task"][:60]))

    if a.turns:
        print_turns(turns)

if __name__ == "__main__":
    sys.exit(main())
