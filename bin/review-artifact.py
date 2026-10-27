#!/usr/bin/env python3
"""
review-artifact.py — Unified quality-gate reviewer for pure agent outputs.

A single quality-gate ("质检员") that reviews artifacts from multiple agents and
returns an auto go/no-go decision, minimizing human involvement.

Profiles (--type):
  html : html-generator reports — links/bilingual/structure/compliance/index/size
  log  : log-analyzer conclusions — output contract + evidence-structure rules
         (turns "is the conclusion trustworthy?" into mechanical evidence checks)

Publish rule (set with user 2026-09-29):
  - HARD-GATE dimensions: any failure => BLOCK.
  - SOFT dimensions: weighted score; publish requires overall >= 90.
  - Bilingual leak (EN mode shows CJK) is a HARD gate.

Usage:
  review-artifact.py <file.html> --type html [--index docs/index.html] [--json]
  review-artifact.py <result.md> --type log [--json]

Exit: 0 = PUBLISH-OK, 1 = BLOCK/needs-attention, 2 = usage error.
"""
import argparse
import json
import os
import re
import sys

PUBLISH_LINE = 90  # user-set 2026-09-29

# Section display limits (sync.md)
SECTION_LIMITS = {"blog": 3, "weekly": 6, "biweekly": 6, "daily": 6, "tech": 4}
# report/learning: no limit


sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from cbp_paths import ROOT  # noqa: E402

def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


CJK = re.compile(r"[\u4e00-\u9fff]")


def check_structure(html):
    """Hard gate: tag balance, no corruption, no active placeholders.

    Covers the 2026-10-16 monthly-template failure class: duplicated {{CONTENT}}
    (one in a doc comment) → content injected twice + into a comment; and a
    missing <script> open tag → JS leaked as page text. structure now checks
    script/div balance, treats leftover {{...}} as a hard fail, and flags
    rendered content accidentally wrapped in / duplicated by a comment.
    """
    issues = []
    for tag in ("section", "svg", "div", "script"):
        o, c = html.count("<%s" % tag), html.count("</%s>" % tag)
        if o != c:
            issues.append(f"{tag} tags unbalanced ({o}/{c})")
    if 'hidden-card"="' in html:
        issues.append('corrupted markup: hidden-card"="')

    # Leftover unreplaced placeholders anywhere outside comments → hard fail
    # (strip comments first, then look for {{NAME}}).
    nocomment = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    if re.search(r"\{\{[A-Z_]+\}\}", nocomment):
        leftover = sorted(set(re.findall(r"\{\{[A-Z_]+\}\}", nocomment)))
        issues.append("unreplaced placeholder(s): " + ", ".join(leftover))

    # Content-swallowed-by-comment / duplication guard: key rendered markers
    # must appear in the comment-stripped HTML (i.e. not only inside a comment),
    # and a hero/header should appear exactly once (duplication = double-filled).
    hero_total = html.count('class="hero"')
    hero_rendered = nocomment.count('class="hero"')
    if hero_total and hero_rendered == 0:
        issues.append("hero present but only inside a comment (content swallowed)")
    if hero_total > 1:
        issues.append(f"hero appears {hero_total}x (content likely duplicated)")

    return issues, None


def check_links(html, base_dir):
    """Hard gate: internal relative links resolve; nav uses ../../index.html."""
    issues = []
    hrefs = re.findall(r'href="([^"]+)"', html)
    for h in set(hrefs):
        if h.startswith(("http", "data:", "#", "mailto:")):
            continue
        target = os.path.normpath(os.path.join(base_dir, h))
        if not os.path.exists(target):
            issues.append(f"broken link: {h}")
    # nav brand/back should be ../../index.html for docs/reports/*/*.html
    if 'href="index.html"' in html:
        issues.append('bare href="index.html" (should be ../../index.html)')
    return issues


def check_compliance(html, base_dir):
    """Hard gate: nav/CSS consistency (sync 'no exceptions').

    Verifies a cbp-base.css link is present AND its relative path actually
    resolves to the real file from this artifact's location — rather than
    hard-coding '../../' (which only holds for docs/reports/*/*.html; pages at
    other depths like docs/tools/*.html correctly use '../').
    """
    issues = []
    css_refs = re.findall(r'href="([^"]*cbp-base\.css)"', html)
    if not css_refs:
        issues.append("missing cbp-base.css link")
    elif not any(
        os.path.exists(os.path.normpath(os.path.join(base_dir, ref)))
        for ref in css_refs
    ):
        issues.append(
            "cbp-base.css link does not resolve from this path: "
            + ", ".join(css_refs)
        )
    if 'class="cbp-nav"' not in html:
        issues.append("missing cbp-nav block")
    if "--kb-" not in html:
        issues.append("missing --kb-* CSS variable mapping")
    return issues


def check_bilingual(html):
    """Hard gate (user-set): EN mode must be fully English.

    In EN mode, hidden content is: <script>, <style>, HTML comments, and any
    text inside a `.zh` span (via [lang=en] .zh{display:none}). Also the CN/EN
    language toggle buttons are intentional. What WOULD leak:
      (a) CJK inside <svg> (SVG <text> is not affected by the lang toggle), and
      (b) bare CJK in rendered HTML that is NOT inside a .zh span.
    Strategy: remove non-rendering / EN-hidden regions, then look for residual CJK.
    """
    issues = []

    # (a) CJK inside any <svg> — always a leak (lang toggle can't hide SVG text)
    for m in re.finditer(r"<svg\b.*?</svg>", html, re.DOTALL):
        if CJK.search(m.group(0)):
            issues.append("CJK inside <svg> (not hidden by lang toggle)")
            break

    # (b) residual CJK after stripping EN-hidden / non-rendering regions
    stripped = html
    stripped = re.sub(r"<svg\b.*?</svg>", "", stripped, flags=re.DOTALL)      # handled in (a)
    stripped = re.sub(r"<script\b.*?</script>", "", stripped, flags=re.DOTALL)  # not rendered text
    stripped = re.sub(r"<style\b.*?</style>", "", stripped, flags=re.DOTALL)
    stripped = re.sub(r"<!--.*?-->", "", stripped, flags=re.DOTALL)            # comments
    stripped = re.sub(r'<span class="zh">.*?</span>', "", stripped, flags=re.DOTALL)  # EN-hidden
    stripped = re.sub(r'<span[^>]*class="zh"[^>]*>.*?</span>', "", stripped, flags=re.DOTALL)
    # data-zh="..." attribute mechanism (EN shows data-en); CN lives in the attribute
    stripped = re.sub(r'data-zh="[^"]*"', "", stripped)
    # language toggle buttons (various forms): the literal 中文 button label
    stripped = re.sub(r">\s*中文\s*<", "><", stripped)

    if CJK.search(stripped):
        # report up to 3 sample snippets for locating
        samples = []
        for m in re.finditer(r".{0,15}[\u4e00-\u9fff]+.{0,15}", stripped):
            s = m.group(0).strip().replace("\n", " ")
            if s and s not in samples:
                samples.append(s)
            if len(samples) >= 3:
                break
        issues.append("bare CJK outside .zh span (leaks in EN mode): "
                      + " | ".join(samples))
    return issues


def check_index_sync(html, index_path, artifact_path):
    """Soft: card inserted, display limits, corruption. Returns (score, notes)."""
    notes = []
    if not index_path or not os.path.exists(index_path):
        return None, ["index.html not provided; skipped index-sync checks"]
    idx = read(index_path)
    score = 100
    rel = os.path.relpath(artifact_path, os.path.dirname(index_path))
    if rel not in idx and os.path.basename(artifact_path) not in idx:
        score -= 50
        notes.append("card for this artifact not found in index.html")
    # What's New is a SEPARATE region from the section grids. A missed
    # What's New update is the 2026-10-16 drift class (section card added,
    # What's New forgotten). Check the artifact URL also appears inside the
    # whats-new block; soft -15 since What's New is curated highlights, not
    # every page — so a hint, not a hard failure.
    wn = re.search(r'class="whats-new".*?</section>', idx, re.DOTALL)
    wn_block = wn.group(0) if wn else ""
    if rel not in idx and os.path.basename(artifact_path) not in idx:
        pass  # already flagged above (card missing entirely)
    elif wn_block and rel not in wn_block and os.path.basename(artifact_path) not in wn_block:
        score -= 15
        notes.append(
            "artifact in a section grid but NOT in What's New — "
            "run bin/update-whats-new.py if this is a highlight (2026-10-16 miss class)"
        )
    if 'hidden-card"="' in idx:
        score -= 30
        notes.append('index.html has corrupted hidden-card markup')
    # display limits
    for sec, lim in SECTION_LIMITS.items():
        cards = re.findall(r'class="post-card( hidden-card)?" data-type="%s"' % sec, idx)
        visible = sum(1 for c in cards if not c.strip())
        if visible > lim:
            score -= 20
            notes.append(f"section '{sec}' visible {visible} > limit {lim}")
    return max(score, 0), notes


def check_size(html_bytes):
    """Soft: size scoring (user-set 2026-09-29): <50KB=100, 50-55KB=70, >=55KB=0.
    Note: static Pages render soft limit ~50KB; 50-55KB accepted with a warning."""
    kb = html_bytes / 1024
    if html_bytes >= 56320:  # 55 KB
        return 0, f"{kb:.1f}KB >= 55KB (too large)"
    if html_bytes >= 51200:  # 50 KB
        return 70, f"{kb:.1f}KB in 50-55KB (over soft limit, accepted)"
    return 100, f"{kb:.1f}KB OK"


# ============================================================
# LOG profile — validates log-analyzer output contract.
# Strategy: turn the "is the conclusion trustworthy?" semantic
# question into mechanical evidence-structure rules (L3 -> L1).
# Derived from log-analyzer-prompt.md Output Format + self-check.
# ============================================================

LOG_REQUIRED = ["Result", "Classification", "Root Cause", "Evidence", "Recommendation"]
LOG_CLASSES = {"product_bug", "env_issue", "known_tr", "test_issue", "rerun_needed"}
# evidence is "locatable" if it contains a timestamp, file ref, line ref, or a number+unit
EVIDENCE_LOCATOR = re.compile(
    r"\d{2}:\d{2}:\d{2}"                 # timestamp HH:MM:SS
    r"|\d{6}_\d{6}"                      # job dir stamp 260924_044424
    r"|\.(log|xml|json)\b"              # file reference
    r"|line\s*\d+|:\d+\b"              # line number
    r"|\d+\s*(%|cores?|ms|s|MB|GB|replicas?)"  # number + unit
    r"|bearer=\d+|OLP|CPU|SU\b"        # known counters/metrics
)
UNDETERMINED = re.compile(r"未确定|undetermined|not determined|inconclusive|unknown", re.I)


def _field(text, name):
    """Extract a field value written as **Name**: value (one line)."""
    m = re.search(r"\*{0,2}%s\*{0,2}\s*[:：]\s*(.+)" % re.escape(name), text)
    return m.group(1).strip() if m else None


def review_log(text):
    """Return (hard_dict, soft_list, note). Mirrors review_html shape."""
    hard = {"fields": [], "classification": [], "evidence": []}

    # L1: required fields present
    present = {f: _field(text, f) for f in LOG_REQUIRED}
    for f in LOG_REQUIRED:
        if not present.get(f):
            hard["fields"].append(f"missing/empty field: {f}")

    # L1: classification is a legal tag
    cls = present.get("Classification") or ""
    tags = set(re.findall(r"[a-z_]+", cls.lower()))
    if not (tags & LOG_CLASSES):
        hard["classification"].append(
            f"Classification not one of {sorted(LOG_CLASSES)} (got: {cls!r})")

    # L3->L1 evidence rule: either Evidence is locatable, OR Root Cause is undetermined.
    root = present.get("Root Cause") or ""
    ev = present.get("Evidence") or ""
    if not UNDETERMINED.search(root):
        # confident root cause => must have locatable evidence
        if not EVIDENCE_LOCATOR.search(ev):
            hard["evidence"].append(
                "confident Root Cause but Evidence lacks a locator "
                "(timestamp/file/line/number) — mark '未确定' or add evidence")

    # Soft: recommendation is actionable
    rec = (present.get("Recommendation") or "").lower()
    actionable = any(k in rec for k in ["rerun", "file tr", "ignore", "fix", "config", "重跑", "忽略", "提单"])
    rec_score = 100 if actionable else 60
    soft = [("recommendation-actionable", rec_score, 1.0,
             [] if actionable else ["Recommendation not clearly actionable"])]

    # L2 note (not auto-run here): known_tr should be verified against the issue tracker
    note = None
    if "known_tr" in tags:
        m = re.search(r"\b(PC[A-Z]*-?\d{3,}|[A-Z]{2,}-\d{3,})\b", text)
        note = (f"known_tr classified (TR {m.group(1)}); verify it exists in the issue tracker (L2)"
                if m else "known_tr classified but no TR key found")
    return hard, soft, note


def main_log(args, text):
    hard, soft, note = review_log(text)
    hard_pass = all(len(v) == 0 for v in hard.values())
    tot_w = sum(w for _, _, w, _ in soft) or 1
    overall = round(sum(s * w for _, s, w, _ in soft) / tot_w)
    publish_ok = hard_pass and overall >= PUBLISH_LINE
    result = {
        "artifact": args.file, "profile": "log",
        "hard_gates": {k: ("PASS" if not v else "FAIL") for k, v in hard.items()},
        "hard_issues": {k: v for k, v in hard.items() if v},
        "soft_scores": {n: s for n, s, _, _ in soft},
        "overall": overall, "publish_line": PUBLISH_LINE,
        "verdict": "PUBLISH-OK" if publish_ok else "BLOCK",
        "l2_note": note,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if publish_ok else 1
    print(f"══════ REVIEW (log): {os.path.basename(args.file)} ══════")
    print("Hard gates (any FAIL => BLOCK):")
    for k, v in hard.items():
        print(f"  {'✅' if not v else '❌'} {k}")
        for it in v:
            print(f"       - {it}")
    print("Soft dimensions (weighted):")
    for n, s, w, notes in soft:
        print(f"  {s:3d}/100  {n}  (w={w})")
        for nt in notes:
            print(f"       - {nt}")
    if note:
        print(f"  ⚠ L2: {note}")
    print(f"Overall soft score: {overall}  (publish line: {PUBLISH_LINE})")
    if publish_ok:
        print("→ ✅ VERDICT: PUBLISH-OK")
    elif not hard_pass:
        print("→ ⛔ VERDICT: BLOCK (hard gate failed — send back to log-analyzer)")
    else:
        print(f"→ ⛔ VERDICT: BLOCK (soft score {overall} < {PUBLISH_LINE})")
    return 0 if publish_ok else 1


# ============================================================
# TEXT profile — validates emails / daily digests against the
# email conventions in daily-summary.md (subject prefix, signature,
# grouping, no leftover placeholders).
# ============================================================

CBP_SUBJECT = re.compile(r"\[Pure\]\[(Daily|Weekly|Monthly|Nightly|Alert)\]")
SIGNATURE_MARK = "Pure AI Assistant"
PLACEHOLDER = re.compile(r"\{\{.*?\}\}|<TODO|TBD\b|XXX\b|FIXME\b|<your ")


def review_text(text):
    hard = {"signature": [], "placeholders": []}
    # signature block (daily-summary.md: '--\nCodeBuddy AI Assistant\nGenerated for: ...')
    if SIGNATURE_MARK not in text:
        hard["signature"].append("missing signature block ('Pure AI Assistant')")
    if "Generated for" not in text:
        hard["signature"].append("missing 'Generated for:' signature line")
    # leftover placeholders / TODO markers
    hits = PLACEHOLDER.findall(text)
    if hits:
        hard["placeholders"].append(f"leftover placeholder/TODO markers: {hits[:3]}")

    # soft: subject format if a subject line is present in the file
    soft_notes = []
    score = 100
    subj_line = next((l for l in text.splitlines() if l.lower().startswith(("subject:", "主题:", "主题："))), None)
    if subj_line:
        if not CBP_SUBJECT.search(subj_line):
            score -= 40
            soft_notes.append("subject present but missing [Pure][Type] prefix")
    soft = [("subject-format", score, 1.0, soft_notes)]

    # L2 note: referenced issue/commit keys could be verified
    note = None
    m = re.search(r"\b([A-Z]{2,}-\d{3,})\b", text)
    if m:
        note = f"references {m.group(1)}; optionally verify it exists (L2)"
    return hard, soft, note


def main_text(args, text):
    hard, soft, note = review_text(text)
    hard_pass = all(len(v) == 0 for v in hard.values())
    tot_w = sum(w for _, _, w, _ in soft) or 1
    overall = round(sum(s * w for _, s, w, _ in soft) / tot_w)
    publish_ok = hard_pass and overall >= PUBLISH_LINE
    result = {
        "artifact": args.file, "profile": "text",
        "hard_gates": {k: ("PASS" if not v else "FAIL") for k, v in hard.items()},
        "hard_issues": {k: v for k, v in hard.items() if v},
        "soft_scores": {n: s for n, s, _, _ in soft},
        "overall": overall, "publish_line": PUBLISH_LINE,
        "verdict": "PUBLISH-OK" if publish_ok else "BLOCK", "l2_note": note,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if publish_ok else 1
    print(f"══════ REVIEW (text): {os.path.basename(args.file)} ══════")
    print("Hard gates (any FAIL => BLOCK):")
    for k, v in hard.items():
        print(f"  {'✅' if not v else '❌'} {k}")
        for it in v:
            print(f"       - {it}")
    print("Soft dimensions (weighted):")
    for n, s, w, notes in soft:
        print(f"  {s:3d}/100  {n}  (w={w})")
        for nt in notes:
            print(f"       - {nt}")
    if note:
        print(f"  ⚠ L2: {note}")
    print(f"Overall soft score: {overall}  (publish line: {PUBLISH_LINE})")
    print("→ ✅ VERDICT: PUBLISH-OK" if publish_ok else
          ("→ ⛔ VERDICT: BLOCK (hard gate failed)" if not hard_pass
           else f"→ ⛔ VERDICT: BLOCK (soft score {overall} < {PUBLISH_LINE})"))
    return 0 if publish_ok else 1


# ============================================================
# PUSH profile — pre-push gate MENSURATION (machine measuring only).
#
# Division of labour (user-set 2026-09-30):
#   - This script = the *measuring tool*: it emits objective readings
#     (file count, README staleness, index-card sync, rate limit, and a
#      template-vs-creative classification for any HTML in the change set).
#   - The reviewer AGENT = the *decision maker*: it reads these readings plus
#     semantic judgment (is this a "new mechanism"? a safety fix? should it
#     batch?) and returns push / defer / block.
#
# So the push profile does NOT print a final PUBLISH-OK/BLOCK verdict the way
# html/log/text do. It prints readings + a *suggested* routing, and the reviewer
# makes the call. Exit code reflects only the HARD readings (staleness / index
# gap) so a scripted caller can still short-circuit obvious blocks.
#
# HTML template-vs-creative rule (user-set 2026-09-30):
#   template  = file lives under a publish_dir registered in style-registry.json
#               (daily/weekly/monthly/insight/health ...) → reviewer may
#               green-light the first PUBLISH-OK version.
#   creative  = HTML not under any registered publish_dir (slides, one-off
#               visualisations) → reviewer only ever returns NEEDS-HUMAN
#               (baseline check ok, but human must say "satisfied").
# ============================================================

# dirs/extensions that count as "mechanism / behaviour" change (higher scrutiny)
MECHANISM_DIRS = {"bin", "rules", "agents", "templates", "settings"}
# dirs that are "content only" (batch candidates when small)
CONTENT_DIRS = {"docs", "history", "logs", "data", "knowledge"}
# commit-subject markers that flag a safety / correctness fix (push immediately)
SAFETY_MARKERS = re.compile(
    r"\b(security|CVE|token|secret|credential|hotfix|revert|"
    r"broken|corrupt|leak|fix accuracy|stale path)\b", re.I)


def _registered_publish_dirs(lab_home):
    """Return set of publish_dir values from style-registry.json (template classes)."""
    reg_path = os.path.join(lab_home, "templates", "style-registry.json")
    dirs = set()
    try:
        reg = json.load(open(reg_path, encoding="utf-8"))
        for k, v in reg.items():
            if k.startswith("_"):
                continue
            if isinstance(v, dict) and v.get("publish_dir"):
                dirs.add(v["publish_dir"].strip("/"))
    except Exception:
        pass
    return dirs


def classify_html(path, publish_dirs):
    """template if path is under a registered publish_dir, else creative."""
    norm = path.replace("\\", "/")
    for pd in publish_dirs:
        if ("/%s/" % pd) in norm or norm.split("docs/", 1)[-1].startswith(pd + "/"):
            return "template"
    return "creative"


def _rate_state(lab_home):
    """(pushes_this_hour, limit). Reads settings/push-log.json epoch list."""
    import time
    limit = 2
    p = os.path.join(lab_home, "settings", "push-log.json")
    try:
        ts = json.load(open(p))
        now = time.time()
        return sum(1 for t in ts if now - t < 3600), limit
    except Exception:
        return 0, limit


def review_push(files, subject, lab_home):
    """Return (hard, readings, suggestion). files = list of changed paths."""
    hard = {"readme_sync": [], "index_sync": []}
    files = [f for f in files if f.strip()]
    n = len(files)
    dirs = {f.split("/", 1)[0] for f in files}
    touches_mechanism = bool(dirs & MECHANISM_DIRS)
    is_safety = bool(SAFETY_MARKERS.search(subject or ""))

    # HARD: touched a mechanism dir but README not in the set -> staleness
    if touches_mechanism and "README.md" not in files:
        hard["readme_sync"].append(
            "touched %s but README.md not updated" % sorted(dirs & MECHANISM_DIRS))

    # HARD: added a report HTML under docs/reports but index.html not touched
    new_reports = [f for f in files if re.search(r"docs/reports/.+\.html$", f)]
    if new_reports and "docs/index.html" not in files:
        hard["index_sync"].append(
            "report HTML added (%s) but docs/index.html not in change set"
            % os.path.basename(new_reports[0]))

    # READINGS (objective, for the reviewer to judge on)
    publish_dirs = _registered_publish_dirs(lab_home)
    # infra/nav files are not deliverables — exclude from template/creative call
    INFRA = ("index.html", "cbp-base.css")
    html_classes = {}
    for f in files:
        if not f.endswith(".html"):
            continue
        if os.path.basename(f) in INFRA:
            continue
        if "/reports/" in f or "docs/" in f:
            html_classes[f] = classify_html(f, publish_dirs)
    pushes, limit = _rate_state(lab_home)

    readings = {
        "file_count": n,
        "dirs": sorted(dirs),
        "touches_mechanism": touches_mechanism,
        "is_safety_fix": is_safety,
        "html_classes": html_classes,
        "rate": {"this_hour": pushes, "limit": limit, "exhausted": pushes >= limit},
    }

    # SUGGESTED routing (reviewer may override with semantic judgment).
    # Order: content classification first; rate-limit only downgrades an
    # otherwise-pushable change to DEFER-TIME. BATCH is unaffected by rate
    # (it isn't trying to push yet).
    has_creative = any(c == "creative" for c in html_classes.values())
    has_template = any(c == "template" for c in html_classes.values())
    rate_exhausted = readings["rate"]["exhausted"]
    if has_creative:
        suggestion = "NEEDS-HUMAN"      # creative HTML present → human satisfaction gate
    elif is_safety:
        suggestion = "PUSH-NOW" if not rate_exhausted else "DEFER-TIME"
    elif touches_mechanism or has_template or n >= 3:
        # new mechanism, a complete template deliverable, or >=3 files → push if
        # gates pass (rate-limit downgrades to the time-window queue)
        suggestion = "DEFER-TIME" if rate_exhausted else "PUSH"
    else:
        suggestion = "BATCH"            # 1-2 files, content only → accumulate

    return hard, readings, suggestion


def main_push(args, lab_home):
    # gather change set: explicit files (comma-sep in args.file) or git staged/unpushed
    if args.file and args.file != "-":
        files = [x.strip() for x in args.file.split(",") if x.strip()]
    else:
        import subprocess
        try:
            out = subprocess.check_output(
                ["git", "-C", lab_home, "diff", "--name-only", "@{u}..HEAD"],
                text=True, stderr=subprocess.DEVNULL)
            files = [l for l in out.splitlines() if l.strip()]
        except Exception:
            files = []
    subject = args.subject or ""
    hard, readings, suggestion = review_push(files, subject, lab_home)
    hard_pass = all(len(v) == 0 for v in hard.values())

    result = {
        "profile": "push",
        "hard_gates": {k: ("PASS" if not v else "FAIL") for k, v in hard.items()},
        "hard_issues": {k: v for k, v in hard.items() if v},
        "readings": readings,
        "suggestion": suggestion,
        "note": "reviewer decides; script only measures",
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if hard_pass else 1

    print("══════ PUSH GATE (measurements — reviewer decides) ══════")
    print("Hard gates (any FAIL => cannot push until fixed):")
    for k, v in hard.items():
        print(f"  {'✅' if not v else '❌'} {k}")
        for it in v:
            print(f"       - {it}")
    print("Readings:")
    print(f"  file_count      : {readings['file_count']}  ({', '.join(readings['dirs'])})")
    print(f"  touches_mechanism: {readings['touches_mechanism']}")
    print(f"  is_safety_fix   : {readings['is_safety_fix']}")
    print(f"  rate            : {readings['rate']['this_hour']}/{readings['rate']['limit']}"
          f"{'  (EXHAUSTED)' if readings['rate']['exhausted'] else ''}")
    if readings["html_classes"]:
        print("  html_classes    :")
        for f, c in readings["html_classes"].items():
            print(f"       - [{c}] {os.path.basename(f)}")
    print(f"→ SUGGESTED routing: {suggestion}  (reviewer makes the final call)")
    return 0 if hard_pass else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?", default="-",
                    help="artifact file; for --type push: comma-sep change set or '-' to read git")
    ap.add_argument("--type", default="html", choices=["html", "log", "text", "push"],
                    help="artifact profile: html (default), log, text, or push")
    ap.add_argument("--index", default="")
    ap.add_argument("--subject", default="",
                    help="commit subject (push profile: safety-fix detection)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--allow-direct", action="store_true",
                    help="bypass the agent-only guard (CI / debugging). The html/log/"
                         "text quality gate is meant to run via the reviewer AGENT "
                         "(run-agent.sh reviewer), not a bare script call.")
    args = ap.parse_args()

    lab_home = str(ROOT)

    # push profile operates on a change set, not a single file
    if args.type == "push":
        return main_push(args, lab_home)

    # --- agent-only guard (quality-gate ownership, 2026-10-16) --------------
    # The html/log/text quality gate belongs to the `reviewer` AGENT, not the
    # main context. run-agent.sh sets CBP_AGENT_DEPTH when it spawns an agent;
    # its absence means this script was invoked directly (bypassing the agent's
    # judgement layer). Refuse, so "I'll just run the script" is impossible, not
    # merely rule-forbidden. (push profile above is exempt: it's the git-workflow
    # pre-push gauge, legitimately script-direct.) Escape hatch: --allow-direct.
    if not os.environ.get("CBP_AGENT_DEPTH") and not args.allow_direct:
        sys.stderr.write(
            "review-artifact.py: direct invocation refused — the quality gate runs "
            "via the reviewer AGENT.\n"
            "  Use:  run-agent.sh reviewer \"Review <file> against docs/index.html\"\n"
            "  (CI/debug only: re-run with --allow-direct to bypass.)\n"
        )
        return 2

    if not os.path.exists(args.file):
        print(f"error: no such file: {args.file}", file=sys.stderr)
        return 2

    # profile dispatch
    if args.type == "log":
        return main_log(args, read(args.file))
    if args.type == "text":
        return main_text(args, read(args.file))

    html = read(args.file)
    base_dir = os.path.dirname(os.path.abspath(args.file))
    raw_bytes = os.path.getsize(args.file)

    # --- HARD GATES ---
    struct_issues, ph_note = check_structure(html)
    link_issues = check_links(html, base_dir)
    comp_issues = check_compliance(html, base_dir)
    biling_issues = check_bilingual(html)

    hard = {
        "structure": struct_issues,
        "links": link_issues,
        "compliance": comp_issues,
        "bilingual": biling_issues,
    }
    hard_pass = all(len(v) == 0 for v in hard.values())

    # --- SOFT DIMENSIONS (weighted) ---
    idx_score, idx_notes = check_index_sync(html, args.index, args.file)
    size_score, size_note = check_size(raw_bytes)

    soft = []  # (name, score, weight, notes)
    if idx_score is not None:
        soft.append(("index-sync", idx_score, 0.6, idx_notes))
    soft.append(("size", size_score, 0.4, [size_note]))
    tot_w = sum(w for _, _, w, _ in soft) or 1
    overall = round(sum(s * w for _, s, w, _ in soft) / tot_w)

    publish_ok = hard_pass and overall >= PUBLISH_LINE

    result = {
        "file": args.file,
        "hard_gates": {k: ("PASS" if not v else "FAIL") for k, v in hard.items()},
        "hard_issues": {k: v for k, v in hard.items() if v},
        "soft_scores": {n: s for n, s, _, _ in soft},
        "overall": overall,
        "publish_line": PUBLISH_LINE,
        "verdict": "PUBLISH-OK" if publish_ok else "BLOCK",
        "placeholder_note": ph_note,
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if publish_ok else 1

    # human-readable scorecard
    print(f"══════ REVIEW: {os.path.basename(args.file)} ══════")
    print("Hard gates (any FAIL => BLOCK):")
    for k, v in hard.items():
        mark = "✅" if not v else "❌"
        print(f"  {mark} {k}")
        for it in v:
            print(f"       - {it}")
    print("Soft dimensions (weighted):")
    for n, s, w, notes in soft:
        print(f"  {s:3d}/100  {n}  (w={w})")
        for nt in notes:
            if nt:
                print(f"       - {nt}")
    if ph_note:
        print(f"  ⚠ note: {ph_note} (verify inside comment blocks)")
    print(f"Overall soft score: {overall}  (publish line: {PUBLISH_LINE})")
    if publish_ok:
        print("→ ✅ VERDICT: PUBLISH-OK")
    elif not hard_pass:
        print("→ ⛔ VERDICT: BLOCK (hard gate failed — fix before publish)")
    else:
        print(f"→ ⛔ VERDICT: BLOCK (soft score {overall} < {PUBLISH_LINE})")
    return 0 if publish_ok else 1


if __name__ == "__main__":
    sys.exit(main())
