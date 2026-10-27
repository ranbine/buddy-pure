#!/bin/bash
# check-drift.sh — content-hash drift detector for pure contracts
#
# ── Why this exists (local evolution trace) ─────────────────────────────────
# In a single session I added run-agent.sh and had to manually sync its
# registries (tips/INDEX.md + analysis-checklist.md); added a tips
# note and again manually registered it in the checklist; edited
# review-artifact.py and the pre-push hook caught a stale README. That is drift
# happening three times in one session, caught only by human memory + one
# narrow hook. Consistency maintenance shouldn't rely on remembering.
#
# This generalizes that single README hook into a content-hash check across all
# contract files: rules/, tips/, the two registries, workflow.md, preferences.md.
#
# ── Theory ──────────────────────────────────────────────────────────────────
# A hash is a file's fingerprint: same content → same hash, one byte changes →
# the whole hash changes. Storing one 64-char hash per file is a cheap "state
# snapshot" without storing the file. Drift = compare current hashes vs a
# saved baseline. The point is not "report a change" but "every drift becomes
# an explicit event that must be acknowledged" — turning silent drift into a
# decision. We reuse `git hash-object` (git's own SHA) instead of hashing
# ourselves, so the fingerprint matches git's blob identity.
#
# ── Usage ───────────────────────────────────────────────────────────────────
#   check-drift.sh            # check current state vs baseline; report drift
#   check-drift.sh --accept   # accept current state as the new baseline
#   check-drift.sh --init     # create the baseline for the first time
#   check-drift.sh --quiet    # machine output: only drift lines + exit code
#
# Exit: 0 = clean (or accepted/init) | 1 = drift found | 2 = no baseline

set -o pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/paths.sh" || exit 1
PURE="$CBP_ROOT"
cd "$PURE" || { echo "check-drift: cannot cd $PURE" >&2; exit 2; }

BASELINE="contexts/.drift-baseline"
REGISTRIES="${CBP_DRIFT_REGISTRIES:-contexts/tips/INDEX.md .codebuddy/rules/analysis-checklist.md}"   # override in config/local.env

MODE="check"
QUIET=0
for a in "$@"; do
    case "$a" in
        --accept) MODE="accept" ;;
        --init)   MODE="init" ;;
        --quiet)  QUIET=1 ;;
        *) echo "check-drift: unknown arg $a" >&2; exit 2 ;;
    esac
done

# --- collect tracked contract files ---------------------------------------
list_files() {
    {
        ls .codebuddy/rules/*.md 2>/dev/null
        find contexts/tips -name '*.md' 2>/dev/null
        ls .codebuddy/rules/workflow.md .codebuddy/rules/preferences.md 2>/dev/null
    } | sort -u
}

# --- compute current fingerprint manifest ---------------------------------
current_manifest() {
    while IFS= read -r f; do
        [ -f "$f" ] || continue
        printf '%s  %s\n' "$(git hash-object "$f")" "$f"
    done < <(list_files)
}

# --- init / accept: write baseline ----------------------------------------
if [ "$MODE" = "init" ] || [ "$MODE" = "accept" ]; then
    if [ "$MODE" = "init" ] && [ -f "$BASELINE" ]; then
        echo "check-drift: baseline already exists ($BASELINE). Use --accept to update." >&2
        exit 2
    fi
    current_manifest > "$BASELINE"
    n=$(wc -l < "$BASELINE")
    echo "✅ baseline ${MODE}ed: $n files → $BASELINE"
    exit 0
fi

# --- check: diff current vs baseline --------------------------------------
if [ ! -f "$BASELINE" ]; then
    echo "⚠️  no baseline yet. Run: check-drift.sh --init" >&2
    exit 2
fi

CUR="$(mktemp)"; trap 'rm -f "$CUR"' EXIT
current_manifest > "$CUR"

# Build assoc arrays: path -> hash
declare -A base cur
while read -r h p; do base["$p"]="$h"; done < "$BASELINE"
while read -r h p; do cur["$p"]="$h"; done < "$CUR"

modified=(); deleted=(); untracked=()
for p in "${!base[@]}"; do
    if [ -z "${cur[$p]:-}" ]; then deleted+=("$p")
    elif [ "${base[$p]}" != "${cur[$p]}" ]; then modified+=("$p"); fi
done
for p in "${!cur[@]}"; do
    [ -z "${base[$p]:-}" ] && untracked+=("$p")
done

total=$(( ${#modified[@]} + ${#deleted[@]} + ${#untracked[@]} ))

if [ "$total" -eq 0 ]; then
    [ "$QUIET" -eq 0 ] && echo "✅ no drift: $(wc -l < "$BASELINE") contract files match baseline"
    exit 0
fi

# --- report ---------------------------------------------------------------
emit() { printf '%s\n' "$@"; }
[ "$QUIET" -eq 0 ] && echo "⚠️  drift detected ($total): contract files differ from baseline"
for p in "${modified[@]}";  do emit "MODIFIED  $p"; done
for p in "${deleted[@]}";   do emit "DELETED   $p"; done
for p in "${untracked[@]}"; do emit "UNTRACKED $p"; done

# --- cross-file linkage hint (the valuable layer) -------------------------
# If any tips/ file drifted, the two registries should be re-checked.
if [ "$QUIET" -eq 0 ]; then
    tips_touched=0
    for p in "${modified[@]}" "${untracked[@]}" "${deleted[@]}"; do
        case "$p" in contexts/tips/*) tips_touched=1 ;; esac
    done
    if [ "$tips_touched" -eq 1 ]; then
        echo ""
        echo "🔗 tips/ changed → verify registries are in sync:"
        for r in $REGISTRIES; do echo "   - $r"; done
    fi
    echo ""
    echo "→ If these changes are intended, accept them: check-drift.sh --accept"
fi
exit 1
