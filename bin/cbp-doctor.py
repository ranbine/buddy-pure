#!/usr/bin/env python3
"""
cbp-doctor.py — Health check for the .codebuddy knowledge system.

Usage:
    python3 bin/cbp-doctor.py          # Human-readable output
    python3 bin/cbp-doctor.py --json   # JSON output

Checks:
    - workflow.md + preferences.md line count (≤300)
    - workflow-patterns.md pattern count (≤50)
    - tips/ file sizes (≤5KB each)
    - tips/INDEX.md reference completeness
    - script-output-index.md vs actual scripts
    - history/ recent coverage (no gaps)
    - Git dirty/push status
    - Pending queue staleness
    - Session archive candidates
    - Auth token age (optional, CBP_AUTH_RECORD)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from cbp_paths import P, ROOT, CLI_HOME, setting, local_list, tz  # noqa: E402
CBP_LAB = ROOT
CBP_CLI = CLI_HOME
PURE = CBP_LAB
CONTEXTS = P["CBP_CONTEXTS"]
TIPS = P["CBP_TIPS"]
RULES = P["CBP_RULES"]
HISTORY = P["CBP_HISTORY"]
PENDING = P["CBP_PENDING"]
SESSIONS = CBP_CLI / "sessions" / "cli"
BIN = P["CBP_BIN"]

MAX_WORKFLOW_LINES = 300
MAX_PATTERNS = 50
MAX_TIP_BYTES = 5120  # 5KB
STALE_PENDING_DAYS = 7
STALE_SESSION_DAYS = 15
AUTH_WARN_DAYS = int(setting("CBP_AUTH_WARN_DAYS", "77"))
AUTH_EXPIRE_DAYS = int(setting("CBP_AUTH_EXPIRE_DAYS", "84"))


def utc_now() -> dt.datetime:
    return dt.datetime.now(tz())


def add(checks: list[dict], name: str, status: str, message: str, detail: dict | None = None):
    checks.append({"name": name, "status": status, "message": message, "detail": detail or {}})


def line_count(path: Path) -> int:
    if not path.exists():
        return 0
    return len(path.read_text(encoding="utf-8", errors="replace").splitlines())


def file_size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0


def run_git(args: list[str], cwd: str | None = None) -> str:
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True, text=True, timeout=15,
            cwd=cwd or str(PURE)
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return ""


def collect_checks() -> list[dict[str, Any]]:
    checks: list[dict] = []

    # 1. Workflow + Preferences line count
    wf_lines = line_count(RULES / "workflow.md")
    pref_lines = line_count(RULES / "preferences.md")
    total = wf_lines + pref_lines
    status = "pass" if total <= MAX_WORKFLOW_LINES else "fail"
    add(checks, "workflow_line_count", status,
        f"workflow.md ({wf_lines}) + preferences.md ({pref_lines}) = {total} lines (limit: {MAX_WORKFLOW_LINES}).",
        {"workflow": wf_lines, "preferences": pref_lines, "total": total, "limit": MAX_WORKFLOW_LINES})

    # 2. Patterns count
    patterns_file = RULES / "workflow-patterns.md"
    if patterns_file.exists():
        content = patterns_file.read_text(encoding="utf-8", errors="replace")
        pattern_count = len(re.findall(r"^###\s+P", content, re.MULTILINE))
        status = "pass" if pattern_count <= MAX_PATTERNS else "warn"
        add(checks, "patterns_count", status,
            f"{pattern_count} patterns (limit: {MAX_PATTERNS}).",
            {"count": pattern_count, "limit": MAX_PATTERNS})
    else:
        add(checks, "patterns_count", "warn", "workflow-patterns.md not found.")

    # 3. Tips file sizes (reference files exempt from 5KB limit)
    REFERENCE_FILES = {"ai-patterns-38.md", "writing-scenes.md",
                       "writing-protected-list.md", "humanize-goals.md",
                       "script-output-index.md"} | set(local_list("reference_tips"))
    oversized = []
    if TIPS.exists():
        for md in TIPS.rglob("*.md"):
            if md.name in REFERENCE_FILES:
                continue
            size = file_size(md)
            if size > MAX_TIP_BYTES:
                oversized.append({"path": str(md.relative_to(TIPS)), "size_kb": round(size / 1024, 1)})
    status = "pass" if not oversized else "warn"
    add(checks, "tips_file_sizes", status,
        f"{len(oversized)} tips exceed {MAX_TIP_BYTES // 1024}KB." if oversized else "All tips within size limit.",
        {"oversized": oversized, "limit_kb": MAX_TIP_BYTES // 1024})

    # 4. Tips INDEX.md completeness
    index_file = TIPS / "INDEX.md"
    if index_file.exists():
        index_content = index_file.read_text(encoding="utf-8", errors="replace")
        referenced = set(re.findall(r"`([^`]+\.md)`", index_content))
        actual_tips = {str(md.relative_to(TIPS)) for md in TIPS.rglob("*.md") if md.name != "INDEX.md"}
        unlisted = sorted(actual_tips - referenced)
        broken = sorted(referenced - actual_tips)
        status = "pass" if not unlisted and not broken else "warn"
        add(checks, "tips_index_parity", status,
            f"INDEX.md: {len(referenced)} refs, {len(actual_tips)} files. Unlisted: {len(unlisted)}, Broken: {len(broken)}.",
            {"unlisted": unlisted[:10], "broken": broken[:10]})
    else:
        add(checks, "tips_index_parity", "warn", "tips/INDEX.md not found.")

    # 5. History coverage (last 7 workdays)
    today = dt.date.today()
    missing_days = []
    for i in range(1, 8):
        d = today - dt.timedelta(days=i)
        if d.weekday() >= 5:  # skip weekends
            continue
        history_file = HISTORY / d.strftime("%Y-%m") / f"{d.isoformat()}.md"
        if not history_file.exists():
            missing_days.append(d.isoformat())
    status = "pass" if not missing_days else "warn"
    add(checks, "history_coverage", status,
        f"{len(missing_days)} workday(s) missing history in last 7 days." if missing_days else "History complete for last 7 workdays.",
        {"missing": missing_days})

    # 6. Git status
    dirty = run_git(["status", "--porcelain"])
    dirty_count = len([l for l in dirty.splitlines() if l.strip()])
    status = "pass" if dirty_count == 0 else "warn"
    add(checks, "git_dirty", status,
        f"{dirty_count} uncommitted changes." if dirty_count else "Working tree clean.",
        {"dirty_count": dirty_count})

    # 7. Git unpushed
    unpushed = run_git(["rev-list", "--count", "@{upstream}..HEAD"])
    try:
        unpushed_count = int(unpushed)
    except (ValueError, TypeError):
        unpushed_count = -1
    if unpushed_count < 0:
        add(checks, "git_unpushed", "warn", "Could not determine unpushed commits.")
    else:
        status = "pass" if unpushed_count <= 5 else "warn"
        add(checks, "git_unpushed", status,
            f"{unpushed_count} unpushed commits.",
            {"count": unpushed_count})

    # 8. Pending queue staleness
    stale_pending = []
    if PENDING.exists():
        now = dt.datetime.now()
        for f in PENDING.iterdir():
            if f.is_file() and f.suffix == ".md":
                age_days = (now - dt.datetime.fromtimestamp(f.stat().st_mtime)).days
                if age_days >= STALE_PENDING_DAYS:
                    stale_pending.append({"file": f.name, "age_days": age_days})
    pending_total = len(list(PENDING.glob("*.md"))) if PENDING.exists() else 0
    status = "pass" if not stale_pending else "warn"
    add(checks, "pending_staleness", status,
        f"{pending_total} pending items, {len(stale_pending)} stale (>{STALE_PENDING_DAYS}d).",
        {"total": pending_total, "stale": stale_pending})

    # 9. Session archive candidates
    archive_candidates = 0
    if SESSIONS.exists():
        now_ts = dt.datetime.now().timestamp()
        for f in SESSIONS.glob("*.json"):
            age_days = (now_ts - f.stat().st_mtime) / 86400
            if age_days >= STALE_SESSION_DAYS:
                archive_candidates += 1
    status = "pass" if archive_candidates == 0 else "warn"
    add(checks, "session_archive", status,
        f"{archive_candidates} session files older than {STALE_SESSION_DAYS} days.",
        {"candidates": archive_candidates})

    # 10. Auth token age (optional): file whose mtime = last login
    auth_rec = setting("CBP_AUTH_RECORD")
    auth_file = Path(os.path.expanduser(auth_rec)) if auth_rec else None
    if auth_file is None:
        add(checks, "auth_token", "pass", "Auth token check disabled (CBP_AUTH_RECORD unset).")
    elif auth_file.exists():
        age_days = (dt.datetime.now().timestamp() - auth_file.stat().st_mtime) / 86400
        if age_days >= AUTH_EXPIRE_DAYS:
            status, msg = "fail", f"Auth token expired ({int(age_days)} days old)."
        elif age_days >= AUTH_WARN_DAYS:
            status, msg = "warn", f"Auth token expiring soon ({int(age_days)} days old, expires at {AUTH_EXPIRE_DAYS})."
        else:
            status, msg = "pass", f"Auth token OK ({int(age_days)} days old)."
        add(checks, "auth_token", status, msg, {"age_days": int(age_days)})
    else:
        add(checks, "auth_token", "warn", f"Auth record not found: {auth_file.name}")

    # 11. Rules files registered in analysis-checklist
    checklist_file = RULES / "analysis-checklist.md"
    if checklist_file.exists():
        checklist_content = checklist_file.read_text(encoding="utf-8", errors="replace")
        tip_files = {str(md.relative_to(CONTEXTS)) for md in TIPS.rglob("*.md") if md.name != "INDEX.md"}
        # Count tips referenced in checklist
        referenced_tips = set(re.findall(r"tips/[^\s|`]+\.md", checklist_content))
        unbound = sorted(tip_files - referenced_tips - {"tips/INDEX.md"})
        # Only warn if many are unbound (some tips are standalone)
        status = "pass" if len(unbound) <= 10 else "warn"
        add(checks, "tips_binding", status,
            f"{len(referenced_tips)} tips bound in analysis-checklist, {len(unbound)} unbound.",
            {"bound": len(referenced_tips), "unbound_count": len(unbound), "sample": unbound[:5]})

    # 12. Dream freshness
    dream_file = PURE / ".dream-last"
    if dream_file.exists():
        age_days = (dt.datetime.now().timestamp() - dream_file.stat().st_mtime) / 86400
        status = "pass" if age_days < 10 else "warn"
        add(checks, "dream_freshness", status,
            f"Last memory dream {int(age_days)} days ago.",
            {"age_days": int(age_days)})
    else:
        add(checks, "dream_freshness", "warn", "No dream record found.")

    # 13. Decision revisit + outcome check
    decisions_dir = PURE / "decisions"
    if decisions_dir.exists():
        overdue_decisions = []
        overdue_outcomes = []
        today = dt.date.today()
        for df in sorted(decisions_dir.glob("2026-*.md")):
            content = df.read_text(encoding="utf-8", errors="replace")
            date_match = re.match(r"(\d{4}-\d{2}-\d{2})", df.name)
            if not date_match:
                continue
            decision_date = dt.date.fromisoformat(date_match.group(1))
            age_days = (today - decision_date).days

            # Check revisit conditions
            revisit_match = re.search(
                r"##\s+Revisit\s+(?:If|When|Condition)s?\s*\n(.*?)(?=\n##|\Z)",
                content, re.DOTALL
            )
            if revisit_match:
                revisit_text = revisit_match.group(1).strip()
                conditions = [l.strip("- ").strip() for l in revisit_text.splitlines() if l.strip().startswith("-")]
                if age_days >= 60 and conditions:
                    overdue_decisions.append({
                        "file": df.name, "age_days": age_days, "conditions": conditions[:3],
                    })

            # Check Outcome section
            outcome_match = re.search(r"##\s+Outcome\s*\n(.*?)(?=\n##|\Z)", content, re.DOTALL)
            if outcome_match:
                outcome_text = outcome_match.group(1)
                review_date_match = re.search(r"复盘日期[:：]\s*(\d{4}-\d{2}-\d{2})", outcome_text)
                result_match = re.search(r"实际结果[:：]\s*(.+)", outcome_text)
                if review_date_match:
                    review_date = dt.date.fromisoformat(review_date_match.group(1))
                    result_value = result_match.group(1).strip() if result_match else ""
                    is_pending = not result_value or result_value in ("待复盘", "TBD", "PENDING")
                    if is_pending and review_date <= today:
                        overdue_outcomes.append({
                            "file": df.name, "review_date": review_date.isoformat(),
                            "days_overdue": (today - review_date).days,
                        })
            elif age_days >= 60:
                overdue_outcomes.append({"file": df.name, "review_date": "missing", "days_overdue": age_days - 60})

        status = "pass" if not overdue_decisions else "warn"
        add(checks, "decision_revisit", status,
            f"{len(overdue_decisions)} decisions due for revisit (>60 days)." if overdue_decisions else "All decisions within review window.",
            {"overdue": overdue_decisions})

        status = "pass" if not overdue_outcomes else "warn"
        add(checks, "decision_outcomes", status,
            f"{len(overdue_outcomes)} decisions need outcome review." if overdue_outcomes else "All decision outcomes up to date.",
            {"overdue": overdue_outcomes})

    # 14. Shared core drift vs a peer install (optional: CBP_SHARED_PEER in config/local.env)
    peer = setting("CBP_SHARED_PEER")
    manifest = ROOT / "shared-files.txt"
    if peer and manifest.exists():
        peer_root = Path(os.path.expanduser(peer))
        files = [l.strip() for l in manifest.read_text(encoding="utf-8").splitlines()
                 if l.strip() and not l.lstrip().startswith("#")]
        diff = [f for f in files if not (peer_root / f).is_file() or not (ROOT / f).is_file()
                or (peer_root / f).read_bytes() != (ROOT / f).read_bytes()]
        if not files:
            add(checks, "shared_drift", "warn", "shared-files.txt has no entries.")
        elif diff:
            add(checks, "shared_drift", "warn",
                f"{len(diff)} shared file(s) differ from {peer_root}: {', '.join(diff[:5])}"
                f"{' …' if len(diff) > 5 else ''} → bin/sync-shared.sh status {peer}", {"files": diff})
        else:
            add(checks, "shared_drift", "pass", f"Shared core identical with peer ({len(files)} files).")

    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="Pure knowledge system health check.")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    checks = collect_checks()
    statuses = {item["status"] for item in checks}
    overall = "error" if "fail" in statuses else ("warning" if "warn" in statuses else "ok")

    summary = {s: sum(1 for c in checks if c["status"] == s) for s in ("pass", "warn", "fail")}

    payload = {
        "time": utc_now().isoformat(),
        "status": overall,
        "summary": summary,
        "checks": checks,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"cbp-doctor: {overall} (pass={summary['pass']} warn={summary['warn']} fail={summary['fail']})")
        print()
        for item in checks:
            icon = {"pass": "✅", "warn": "⚠️", "fail": "❌"}.get(item["status"], "?")
            print(f"  {icon} {item['name']}: {item['message']}")

    return 2 if overall == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
