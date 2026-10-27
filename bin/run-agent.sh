#!/bin/bash
# run-agent.sh — Generic process-boundary subagent invoker ("曲线救国") v2
#
# Turns any Pure subagent into a Unix-style component: standardized input,
# machine-readable stdout, debug noise on stderr. Starts the agent as a
# *separate process* (loads its JSON + prompt + restricted tool set) so you get
# role-level judgement + context isolation + least-privilege sandbox.
#
# Methodology:
#   native delegation = switch agent context in-process
#   this (曲线救国)    = spawn the SAME agents/<name>.json in another process
#
# ── Design goal: make an agent behave like a reliable CLI tool ──────────────
#   stdout = the agent's FINAL answer only (the RESULT= contract line)
#   stderr = narration, [tool] logs, banners, errors  (the "kitchen noise")
#   exit   = 0 ok | 124 timeout | 2 usage/guard | 3 contract-missing
#
# ── Input contract (two modes) ──────────────────────────────────────────────
#   A) Bare args (back-compat, same as analyze-log.sh style):
#        run-agent.sh <agent> <task...> [flags]
#   B) Structured stdin JSON (preferred for pipelines):
#        echo '{"task":"...","contract":"json|verdict|raw","session_id":"..."}' \
#          | run-agent.sh <agent> [flags]
#      Fields:
#        task       (required) the work description
#        contract   (optional) output shape the agent is told to emit:
#                     json    → one line: RESULT={...}
#                     verdict → one line: RESULT=<token>
#                     raw     → no contract, pass through full stdout (default
#                               when no stdin and no --contract)
#        session_id (optional) resume a prior CLI session (native state, no Redis)
#
# ── Flags ───────────────────────────────────────────────────────────────────
#   --timeout <sec>   kill after N sec (default 180); timeout → exit 124
#   --contract <c>    json|verdict|raw  (overrides stdin field)
#   --session <id>    resume session id (overrides stdin field)
#   --out <file>      tee the extracted result to this file
#   --raw             force raw mode: no contract injection, no extraction,
#                     pass agent stdout through verbatim
#   --quiet           suppress the spawn banner on stderr
#
# ── State note ───────────────────────────────────────────────────────────────
#   Processes are ephemeral by design — ideal for one-shot review/analysis.
#   For multi-turn needs, DON'T add an external store: reuse the CLI's own
#   session via --session/session_id (--resume-id under the hood). Only revisit
#   if cross-agent shared state is ever truly required.
#
# Fallback: on failure (token expired / timeout / network) the CALLER should
# fall back to the underlying script directly (e.g. review-artifact.py).

set -o pipefail

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/paths.sh" || exit 1
PURE="$CBP_ROOT"
CLI="$CBP_CLI_BIN"
# Rendered agent JSONs live in cbp-cli's agents dir (installed by install.sh)
AGENTS_DIR="$CBP_CLI_HOME/agents"

TIMEOUT=180
OUT=""
QUIET=0
CONTRACT=""
SESSION=""
RAW=0

# --- depth guard: block agent→run-agent→agent recursion -------------------
MAX_DEPTH="${CBP_AGENT_MAX_DEPTH:-1}"
CUR_DEPTH="${CBP_AGENT_DEPTH:-0}"
if [ "$CUR_DEPTH" -ge "$MAX_DEPTH" ]; then
    echo "run-agent.sh: depth guard hit (CBP_AGENT_DEPTH=$CUR_DEPTH >= $MAX_DEPTH) — refusing nested agent spawn" >&2
    exit 2
fi

# --- arg parse ------------------------------------------------------------
AGENT="${1:-}"
if [ -z "$AGENT" ]; then
    echo "Usage: run-agent.sh <agent> <task...> [--contract c] [--session id] [--timeout N] [--budget N] [--out F] [--raw] [--quiet]" >&2
    echo "   or: echo '{\"task\":...}' | run-agent.sh <agent> [flags]" >&2
    exit 2
fi
shift

TASK_PARTS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --timeout)  TIMEOUT="$2"; shift 2 ;;
        --budget)   BUDGET="$2"; shift 2 ;;
        --out)      OUT="$2"; shift 2 ;;
        --contract) CONTRACT="$2"; shift 2 ;;
        --session)  SESSION="$2"; shift 2 ;;
        --raw)      RAW=1; shift ;;
        --quiet)    QUIET=1; shift ;;
        *)          TASK_PARTS+=("$1"); shift ;;
    esac
done
TASK="${TASK_PARTS[*]}"
BUDGET="${BUDGET:-}"

# --- input contract: structured stdin JSON (if piped) ---------------------
# If stdin is not a TTY and args gave no task, read a JSON object from stdin.
if [ -z "$TASK" ] && [ ! -t 0 ]; then
    STDIN_JSON="$(cat)"
    if [ -n "$STDIN_JSON" ]; then
        # Parse with python3 (always available here); emit shell-safe assignments.
        eval "$(python3 - "$STDIN_JSON" <<'PY'
import json, sys, shlex
try:
    d = json.loads(sys.argv[1])
except Exception as e:
    sys.stderr.write(f"run-agent.sh: invalid stdin JSON: {e}\n"); sys.exit(2)
def emit(k, v):
    if v is None: return
    print(f'{k}={shlex.quote(str(v))}')
emit("J_TASK", d.get("task"))
emit("J_CONTRACT", d.get("contract"))
emit("J_SESSION", d.get("session_id"))
PY
)"
        TASK="${J_TASK:-$TASK}"
        [ -z "$CONTRACT" ] && CONTRACT="${J_CONTRACT:-}"
        [ -z "$SESSION" ]  && SESSION="${J_SESSION:-}"
    fi
fi

if [ -z "$TASK" ]; then
    echo "run-agent.sh: no task given (neither args nor stdin JSON 'task')" >&2
    exit 2
fi

# --- agent-exists check ---------------------------------------------------
# Tool budget: --budget N, else "BUDGET: <= N tool calls" (or ≤ N) in the task (Delegation brief).
# Exported as CBP_TOOL_BUDGET → bin/agent-trace.py refuses tool call N+1 and tells the agent to wrap up.
if [ -z "$BUDGET" ] && [ -n "$TASK" ]; then
    BUDGET="$(printf '%s\n' "$TASK" | grep -iE '^[[:space:]*>-]*\**BUDGET\**[[:space:]]*(:|：)' | tail -1 \
              | grep -oiE '(<=|≤|<|max)?[[:space:]]*[0-9]+[[:space:]]*(tool|calls)' | head -1 | grep -oE '[0-9]+' | head -1)"
fi
case "$BUDGET" in
    '') ;;
    *[!0-9]*|0) echo "run-agent.sh: ignoring invalid tool budget '$BUDGET' (need a positive integer)" >&2; BUDGET="" ;;
esac

# Validate via JSON path (rendered agents live in $CBP_CLI_HOME/agents); invoke CLI by *name* (passing a path → "failed to set agent").
AGENT_JSON="$AGENTS_DIR/$AGENT.json"
if [ ! -f "$AGENT_JSON" ]; then
    echo "run-agent.sh: agent definition not found: $AGENT_JSON" >&2
    echo "Available agents:" >&2
    ls -1 "$AGENTS_DIR"/*.json 2>/dev/null | xargs -n1 basename 2>/dev/null | sed 's/\.json$//' | sed 's/^/  - /' >&2
    exit 2
fi

# --- contract injection: append an output-format directive to the task ----
# RAW mode (flag or contract=raw) injects nothing and skips extraction.
[ "$CONTRACT" = "raw" ] && RAW=1
if [ "$RAW" -eq 0 ] && [ -n "$CONTRACT" ]; then
    case "$CONTRACT" in
        json)
            TASK="$TASK

Respond with EXACTLY ONE line, nothing before or after, no narration:
RESULT=<a single-line compact JSON object>" ;;
        verdict)
            TASK="$TASK

Respond with EXACTLY ONE line, nothing before or after, no narration:
RESULT=<single token>" ;;
        *) echo "run-agent.sh: unknown --contract '$CONTRACT' (use json|verdict|raw)" >&2; exit 2 ;;
    esac
fi

# --- banner (stderr, never pollutes stdout) -------------------------------
if [ "$QUIET" -eq 0 ]; then
    {
      echo "🤖 Spawning agent '$AGENT' (process-boundary, timeout ${TIMEOUT}s, depth $((CUR_DEPTH+1)))"
      [ -n "$CONTRACT" ] && [ "$RAW" -eq 0 ] && echo "   Contract: $CONTRACT"
      [ -n "$SESSION" ] && echo "   Session: $SESSION (resume)"
      echo "   Task: ${TASK%%$'\n'*} ..."
    } >&2
fi

# --- spawn ----------------------------------------------------------------
# CLI already routes [tool] logs/warns to stderr; we capture full stdout into
# a temp file, then emit only the RESULT= contract line to our stdout. The
# agent's narration (stdout) and the CLI noise (stderr) go to our stderr.
AGENT_STDOUT="$(mktemp)"
RUN_START="$(date +%s.%N)"
RUNS_LOG="${CBP_AGENT_RUNS_LOG:-$CBP_DATA/agent-runs.jsonl}"
# Run record (one JSON line per spawn) for bin/agent-perf.py. Best-effort: never changes the exit code.
log_run() {
    local code=$?
    rm -f "$AGENT_STDOUT"
    timeout 5 python3 - "$RUNS_LOG" "$AGENT" "$TIMEOUT" "$code" "$RUN_START" "$(date +%s.%N)" \
        "${CONTRACT:-}" "${SESSION:-}" "$PWD" "$((CUR_DEPTH+1))" "${TASK%%$'\n'*}" "${CBP_SESSION_ID:-}" "${BUDGET:-}" <<'PY' 2>/dev/null || true
import json, os, sys, datetime
log, agent, tmo, code, t0, t1, contract, resume, cwd, depth, task, parent, budget = sys.argv[1:14]
os.makedirs(os.path.dirname(log), exist_ok=True)
try:
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(os.environ.get("CBP_TZ") or "UTC")
except Exception:
    tz = datetime.timezone.utc
rec = {"ts": datetime.datetime.fromtimestamp(float(t0), tz).isoformat(timespec="seconds"),
       "agent": agent, "timeout_s": int(tmo) if tmo.isdigit() else tmo, "exit": int(code),
       "outcome": {"0": "ok", "124": "timeout", "2": "usage", "3": "no-contract"}.get(code, "error"),
       "wall_s": round(float(t1) - float(t0), 1), "start_epoch": float(t0), "contract": contract,
       "resume": resume, "cwd": cwd, "depth": int(depth), "parent_session": parent, "task": task[:200],
       "budget": int(budget) if budget.isdigit() else None}
with open(log, "a") as f:
    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
PY
    exit "$code"
}
trap log_run EXIT

run() {
    local -a extra=()
    [ -n "$SESSION" ] && extra+=(--resume-id "$SESSION")
    CBP_AGENT_DEPTH=$((CUR_DEPTH+1)) CBP_TOOL_BUDGET="${BUDGET:-}" \
    timeout "$TIMEOUT" "$CLI" chat \
        --agent "$AGENT" \
        --no-interactive \
        "${extra[@]}" \
        -a "$TASK"
}

# agent stdout → temp file ; agent/CLI stderr → our stderr (streamed through)
run 2>>/dev/stderr >"$AGENT_STDOUT"
rc=$?

if [ "$rc" -eq 124 ]; then
    echo "run-agent.sh: agent '$AGENT' timed out after ${TIMEOUT}s — caller should fall back to the underlying script" >&2
    exit 124
fi

# --- output contract: extract RESULT= line (unless raw) -------------------
if [ "$RAW" -eq 1 ]; then
    cat "$AGENT_STDOUT"
    [ -n "$OUT" ] && cp "$AGENT_STDOUT" "$OUT"
    exit "$rc"
fi

# Extract the contract payload. The CLI may concatenate the agent's narration
# and the RESULT= token onto the SAME line (no newline before RESULT=), so we
# match RESULT= anywhere, not just at line start.
RESULT_RAW="$(grep -o 'RESULT=.*' "$AGENT_STDOUT" | head -1)"

# Narration = full stdout with the RESULT= tail stripped → stderr for debugging.
sed 's/RESULT=.*//' "$AGENT_STDOUT" | grep -v '^[[:space:]]*$' >&2 || true

if [ -z "$RESULT_RAW" ]; then
    # Agent didn't honor the contract. Fall back: emit last non-empty line,
    # but signal via exit 3 so callers know extraction was best-effort.
    FALLBACK="$(grep -v '^[[:space:]]*$' "$AGENT_STDOUT" | tail -1)"
    echo "run-agent.sh: no RESULT= contract token found; emitting last line as best-effort" >&2
    printf '%s\n' "$FALLBACK"
    [ -n "$OUT" ] && printf '%s\n' "$FALLBACK" > "$OUT"
    exit 3
fi

# Strip the RESULT= prefix → clean payload on stdout.
PAYLOAD="${RESULT_RAW#RESULT=}"
printf '%s\n' "$PAYLOAD"
[ -n "$OUT" ] && printf '%s\n' "$PAYLOAD" > "$OUT"
exit "$rc"
