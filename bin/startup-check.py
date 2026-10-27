#!/usr/bin/env python3
"""
startup-check.py — Startup verification for Pure daily flow.

Checks:
1. Daily summary completeness for last active day
2. Calendar context (weekday, week number, reminders)

Usage:
    python3 startup-check.py [--date YYYY-MM-DD]
    (defaults to last active day from session files)

Output:
    JSON to stdout with completeness status + calendar info.
    Exit code: 0 = COMPLETE, 1 = INCOMPLETE, 2 = NO_SUMMARY_NEEDED
"""

import json
import os
import sys
import glob
import re
from datetime import datetime, date, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from cbp_paths import P, ROOT, CLI_HOME, setting, local_list  # noqa: E402


def _valid_re(p):
    try:
        re.compile(p)
        return True
    except re.error:
        print("startup-check: bad regex in config/local.json log_patterns: %r" % p, file=sys.stderr)
        return False

TZ = None  # local time of the machine (override via TZ env var)
_LAB = str(ROOT)
SESSIONS_DIR = str(CLI_HOME / "sessions" / "cli")
HISTORY_DIR = str(P["CBP_HISTORY"])
REPORTS_DIR = str(P["CBP_DOCS"] / "reports" / "daily")
INSIGHT_DIR = str(P["CBP_HISTORY"])
PENDING_DIR = str(P["CBP_PENDING"])

# Tag rules to detect log_analysis sessions
LOG_ANALYSIS_PATTERNS = [
    r"log.analysis",
    r"failure.*log",
    r"root.cause",
    r"alarm",
    r"pod.*kill|kill.*pod",
    r"regression",
]
LOG_ANALYSIS_PATTERNS += [p for p in local_list("log_patterns") if _valid_re(p)]   # domain-specific, config/local.json

WEEKDAY_ZH = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def get_now():
    """Get current local datetime (timezone-aware)."""
    return datetime.now().astimezone()


def get_today_str(now):
    """Get today's date string."""
    return now.strftime("%Y-%m-%d")


def get_calendar_info(now):
    """Get calendar context: weekday, week number, reminders."""
    iso_year, iso_week, iso_weekday = now.isocalendar()
    is_monday = iso_weekday == 1
    even_week = iso_week % 2 == 0
    first_of_month = now.day == 1

    reminders = []
    if is_monday:
        reminders.append("weekly_review")
        if even_week:
            reminders.append("biweekly_review")
        # Check if insight exists this week
        if not has_insight_this_week(now, iso_week):
            reminders.append("insight_reminder")
    if first_of_month:
        reminders.append("monthly_review")

    return {
        "weekday": now.strftime("%A"),
        "weekday_zh": WEEKDAY_ZH[iso_weekday - 1],
        "iso_week": iso_week,
        "is_monday": is_monday,
        "even_week": even_week,
        "first_of_month": first_of_month,
        "reminders": reminders,
    }


def has_insight_this_week(now, iso_week):
    """Check if an insight file exists for the current week."""
    # Look for insight-YYYY-MM-DD.md files in current month's history
    month_dir = os.path.join(INSIGHT_DIR, now.strftime("%Y-%m"))
    if not os.path.isdir(month_dir):
        return False
    pattern = os.path.join(month_dir, "insight-*.md")
    for f in glob.glob(pattern):
        basename = os.path.basename(f)
        # Extract date from insight-YYYY-MM-DD.md
        m = re.match(r"insight-(\d{4}-\d{2}-\d{2})\.md", basename)
        if m:
            insight_date = datetime.strptime(m.group(1), "%Y-%m-%d")
            if insight_date.isocalendar()[1] == iso_week:
                return True
    return False


def get_session_dates():
    """Get all session files grouped by date (from mtime)."""
    pattern = os.path.join(SESSIONS_DIR, "*.jsonl")
    files = glob.glob(pattern)
    date_sessions = {}
    for f in files:
        mtime = os.path.getmtime(f)
        dt = datetime.fromtimestamp(mtime, TZ)
        date_str = dt.strftime("%Y-%m-%d")
        if date_str not in date_sessions:
            date_sessions[date_str] = []
        date_sessions[date_str].append(f)
    return date_sessions


def find_last_active_day(date_sessions, today_str):
    """Find the most recent active day that is not today."""
    dates = sorted([d for d in date_sessions.keys() if d != today_str], reverse=True)
    return dates[0] if dates else None


def check_history_exists(date_str):
    """Check if history .md file exists for the given date."""
    month = date_str[:7]
    path = os.path.join(HISTORY_DIR, month, f"{date_str}.md")
    return os.path.isfile(path), path


def check_email_sent(history_path):
    """Check if history file contains 📧 marker."""
    if not os.path.isfile(history_path):
        return False
    with open(history_path, "r", encoding="utf-8") as f:
        content = f.read()
    return "📧" in content


def check_skip_marker(history_path):
    """Check if history file has 📭 skip marker (non-technical day, no report needed)."""
    if not os.path.isfile(history_path):
        return False
    with open(history_path, "r", encoding="utf-8") as f:
        content = f.read()
    return "📭" in content


def check_alt_report(history_path):
    """Check if the day's deliverable is a periodic report instead of a daily report.

    Some workdays produce a monthly/weekly/biweekly review or an insight HTML
    rather than a daily log-analysis report. When the history records such an
    HTML deliverable, the daily-report requirement is considered satisfied.
    """
    if not os.path.isfile(history_path):
        return False
    with open(history_path, "r", encoding="utf-8") as f:
        content = f.read()
    markers = (
        "monthly-review-",
        "weekly-review-",
        "biweekly-review-",
        "insight-",
    )
    # Require it to be an actual HTML deliverable mention, not just a reminder.
    return any(m in content for m in markers) and ".html" in content


def check_has_log_analysis(history_path):
    """Check if the day involved log analysis (from history content)."""
    if not os.path.isfile(history_path):
        return False
    with open(history_path, "r", encoding="utf-8") as f:
        content = f.read().lower()
    if "log analysis" in content or "日志分析" in content:
        return True
    for pattern in LOG_ANALYSIS_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            return True
    return False


def check_html_report_exists(date_str):
    """Check if HTML daily report exists for the date."""
    path = os.path.join(REPORTS_DIR, f"daily-report-{date_str}.html")
    return os.path.isfile(path), path


def count_sessions_for_date(date_sessions, date_str):
    """Count session files for the given date."""
    return len(date_sessions.get(date_str, []))


def check_push_queue():
    """Report the dual push-gate queues (user-set 2026-09-30).

    time    : changes ready but rate-window was full → auto-retry when free.
    quality : changes blocked on a hard gate / batching → retry only after fix.
    Only the time queue is eligible for automatic push (and only when the
    2/hour rate window has freed up).
    """
    import time as _t
    st = os.path.join(_LAB, "settings")
    tq = os.path.join(st, "push-deferred-time.json")
    qq = os.path.join(st, "push-blocked-quality.json")
    plog = os.path.join(st, "push-log.json")

    def _load(p):
        try:
            return json.load(open(p))
        except Exception:
            return []

    time_items = _load(tq)
    qual_items = _load(qq)
    ts = _load(plog)
    now = _t.time()
    rate_free = sum(1 for t in ts if now - t < 3600) < 2
    ready = time_items if (rate_free and time_items) else []

    n_t, n_q = len(time_items), len(qual_items)
    if not n_t and not n_q:
        zh, en = "推送队列空 ✓", "Push queues empty ✓"
    else:
        parts_zh, parts_en = [], []
        if ready:
            parts_zh.append(f"{len(ready)} 个待推改动到点可推（速率窗口已释放）")
            parts_en.append(f"{len(ready)} change(s) ready to auto-push (rate window free)")
        elif n_t:
            parts_zh.append(f"{n_t} 个待推改动等下一个时间窗口")
            parts_en.append(f"{n_t} change(s) waiting for next time window")
        if n_q:
            parts_zh.append(f"{n_q} 个改动被质量门禁拦下（需修复后重审）")
            parts_en.append(f"{n_q} change(s) blocked on quality (fix then re-review)")
        zh, en = " | ".join(parts_zh), " | ".join(parts_en)

    return {
        "time_count": n_t,
        "quality_count": n_q,
        "rate_free": rate_free,
        "ready_to_push": ready,
        "summary_zh": zh,
        "summary_en": en,
    }


def check_pending_queue():
    """Scan pending directory for unprocessed tasks."""
    pending_dir = PENDING_DIR
    if not os.path.isdir(pending_dir):
        return {"count": 0, "files": [], "summary_zh": "无 pending 任务 ✓", "summary_en": "No pending tasks ✓"}

    files = []
    for f in sorted(os.listdir(pending_dir)):
        full = os.path.join(pending_dir, f)
        if os.path.isfile(full) and not f.startswith("."):
            files.append(f)

    if not files:
        return {"count": 0, "files": [], "summary_zh": "无 pending 任务 ✓", "summary_en": "No pending tasks ✓"}

    # Categorize
    categories = {}
    for f in files:
        if "scope-diff" in f:
            categories["scope diff"] = categories.get("scope diff", 0) + 1
        elif "insight" in f:
            categories["insight"] = categories.get("insight", 0) + 1
        else:
            categories["other"] = categories.get("other", 0) + 1

    desc_parts_zh = [f"{t} ×{n}" for t, n in categories.items()]
    desc_parts_en = desc_parts_zh  # category names are English already

    summary_zh = f"{len(files)} 个 pending 任务待处理（{', '.join(desc_parts_zh)}）"
    summary_en = f"{len(files)} pending task(s) ({', '.join(desc_parts_en)})"

    return {"count": len(files), "files": files, "summary_zh": summary_zh, "summary_en": summary_en}


def check_session_archive():
    """Check for session files older than 15 days."""
    sessions_dir = SESSIONS_DIR
    if not os.path.isdir(sessions_dir):
        return {"stale_count": 0, "summary_zh": "无需归档 ✓", "summary_en": "No archive needed ✓"}

    now_ts = datetime.now(TZ).timestamp()
    threshold = 15 * 86400  # 15 days in seconds
    stale = []

    for f in os.listdir(sessions_dir):
        if not (f.endswith(".jsonl") or f.endswith(".json")):
            continue
        full = os.path.join(sessions_dir, f)
        if os.path.isfile(full):
            mtime = os.path.getmtime(full)
            if (now_ts - mtime) > threshold:
                stale.append((f, mtime))

    if not stale:
        return {"stale_count": 0, "summary_zh": "无需归档 ✓", "summary_en": "No archive needed ✓"}

    stale.sort(key=lambda x: x[1])
    oldest = datetime.fromtimestamp(stale[0][1], TZ).strftime("%Y-%m-%d")

    summary_zh = f"{len(stale)} 个 session 文件超 15 天（最早 {oldest}），建议归档"
    summary_en = f"{len(stale)} session file(s) older than 15 days (oldest: {oldest}), suggest archive"

    return {"stale_count": len(stale), "oldest_date": oldest, "summary_zh": summary_zh, "summary_en": summary_en}


def generate_summary(status, date_str, session_count, missing):
    """Generate bilingual human-readable summary strings."""
    MISSING_LABELS = {
        "history_md": ("历史记录", "history file"),
        "email": ("邮件", "email"),
        "html_report": ("HTML 报告", "HTML report"),
    }

    if status == "COMPLETE":
        return ("无需补总结 ✓", "Summary complete ✓")

    missing_zh = " + ".join(MISSING_LABELS[m][0] for m in missing)
    missing_en = " + ".join(MISSING_LABELS[m][1] for m in missing)
    s = "session" if session_count == 1 else "sessions"

    zh = f"{date_str}（{session_count} session）不完整：缺 {missing_zh}"
    en = f"{date_str} ({session_count} {s}) incomplete: missing {missing_en}"

    return (zh, en)


def main():
    # Parse args
    target_date = None
    if "--date" in sys.argv:
        idx = sys.argv.index("--date")
        if idx + 1 < len(sys.argv):
            target_date = sys.argv[idx + 1]

    now = get_now()
    today_str = get_today_str(now)
    calendar = get_calendar_info(now)
    pending = check_pending_queue()
    archive = check_session_archive()
    push_queue = check_push_queue()
    date_sessions = get_session_dates()

    # Determine target date
    if target_date is None:
        target_date = find_last_active_day(date_sessions, today_str)

    # Guard: future date
    if target_date is not None and target_date > today_str:
        result = {
            "status": "NO_SUMMARY_NEEDED",
            "summary_zh": "无需补总结 ✓",
            "summary_en": "No summary needed ✓",
            "reason": f"Target date {target_date} is in the future",
            "today": today_str,
            "calendar": calendar,
            "pending": pending,
            "archive": archive,
            "push_queue": push_queue,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(2)

    if target_date is None:
        result = {
            "status": "NO_SUMMARY_NEEDED",
            "summary_zh": "无需补总结 ✓",
            "summary_en": "No summary needed ✓",
            "reason": "No active day found before today",
            "today": today_str,
            "calendar": calendar,
            "pending": pending,
            "archive": archive,
            "push_queue": push_queue,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(2)

    # If target_date == today, no summary needed yet
    if target_date == today_str:
        result = {
            "status": "NO_SUMMARY_NEEDED",
            "summary_zh": "无需补总结 ✓",
            "summary_en": "No summary needed ✓",
            "reason": "Target date is today, session still active",
            "today": today_str,
            "calendar": calendar,
            "pending": pending,
            "archive": archive,
            "push_queue": push_queue,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(2)

    # Run checks
    session_count = count_sessions_for_date(date_sessions, target_date)
    history_exists, history_path = check_history_exists(target_date)
    email_sent = check_email_sent(history_path) if history_exists else False
    has_log_analysis = check_has_log_analysis(history_path) if history_exists else False
    html_exists, html_path = check_html_report_exists(target_date)
    alt_report = history_exists and check_alt_report(history_path)

    # Skip marker: non-technical day (e.g. interview prep, learning) → no report needed
    if history_exists and check_skip_marker(history_path):
        result = {
            "status": "NO_SUMMARY_NEEDED",
            "summary_zh": "无需补总结 ✓（已标记跳过：无技术内容）",
            "summary_en": "No summary needed ✓ (marked skip: non-technical day)",
            "reason": "History contains 📭 skip marker",
            "date": target_date,
            "today": today_str,
            "calendar": calendar,
            "pending": pending,
            "archive": archive,
            "push_queue": push_queue,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(2)

    # Determine what's missing
    missing = []
    if not history_exists:
        missing.append("history_md")
    if not email_sent:
        missing.append("email")
    if not html_exists and not alt_report:
        missing.append("html_report")

    status = "COMPLETE" if not missing else "INCOMPLETE"

    # Generate human-readable summaries
    summary_zh, summary_en = generate_summary(
        status, target_date, session_count, missing
    )

    result = {
        "status": status,
        "summary_zh": summary_zh,
        "summary_en": summary_en,
        "date": target_date,
        "today": today_str,
        "calendar": calendar,
        "pending": pending,
        "archive": archive,
        "push_queue": push_queue,
        "sessions": session_count,
        "history_exists": history_exists,
        "history_path": history_path,
        "email_sent": email_sent,
        "has_log_analysis": has_log_analysis,
        "html_needed": not alt_report,
        "html_exists": html_exists,
        "html_path": html_path,
        "missing": missing,
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if status == "COMPLETE" else 1)


if __name__ == "__main__":
    main()
