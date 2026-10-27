#!/usr/bin/env python3
"""
cbp-audit.py — Actionable audit findings for the .codebuddy knowledge system.

Unlike cbp-doctor.py (pass/warn/fail health checks), this produces
specific findings with IDs that can be ignored or acted upon.

Usage:
    python3 bin/cbp-audit.py                    # Run audit, show findings
    python3 bin/cbp-audit.py --json             # JSON output
    python3 bin/cbp-audit.py --ignore F001 --note "intentionally large"
    python3 bin/cbp-audit.py --show-ignored     # List ignored findings
    python3 bin/cbp-audit.py --min-interval 7   # Skip if ran <7 days ago

Findings are persisted in .codebuddy/.audit-findings.jsonl.
Ignored findings are in .codebuddy/.audit-ignored.jsonl.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import os
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from cbp_paths import P, ROOT, CLI_HOME, setting, local_list, tz  # noqa: E402
PURE = ROOT
FINDINGS_LOG = P["CBP_DATA"] / ".audit-findings.jsonl"
IGNORED_LOG = P["CBP_DATA"] / ".audit-ignored.jsonl"
AUDIT_RUN_LOG = P["CBP_DATA"] / ".audit-runs.jsonl"
TIPS = P["CBP_TIPS"]
RULES = P["CBP_RULES"]
HISTORY = P["CBP_HISTORY"]
P["CBP_DATA"].mkdir(parents=True, exist_ok=True)


def utc_now() -> str:
    return dt.datetime.now(tz()).replace(microsecond=0).isoformat()


def finding_id(category: str, path: str) -> str:
    """Generate a stable short ID for a finding."""
    raw = f"{category}:{path}"
    return "F" + hashlib.sha1(raw.encode()).hexdigest()[:7]


def load_ignored() -> dict[str, dict]:
    """Load ignored finding IDs → {id: {note, time}}."""
    ignored = {}
    if IGNORED_LOG.exists():
        for line in IGNORED_LOG.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                item = json.loads(line)
                ignored[item["id"]] = item
            except (json.JSONDecodeError, KeyError):
                continue
    return ignored


def run_audit() -> list[dict[str, Any]]:
    """Run all audit checks, return findings."""
    findings = []
    today = dt.date.today()

    # 1. Oversized tips (>5KB)
    if TIPS.exists():
        for md in TIPS.rglob("*.md"):
            if md.name == "INDEX.md":
                continue
            size = md.stat().st_size
            if size > 5120:
                fid = finding_id("oversized_tip", str(md.relative_to(TIPS)))
                findings.append({
                    "id": fid,
                    "category": "oversized_tip",
                    "severity": "low",
                    "path": str(md.relative_to(TIPS)),
                    "message": f"Tip exceeds 5KB ({size // 1024}KB). Consider splitting.",
                    "detail": {"size_bytes": size},
                })

    # 2. Tips with stale verified_at (>90 days)
    if TIPS.exists():
        for md in TIPS.rglob("*.md"):
            if md.name == "INDEX.md":
                continue
            content = md.read_text(encoding="utf-8", errors="replace")
            match = re.search(r"verified_at:\s*(\d{4}-\d{2}-\d{2})", content)
            if match:
                verified = dt.date.fromisoformat(match.group(1))
                age = (today - verified).days
                if age > 90:
                    fid = finding_id("stale_tip", str(md.relative_to(TIPS)))
                    findings.append({
                        "id": fid,
                        "category": "stale_tip",
                        "severity": "low",
                        "path": str(md.relative_to(TIPS)),
                        "message": f"Tip not verified in {age} days. Review for accuracy.",
                        "detail": {"verified_at": match.group(1), "age_days": age},
                    })

    # 3. Duplicate/overlapping tips (same keywords)
    keyword_map: dict[str, list[str]] = {}
    if TIPS.exists():
        for md in TIPS.rglob("*.md"):
            if md.name == "INDEX.md":
                continue
            content = md.read_text(encoding="utf-8", errors="replace")
            keywords = re.findall(r"^\s+-\s+(\w+)", content[:500], re.MULTILINE)
            for kw in keywords:
                keyword_map.setdefault(kw, []).append(str(md.relative_to(TIPS)))
        # Find keywords shared by 3+ files (potential duplication)
        for kw, files in keyword_map.items():
            if len(files) >= 4 and kw not in {"tooling", "automation", "cli", "analysis"} | set(local_list("audit_ignore_keywords")):
                fid = finding_id("keyword_overlap", kw)
                findings.append({
                    "id": fid,
                    "category": "keyword_overlap",
                    "severity": "info",
                    "path": kw,
                    "message": f"Keyword '{kw}' shared by {len(files)} tips. Potential overlap.",
                    "detail": {"keyword": kw, "files": files[:5]},
                })

    # 4. Patterns without dates or confidence (incomplete metadata)
    patterns_file = RULES / "workflow-patterns.md"
    if patterns_file.exists():
        content = patterns_file.read_text(encoding="utf-8", errors="replace")
        patterns = re.split(r"(?=^### P)", content, flags=re.MULTILINE)
        for p in patterns:
            if not p.strip().startswith("### P"):
                continue
            name_match = re.match(r"### (P[^\n:]+)", p)
            name = name_match.group(1).strip() if name_match else "?"
            has_confidence = bool(re.search(r"Confidence", p))
            has_date = bool(re.search(r"2026-\d{2}-\d{2}", p))
            if not has_confidence or not has_date:
                fid = finding_id("incomplete_pattern", name)
                missing = []
                if not has_confidence:
                    missing.append("confidence")
                if not has_date:
                    missing.append("date")
                findings.append({
                    "id": fid,
                    "category": "incomplete_pattern",
                    "severity": "medium",
                    "path": name,
                    "message": f"Pattern {name} missing: {', '.join(missing)}. Cannot evaluate for evolution.",
                    "detail": {"pattern": name, "missing_fields": missing},
                })

    # 5. History gaps (weekdays without entry in last 30 days)
    if HISTORY.exists():
        gaps = []
        for i in range(1, 31):
            d = today - dt.timedelta(days=i)
            if d.weekday() >= 5:
                continue
            month_dir = HISTORY / d.strftime("%Y-%m")
            if not (month_dir / f"{d.isoformat()}.md").exists():
                gaps.append(d.isoformat())
        if len(gaps) > 3:
            fid = finding_id("history_gaps", str(len(gaps)))
            findings.append({
                "id": fid,
                "category": "history_gaps",
                "severity": "low",
                "path": "history/",
                "message": f"{len(gaps)} workday gaps in last 30 days.",
                "detail": {"gaps": gaps[:10]},
            })

    # 6. Open-loop: pending items older than 14 days
    pending_dir = PURE / "pending"
    if pending_dir.exists():
        now_ts = dt.datetime.now().timestamp()
        for f in pending_dir.glob("*.md"):
            age_days = (now_ts - f.stat().st_mtime) / 86400
            if age_days > 14:
                fid = finding_id("stale_pending", f.name)
                findings.append({
                    "id": fid,
                    "category": "stale_pending",
                    "severity": "medium",
                    "path": f.name,
                    "message": f"Pending item '{f.name}' is {int(age_days)} days old. Close or act.",
                    "detail": {"age_days": int(age_days)},
                })

    return findings


def ignore_finding(finding_id: str, note: str) -> bool:
    """Mark a finding as ignored."""
    entry = {"id": finding_id, "note": note, "time": utc_now()}
    with IGNORED_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Pure audit: actionable findings.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--ignore", metavar="ID", help="Ignore a finding by ID")
    parser.add_argument("--note", default="", help="Note for --ignore")
    parser.add_argument("--show-ignored", action="store_true")
    parser.add_argument("--min-interval", type=int, default=0, help="Skip if last audit was <N days ago")
    args = parser.parse_args()

    # Handle --ignore
    if args.ignore:
        ignore_finding(args.ignore, args.note)
        print(f"✓ Ignored {args.ignore}" + (f": {args.note}" if args.note else ""))
        return 0

    # Handle --show-ignored
    if args.show_ignored:
        ignored = load_ignored()
        if not ignored:
            print("No ignored findings.")
        else:
            for fid, info in ignored.items():
                print(f"  {fid}: {info.get('note', '')} ({info.get('time', '')})")
        return 0

    # Check min interval
    if args.min_interval and AUDIT_RUN_LOG.exists():
        for line in reversed(AUDIT_RUN_LOG.read_text(encoding="utf-8", errors="replace").splitlines()):
            try:
                last_run = json.loads(line)
                last_time = dt.datetime.fromisoformat(last_run["time"].replace("Z", "+00:00"))
                age_days = (dt.datetime.now(dt.timezone.utc) - last_time).days
                if age_days < args.min_interval:
                    if args.json:
                        print(json.dumps({"status": "skipped", "reason": f"Last audit {age_days}d ago < {args.min_interval}d interval"}))
                    else:
                        print(f"⏭ Skipped: last audit was {age_days} days ago (interval: {args.min_interval}d)")
                    return 0
            except (json.JSONDecodeError, KeyError, ValueError):
                break

    # Run audit
    all_findings = run_audit()
    ignored = load_ignored()

    # Filter out ignored
    active_findings = [f for f in all_findings if f["id"] not in ignored]
    ignored_count = len(all_findings) - len(active_findings)

    # Record run
    run_record = {
        "time": utc_now(),
        "total_findings": len(all_findings),
        "active_findings": len(active_findings),
        "ignored": ignored_count,
        "status": "ran",
        "ok": len([f for f in active_findings if f["severity"] in ("high", "medium")]) == 0,
    }
    with AUDIT_RUN_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(run_record, ensure_ascii=False) + "\n")

    # Save findings
    with FINDINGS_LOG.open("w", encoding="utf-8") as f:
        for finding in active_findings:
            f.write(json.dumps(finding, ensure_ascii=False) + "\n")

    # Output
    if args.json:
        print(json.dumps({"findings": active_findings, "ignored_count": ignored_count, "run": run_record}, ensure_ascii=False, indent=2))
    else:
        severity_icon = {"high": "🔴", "medium": "🟡", "low": "🟠", "info": "ℹ️"}
        print(f"cbp-audit: {len(active_findings)} findings ({ignored_count} ignored)\n")
        if not active_findings:
            print("  ✅ No actionable findings.")
        else:
            for f in sorted(active_findings, key=lambda x: {"high": 0, "medium": 1, "low": 2, "info": 3}[x["severity"]]):
                icon = severity_icon.get(f["severity"], "?")
                print(f"  {icon} [{f['id']}] {f['category']}: {f['message']}")
            print(f"\n  To ignore: python3 bin/cbp-audit.py --ignore <ID> --note \"reason\"")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
