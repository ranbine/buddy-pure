#!/usr/bin/env bash
# sync-shared.sh — keep the shared core identical between this repo and another install.
#
#   bin/sync-shared.sh status <other-root>        list shared files that differ / are missing
#   bin/sync-shared.sh push   <other-root> [-n]   copy shared files FROM this repo TO other-root
#   bin/sync-shared.sh pull   <other-root> [-n]   copy shared files FROM other-root TO this repo
#
# The file list is shared-files.txt (repo root). Only listed paths are ever copied, so personal
# content (config/local*, contexts/local/, history/ …) cannot travel. -n = dry run.
# After a pull into a public repo, run its leak check before committing.
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/lib/paths.sh" || exit 1
cmd="${1:-}"; other="${2:-}"; dry="${3:-}"
[ -n "$cmd" ] && [ -n "$other" ] && [ -d "$other" ] || { sed -n '2,10p' "$0"; exit 2; }
other="$(cd "$other" && pwd -P)"
[ "$other" != "$CBP_ROOT" ] || { echo "other-root is this repo"; exit 2; }
MANIFEST="$CBP_ROOT/shared-files.txt"
[ -f "$MANIFEST" ] || { echo "missing $MANIFEST"; exit 2; }
# Manifest entries are validated: repo-relative, no '..', never personal/runtime paths.
list() {
  grep -v -E '^\s*(#|$)' "$MANIFEST" | while read -r f; do
    case "$f" in
      /*|*..*|config/local*|config/*.local.*|contexts/local/*|*.env|*.env.*|history/*|pending/*|data/*|logs/*|docs/*|knowledge/*|settings/*|tmp/*|.tmp/*)
        echo "sync-shared: refusing manifest entry '$f'" >&2; exit 3 ;;
    esac
    printf '%s\n' "$f"
  done
}
N=$(list | wc -l) || { echo "sync-shared: bad or empty manifest" >&2; exit 2; }
[ "$N" -gt 0 ] || { echo "empty manifest"; exit 2; }
# Gate-protected files are never copied by this script (agents may run it): the user copies them.
protected() { case "$1" in bin/action-gate.py|bin/cbp-gate|bin/gate-install.py|bin/agent-trace.py|bin/lib/*|.codebuddy/rules/gate-policy.json) return 0;; esac; return 1; }
case "$cmd" in
  status)
    n=0
    while read -r f; do
      if [ ! -f "$other/$f" ]; then echo "missing-there  $f"; n=$((n+1))
      elif [ ! -f "$CBP_ROOT/$f" ]; then echo "missing-here   $f"; n=$((n+1))
      elif ! cmp -s "$CBP_ROOT/$f" "$other/$f"; then echo "differs        $f"; n=$((n+1)); fi
    done < <(list)
    [ "$n" -eq 0 ] && echo "shared core identical ($N files)"
    exit $(( n > 0 ))
    ;;
  push|pull)
    if [ "$cmd" = push ]; then src="$CBP_ROOT"; dst="$other"; else src="$other"; dst="$CBP_ROOT"; fi
    # All-or-nothing: other shared files may depend on a newer protected file (e.g. bin/lib/*),
    # so if any protected file differs, copy nothing and tell the user what to copy first.
    blocked=0
    while read -r f; do
      if protected "$f" && [ -f "$src/$f" ] && ! cmp -s "$src/$f" "$dst/$f" 2>/dev/null; then
        echo "PROTECTED differs — copy it yourself first: cp '$src/$f' '$dst/$f'"; blocked=1
      fi
    done < <(list)
    if [ "$blocked" = 1 ]; then echo "sync-shared: nothing copied; re-run after the cp above."; exit 4; fi
    while read -r f; do
      [ -f "$src/$f" ] || { echo "skip (absent in source): $f"; continue; }
      cmp -s "$src/$f" "$dst/$f" 2>/dev/null && continue
      echo "copy $f"
      [ "$dry" = "-n" ] && continue
      mkdir -p "$dst/$(dirname "$f")"
      cp "$src/$f" "$dst/$f"
      if [ -x "$src/$f" ]; then chmod +x "$dst/$f"; else chmod -x "$dst/$f"; fi
    done < <(list)
    ;;
  *) sed -n '2,10p' "$0"; exit 2 ;;
esac
exit 0
