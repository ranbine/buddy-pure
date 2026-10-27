#!/usr/bin/env python3
"""
daily-summary-extract.py — Pre-process session files for daily summary.
Extracts conversations, tags them, outputs structured JSON for LLM consumption.

Usage:
    python3 daily-summary-extract.py [YYYY-MM-DD]
    (defaults to last active day if no date given)

Output:
    $CBP_TMP/daily-summary-raw.json   (see config/paths.env)
"""

import json
import os
import re
import sys
import glob
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from cbp_paths import P, ROOT, CLI_HOME, setting, local_list  # noqa: E402
SESSIONS_DIR = str(CLI_HOME / "sessions" / "cli")
OUTPUT_PATH = str(P["CBP_TMP"] / "daily-summary-raw.json")
TZ = datetime.now().astimezone().tzinfo  # machine local time

# --- Tag definitions ---
TAG_RULES = [
    ("log_analysis", r"log.analysis|failure.*log|root.cause"),
    ("tool",       r"bin/|script|triage|rerun|\.py\b"),
    ("dashboard",  r"dashboard"),
    ("git",        r"git push|commit|deploy|pages|push.*origin"),
    ("report",     r"html.*report|daily-report|weekly-review|insight"),
    ("learning",   r"learning|path|reading|ai-coding-guide|hooks"),
    ("config",     r"workflow\.md|rules/|preferences|memory\.md|tips/"),
]
# config/local.json "summary_tags": [[name, regex], ...] — same name ORs the regex, new names are added
for _t in local_list("summary_tags", list):
    if len(_t) != 2 or not all(isinstance(x, str) for x in _t):
        print("daily-summary-extract: summary_tags entry must be [name, regex]: %r" % (_t,), file=sys.stderr)
        continue
    _name, _rx = _t
    try:
        re.compile(_rx)
    except re.error:
        print("daily-summary-extract: bad regex for tag %r" % _name, file=sys.stderr)
        continue
    _i = next((k for k, (n, _) in enumerate(TAG_RULES) if n == _name), None)
    if _i is None:
        TAG_RULES.insert(0, (_name, _rx))
    else:
        TAG_RULES[_i] = (_name, TAG_RULES[_i][1] + "|" + _rx)

A_PREVIEW_LEN = 300  # chars to keep from assistant responses


def get_target_date(argv):
    """Determine target date: from arg, or last active day."""
    if len(argv) > 1:
        return argv[1]

    # Find last active day (most recent mtime that is not today)
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    files = glob.glob(os.path.join(SESSIONS_DIR, "*.jsonl"))
    dates_seen = set()
    for f in files:
        mtime = os.path.getmtime(f)
        d = datetime.fromtimestamp(mtime, TZ).strftime("%Y-%m-%d")
        if d != today:
            dates_seen.add(d)

    if not dates_seen:
        print("No previous active day found.", file=sys.stderr)
        sys.exit(1)

    return max(dates_seen)


def find_sessions_for_date(target_date):
    """Find session files whose mtime falls on target_date."""
    files = glob.glob(os.path.join(SESSIONS_DIR, "*.jsonl"))
    matched = []
    for f in files:
        mtime = os.path.getmtime(f)
        d = datetime.fromtimestamp(mtime, TZ).strftime("%Y-%m-%d")
        if d == target_date:
            matched.append(f)
    return sorted(matched, key=os.path.getmtime)


def parse_session(filepath):
    """Parse a single session jsonl file."""
    conversations = []
    first_ts = None
    last_ts = None
    prompt_count = 0
    current_prompt = None

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            kind = obj.get("kind")

            if kind == "Prompt":
                prompt_count += 1
                data = obj.get("data", {})
                # Extract timestamp
                ts = data.get("meta", {}).get("timestamp")
                if ts:
                    if first_ts is None:
                        first_ts = ts
                    last_ts = ts
                # Extract text
                content = data.get("content", [])
                text_parts = [c.get("data", "") for c in content if c.get("kind") == "text"]
                current_prompt = " ".join(text_parts).strip()

            elif kind == "AssistantMessage" and current_prompt is not None:
                data = obj.get("data", {})
                content = data.get("content", [])
                text_parts = [c.get("data", "") for c in content if c.get("kind") == "text"]
                full_text = " ".join(text_parts).strip()

                if len(full_text) > 50:  # Skip trivial/empty responses
                    conversations.append({
                        "q": current_prompt[:500],
                        "a_preview": full_text[:A_PREVIEW_LEN]
                    })
                    current_prompt = None  # Only take first meaningful response per prompt

    # Calculate times
    start_time = None
    end_time = None
    duration_min = 0

    if first_ts:
        start_time = datetime.fromtimestamp(first_ts, TZ).strftime("%H:%M")
    if last_ts:
        end_time = datetime.fromtimestamp(last_ts, TZ).strftime("%H:%M")

    # Use file mtime as end time (more accurate, includes last response)
    mtime = os.path.getmtime(filepath)
    end_time = datetime.fromtimestamp(mtime, TZ).strftime("%H:%M")

    if first_ts:
        duration_min = int((mtime - first_ts) / 60)

    return {
        "file": os.path.basename(filepath),
        "start": start_time or "??:??",
        "end": end_time,
        "duration_min": duration_min,
        "prompts": prompt_count,
        "conversations": conversations
    }


def tag_session(session):
    """Apply keyword-based tags to a session."""
    tags = set()
    # Combine all text for matching
    all_text = ""
    for conv in session["conversations"]:
        all_text += conv["q"] + " " + conv["a_preview"] + " "

    for tag_name, pattern in TAG_RULES:
        if re.search(pattern, all_text, re.IGNORECASE):
            tags.add(tag_name)

    if not tags:
        tags.add("other")

    return sorted(tags)


def main():
    target_date = get_target_date(sys.argv)
    sessions_files = find_sessions_for_date(target_date)

    if not sessions_files:
        print(f"No sessions found for {target_date}", file=sys.stderr)
        sys.exit(1)

    sessions = []
    all_tags = {}

    for sf in sessions_files:
        session = parse_session(sf)
        tags = tag_session(session)
        session["tags"] = tags

        for t in tags:
            all_tags[t] = all_tags.get(t, 0) + 1

        sessions.append(session)

    total_prompts = sum(s["prompts"] for s in sessions)
    total_duration = sum(s["duration_min"] for s in sessions)

    output = {
        "date": target_date,
        "weekday": datetime.strptime(target_date, "%Y-%m-%d").strftime("%A"),
        "sessions": sessions,
        "stats": {
            "total_sessions": len(sessions),
            "total_prompts": total_prompts,
            "total_duration_min": total_duration,
            "tags_summary": all_tags
        }
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Print brief summary to stdout
    print(f"✅ Extracted: {target_date} ({output['weekday']})")
    print(f"   Sessions: {len(sessions)}, Prompts: {total_prompts}, Duration: {total_duration}min")
    print(f"   Tags: {all_tags}")
    print(f"   Output: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
