#!/usr/bin/env bash
# cbp-startup-hook.sh — agentSpawn hook for the pure agent.
#
# Runs the deterministic part of the workflow "Startup Check" once per session
# and prints a compact digest; cbp-cli injects stdout into the agent context.
# The agent then only has to ACT on the digest (ask / remind), not re-collect it.
#
#   - startup-check.py : daily-summary completeness, calendar reminders,
#                        pending queue, archive, push queue   (~0.2s)
#   - cbp-auth-check  : first session of the day only (stamp file)
#
# Must never block or fail a session: every step is time-boxed and errors are
# reported as a line in the digest, exit code is always 0.

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/paths.sh" || exit 1
LAB="$CBP_ROOT"
BIN="$CBP_BIN"
TODAY="$(date +%F)"
STAMP_DIR="$CBP_DATA"
AUTH_STAMP="$STAMP_DIR/.auth-check-$TODAY"

echo "## ${CBP_DIGEST_NAME:-pure} startup digest (agentSpawn hook, $(date '+%F %H:%M'))"
echo "Use this instead of re-running the startup scripts. Act per workflow.md priority order."

# --- 1. startup-check.py -> compact lines ---
SC_JSON="$(timeout 15 python3 "$BIN/startup-check.py" 2>/dev/null)"
if [[ -z "$SC_JSON" ]]; then
  echo "- startup-check: FAILED to run — fall back to reading rules manually"
else
  python3 - "$SC_JSON" <<'PY'
import json, sys
try:
    d = json.loads(sys.argv[1])
except json.JSONDecodeError:
    print("- startup-check: unparseable output"); sys.exit(0)

def line(label, block):
    if isinstance(block, dict) and block.get("summary_zh"):
        print(f"- {label}: {block['summary_zh']}")

status = d.get("status", "?")
if status == "INCOMPLETE":
    print(f"- daily-summary: INCOMPLETE — {d.get('summary_zh','')} "
          f"(missing={','.join(d.get('missing', []))}) → rules/daily-summary.md")
elif status == "COMPLETE":
    print(f"- daily-summary: complete ✓ ({d.get('date','')})")
else:
    print(f"- daily-summary: {status} (nothing needed)")

cal = d.get("calendar", {})
rem = cal.get("reminders") or []
print(f"- calendar: {cal.get('weekday_zh','')} W{cal.get('iso_week','?')}"
      + (f" — reminders: {'; '.join(map(str, rem))}" if rem else ""))

p = d.get("pending", {})
if p.get("count"):
    print(f"- pending: {p['summary_zh']} → {', '.join(p.get('files', []))} → rules/pending-queue.md")
else:
    print("- pending: none ✓")
line("archive", d.get("archive"))
pq = d.get("push_queue", {})
line("push-queue", pq)
if pq.get("ready_to_push"):
    print(f"  ready_to_push: {pq['ready_to_push']}")
PY
fi

# --- 2. auth check: first session of the day only ---
if [[ -f "$AUTH_STAMP" ]]; then
  echo "- auth-check: already run today ✓"
elif [[ -x "$BIN/cbp-auth-check" ]]; then
  AUTH_OUT="$(timeout 25 "$BIN/cbp-auth-check" --quiet 2>&1)"; rc=$?
  if [[ $rc -eq 0 ]]; then
    echo "- auth-check: all OK ✓"
    mkdir -p "$STAMP_DIR" && rm -f "$STAMP_DIR"/.auth-check-* && touch "$AUTH_STAMP"
  else
    # don't stamp on failure: re-check next session until fixed
    echo "- auth-check: FAILED (rc=$rc) — tell the user:"
    printf '%s\n' "$AUTH_OUT" | sed 's/^/    /' | head -8
  fi
else
  echo "- auth-check: skipped (no bin/cbp-auth-check; optional)"
fi

exit 0
