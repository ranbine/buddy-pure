#!/usr/bin/env python3
"""
push-queue.py — dual-queue manager for the pre-push gate (user-set 2026-09-30).

Two queues with DIFFERENT "next cycle" semantics — never mixed:

  time  (settings/push-deferred-time.json)
      Change already meets quality but the 2/hour rate window was full.
      "Next cycle" = the next time window. Eligible for AUTOMATIC retry once
      the rate window frees up (checked at each `启动`/`daily`).

  quality (settings/push-blocked-quality.json)
      Change failed a hard gate (README/index) OR is a small BATCH item still
      accumulating. "Next cycle" = when the quality requirement is met. NEVER
      auto-pushed — must re-pass the gate first.

Each entry:
  {
    "id": "<epoch>-<shortsha|batch>",
    "queued_at": <epoch>,
    "reason": "DEFER-TIME" | "BLOCK" | "BATCH",
    "subject": "<commit subject>",
    "files": ["docs/...", ...],
    "issues": ["..."],          # quality queue only
    "commits": ["<sha>", ...]   # optional: local commits waiting to push
  }

Usage:
  push-queue.py list [--json]
  push-queue.py add   --queue time|quality --reason R --subject S [--files a,b] [--issues x,y] [--commits sha1,sha2]
  push-queue.py ready [--json]      # time-queue items eligible now (rate window free)
  push-queue.py pop   --queue Q --id ID   # remove an entry (after push / after fix)
  push-queue.py clear --queue Q            # empty a queue (careful)

Exit: 0 ok, 2 usage error.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from cbp_paths import P, ROOT, CLI_HOME, setting  # noqa: E402
LAB = str(ROOT)
_SET = P["CBP_SETTINGS"]
QFILES = {
    "time": str(_SET / "push-deferred-time.json"),
    "quality": str(_SET / "push-blocked-quality.json"),
}
PUSH_LOG = str(_SET / "push-log.json")
RATE_LIMIT = 2


def _load(path):
    try:
        return json.load(open(path))
    except Exception:
        return []


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(data, open(path, "w"), ensure_ascii=False, indent=2)


def _rate_free():
    """True if fewer than RATE_LIMIT pushes happened in the last hour."""
    ts = _load(PUSH_LOG)
    now = time.time()
    return sum(1 for t in ts if now - t < 3600) < RATE_LIMIT


def cmd_list(args):
    out = {}
    for q, path in QFILES.items():
        out[q] = _load(path)
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    for q, items in out.items():
        print(f"══ {q} queue ({len(items)}) ══")
        for e in items:
            age = int((time.time() - e.get("queued_at", 0)) / 60)
            print(f"  [{e.get('reason')}] {e.get('subject','')[:50]}  "
                  f"({len(e.get('files',[]))} files, {age}min ago)")
            for it in e.get("issues", []):
                print(f"       - {it}")
    return 0


def cmd_add(args):
    if args.queue not in QFILES:
        print("error: --queue must be time|quality", file=sys.stderr)
        return 2
    path = QFILES[args.queue]
    items = _load(path)
    sha = (args.commits.split(",")[0][:7] if args.commits else "batch")
    entry = {
        "id": f"{int(time.time())}-{sha}",
        "queued_at": int(time.time()),
        "reason": args.reason,
        "subject": args.subject,
        "files": [x for x in args.files.split(",") if x] if args.files else [],
        "issues": [x for x in args.issues.split(",") if x] if args.issues else [],
        "commits": [x for x in args.commits.split(",") if x] if args.commits else [],
    }
    items.append(entry)
    _save(path, items)
    print(f"queued to {args.queue}: {entry['id']}")
    return 0


def cmd_ready(args):
    """Time-queue items eligible for automatic retry now."""
    items = _load(QFILES["time"])
    free = _rate_free()
    ready = items if free else []
    if args.json:
        print(json.dumps({"rate_free": free, "ready": ready},
                         ensure_ascii=False, indent=2))
        return 0
    if not free:
        print("rate window still full — no time-queue items eligible yet")
        return 0
    if not ready:
        print("time queue empty ✓")
        return 0
    print(f"{len(ready)} time-queue item(s) ready to push (rate window free):")
    for e in ready:
        print(f"  {e['id']}  {e['subject'][:50]}  ({len(e['files'])} files)")
    return 0


def cmd_pop(args):
    if args.queue not in QFILES:
        print("error: --queue must be time|quality", file=sys.stderr)
        return 2
    path = QFILES[args.queue]
    items = _load(path)
    before = len(items)
    items = [e for e in items if e.get("id") != args.id]
    _save(path, items)
    print(f"removed {before - len(items)} entry from {args.queue}")
    return 0


def cmd_clear(args):
    if args.queue not in QFILES:
        print("error: --queue must be time|quality", file=sys.stderr)
        return 2
    _save(QFILES[args.queue], [])
    print(f"cleared {args.queue} queue")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("ready"); p.add_argument("--json", action="store_true")

    p = sub.add_parser("add")
    p.add_argument("--queue", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--subject", default="")
    p.add_argument("--files", default="")
    p.add_argument("--issues", default="")
    p.add_argument("--commits", default="")

    p = sub.add_parser("pop")
    p.add_argument("--queue", required=True)
    p.add_argument("--id", required=True)

    p = sub.add_parser("clear")
    p.add_argument("--queue", required=True)

    args = ap.parse_args()
    return {"list": cmd_list, "add": cmd_add, "ready": cmd_ready,
            "pop": cmd_pop, "clear": cmd_clear}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
