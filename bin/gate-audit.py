#!/usr/bin/python3
"""gate-audit — weekly audit of action-gate decisions → policy *proposals* (never edits the policy).

  gate-audit.py [--days 7] [--min-count 5] [--min-sessions 2] [--out DIR] [--json]

Reads data/gate/decisions-*.jsonl and writes
  data/gate/proposals/YYYY-MM-DD.json   machine-readable proposals (input to `cbp-gate apply`)
  data/gate/proposals/YYYY-MM-DD.md     human report (stats, false-positive review, proposals)

Proposal kinds (only *additions* — the classifier checks DENY > L3 > L0 > L1, so an added L1 rule can
never lower anything that an L3/DENY rule matches; L3 is never downgraded):
  relax   : an L2 shell command key allowed >= min-count times in >= min-sessions sessions
            → add an L1 rule for that key, restricted to paths under write_roots
  tighten : L2 commands matching a known-risky pattern (remote writes, ssh, kill, ...) → add an L3 rule
Report-only sections (changes to existing rules stay manual): L3/DENY hits per rule with samples
(spot false positives during shadow), approvals, gate errors, latency.

Division of labour (see contexts/tips/tools/action-gate.md):
  this script = statistics; reviewer agent = per-proposal judgement; user = `cbp-gate apply` in a tty.
"""
import argparse
import collections
import datetime
import glob
import json
import os
import re
import sys

# Paths come from action-gate (config files only, environment ignored) so the CLI, the audit and
# the hook always agree on policy / data / approvals locations.
import importlib.util as _ilu  # noqa: E402
_spec = _ilu.spec_from_file_location("action_gate", os.path.join(os.path.dirname(os.path.realpath(__file__)), "action-gate.py"))
_AG = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_AG)
ROOT, CLI_HOME, P = _AG.ROOT, _AG.CLI_HOME, _AG.P
LAB = str(ROOT)
DATA = _AG.DATA
POLICY_PATH = _AG.POLICY_PATH
DATA_DIR = _AG.DATA_DIR
TZ = _AG.tz()

TWO_WORD = {"git", "kubectl", "oc", "helm", "docker", "podman", "python", "python3", "bash", "sh",
            "cbp-cli", "npm", "pip", "pip3", "systemctl"}
VALUE_OPTS = {"-n", "--namespace", "--context", "-C", "-c", "--kubeconfig", "-f", "-m"}
RISKY = [
    ("http-write", r"^(curl|wget)\b.*(\s-X\s*(POST|PUT|DELETE|PATCH)\b|\s--data(-\w+)?\b|\s-d\s|\s-F\s|--upload-file|\s-T\s)"),
    ("remote-copy", r"^(scp|sftp|ftp|lftp)\b|^rsync\b.*\s\S+:\S*"),
    ("ssh", r"^ssh\b"),
    ("container-write", r"^(docker|podman)\s+(run|rm|rmi|exec|kill|stop|system\s+prune|volume\s+rm)\b"),
    ("process-kill", r"^(kill|pkill|killall)\b"),
    ("service", r"^(systemctl|service)\s+(start|stop|restart|disable|enable)\b"),
    ("cron", r"^crontab\b"),
    ("pkg-install", r"^(pip3?|npm|yum|dnf|apt(-get)?)\s+(install|uninstall|remove)\b"),
]
RISKY_RE = [(n, re.compile(p)) for n, p in RISKY]


def load(days):
    cutoff = datetime.datetime.now(TZ) - datetime.timedelta(days=days)
    out = []
    for fn in sorted(glob.glob(os.path.join(DATA_DIR, "decisions-*.jsonl"))):
        with open(fn) as f:
            for line in f:
                try:
                    r = json.loads(line)
                    if datetime.datetime.fromisoformat(r["ts"]) >= cutoff:
                        out.append(r)
                except (ValueError, KeyError):
                    continue
    return out


def segment_text(r):
    t = r.get("trigger") or r.get("summary") or ""
    return t.replace("\\n", "\n").split("\n")[0].strip()


def cmd_key(text):
    words = [w for w in text.split() if not re.fullmatch(r"[A-Za-z_]\w*=.*", w)]
    if not words:
        return ""
    head = os.path.basename(words[0])
    if head in TWO_WORD:
        nxt, skip = "", False
        for w in words[1:]:
            if skip:
                skip = False
                continue
            if w in VALUE_OPTS:
                skip = True
                continue
            if not w.startswith("-"):
                nxt = w
                break
        if head.startswith("python") or head in ("bash", "sh"):
            nxt = os.path.basename(nxt)
        return ("%s %s" % (head, nxt)).strip()
    return head


def _gate():
    return _AG


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "x"


def existing_ids():
    try:
        return {r["id"] for r in _gate().load_policy(POLICY_PATH)["rules"]}
    except Exception:
        return set()


def current_classifier():
    """Return f(rec) -> current level, using the live policy (None if unavailable)."""
    try:
        ag = _gate()
        pol = ag.load_policy(POLICY_PATH)
    except Exception:
        return None

    def f(r):
        if r.get("tool") != "shell":
            return None
        cmd = (r.get("detail") or r.get("summary") or "").replace("\\n", "\n")
        if not cmd or cmd.endswith("…[truncated]"):
            return None
        try:
            return ag.classify("shell", {"command": cmd}, r.get("cwd") or LAB, pol)[0]
        except Exception:
            return None
    return f


def audit(recs, min_count, min_sessions, reclassify=None):
    ids = existing_ids()
    l2 = [r for r in recs if r.get("level") == "L2" and r.get("tool") == "shell"]
    by_key = collections.defaultdict(list)
    for r in l2:
        by_key[cmd_key(segment_text(r))].append(r)

    proposals = []
    tighten_seen = set()
    for key, rs in sorted(by_key.items(), key=lambda kv: -len(kv[1])):
        if not key:
            continue
        texts = [segment_text(r) for r in rs]
        risky = [(n, rx) for n, rx in RISKY_RE if any(rx.search(t) for t in texts)]
        sessions = {r.get("session") for r in rs}
        if risky:
            for n, rx in risky:
                if n in tighten_seen:
                    continue
                tighten_seen.add(n)
                rid = "l3-auto-%s" % n
                if rid in ids:
                    continue
                hits = [t for t in texts if rx.search(t)]
                proposals.append({
                    "id": "P%02d" % (len(proposals) + 1), "kind": "tighten", "action": "add_rule",
                    "evidence": {"key": key, "count": len(hits), "sessions": len(sessions), "samples": hits[:3]},
                    "rule": {"id": rid, "level": "L3", "tool": "shell", "cmd": dict(RISKY)[n],
                             "note": "gate-audit %s: %d L2 hits" % (datetime.date.today(), len(hits))}})
            continue
        if len(rs) < min_count or len(sessions) < min_sessions:
            continue
        if any(r.get("verdict") != "allow" for r in rs):
            continue
        rid = "l1-auto-%s" % slug(key)
        if rid in ids:
            continue
        proposals.append({
            "id": "P%02d" % (len(proposals) + 1), "kind": "relax", "action": "add_rule",
            "evidence": {"key": key, "count": len(rs), "sessions": len(sessions), "samples": texts[:3]},
            "rule": {"id": rid, "level": "L1", "tool": "shell", "cmd": "^%s(\\s|$)" % re.escape(key).replace("\\ ", "\\s+"),
                     "paths_under": "write_roots",
                     "note": "gate-audit %s: %d allows in %d sessions" % (datetime.date.today(), len(rs), len(sessions))}})

    hits = collections.defaultdict(list)
    for r in recs:
        if r.get("level") in ("L3", "DENY"):
            hits[(r["level"], r.get("rule"))].append(r)
    lat = sorted(r["latency_ms"] for r in recs if "latency_ms" in r)
    stats = {
        "decisions": len(recs),
        "by_level": dict(collections.Counter(r.get("level") for r in recs)),
        "l2_share_of_writes": round(len(l2) / max(1, sum(1 for r in recs if r.get("level") in ("L1", "L2", "L3", "DENY"))), 3),
        "errors": sum(1 for r in recs if r.get("verdict") == "error"),
        "approved": sum(1 for r in recs if r.get("verdict") == "approved"),
        "latency_p50": lat[len(lat) // 2] if lat else None,
        "latency_p95": lat[int(len(lat) * .95)] if lat else None,
        "l3_deny_by_rule": [
            {"level": lv, "rule": ru, "count": len(rs), "agents": sorted({r.get("agent", "") for r in rs}),
             "samples": list(dict.fromkeys(segment_text(r)[:120] for r in rs))[:3],
             "now_different": sum(1 for r in rs if reclassify and reclassify(r) not in (None, lv))}
            for (lv, ru), rs in sorted(hits.items(), key=lambda kv: -len(kv[1]))],
        "l2_top": [{"key": k, "count": len(v)} for k, v in sorted(by_key.items(), key=lambda kv: -len(kv[1]))[:15]],
    }
    return proposals, stats


def render_md(day, days, stats, proposals, mode):
    L = ["# Gate audit — %s (last %d days, policy mode: %s)" % (day, days, mode), ""]
    L.append("decisions %d | by level %s | L2 share of non-read %.0f%% | approved %d | errors %d | latency p50/p95 %s/%s ms"
             % (stats["decisions"], stats["by_level"], 100 * stats["l2_share_of_writes"], stats["approved"],
                stats["errors"], stats["latency_p50"], stats["latency_p95"]))
    L += ["", "## Proposals (apply with `cbp-gate apply %s` in your terminal)" % day, ""]
    if not proposals:
        L.append("none")
    for p in proposals:
        e = p["evidence"]
        L.append("- **%s %s** `%s` → %s `%s` (%d hits, %d sessions)" % (
            p["id"], p["kind"], e["key"], p["rule"]["level"], p["rule"]["id"], e["count"], e["sessions"]))
        L.append("  - rule: `%s`" % json.dumps(p["rule"], ensure_ascii=False))
        for s in e["samples"]:
            L.append("  - e.g. `%s`" % s[:160])
    L += ["", "## L3/DENY hits — check for false positives (edit rules manually if needed)", ""]
    for h in stats["l3_deny_by_rule"] or []:
        stale = " — %d no longer hit under current policy" % h["now_different"] if h.get("now_different") else ""
        L.append("- %s `%s` ×%d (%s)%s: %s" % (h["level"], h["rule"], h["count"], ", ".join(h["agents"]), stale,
                                              " | ".join("`%s`" % s for s in h["samples"])))
    if not stats["l3_deny_by_rule"]:
        L.append("none")
    L += ["", "## L2 top keys", ""] + ["- `%s` ×%d" % (x["key"], x["count"]) for x in stats["l2_top"]]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--min-count", type=int, default=5)
    ap.add_argument("--min-sessions", type=int, default=2)
    ap.add_argument("--out", default=os.path.join(DATA_DIR, "proposals"))
    ap.add_argument("--json", action="store_true", help="print the proposal JSON to stdout")
    a = ap.parse_args()
    recs = load(a.days)
    proposals, stats = audit(recs, a.min_count, a.min_sessions, current_classifier())
    try:
        mode = _gate().load_policy(POLICY_PATH).get("mode", "?")
    except Exception:
        mode = "?"
    day = datetime.datetime.now(TZ).strftime("%Y-%m-%d")
    doc = {"date": day, "days": a.days, "policy_mode": mode, "stats": stats, "proposals": proposals}
    os.makedirs(a.out, exist_ok=True)
    jp, mp = os.path.join(a.out, day + ".json"), os.path.join(a.out, day + ".md")
    with open(jp, "w") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
    with open(mp, "w") as f:
        f.write(render_md(day, a.days, stats, proposals, mode))
    if a.json:
        print(json.dumps(doc, ensure_ascii=False))
    else:
        print("%d decisions, %d proposals (%d relax, %d tighten) → %s" % (
            len(recs), len(proposals), sum(p["kind"] == "relax" for p in proposals),
            sum(p["kind"] == "tighten" for p in proposals), mp))


if __name__ == "__main__":
    sys.exit(main())
