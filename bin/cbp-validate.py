#!/usr/bin/env python3
"""
cbp-validate.py
================
Health check for the codebuddy-pure knowledge base.

Checks:
  1. Tips INDEX.md ↔ actual files consistency (orphans + missing)
  2. Analysis-checklist trigger table references exist
  3. Workflow.md rules/ references exist
  4. Discipline.md D-* numbering continuity
  5. Workflow-patterns P-* no duplicates
  6. Decisions format compliance
  7. History file naming format (YYYY-MM-DD.md)
  8. Tips files non-empty and have heading

Usage:
  python3 bin/cbp-validate.py            # normal run
  python3 bin/cbp-validate.py --strict    # warnings become errors
  python3 bin/cbp-validate.py --fix       # auto-fix what's possible (INDEX rebuild)
"""

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from cbp_paths import P, ROOT, CLI_HOME, setting  # noqa: E402
PURE = ROOT
CONTEXTS = P["CBP_CONTEXTS"]
TIPS_DIR = P["CBP_TIPS"]
RULES_DIR = P["CBP_RULES"]
DECISIONS_DIR = P["CBP_DECISIONS"]
HISTORY_DIR = P["CBP_HISTORY"]
INDEX_FILE = TIPS_DIR / "INDEX.md"
WORKFLOW_FILE = RULES_DIR / "workflow.md"
CHECKLIST_FILE = RULES_DIR / "analysis-checklist.md"
DISCIPLINE_FILE = RULES_DIR / "discipline.md"
PATTERNS_FILE = RULES_DIR / "workflow-patterns.md"


class Checker:
    def __init__(self, strict=False):
        self.errors = []
        self.warnings = []
        self.strict = strict

    def error(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        if self.strict:
            self.errors.append(f"[strict] {msg}")
        else:
            self.warnings.append(msg)

    def report(self):
        """Print results and return exit code."""
        total_checks = len(self.errors) + len(self.warnings)

        if self.warnings:
            print(f"\n⚠  WARNINGS ({len(self.warnings)}):")
            for w in self.warnings:
                print(f"   {w}")

        if self.errors:
            print(f"\n✗  ERRORS ({len(self.errors)}):")
            for e in self.errors:
                print(f"   {e}")

        if not self.errors and not self.warnings:
            print("\n✓  All checks passed.")
            return 0
        elif not self.errors:
            print(f"\n✓  Passed with {len(self.warnings)} warning(s).")
            return 0
        else:
            print(f"\n✗  {len(self.errors)} error(s), {len(self.warnings)} warning(s).")
            return 1


def get_actual_tips(tips_dir):
    """Get all .md files under tips/ excluding INDEX.md."""
    actual = set()
    for p in tips_dir.rglob("*.md"):
        if p.name == "INDEX.md":
            continue
        rel = p.relative_to(tips_dir)
        actual.add(str(rel))
    return actual


def parse_index_entries(index_file):
    """Extract file paths referenced in INDEX.md tree structure."""
    if not index_file.exists():
        return set()
    indexed = set()
    text = index_file.read_text()
    # Match patterns like: ├── filename.md or └── filename.md
    # with optional description in parens
    # Need to track current directory from lines like: ├── category/
    current_dir = ""
    for line in text.split("\n"):
        # Directory line: ├── tools/ or │   ├── domain/
        dir_match = re.search(r"[├└]── (\S+)/", line)
        if dir_match:
            # Check indentation to determine nesting
            indent = len(line) - len(line.lstrip())
            stripped = line.lstrip()
            pipe_count = stripped.count("│")
            # Top-level dirs have pipe_count 0, subdirs have more
            if pipe_count == 0 and "│" not in stripped[:4]:
                current_dir = dir_match.group(1)
            continue

        # File line: ├── filename.md (description)
        file_match = re.search(r"[├└]── (\S+\.md)\s", line)
        if file_match:
            filename = file_match.group(1)
            if current_dir:
                indexed.add(f"{current_dir}/{filename}")
            else:
                indexed.add(filename)
    return indexed


def parse_index_entries_v2(index_file):
    """More robust: extract all .md filenames from INDEX.md and match against actual paths."""
    if not index_file.exists():
        return set()
    text = index_file.read_text()
    # Extract all .md filenames mentioned (without path)
    filenames = set()
    for match in re.finditer(r"(\S+\.md)", text):
        name = match.group(1)
        if name != "INDEX.md":
            filenames.add(name)
    return filenames


def check_tips_index(c):
    """Check 1: INDEX.md ↔ actual tips files."""
    print("── Check 1: Tips INDEX.md consistency")

    if not INDEX_FILE.exists():
        c.error("tips/INDEX.md does not exist")
        return

    actual_files = get_actual_tips(TIPS_DIR)
    actual_basenames = {Path(f).name for f in actual_files}

    # Parse index — get basenames mentioned
    index_basenames = parse_index_entries_v2(INDEX_FILE)

    # Files on disk but not in INDEX
    orphans = actual_basenames - index_basenames
    if orphans:
        for f in sorted(orphans):
            c.error(f"Orphan tip (on disk, not in INDEX): {f}")

    # Files in INDEX but not on disk
    missing = index_basenames - actual_basenames
    if missing:
        for f in sorted(missing):
            c.error(f"Missing tip (in INDEX, not on disk): {f}")

    indexed_count = len(index_basenames)
    actual_count = len(actual_basenames)
    print(f"   INDEX mentions {indexed_count} files, disk has {actual_count} files")

    # Check the "N files" count declaration in INDEX
    text = INDEX_FILE.read_text()
    count_match = re.search(r"(\d+)\s+files", text)
    if count_match:
        declared = int(count_match.group(1))
        if declared != actual_count:
            c.warn(f"INDEX declares {declared} files, disk has {actual_count}")


def check_checklist_refs(c):
    """Check 2: analysis-checklist.md trigger table references exist."""
    print("── Check 2: Analysis-checklist trigger table references")

    if not CHECKLIST_FILE.exists():
        c.error("rules/analysis-checklist.md does not exist")
        return

    text = CHECKLIST_FILE.read_text()
    # Extract tips/ paths from backtick-quoted references
    refs = re.findall(r"`(tips/\S+\.md)`", text)

    for ref in refs:
        full_path = CONTEXTS / ref
        if not full_path.exists():
            c.error(f"Checklist references missing file: {ref}")
        else:
            print(f"   ✓ {ref}")


def check_workflow_rules_refs(c):
    """Check 3: workflow.md references to rules/ files exist."""
    print("── Check 3: Workflow.md rules/ references")

    if not WORKFLOW_FILE.exists():
        c.error("workflow.md does not exist")
        return

    text = WORKFLOW_FILE.read_text()
    refs = re.findall(r"`?(rules/[\w-]+\.md)`?", text)
    refs = list(set(refs))  # dedup

    for ref in sorted(refs):
        # rules/ now lives under .codebuddy/rules, so resolve the prefix through the path registry
        full_path = (RULES_DIR / ref[len("rules/"):]) if ref.startswith("rules/") else (ROOT / ref)
        if not full_path.exists():
            c.error(f"Workflow.md references missing file: {ref}")
        else:
            print(f"   ✓ {ref}")


def check_discipline_numbering(c):
    """Check 4: discipline.md D-A/D-O/D-P numbering is continuous."""
    print("── Check 4: Discipline.md numbering continuity")

    if not DISCIPLINE_FILE.exists():
        c.error("rules/discipline.md does not exist")
        return

    text = DISCIPLINE_FILE.read_text()

    for prefix, name in [("D-A", "Analysis"), ("D-O", "Output"), ("D-P", "Process")]:
        numbers = sorted(
            int(m.group(1))
            for m in re.finditer(rf"### {prefix}(\d+):", text)
        )
        if not numbers:
            c.warn(f"No {prefix} entries found in discipline.md")
            continue

        expected = list(range(1, max(numbers) + 1))
        missing = set(expected) - set(numbers)
        dupes = [n for n in numbers if numbers.count(n) > 1]

        if missing:
            c.error(f"{prefix} gap: missing {prefix}{sorted(missing)}")
        if dupes:
            c.error(f"{prefix} duplicates: {prefix}{sorted(set(dupes))}")
        print(f"   {prefix}: {len(numbers)} entries ({prefix}1–{prefix}{max(numbers)})")

    # Check that each entry has a "来源" or "Learned From"
    entries = re.findall(r"### (D-[AOP]\d+):.*?\n(.*?)(?=### D-|\Z)", text, re.S)
    for eid, body in entries:
        if "来源" not in body and "Learned From" not in body and "翻车" not in body:
            c.warn(f"{eid} has no 来源/翻车 — discipline rules must cite incidents")


def check_patterns_duplicates(c):
    """Check 5: workflow-patterns.md P-* IDs have no duplicates."""
    print("── Check 5: Workflow-patterns P-* uniqueness")

    if not PATTERNS_FILE.exists():
        c.error("rules/workflow-patterns.md does not exist")
        return

    text = PATTERNS_FILE.read_text()

    # Uniqueness only applies to the Active Staging section — the Promotion
    # Ledger is an archive of graduated IDs and must not count as duplicates.
    staging = text
    m = re.search(r"##\s*当前暂存.*?(?=\n##\s|\Z)", text, re.S)
    if m:
        staging = m.group(0)
    else:
        c.warn("Active Staging section (当前暂存) not found — scanning whole file")

    # Match both heading-style (### P-EXEC:) and table-row style (| P-CRED-READ-FIRST |).
    # ID = P + 3 digits (P001) or P- + uppercase (P-EXEC); excludes the "Pattern" header.
    pid_pat = r"(P(?:[0-9]{3}|-[A-Z][\w-]*))"
    ids = re.findall(rf"###?\s+{pid_pat}[:\s]", staging)
    ids += re.findall(rf"^\|\s*{pid_pat}\s*[|\s]", staging, re.M)

    seen = {}
    for pid in ids:
        if pid in seen:
            c.error(f"Duplicate pattern ID in Active Staging: {pid}")
        seen[pid] = seen.get(pid, 0) + 1

    print(f"   {len(seen)} unique pattern IDs (Active Staging)")


def check_decisions_format(c):
    """Check 6: decisions/ files follow the required format."""
    print("── Check 6: Decisions format compliance")

    if not DECISIONS_DIR.exists():
        c.warn("decisions/ directory does not exist")
        return

    # Each tuple: (section_name, list_of_acceptable_patterns)
    required_sections = [
        ("Decision", [r"## Decision"]),
        ("Alternatives", [r"## Alternatives Considered", r"[Aa]lternatives?\s*(considered|:)"]),
        ("Reason", [r"## Reason", r"\*\*Reason\*\*:", r"[Rr]eason\s*:"]),
        ("Revisit", [r"## Revisit (If|Condition)", r"[Rr]evisit\s*(if|condition|when)"]),
    ]
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}-")

    decision_files = [
        f for f in DECISIONS_DIR.iterdir()
        if f.suffix == ".md" and f.name != "README.md"
    ]

    if not decision_files:
        print("   No decision files to check")
        return

    for df in sorted(decision_files):
        # Check filename format
        if not date_pattern.match(df.name):
            c.warn(f"Decision file name doesn't start with YYYY-MM-DD-: {df.name}")

        text = df.read_text()
        for section_name, patterns in required_sections:
            found = any(re.search(p, text) for p in patterns)
            if not found:
                c.warn(f"{df.name}: missing '{section_name}' section")

    print(f"   {len(decision_files)} decision files checked")


def check_history_naming(c):
    """Check 7: history/ file naming is YYYY-MM-DD.md."""
    print("── Check 7: History file naming")

    if not HISTORY_DIR.exists():
        c.warn("history/ directory does not exist")
        return

    date_file = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")
    # Also allow weekly/monthly review files, insight files, and friction reports
    special = re.compile(
        r"^(weekly-review|monthly-review|insight|bi-weekly-review|w\d+-friction)-?.*\.md$"
    )
    month_dir = re.compile(r"^\d{4}-\d{2}$")
    # Special top-level dirs that are not month-based
    special_dirs = {"milestones"}

    bad_dirs = []
    bad_files = []
    file_count = 0

    for month in sorted(HISTORY_DIR.iterdir()):
        if not month.is_dir():
            continue
        if month.name in special_dirs:
            continue
        if not month_dir.match(month.name):
            bad_dirs.append(month.name)
            continue
        for f in month.iterdir():
            if f.suffix != ".md":
                continue
            file_count += 1
            if not date_file.match(f.name) and not special.match(f.name):
                bad_files.append(f"{month.name}/{f.name}")

    if bad_dirs:
        for d in bad_dirs:
            c.warn(f"History dir not YYYY-MM format: {d}")
    if bad_files:
        for f in bad_files:
            c.warn(f"History file name irregular: {f}")

    print(f"   {file_count} history files checked")


def check_tips_nonempty(c):
    """Check 8: tips files are non-empty and have at least one heading."""
    print("── Check 8: Tips files non-empty with heading")

    actual = get_actual_tips(TIPS_DIR)
    empty = []
    no_heading = []

    for rel in sorted(actual):
        path = TIPS_DIR / rel
        text = path.read_text().strip()
        if not text:
            empty.append(rel)
            continue
        if not re.search(r"^#", text, re.M):
            no_heading.append(rel)

    if empty:
        for f in empty:
            c.error(f"Empty tip file: {f}")
    if no_heading:
        for f in no_heading:
            c.warn(f"Tip file has no heading: {f}")

    print(f"   {len(actual)} tip files checked, {len(empty)} empty, {len(no_heading)} headingless")


def rebuild_index(tips_dir, index_file):
    """Rebuild INDEX.md from disk contents."""
    actual = sorted(get_actual_tips(tips_dir))

    # Group by directory
    tree = {}
    for f in actual:
        parts = Path(f).parts
        if len(parts) == 1:
            tree.setdefault(".", []).append(parts[0])
        else:
            tree.setdefault(parts[0], []).append(parts[-1])

    lines = [
        "# Tips Index",
        "",
        f"> Auto-generated by cbp-validate.py",
        "",
        "## Structure",
        "",
        "```",
        "tips/",
    ]

    dirs = sorted(k for k in tree if k != ".")
    for i, d in enumerate(dirs):
        is_last_dir = (i == len(dirs) - 1 and "." not in tree)
        prefix = "└── " if is_last_dir else "├── "
        lines.append(f"{prefix}{d}/")
        files = sorted(tree[d])
        for j, f in enumerate(files):
            is_last = (j == len(files) - 1)
            connector = "│   " if not is_last_dir else "    "
            fprefix = "└── " if is_last else "├── "
            lines.append(f"{connector}{fprefix}{f}")

    if "." in tree:
        for f in sorted(tree["."]):
            lines.append(f"├── {f}")

    total = sum(len(v) for v in tree.values())
    lines.append("```")
    lines.append("")
    lines.append(f"{total} files · {len(dirs)} categories")
    lines.append("")

    index_file.write_text("\n".join(lines))
    print(f"   INDEX.md rebuilt with {total} files")


def main():
    parser = argparse.ArgumentParser(description="Validate .codebuddy knowledge base health")
    parser.add_argument("--strict", action="store_true", help="Warnings become errors")
    parser.add_argument("--fix", action="store_true", help="Auto-fix INDEX.md")
    args = parser.parse_args()

    print("=" * 50)
    print("  .codebuddy Knowledge Base Health Check")
    print("=" * 50)

    c = Checker(strict=args.strict)

    check_tips_index(c)
    check_checklist_refs(c)
    check_workflow_rules_refs(c)
    check_discipline_numbering(c)
    check_patterns_duplicates(c)
    check_decisions_format(c)
    check_history_naming(c)
    check_tips_nonempty(c)

    if args.fix:
        print("\n── Auto-fix: rebuilding INDEX.md")
        rebuild_index(TIPS_DIR, INDEX_FILE)

    exit_code = c.report()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
