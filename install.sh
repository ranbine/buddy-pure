#!/usr/bin/env bash
# install.sh — set up codebuddy-pure for the current checkout.
#
#   ./install.sh            check the environment, seed config/local.env, report health (no changes
#                           outside the repo)
#   ./install.sh --hooks    also enable the repo's git hooks (leak-check on commit/push)
#   ./install.sh --user     also copy rules/agents/skills/commands into ~/.codebuddy so they work in
#                           every project (refuses to overwrite without --force)
#   ./install.sh --force    allow --user to overwrite existing files (backs them up as *.bak.<ts>)
#
# Working *in this repo* needs no install step: CodeBuddy reads .codebuddy/ from the project root.
# --user is only for people who want the same rules and agents everywhere.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=bin/lib/paths.sh
. "$ROOT/bin/lib/paths.sh"

HOOKS=0; USER_INSTALL=0; FORCE=0
for a in "$@"; do
    case "$a" in
        --hooks) HOOKS=1 ;;
        --user)  USER_INSTALL=1 ;;
        --force) FORCE=1 ;;
        -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
        *) echo "unknown arg: $a" >&2; exit 2 ;;
    esac
done

say() { printf '%s\n' "$*"; }
step() { printf '\n\033[1m%s\033[0m\n' "$*"; }

step "1/5 interpreter"
if ! command -v python3 >/dev/null 2>&1; then
    say "python3 not found — the scripts in bin/ are stdlib-only Python 3.9+."
    say "Install it, or run everything through a host that provides it."
    exit 1
fi
say "python3 $(python3 -V 2>&1 | awk '{print $2}')"

step "2/5 local config"
if [ -f "$ROOT/config/local.env" ]; then
    say "config/local.env exists — leaving it alone"
else
    cp "$ROOT/config/local.env.example" "$ROOT/config/local.env"
    say "seeded config/local.env from the example — fill in name / email / timezone"
fi

step "3/5 permissions"
chmod +x "$ROOT"/bin/cbp-gate "$ROOT"/bin/cbp-archive 2>/dev/null || true
chmod +x "$ROOT"/bin/*.sh "$ROOT"/scripts/*.sh 2>/dev/null || true
say "bin/ executables ready"

step "4/5 health"
python3 "$ROOT/bin/cbp-doctor.py" || say "cbp-doctor reported problems (see above)"
python3 "$ROOT/bin/cbp-validate.py" || say "cbp-validate reported problems (see above)"

if [ "$HOOKS" = "1" ]; then
    step "5/5 git hooks"
    if [ -d "$ROOT/.git" ]; then
        git -C "$ROOT" config core.hooksPath scripts/hooks
        say "core.hooksPath -> scripts/hooks (leak-check on commit and push)"
    else
        say "not a git repository — skipped"
    fi
else
    step "5/5 git hooks"
    say "skipped (pass --hooks to enable the leak guard)"
fi

if [ "$USER_INSTALL" = "1" ]; then
    step "user scope (~/.codebuddy)"
    DEST="${HOME}/.codebuddy"
    mkdir -p "$DEST"
    ts="$(date +%Y%m%d%H%M%S)"
    for sub in rules agents skills commands; do
        [ -d "$ROOT/.codebuddy/$sub" ] || continue
        mkdir -p "$DEST/$sub"
        # copy contents, never the directory itself, so an existing tree merges instead of nesting
        while IFS= read -r -d '' src; do
            rel="${src#"$ROOT/.codebuddy/$sub/"}"
            dst="$DEST/$sub/$rel"
            mkdir -p "$(dirname "$dst")"
            if [ -e "$dst" ] && [ "$FORCE" != "1" ]; then
                say "exists, skipped: $sub/$rel (use --force to replace)"
                continue
            fi
            [ -e "$dst" ] && cp -p "$dst" "$dst.bak.$ts"
            cp -p "$src" "$dst"
        done < <(find "$ROOT/.codebuddy/$sub" -type f -print0)
        say "installed $sub -> $DEST/$sub"
    done
    say "note: settings.json is not copied — hooks stay project-scoped on purpose"
fi

say ""
say "done. Start CodeBuddy in this directory and run /checkup."
