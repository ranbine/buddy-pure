#!/usr/bin/env python3
"""
cbp-closeout.py — Session closeout automation.

Runs at the end of a work session to:
1. Check for uncommitted .codebuddy/ changes
2. Categorize changes (tips, rules, history, docs, bin, etc.)
3. Generate commit message
4. Commit (with --dry-run option)
5. Update docs/index.html What's New if applicable
6. Report summary

Usage:
    python3 bin/cbp-closeout.py              # Dry run (show what would happen)
    python3 bin/cbp-closeout.py --execute    # Actually commit
    python3 bin/cbp-closeout.py --json       # JSON output
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from cbp_paths import P, ROOT, CLI_HOME, setting, local_list, local_dict, tz  # noqa: E402
PURE = ROOT
OBSERVATIONS_LOG = P["CBP_DATA"] / ".observations.jsonl"

# Report timezone: CBP_TZ, else machine local
BJT = tz()
CATEGORIES = {
    "contexts/tips": "tips",
    ".codebuddy/rules": "rules",
    ".codebuddy/rules/workflow.md": "workflow",
    ".codebuddy/rules/preferences.md": "preferences",
    "contexts/learning-path.md": "learning",
    "history/": "history",
    "docs/reports/daily": "daily-report",
    "docs/reports/analysis": "analysis",
    "docs/index.html": "index",
    "docs/tools": "tools",
    "bin/": "scripts",
    "decisions/": "decisions",
    "pending/": "pending",
    "sessions/": "sessions",
    "knowledge/": "knowledge",
    "templates/": "templates",
    "agents/": "agents",
}
CATEGORIES.update(local_dict("closeout_categories"))   # config/local.json

# Files to always exclude from commit
EXCLUDE_PATTERNS = [
    "sessions/cli/",  # Active session files
    ".dream-last",
    "config/local.env",
]
EXCLUDE_PATTERNS += local_list("closeout_exclude")


def run_git(args: list[str]) -> tuple[int, str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(PURE)] + args,
            capture_output=True, text=True, timeout=30
        )
        return result.returncode, result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return 1, ""


def file_sha256(path: Path) -> str:
    """Compute SHA-256 of a file."""
    if not path.exists():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def record_observations(committed_files: list[str], commit_msg: str) -> int:
    """Record sha256 of each committed file to .observations.jsonl.
    
    This proves that a specific version of a file was processed during closeout.
    Memory Dream can skip files whose hash matches a recorded observation.
    """
    now = dt.datetime.now(BJT).isoformat()
    observations = []
    for rel_path in committed_files:
        full_path = PURE / rel_path
        if not full_path.exists():
            continue  # deleted file
        sha = file_sha256(full_path)
        observations.append({
            "time": now,
            "path": rel_path,
            "sha256": sha,
            "event": "closeout",
            "commit_message": commit_msg,
        })
    
    if observations:
        with OBSERVATIONS_LOG.open("a", encoding="utf-8") as f:
            for obs in observations:
                f.write(json.dumps(obs, ensure_ascii=False) + "\n")
    
    return len(observations)


def get_dirty_files() -> list[dict[str, str]]:
    """Get uncommitted changes in .codebuddy/ repo."""
    rc, output = run_git(["status", "--porcelain=v1"])
    if rc != 0:
        return []

    files = []
    for line in output.splitlines():
        if not line.strip():
            continue
        status = line[:2].strip()
        path = line[3:].strip()
        # Handle renamed files
        if " -> " in path:
            path = path.split(" -> ")[1]
        files.append({"status": status, "path": path})
    return files


def categorize_file(path: str) -> str:
    """Determine category of a file based on its path."""
    for prefix, category in sorted(CATEGORIES.items(), key=lambda kv: -len(kv[0])):   # longest prefix wins
        if path.startswith(prefix) or f"/{prefix}" in path:
            return category
    return "other"


def should_exclude(path: str) -> bool:
    """Check if file should be excluded from commit."""
    return any(pattern in path for pattern in EXCLUDE_PATTERNS)


def generate_commit_message(categories: dict[str, list[str]], today: str) -> str:
    """Generate a descriptive commit message."""
    parts = []
    for cat, files in sorted(categories.items()):
        if cat == "sessions":
            continue  # Don't mention session files
        count = len(files)
        if count == 1:
            parts.append(f"{cat}: {Path(files[0]).name}")
        else:
            parts.append(f"{cat}: {count} files")

    if not parts:
        return f"closeout {today}"

    subject = f"closeout {today}: " + ", ".join(parts[:3])
    if len(subject) > 72:
        subject = f"closeout {today}: {len(parts)} categories updated"

    return subject



def is_observed(rel_path: str) -> bool:
    """Check if the current version of a file has been observed (processed by closeout).
    
    Used by Memory Dream to skip already-processed files.
    """
    full_path = PURE / rel_path
    if not full_path.exists() or not OBSERVATIONS_LOG.exists():
        return False
    current_sha = file_sha256(full_path)
    if not current_sha:
        return False
    # Search backwards for efficiency (latest first)
    for line in reversed(OBSERVATIONS_LOG.read_text(encoding="utf-8", errors="replace").splitlines()):
        try:
            obs = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obs.get("path") == rel_path and obs.get("sha256") == current_sha:
            return True
    return False


def closeout(execute: bool = False) -> dict[str, Any]:
    """Main closeout logic."""
    today = dt.date.today().isoformat()
    now = dt.datetime.now(BJT).isoformat()

    # Get dirty files
    dirty = get_dirty_files()
    if not dirty:
        return {
            "time": now,
            "status": "noop",
            "message": "Working tree clean, nothing to close out.",
            "files": [],
        }

    # Categorize and filter
    categories: dict[str, list[str]] = defaultdict(list)
    committable = []
    excluded = []

    for item in dirty:
        path = item["path"]
        if should_exclude(path):
            excluded.append(path)
            continue
        cat = categorize_file(path)
        categories[cat].append(path)
        committable.append(item)

    if not committable:
        return {
            "time": now,
            "status": "noop",
            "message": f"All {len(excluded)} dirty files are excluded from commit.",
            "excluded_count": len(excluded),
            "files": [],
        }

    # Generate commit message
    commit_msg = generate_commit_message(dict(categories), today)

    # Summary
    summary = {
        "time": now,
        "status": "dry_run" if not execute else "committed",
        "commit_message": commit_msg,
        "total_files": len(committable),
        "excluded_files": len(excluded),
        "categories": {cat: len(files) for cat, files in sorted(categories.items())},
        "files": [f["path"] for f in committable],
    }

    if execute:
        # Stage all committable files
        paths_to_add = [f["path"] for f in committable if f["status"] != "D"]
        paths_to_rm = [f["path"] for f in committable if f["status"] == "D"]

        if paths_to_add:
            run_git(["add", "--"] + paths_to_add)
        if paths_to_rm:
            run_git(["rm", "--cached", "--"] + paths_to_rm)

        # Commit
        rc, output = run_git(["commit", "-m", commit_msg])
        summary["git_output"] = output
        summary["git_rc"] = rc
        if rc != 0:
            summary["status"] = "error"
            summary["error"] = output
        else:
            # Record file observations (proves this version was processed)
            obs_count = record_observations([f["path"] for f in committable], commit_msg)
            summary["observations_recorded"] = obs_count

            # Audit piggyback: run audit if >7 days since last run
            audit_due = True
            audit_run_log = PURE / ".audit-runs.jsonl"
            if audit_run_log.exists():
                import datetime
                for line in reversed(audit_run_log.read_text(encoding="utf-8", errors="replace").splitlines()):
                    try:
                        last = json.loads(line)
                        last_time = dt.datetime.fromisoformat(last["time"].replace("Z", "+00:00"))
                        if (dt.datetime.now(dt.timezone.utc) - last_time).days < 7:
                            audit_due = False
                        break
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue
            if audit_due:
                import subprocess as sp
                audit_result = sp.run(
                    [sys.executable, str(PURE / "bin" / "cbp-audit.py"), "--min-interval", "7", "--json"],
                    capture_output=True, text=True, timeout=60
                )
                try:
                    audit_data = json.loads(audit_result.stdout)
                    summary["audit_piggyback"] = {
                        "ran": True,
                        "findings": audit_data.get("findings", [])[:5],
                        "total": len(audit_data.get("findings", [])),
                    }
                except (json.JSONDecodeError, TypeError):
                    summary["audit_piggyback"] = {"ran": True, "error": "parse_failed"}
            else:
                summary["audit_piggyback"] = {"ran": False, "reason": "recent"}

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Pure session closeout automation.")
    parser.add_argument("--execute", action="store_true", help="Actually commit (default is dry-run)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    result = closeout(execute=args.execute)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status_icon = {"noop": "✓", "dry_run": "🔍", "committed": "✅", "error": "❌"}.get(result["status"], "?")
        print(f"{status_icon} cbp-closeout: {result['status']}")
        print(f"  {result.get('message', result.get('commit_message', ''))}")

        if result.get("categories"):
            print()
            for cat, count in sorted(result["categories"].items()):
                print(f"  {cat}: {count} file(s)")

        if result["status"] == "dry_run":
            print(f"\n  Total: {result['total_files']} files to commit, {result['excluded_files']} excluded.")
            print(f"  Commit message: \"{result['commit_message']}\"")
            print(f"\n  Run with --execute to commit.")

    return 0 if result["status"] != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
