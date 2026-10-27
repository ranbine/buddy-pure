# shellcheck shell=bash
# Source this file:  . "$(dirname "$0")/lib/paths.sh"
#
# Exports CBP_ROOT plus every KEY in config/paths.env as an absolute path.
# config/local.env (optional, gitignored) is sourced last and may override.

_kp_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"   # -P: resolve symlinked installs
CBP_ROOT="${CBP_ROOT:-$(cd "$_kp_here/../.." && pwd -P)}"
export CBP_ROOT

_kp_env="$CBP_ROOT/config/paths.env"
if [ ! -f "$_kp_env" ]; then
    echo "paths.sh: missing $_kp_env" >&2
    return 1 2>/dev/null || exit 1
fi

while IFS='=' read -r _k _v; do
    case "$_k" in ''|\#*) continue ;; esac
    _k="${_k// /}"; _v="${_v%%#*}"; _v="${_v// /}"
    # Don't clobber values already exported by the caller
    if [ -z "${!_k:-}" ]; then
        export "$_k=$CBP_ROOT/$_v"
    fi
done < "$_kp_env"

[ -f "$CBP_ROOT/config/local.env" ] && set -a && . "$CBP_ROOT/config/local.env" && set +a

export CBP_CLI_HOME="${CBP_CLI_HOME:-$HOME/.codebuddy}"
export CBP_CLI_BIN="${CBP_CLI_BIN:-$(command -v cbp-cli 2>/dev/null || echo cbp-cli)}"

unset _kp_here _kp_env _k _v
