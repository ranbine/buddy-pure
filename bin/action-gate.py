#!/usr/bin/python3
"""action-gate: cbp-cli preToolUse hook — risk-tiered action gate (scheme A).

Reads the hook payload from stdin:
  {"hook_event_name":"preToolUse","cwd":..,"session_id":..,"tool_name":..,"tool_input":{..}}
Classifies the action as DENY / L3 / L2 / L1 / L0 using .codebuddy/rules/gate-policy.json,
logs every decision to data/gate/decisions-YYYY-MM.jsonl, and:
  mode=enforce : exit 2 (block, reason on stderr) for DENY and unapproved L3; L2 per l2_default
  mode=shadow  : always exit 0, log what enforce would have done
cbp-cli treats hook crash/timeout as ALLOW, so every failure path here is handled explicitly
(fail-closed in enforce mode, logged-and-allowed in shadow mode).

This is a guard-rail against agent *mistakes*, not a sandbox: a same-user process that
deliberately obfuscates (e.g. builds a command inside a script) can get around string rules.

Usage in agent JSON:
  {"matcher":"shell","command":"/usr/bin/python3 -I $CBP_ROOT/bin/action-gate.py --agent pure","timeout_ms":3000}
  (-I: ignore PYTHON* env vars and user site-packages, so the environment cannot swap modules)
Stdlib only, Python 3.9 compatible.
"""
import datetime
import hashlib
import json
import os
import re
import shlex
import signal
import sys
import time

import threading
import getpass
import tempfile
from pathlib import Path

try:                                    # POSIX only; absent on Windows
    import pwd
except ImportError:                     # pragma: no cover - platform branch
    pwd = None


def _account_home():
    """Home directory from the OS account database when available, else ~ expansion."""
    if pwd is not None:
        try:
            return pwd.getpwuid(os.getuid()).pw_dir
        except (KeyError, OSError):
            pass
    return os.path.expanduser("~")


def _account_name():
    """Login name from the OS account database when available, else the platform default."""
    if pwd is not None:
        try:
            return pwd.getpwuid(os.getuid()).pw_name
        except (KeyError, OSError):
            pass
    return getpass.getuser()


def _tmp_prefix_default():
    """Per-user scratch prefix. POSIX keeps the historical /tmp form; Windows uses %TEMP%."""
    if os.name == "nt":
        return os.path.join(tempfile.gettempdir(), _account_name() + "-")
    return "/tmp/%s-" % _account_name()


# ---------------------------------------------------------------- configuration (files only)
# The gate reads its configuration ONLY from protected files: config/paths.env + config/local.env
# next to this script. Environment variables are deliberately ignored here — the agent can influence
# the environment (e.g. an approved .env edit picked up by a launcher), so env must not widen the gate.
# Tests and special setups pass --policy / --policy-local / --data on the hook command line, which
# lives in the (protected) agent config.

def _parse_env_file(path):
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                if "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


HOME = _account_home()                       # not $HOME (env)
ROOT = Path(__file__).resolve().parents[1]       # repo root (not $CBP_ROOT)
_REL = _parse_env_file(ROOT / "config" / "paths.env")
GATE_CFG = _parse_env_file(ROOT / "config" / "local.env")


def _home_expand(v):
    """'~' in config values = the passwd home, never $HOME from the (agent-influenced) environment."""
    return re.sub(r"^~(?=/|$)", HOME.replace("\\", "\\\\"), v)


def _cfg(key, default=""):
    return GATE_CFG.get(key) or default


def _path(key, default_rel):
    v = GATE_CFG.get(key)
    return Path(_home_expand(v)) if v else ROOT / _REL.get(key, default_rel)


P = {k: _path(k, v) for k, v in _REL.items()}
for _k, _d in (("CBP_DATA", "data"), ("CBP_CONFIG", "config"), ("CBP_TMP", ".tmp")):
    P.setdefault(_k, _path(_k, _d))
CLI_HOME = Path(_home_expand(_cfg("CBP_CLI_HOME", os.path.join(HOME, ".codebuddy"))))


def tz():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(_cfg("CBP_TZ", "UTC"))
    except Exception:
        return datetime.timezone.utc


LAB = str(ROOT)
DATA = str(P["CBP_DATA"])
POLICY_PATH = os.path.join(LAB, ".codebuddy/rules/gate-policy.json")
DATA_DIR = os.path.join(DATA, "gate")
# Personal / site-specific additions (gitignored, protected): see contexts/tips/tools/action-gate.md
POLICY_LOCAL = os.path.join(str(P["CBP_CONFIG"]), "gate-policy.local.json")
DEADLINE_SEC = 1.5
MAX_DEPTH = 8
TZ = tz()  # CBP_TZ (config/local.env)

SEVERITY = {"L0": 0, "L1": 1, "L2": 2, "L3": 3, "DENY": 4}
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
SECRET_RE = re.compile(r"(?i)(token|password|passwd|secret|authorization|api[_-]?key)"
                       r"(\s*[=:]\s*|\s+)((?:bearer|basic)\s+)?(\S+)")
HD_RE = re.compile(r"__HEREDOC_(\d+)__")
ASSIGN_RE = re.compile(r"[A-Za-z_]\w*=.*")
DURATION_RE = re.compile(r"[\d.]+[smhd]?")
DEV_PATHS = ("/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty")

SHELLS = {"bash", "sh", "zsh", "ksh", "dash"}
INTERP_RE = re.compile(r"^(python[\d.]*|perl|ruby|node)$")
KEYWORDS = {"{", "}", "!", "if", "then", "else", "elif", "do", "while", "until", "fi", "done", "esac", "coproc"}
LOOP_HEADERS = {"for", "select", "case", "function"}
# wrapper command -> options that take a separate value
WRAPPERS = {
    "nohup": set(), "nice": {"-n", "--adjustment"}, "time": {"-f", "-o"}, "command": set(),
    "builtin": set(), "exec": {"-a"}, "stdbuf": {"-i", "-o", "-e"}, "setsid": set(),
    "ionice": {"-c", "-n", "-p", "-P", "-u"}, "chronic": set(), "unbuffer": set(),
    "timeout": {"-s", "-k", "--signal", "--kill-after"}, "watch": {"-n", "-d", "--interval"},
    "xargs": {"-I", "-n", "-P", "-d", "-L", "-s", "-E", "-a"}, "env": {"-u", "-C", "--unset", "--chdir"},
}
SSH_VALUE_OPTS = set("bcDEeFIiJLlmOopQRSWw")
# commands whose (non-option) args are all files they modify
MODIFY_ALL_ARGS = {"rm", "rmdir", "unlink", "shred", "mkdir", "touch", "chmod", "chown", "truncate", "tee", "mv"}
# commands whose last arg is the file they write
MODIFY_LAST_ARG = {"cp", "install", "ln", "rsync", "scp"}
FILE_ARG_CMDS = MODIFY_ALL_ARGS | MODIFY_LAST_ARG | {"sed"}
# commands whose write targets we compute precisely (protected *source* args are fine)
KNOWN_WRITE_CMDS = FILE_ARG_CMDS | {"git", "tar", "unzip", "cat", "grep", "diff", "wc", "head", "tail"}


class GateTimeout(Exception):
    pass


# ---------------------------------------------------------------- deadline (fail closed, cross-platform)
# POSIX: SIGALRM + setitimer arms a hard deadline around the whole decision. Windows has neither,
# so the deadline is enforced on the only unbounded step there — reading the hook payload from stdin.

_HAS_ALARM = hasattr(signal, "SIGALRM") and hasattr(signal, "setitimer")

# Enforcement compares POSIX-style paths taken from the command string against policy roots derived
# with os.path.realpath. On Windows those two disagree (C:\\Users\\x vs /c/Users/x), so path rules can
# silently under-match. Rather than block on a comparison we cannot trust, the gate degrades to
# record-only there and says so loudly. Run the gate on a POSIX host (or WSL) for real enforcement.
ENFORCE_SUPPORTED = os.name != "nt"


def _warn_degraded(agent, tool):
    """Tell the user once per session that this platform cannot enforce, then keep logging."""
    marker = os.path.join(DATA_DIR, ".degraded-warned-%s" % (os.environ.get("CBP_SESSION_ID") or "local"))
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        if os.path.exists(marker):
            return
        with open(marker, "w", encoding="utf-8") as f:
            f.write("1")
    except OSError:
        return
    sys.stderr.write(
        "GATE NOT ENFORCING on this platform (Windows path semantics): %s/%s was only recorded. "
        "Policy still classifies, but nothing is blocked. Use a POSIX host or WSL for enforcement; "
        "review with `cbp-gate tail`.\n" % (agent, tool))


def _raise_gate_timeout(signum, frame):
    raise GateTimeout()


def _arm_deadline(sec):
    if _HAS_ALARM:
        signal.signal(signal.SIGALRM, _raise_gate_timeout)
        signal.setitimer(signal.ITIMER_REAL, sec)


def _disarm_deadline():
    if _HAS_ALARM:
        signal.setitimer(signal.ITIMER_REAL, 0)


def _read_payload(sec):
    """sys.stdin.read() bounded by `sec` on platforms without SIGALRM."""
    if _HAS_ALARM:
        return sys.stdin.read()
    box = {}

    def _read():
        try:
            box["raw"] = sys.stdin.read()
        except BaseException as e:          # surfaced to the caller on the main thread
            box["err"] = e

    t = threading.Thread(target=_read, daemon=True)
    t.start()
    t.join(sec)
    if t.is_alive():
        raise GateTimeout()
    if "err" in box:
        raise box["err"]
    return box.get("raw", "")


# ---------------------------------------------------------------- policy

def _split(v):
    return [x.strip() for x in re.split(r"[:,]", v or "") if x.strip()]


def _abs(p):
    p = _home_expand(p)
    return p if os.path.isabs(p) else os.path.join(HOME, p)


def _dir_re(p):
    """Regex for a directory: absolute form, plus '~/...' form when under $HOME."""
    p = os.path.realpath(p).rstrip("/")
    alts = [re.escape(p)]
    if p.startswith(HOME + "/"):
        alts.append(re.escape("~" + p[len(HOME):]))
    return "(?:%s)" % "|".join(alts)


def _check_roots(tmp, scratch, allow):
    """Refuse config that would widen the allow-lists to everything (raise → load fails → fail-closed)."""
    too_broad = {"/"} | {os.path.realpath(x) for x in (HOME, str(ROOT), str(CLI_HOME))}
    for d in (HOME, str(ROOT), str(CLI_HOME)):           # ...and every ancestor of them
        d = os.path.realpath(d)
        while True:                                     # portable: stop when the parent stops changing
            parent = os.path.dirname(d)                 # ("C:\\" has no "/" terminator on Windows)
            if parent == d:
                break
            d = parent
            too_broad.add(d)
    ancestors = too_broad - {os.path.realpath(x) for x in (HOME, str(ROOT), str(CLI_HOME))}
    for p in scratch:          # scratch = L1 deletes: never a whole home / repo / CLI dir
        if os.path.realpath(p.rstrip("/") or "/") in too_broad:
            raise ValueError("gate-policy: %r is too broad for CBP_SCRATCH_DIRS" % p)
    for p in allow:            # allow-list only lifts DENY → L3 (still needs approval); $HOME is OK, '/' is not
        if os.path.realpath(p.rstrip("/") or "/") in ancestors:
            raise ValueError("gate-policy: %r is too broad for CBP_DELETE_ALLOW" % p)
    head, last = os.path.split(tmp)
    covered = [x for x in (HOME, str(ROOT), str(CLI_HOME)) if os.path.realpath(x).startswith(tmp)]
    rootish = head in ("", "/") or os.path.dirname(head) == head   # a bare root, either platform
    absolute = tmp.startswith("/") or os.path.isabs(tmp)           # POSIX form stays valid on Windows
    if not absolute or not last or rootish or covered:
        raise ValueError("gate-policy: CBP_TMP_PREFIX must look like /tmp/<name>- (got %r)" % tmp)


def policy_vars():
    """Values for {{PLACEHOLDERS}} in gate-policy.json — all machine-specific, never in the repo.

    Sources: config/paths.env + config/local.env + environment (see config/local.env.example).
    """
    tmp = _cfg("CBP_TMP_PREFIX") or _tmp_prefix_default()
    scratch = [_abs(p).rstrip("/") + "/" for p in _split(_cfg("CBP_SCRATCH_DIRS"))]
    runtime = [str(P[k]) for k in ("CBP_HISTORY", "CBP_PENDING", "CBP_LOGS", "CBP_DATA", "CBP_DOCS",
                                     "CBP_ARCHIVE", "CBP_BUILD", "CBP_TMP") if k in P]
    allow = [_abs(p) for p in _split(_cfg("CBP_DELETE_ALLOW"))] or runtime
    emails = _split(_cfg("CBP_SELF_EMAILS")) or _split(_cfg("CBP_USER_EMAIL"))
    agents = _split(_cfg("CBP_GATED_AGENTS")) or ["pure", "reviewer", "html-generator", "health-checker"]
    _check_roots(tmp, scratch, allow)
    ok = ["^" + _dir_re(p) + "(/|$)" for p in allow + scratch] + ["^" + re.escape(tmp)]
    return {
        "HOME": HOME, "CBP_ROOT": str(ROOT), "CLI_HOME": str(CLI_HOME), "CBP_DATA": DATA,
        "CBP_TMP": str(P["CBP_TMP"]),
        "TMP_PREFIX": tmp, "SCRATCH_DIRS": scratch, "SELF_EMAILS": emails, "GATED_AGENTS": agents,
        "HOME_RE": re.escape(HOME), "CBP_ROOT_RE": _dir_re(str(ROOT)), "CLI_HOME_RE": _dir_re(str(CLI_HOME)),
        "GATED_AGENTS_RE": "|".join(re.escape(a) for a in agents),
        "DELETE_OK_RE": "|".join(ok),
    }


def expand_policy(obj, v):
    """Expand {{KEY}} recursively. A list item that is exactly {{KEY}} with a list value is spliced.
    Unknown keys raise → load fails → gate fails closed. Keys starting with '_' are left as-is."""
    def s(x):
        def sub(m):
            if m.group(1) not in v:
                raise ValueError("gate-policy: unknown placeholder {{%s}}" % m.group(1))
            val = v[m.group(1)]
            if isinstance(val, list):
                raise ValueError("gate-policy: list placeholder {{%s}} must be a whole list item" % m.group(1))
            return val
        return re.sub(r"\{\{([A-Z_]+)\}\}", sub, x)
    if isinstance(obj, dict):
        return {k: (val if k.startswith("_") else expand_policy(val, v)) for k, val in obj.items()}
    if isinstance(obj, list):
        out = []
        for it in obj:
            m = re.fullmatch(r"\{\{([A-Z_]+)\}\}", it) if isinstance(it, str) else None
            if m and isinstance(v.get(m.group(1)), list):
                out.extend(v[m.group(1)])
            else:
                out.append(expand_policy(it, v))
        return out
    return s(obj) if isinstance(obj, str) else obj


OVERLAY_SCALARS = ("mode", "l2_default", "approval_ttl_sec")
# Overrides may re-target a rule (which tool / command it matches) but never change its level,
# and DENY / builtin rules are off-limits. Extra overlay rules can only *add* matches (the highest
# matching severity wins), so they cannot lower anything.
OVERRIDE_KEYS = {"tool", "cmd", "unless_cmd", "unless_tool", "wpath_match", "argv_any", "note"}


def read_overlay(path=None):
    """config/gate-policy.local.json — personal rules kept out of the shared policy. {} if absent."""
    path = path or POLICY_LOCAL
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        ov = json.load(f)
    bad = set(ov) - set(OVERLAY_SCALARS) - {"rules", "rule_overrides", "_comment"}
    if bad:
        raise ValueError("gate-policy.local: unknown keys %s" % sorted(bad))
    return ov


def merge_overlay(base, ov):
    """Overlay scalars win; overlay rules go *before* base rules (same level → their id is reported);
    rule_overrides patch base rules by id (unknown id → error → fail-closed)."""
    pol = dict(base)
    for k in OVERLAY_SCALARS:
        if k in ov:
            pol[k] = ov[k]
    rules = [dict(r) for r in base["rules"]]
    by_id = {r["id"]: r for r in rules}
    for rid, patch in (ov.get("rule_overrides") or {}).items():
        if rid not in by_id:
            raise ValueError("gate-policy.local: rule_overrides for unknown rule %r" % rid)
        base_r = by_id[rid]
        if base_r.get("level") == "DENY" or base_r.get("builtin"):
            raise ValueError("gate-policy.local: rule %r cannot be overridden (DENY / builtin)" % rid)
        bad = set(patch) - OVERRIDE_KEYS
        if bad:
            raise ValueError("gate-policy.local: rule_overrides[%r] may only set %s (got %s)"
                             % (rid, sorted(OVERRIDE_KEYS), sorted(bad)))
        base_r.update(patch)
    extra = list(ov.get("rules") or [])
    clash = {r.get("id") for r in extra} & set(by_id)
    if clash:
        raise ValueError("gate-policy.local: rule ids already in base policy: %s" % sorted(clash))
    pol["rules"] = extra + rules
    return pol


def load_policy(path=None, variables=None, local=None):
    """Base policy (shared template) + local overlay, placeholders expanded. local=False → base only."""
    with open(path or POLICY_PATH) as f:
        base = json.load(f)
    raw = base if local is False else merge_overlay(base, read_overlay(local))
    pol = expand_policy(raw, variables or policy_vars())
    for r in pol["rules"]:
        r["_tool"] = re.compile(r["tool"])
        for k in ("cmd", "unless_cmd", "wpath_match", "paths_outside_re", "unless_tool", "argv_any"):
            if r.get(k):
                r["_" + k] = re.compile(r[k], re.S)
        if r["level"] not in SEVERITY or r["level"] == "L2":
            raise ValueError("rule %s: bad level %s" % (r["id"], r["level"]))
    pol["_roots"] = {k: [_norm_root(p) for p in pol.get(k, [])]
                     for k in ("write_roots", "delete_roots", "protected_paths")}
    prot = pol["_roots"]["protected_paths"]
    pol["_protected_strs"] = sorted({s for p in prot for s in (p, p.replace(HOME, "~", 1))})
    pol["_self_emails"] = {e.lower() for e in pol.get("self_emails", [])}
    if pol.get("mode") not in ("shadow", "enforce"):
        raise ValueError("gate-policy: mode must be shadow|enforce (got %r)" % pol.get("mode"))
    if pol.get("l2_default", "allow") not in ("allow", "block"):
        raise ValueError("gate-policy: l2_default must be allow|block (got %r)" % pol.get("l2_default"))
    ttl = pol.get("approval_ttl_sec", 600)
    if not isinstance(ttl, int) or isinstance(ttl, bool) or not 1 <= ttl <= 3600:
        raise ValueError("gate-policy: approval_ttl_sec must be an int in 1..3600 (got %r)" % ttl)
    return pol


def _norm_root(p):
    """Resolve symlinks but keep trailing '/' or prefix semantics ('/tmp/<user>-')."""
    p = _home_expand(p)
    if p.endswith("/"):
        return os.path.realpath(p) + "/"
    head, tail = os.path.split(p)
    return os.path.join(os.path.realpath(head), tail)


# ---------------------------------------------------------------- shell parsing

def _preprocess(cmd, bodies):
    """Quote-aware pass over the raw command:
    - drop comments ('#' starting a word, outside quotes)
    - replace each unquoted heredoc operator with a __HEREDOC_n__ marker and cut its body
      into bodies[n] (body lines are removed from the command text)."""
    lines = cmd.split("\n")
    out, q, li = [], None, 0
    while li < len(lines):
        line = lines[li]
        li += 1
        buf, pending, i, n = [], [], 0, len(line)
        while i < n:
            c = line[i]
            if q is None:
                if c == "\\" and i + 1 < n:
                    buf.append(line[i:i + 2]); i += 2; continue
                if c in "'\"":
                    q = c; buf.append(c); i += 1; continue
                if c == "#" and (i == 0 or line[i - 1] in " \t;&|()"):
                    break
                if line.startswith("<<", i) and not line.startswith("<<<", i):
                    j, strip = i + 2, False
                    if j < n and line[j] == "-":
                        strip, j = True, j + 1
                    while j < n and line[j] in " \t":
                        j += 1
                    m = re.match(r"""(['"]?)\\?([A-Za-z_][\w.-]*)\1""", line[j:])
                    if m:
                        idx = len(bodies)
                        bodies.append("")
                        pending.append((idx, m.group(2), strip))
                        buf.append(" __HEREDOC_%d__ " % idx)
                        i = j + m.end()
                        continue
                buf.append(c); i += 1; continue
            if q == "'":
                if c == "'":
                    q = None
                buf.append(c); i += 1; continue
            if c == "\\" and i + 1 < n:  # inside double quotes
                buf.append(line[i:i + 2]); i += 2; continue
            if c == '"':
                q = None
            buf.append(c); i += 1
        out.append("".join(buf))
        for idx, delim, strip in pending:
            body = []
            while li < len(lines):
                ln = lines[li]
                li += 1
                if (ln.lstrip("\t") if strip else ln) == delim:
                    break
                body.append(ln)
            bodies[idx] = "\n".join(body)
    return "\n".join(out)


def _extract_subshells(cmd):
    """Return (outer_cmd_with_placeholders, [inner_cmds]) for $(...) and `...`."""
    inner = []
    for _ in range(5):  # nested $( ) up to depth 5
        new = re.sub(r"\$\(([^()]*)\)", lambda m: (inner.append(m.group(1)), "__SUBSHELL__")[1], cmd)
        new = re.sub(r"`([^`]*)`", lambda m: (inner.append(m.group(1)), "__SUBSHELL__")[1], new)
        if new == cmd:
            break
        cmd = new
    return cmd, inner


def split_shell(cmd, depth=0, bodies=None):
    """Split a shell command line into segments: list of dicts
    {argv:[...], redirects:[targets], text:str}. Raises ValueError if unparseable."""
    if depth > MAX_DEPTH:
        raise ValueError("nesting too deep")
    bodies = [] if bodies is None else bodies
    cmd = cmd.replace("\\\n", " ")
    cmd = _preprocess(cmd, bodies)
    cmd, inner = _extract_subshells(cmd)
    segs = []
    for sub in inner:
        segs.extend(split_shell(sub, depth + 1, bodies))
    lex = shlex.shlex(cmd.replace("\n", " ; "), posix=True, punctuation_chars=";&|<>()")
    lex.whitespace_split = True
    lex.commenters = ""  # comments already removed quote-aware
    tokens = list(lex)  # ValueError on unbalanced quotes
    tokens.append(";")
    cur, redirects, expect = [], [], None
    for i, tok in enumerate(tokens):
        if tok and set(tok) <= set(";&|()"):
            if cur or redirects:
                segs.extend(_finish_segment(cur, redirects, bodies, depth))
            cur, redirects, expect = [], [], None
            continue
        if tok and set(tok) <= set("<>&"):
            expect = tok
            continue
        if expect is not None:
            if expect == "<<<":  # here-string: treat like a one-line heredoc
                bodies.append(tok)
                cur.append("__HEREDOC_%d__" % (len(bodies) - 1))
            elif ">" in expect and not tok.isdigit():
                redirects.append(tok)
            expect = None
            continue
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        if tok.isdigit() and nxt and set(nxt) <= set("<>&") and nxt != "&":
            continue  # fd number of a redirect (2>, 2>&1)
        cur.append(tok)
    return segs


def _strip_wrappers(argv):
    while argv:
        while argv and ASSIGN_RE.fullmatch(argv[0]):
            argv.pop(0)
        while argv and argv[0] in KEYWORDS:
            argv.pop(0)
        if not argv:
            break
        base = os.path.basename(argv[0])
        if base not in WRAPPERS:
            break
        argv.pop(0)
        vopts = WRAPPERS[base]
        while argv and argv[0].startswith("-") and argv[0] != "-":
            opt = argv.pop(0)
            if opt == "--":
                break
            if opt in vopts and argv:
                argv.pop(0)
        if base == "timeout" and argv and DURATION_RE.fullmatch(argv[0]):
            argv.pop(0)
    return argv


def _shell_script(argv):
    """For bash/sh argv: return (script_string_or_None, has_operand)."""
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "--":
            i += 1
            break
        if a.startswith("--"):
            i += 1; continue
        if a in ("-o", "+o", "-O", "+O"):
            i += 2; continue
        if a[:1] in "-+" and len(a) > 1:
            if "c" in a[1:]:
                return (argv[i + 1] if i + 1 < len(argv) else ""), True
            i += 1; continue
        break
    return None, i < len(argv) and argv[i] != "-"


def _redir_only(redirects):
    return [_seg(["true"], redirects)] if redirects else []


def _finish_segment(argv, redirects, bodies, depth):
    hd = [bodies[int(m.group(1))] for m in (HD_RE.fullmatch(t) for t in argv)
          if m and int(m.group(1)) < len(bodies)]
    argv = _strip_wrappers([t for t in argv if not HD_RE.fullmatch(t)])
    if not argv or argv[0] in LOOP_HEADERS:
        return _redir_only(redirects)
    base = os.path.basename(argv[0])
    sub = lambda text: split_shell(text, depth + 1, bodies)  # noqa: E731

    if base == "eval":
        return sub(" ".join(argv[1:])) + _redir_only(redirects)
    if base == "flock":
        rest = argv[1:]
        while rest and rest[0].startswith("-") and rest[0] not in ("-c", "--command"):
            opt = rest.pop(0)
            if opt in ("-w", "-E", "--timeout", "--conflict-exit-code") and rest:
                rest.pop(0)
        if rest and rest[0] not in ("-c", "--command"):
            rest.pop(0)  # lock file
        if rest and rest[0] in ("-c", "--command"):
            return sub(rest[1] if len(rest) > 1 else "") + _redir_only(redirects)
        return _finish_segment(rest, redirects, bodies, depth + 1) if rest else _redir_only(redirects)
    if base in SHELLS:
        script, has_operand = _shell_script(argv)
        if script is not None:
            return sub(script) + _redir_only(redirects)
        if hd:
            out = []
            for b in hd:
                out.extend(sub(b))
            return out + _redir_only(redirects)
        if not has_operand:
            return [_seg(["__shell_stdin__"] + argv, redirects)]
        return [_seg(argv, redirects)]
    if INTERP_RE.match(base) and hd:
        return [_seg(argv, redirects)] + [_seg(["__interp_body__", b], []) for b in hd]
    if base == "find":
        roots = []
        for t in argv[1:]:
            if t.startswith("-") or t in ("(", "!", ")"):
                break
            roots.append(t)
        rep = roots[0] if roots else "."
        main, subs, i = [], [], 0
        while i < len(argv):
            t = argv[i]
            if t in ("-exec", "-execdir", "-ok", "-okdir"):
                j, inner = i + 1, []
                while j < len(argv) and argv[j] not in (";", "+"):
                    inner.append(argv[j].replace("{}", rep))
                    j += 1
                if inner:
                    subs.extend(_finish_segment(inner, [], bodies, depth + 1))
                i = j + 1
                continue
            main.append(t)
            i += 1
        return [_seg(main, redirects)] + subs
    if base == "ssh":
        i = 1
        while i < len(argv) and argv[i].startswith("-"):
            a = argv[i]
            i += 2 if (len(a) == 2 and a[1] in SSH_VALUE_OPTS) else 1
        if i + 1 < len(argv):
            return sub(" ".join(argv[i + 1:])) + _redir_only(redirects)
        return [_seg(argv, redirects)]
    return [_seg(argv, redirects)]


def _seg(argv, redirects):
    if argv and argv[0] == "__interp_body__":
        return {"argv": argv, "redirects": [], "text": "__interp_body__ " + (argv[1] if len(argv) > 1 else "")}
    head = argv[0]
    if head.startswith("/") and not head.startswith(HOME + "/"):
        head = os.path.basename(head)  # /usr/bin/rm -> rm (keep our own bins as full paths)
    return {"argv": argv, "redirects": redirects, "text": " ".join([head] + argv[1:])}


# ---------------------------------------------------------------- path extraction

def _resolve(tok, cwd):
    """Absolute real path, or None if unknown ($VAR, subshell, relative with unknown cwd)."""
    if "$" in tok or "__SUBSHELL__" in tok or HD_RE.search(tok):
        return None
    p = os.path.expanduser(tok)
    if not os.path.isabs(p):
        if cwd is None:
            return None
        p = os.path.join(cwd, p)
    try:
        return os.path.realpath(p)
    except OSError:
        return os.path.normpath(p)


GLOB_CHARS = set("*?[{")


def _target_dir(argv):
    """Return the -t/--target-directory value (also inside short clusters like -at DIR, -rtDIR), else None."""
    for i, a in enumerate(argv[1:], 1):
        if a == "--":
            break
        if a == "--target-directory" and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith("--target-directory="):
            return a.split("=", 1)[1]
        if a.startswith("-") and not a.startswith("--") and "t" in a[1:]:
            rest = a[a.index("t", 1) + 1:]
            if rest:
                return rest
            if i + 1 < len(argv):
                return argv[i + 1]
    return None
# an s command can only start at script start, after ; newline { } ! or after an address (digit, $, /re/, ,)
SED_S_RE = re.compile(r"(?:^|(?<=[;\n{}!$0-9/,\s]))s([^\s\\\n])(?:\\.|(?!\1).)*\1(?:\\.|(?!\1).)*\1"
                      r"([gpiImMe0-9]*)(?:[wW]\s+([^\n;}]+))?")
SED_W_RE = re.compile(r"(?:^|[;\n{}!$,/0-9\s])[wW]\s+([^\n;}]+)")


def _sed_inplace(args):
    for a in args:
        if a.startswith("--in-place"):
            return True
        if a.startswith("-") and not a.startswith("--") and "i" in a[1:].split("=")[0]:
            # -i, -i.bak, -ni, -Ei ... ('i' inside a short-option cluster); -f/-e take values, not clusters
            if a[1:2] not in ("e", "f") or a[1:2] == "i":
                return True
    return False


def _sed_scripts(args):
    out, i, first = [], 0, True
    while i < len(args):
        a = args[i]
        if a in ("-e", "--expression") and i + 1 < len(args):
            out.append(args[i + 1]); first = False; i += 2; continue
        if a.startswith("--expression="):
            out.append(a.split("=", 1)[1]); first = False; i += 1; continue
        if a in ("-f", "--file"):
            first = False; i += 2; continue
        if a.startswith("-") and a != "-":
            i += 1; continue
        if first:
            out.append(a)
        break
    return out


def _sed_wfiles(args):
    files = []
    for sc in _sed_scripts(args):
        rest = []
        pos = 0
        sc = re.sub(r"((?:^|[;\n{}!$,/0-9\s])[wW]\s+)([^\n;}]+)",
                    lambda m: (files.append(m.group(2).strip()), m.group(1) + "__WFILE__")[1], sc) \
            if not SED_S_RE.search(sc) else sc
        for m in SED_S_RE.finditer(sc):  # pull s/// out so its text isn't misread as a w command
            rest.append(sc[pos:m.start()] + " ")
            pos = m.end()
            if m.group(3):
                files.append(m.group(3).strip())
        rest.append(sc[pos:])
        for m in SED_W_RE.finditer("".join(rest)):
            files.append(m.group(1).strip())
    return [f for f in files if f and f not in DEV_PATHS]


def _sed_has_script_file(args):
    return any(a in ("-f", "--file") or a.startswith("--file=") for a in args)


def _sed_files(args):
    files, have_script, i = [], False, 0
    while i < len(args):
        a = args[i]
        if a in ("-e", "--expression", "-f", "--file"):
            have_script = True; i += 2; continue
        if a.startswith(("--expression=", "--file=")):
            have_script = True; i += 1; continue
        if a.startswith("-") and a != "-":
            i += 1; continue
        if not have_script:
            have_script = True; i += 1; continue  # the script itself
        files.append(a)
        i += 1
    return files


def segment_paths(seg, cwd):
    """Return dict with
      paths  : all path-like args + redirect targets (resolved)
      dpaths : paths excluding an interpreter's program file
      wpaths : paths the command writes/removes (redirects, modify-args)
      unknown: some path could not be resolved
      rel_unknown_cwd: a relative path while cwd is unknown"""
    argv = seg["argv"]
    cmd = os.path.basename(argv[0]) if argv else ""
    res = {"paths": [], "dpaths": [], "wpaths": [], "wtrees": [], "unknown": False,
           "rel_unknown_cwd": False,
           "known_writes": cmd in KNOWN_WRITE_CMDS and not (cmd == "sed" and _sed_has_script_file(argv[1:]))}
    if cmd in ("__interp_body__", "__shell_stdin__"):
        args = []
    elif cmd == "sed":
        args = _sed_files(argv[1:]) + _sed_wfiles(argv[1:])
    elif cmd == "dd":
        args = [a.split("=", 1)[1] for a in argv[1:] if a.startswith(("if=", "of=")) and "=" in a]
    else:
        args = argv[1:]
    cands = []
    for tok in args:
        if tok.startswith("-") and cmd != "sed":
            if "=" in tok:
                tok = tok.split("=", 1)[1]
            else:
                continue
        if not tok or "://" in tok or EMAIL_RE.fullmatch(tok):
            continue
        looks_path = tok.startswith(("/", "~", "./", "../")) or "/" in tok or tok in (".", "..")
        if cmd == "sed" or looks_path or (cmd in FILE_ARG_CMDS and not re.fullmatch(r"[0-7]{3,4}|[ugoa]*[-+=][rwxXst]+", tok)):
            if ":" in tok and cmd in ("scp", "rsync") and not tok.startswith("/"):
                continue  # remote host:path
            cands.append(tok)
    program = None
    if (INTERP_RE.match(cmd) or cmd in SHELLS) and cands and cands[0] == next((a for a in args if not a.startswith("-")), None):
        program = cands[0]
    writes = set()
    sed_inplace = cmd == "sed" and _sed_inplace(argv[1:])
    if cmd in MODIFY_ALL_ARGS or sed_inplace:
        writes = set(cands)
    elif cmd == "sed":
        writes = set(_sed_wfiles(argv[1:]))
    elif cmd == "dd":
        writes = {a.split("=", 1)[1] for a in argv[1:] if a.startswith("of=")}
    elif cmd in MODIFY_LAST_ARG and cands and _target_dir(argv) is None:
        writes = {cands[-1]}  # with -t DIR the target is handled by _dir_targets
    for tok in cands + list(seg["redirects"]):
        if tok in DEV_PATHS:
            continue
        r = _resolve(tok, cwd)
        if r is None:
            res["unknown"] = True
            if cwd is None and not tok.startswith(("/", "~")) and "$" not in tok:
                res["rel_unknown_cwd"] = True
            continue
        res["paths"].append(r)
        if tok != program:
            res["dpaths"].append(r)
        if tok in writes or tok in seg["redirects"]:
            res["wpaths"].append(r)
    _dir_targets(cmd, argv, cands, cwd, res)
    return res


def _dir_targets(cmd, argv, cands, cwd, res):
    """Copy/move/extract into a directory writes target/basename(src) (or a whole tree)."""
    opts = [a for a in argv[1:] if a.startswith("-")]
    recursive = cmd in ("mv", "rsync") or any(
        a in ("-r", "-R", "-a", "--recursive", "--archive") or (not a.startswith("--") and set(a[1:]) & set("rRa"))
        for a in opts)
    if cmd in MODIFY_LAST_ARG | {"mv"}:
        tdir = _target_dir(argv)
        no_target_dir = any(a == "-T" or a == "--no-target-directory" or
                            (a.startswith("-") and not a.startswith("--") and "T" in a[1:]) for a in opts)
        if tdir is not None:
            srcs = [c for c in cands if c != tdir]
            tgt_tok = tdir
        elif len(cands) >= 2:
            srcs, tgt_tok = cands[:-1], cands[-1]
        else:
            return
        tgt = _resolve(tgt_tok, cwd)
        if tgt is None:
            res["unknown"] = True
            return
        if tgt not in res["wpaths"]:
            res["wpaths"].append(tgt)
        broad = any(set(sx) & GLOB_CHARS or sx.endswith(("/.", "/")) for sx in srcs)
        if no_target_dir or broad and (recursive or cmd == "mv" or tdir is not None or os.path.isdir(tgt)
                                       or tgt_tok.endswith("/")):
            res["wtrees"].append(tgt)  # contents land directly in tgt (or unknown file names)
            if not no_target_dir:
                return
        if no_target_dir:
            return
        if cmd == "rsync" or tdir is not None or tgt_tok.endswith("/") or os.path.isdir(tgt):
            for src in srcs:
                if cmd == "rsync" and src.endswith("/"):
                    dest = tgt  # rsync src/ dst/ copies the contents
                else:
                    dest = os.path.join(tgt, os.path.basename(src.rstrip("/")) or ".")
                res["wpaths"].append(dest)
                if recursive:
                    res["wtrees"].append(dest)
        elif recursive:
            res["wtrees"].append(tgt)
        return
    if cmd == "tar" and any(re.match(r"^-?[A-Za-z]*x", a) for a in argv[1:2]) or (cmd == "tar" and "--extract" in argv):
        d = cwd
        for i, a in enumerate(argv):
            if a in ("-C", "--directory") and i + 1 < len(argv):
                d = _resolve(argv[i + 1], cwd)
            elif a.startswith("--directory="):
                d = _resolve(a.split("=", 1)[1], cwd)
        if d is None:
            res["unknown"] = True
        else:
            res["wtrees"].append(d)
    elif cmd == "unzip":
        d = cwd
        if "-d" in argv and argv.index("-d") + 1 < len(argv):
            d = _resolve(argv[argv.index("-d") + 1], cwd)
        if d is None:
            res["unknown"] = True
        else:
            res["wtrees"].append(d)


def _under(path, roots):
    return any(path == r.rstrip("/") or path.startswith(r) for r in roots)


def _inside(path, roots):
    """Strictly inside a root, and not the root's whole top level (root/*)."""
    for r in roots:
        if path.startswith(r) and path != r.rstrip("/"):
            rest = path[len(r):]
            if rest and not rest.startswith("*") and rest not in ("/", "/*"):
                return True
    return False


# ---------------------------------------------------------------- classification

def _strip_purpose(tool_input):
    if isinstance(tool_input, dict):
        return {k: v for k, v in tool_input.items() if k != "__tool_use_purpose"}
    return tool_input


def action_id(tool_name, tool_input, cwd=""):
    canon = json.dumps([tool_name, _strip_purpose(tool_input), cwd or ""], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canon.encode()).hexdigest()


def _roots(pol, key):
    return pol["_roots"][key] if isinstance(key, str) else [_norm_root(p) for p in key]


def _rule_matches(r, tool_name, u, pol):
    """u: unit dict {text, paths, dpaths, wpaths, unknown, modify, emails}"""
    if r.get("builtin") or not r["_tool"].fullmatch(tool_name):
        return False
    if r.get("_unless_tool") and r["_unless_tool"].fullmatch(tool_name):
        return False
    text = u["text"]
    if r.get("_cmd") and not r["_cmd"].search(text):
        return False
    if r.get("_unless_cmd") and r["_unless_cmd"].search(text):
        return False
    if r.get("applies") == "modify" and not u["modify"]:
        return False
    if r.get("wpath_in") and not any(_under(p, _roots(pol, r["wpath_in"])) for p in u["wpaths"]):
        return False
    if r.get("dpath_in") and not any(_under(p, _roots(pol, r["dpath_in"])) for p in u["dpaths"]):
        return False
    if r.get("unknown_write_semantics") and u.get("known_writes"):
        return False
    if r.get("wtree_covers"):
        prot = _roots(pol, r["wtree_covers"])
        if not any(_under(pr.rstrip("/"), [t.rstrip("/") + "/"]) or pr.rstrip("/") == t.rstrip("/")
                   or _under(t, [pr]) for t in u.get("wtrees", []) for pr in prot):
            return False
    if r.get("_argv_any") and not any(r["_argv_any"].fullmatch(a) for a in u.get("argv", [])[1:]):
        return False
    if r.get("_wpath_match") and not any(r["_wpath_match"].search(p) for p in u["wpaths"]):
        return False
    if r.get("_paths_outside_re") and not any(not r["_paths_outside_re"].search(p) for p in u["paths"]):
        return False
    if r.get("paths_any_outside"):
        roots = _roots(pol, r["paths_any_outside"])
        if not (u["unknown"] or any(not _under(p, roots) for p in u["paths"])):
            return False
    if r.get("paths_under"):
        roots = _roots(pol, r["paths_under"])
        if u["unknown"] or not all(_under(p, roots) for p in u["paths"]):
            return False
    if r.get("paths_inside"):
        roots = _roots(pol, r["paths_inside"])
        if u["unknown"] or not u["paths"] or not all(_inside(p, roots) for p in u["paths"]):
            return False
    if r.get("unless_paths_inside"):
        roots = _roots(pol, r["unless_paths_inside"])
        if not u["unknown"] and u["paths"] and all(_inside(p, roots) for p in u["paths"]):
            return False
    if r.get("text_mentions") and not any(s in text for s in pol["_protected_strs"]):
        return False
    if r.get("emails_subset_of"):
        if not u["emails"] or not u["emails"] <= pol["_self_emails"]:
            return False
    if r.get("emails_not_subset_of"):
        if u["emails"] and u["emails"] <= pol["_self_emails"]:
            return False
    return True


def _classify_unit(tool_name, u, pol):
    """First match in severity order DENY > L3 > L0 > L1; else L2."""
    for level in ("DENY", "L3", "L0", "L1"):
        for r in pol["rules"]:
            if r["level"] == level and _rule_matches(r, tool_name, u, pol):
                return level, r["id"]
    return "L2", None


def _unit(text, paths=None, dpaths=None, wpaths=None, unknown=False, modify=True, emails=None,
          wtrees=None, argv=None, known_writes=False):
    return {"text": text, "paths": paths or [], "dpaths": dpaths or [], "wpaths": wpaths or [],
            "unknown": unknown, "modify": modify, "emails": emails or set(), "wtrees": wtrees or [],
            "argv": argv or [], "known_writes": known_writes}


def _is_readonly(seg, pol):
    argv = seg["argv"]
    if argv and os.path.basename(argv[0]) == "sed":
        a = argv[1:]
        return not (_sed_inplace(a) or _sed_wfiles(a) or _sed_has_script_file(a))
    r = next((x for x in pol["rules"] if x["id"] == "l0-shell-readonly"), None)
    return bool(r and _rule_matches(r, "shell", _unit(seg["text"], modify=False), pol))


def _classify_seg(seg, cwd, pol):
    p = segment_paths(seg, cwd)
    readonly = _is_readonly(seg, pol)
    modify = (not readonly) or bool(seg["redirects"])
    if p["rel_unknown_cwd"] and modify:
        return "L3", "unknown-cwd"
    emails = {e.lower() for e in EMAIL_RE.findall(seg["text"])}
    u = _unit(seg["text"], p["paths"], p["dpaths"], p["wpaths"], p["unknown"], modify, emails,
              p["wtrees"], seg["argv"], p["known_writes"])
    if readonly and seg["redirects"]:
        # read-only command writing via redirect: judge the redirect like a file write
        rp = [x for x in (_resolve(t, cwd) for t in seg["redirects"] if t not in DEV_PATHS) if x]
        runknown = any(_resolve(t, cwd) is None for t in seg["redirects"] if t not in DEV_PATHS)
        if not rp and not runknown:
            return _classify_unit("shell", dict(u, modify=False), pol)
        lvl, rid = _classify_unit("write", _unit("", rp, rp, rp, runknown), pol)
        cmd_lvl, cmd_rid = _classify_unit("shell", dict(u, modify=False), pol)
        if SEVERITY[cmd_lvl] > SEVERITY[lvl]:
            return cmd_lvl, cmd_rid
        return lvl, rid
    return _classify_unit("shell", u, pol)


def classify(tool_name, tool_input, cwd, pol):
    """Return (level, rule_id, summary, trigger_text)."""
    ti = _strip_purpose(tool_input) or {}
    if tool_name == "shell":
        command = str(ti.get("command", ""))
        try:
            segs = split_shell(command)
        except ValueError:
            return "L3", "unparseable", command, command
        if not segs:
            return "L0", "empty", command, ""
        cur_cwd = cwd
        best = ("L0", None, "")
        for seg in segs:
            argv = seg["argv"]
            if argv and argv[0] in ("cd", "pushd", "popd"):
                if argv[0] == "popd":
                    cur_cwd = None
                else:
                    tgt = next((a for a in argv[1:] if not a.startswith("-")), "~")
                    cur_cwd = None if tgt == "-" else _resolve(tgt, cur_cwd)
                lvl, rid = "L0", "cd"
            else:
                lvl, rid = _classify_seg(seg, cur_cwd, pol)
            if SEVERITY[lvl] > SEVERITY[best[0]] or (lvl == best[0] and best[1] is None and rid):
                best = (lvl, rid, seg["text"])
        return best[0], best[1], command, best[2]
    if tool_name == "write":
        path = str(ti.get("path", ""))
        r = _resolve(path, cwd) if path else None
        u = _unit("", [r] if r else [], [r] if r else [], [r] if r else [], r is None)
        lvl, rid = _classify_unit("write", u, pol)
        s = "%s %s" % (ti.get("command", "write"), path)
        return lvl, rid, s, s
    lvl, rid = _classify_unit(tool_name, _unit(""), pol)
    s = json.dumps(ti, ensure_ascii=False, sort_keys=True)
    return lvl, rid, s, tool_name


# ---------------------------------------------------------------- approvals + log

def redact(s, limit=200):
    s = SECRET_RE.sub(lambda m: m.group(1) + m.group(2) + "***", s)
    s = s.replace("\n", "\\n")
    return s if len(s) <= limit else s[:limit] + "…[truncated]"


def consume_approval(aid, now):
    """Return True if a valid one-shot approval exists for aid (and consume it)."""
    adir = os.path.join(DATA_DIR, "approvals")
    p = os.path.join(adir, aid + ".json")
    if not os.path.exists(p):
        return False
    try:
        with open(p) as f:
            rec = json.load(f)
        valid = rec.get("action_id") == aid and float(rec.get("expires", 0)) > now
    except (OSError, ValueError):
        valid = False
    used = os.path.join(adir, "used")
    os.makedirs(used, exist_ok=True)
    os.replace(p, os.path.join(used, "%s.%d.json" % (aid, int(now))))  # one-shot, keep audit trail
    return valid


def write_log(rec):
    os.makedirs(DATA_DIR, exist_ok=True)
    month = datetime.datetime.now(TZ).strftime("%Y-%m")
    with open(os.path.join(DATA_DIR, "decisions-%s.jsonl" % month), "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def decide(payload, pol, agent, now=None):
    """Returns (exit_code, stderr_msg, log_record)."""
    now = now or time.time()
    t0 = time.time()
    tool = payload.get("tool_name", "")
    tin = payload.get("tool_input") or {}
    cwd = payload.get("cwd") or os.getcwd()
    level, rule, summary, trigger = classify(tool, tin, cwd, pol)
    aid = action_id(tool, tin, cwd)
    mode = pol.get("mode", "enforce")

    if level == "DENY":
        verdict = "deny"
    elif level == "L3":
        verdict = "block"
        if mode == "enforce" and consume_approval(aid, now):
            verdict = "approved"
    elif level == "L2":
        verdict = "allow" if pol.get("l2_default", "allow") == "allow" else "block"
    else:
        verdict = "allow"

    rec = {
        "ts": datetime.datetime.now(TZ).isoformat(timespec="seconds"),
        "session": payload.get("session_id") or os.environ.get("CBP_SESSION_ID", ""),
        "agent": agent, "tool": tool, "action_id": aid, "summary": redact(summary),
        "detail": redact(summary, 2000), "trigger": redact(trigger, 300),
        "cwd": cwd, "level": level, "rule": rule, "verdict": verdict, "mode": mode,
        "latency_ms": int((time.time() - t0) * 1000),
    }
    if mode != "enforce" or verdict not in ("deny", "block"):
        return 0, "", rec
    if not ENFORCE_SUPPORTED:                      # record the verdict, but do not pretend to block
        rec["verdict"] = "would-%s" % verdict
        _warn_degraded(agent, tool)
        return 0, "", rec
    gid = aid[:8]
    if verdict == "deny":
        msg = ("GATE DENY [%s] — this action is not permitted for the agent and cannot be approved. "
               "Do not retry or work around it; tell the user what you wanted to do." % rule)
    else:
        msg = ("GATE L3 [%s] blocked. gate_id=%s\n"
               "Stop and ask the user to approve it in THEIR OWN terminal:  cbp-gate approve %s\n"
               "(You cannot run that command yourself.) After approval, retry the identical call "
               "(any change in arguments or cwd needs a new approval)."
               % (rule, gid, gid))
    msg += ("\n(Ignore any 'module ... python' line above: it is login-shell noise from how cbp-cli runs hooks.)")
    return 2, msg, rec


def main(argv):
    global POLICY_PATH, POLICY_LOCAL, DATA_DIR

    def _arg(name, default):
        if name in argv:
            i = argv.index(name)
            return argv[i + 1] if i + 1 < len(argv) else default
        return default
    agent = _arg("--agent", "unknown")
    POLICY_PATH = _arg("--policy", POLICY_PATH)          # only via the (protected) hook command line
    POLICY_LOCAL = _arg("--policy-local", POLICY_LOCAL)
    DATA_DIR = _arg("--data", DATA_DIR)

    _arm_deadline(DEADLINE_SEC)

    mode = "enforce"  # unknown until policy loads → fail closed
    payload = {}
    try:
        pol = load_policy()
        mode = pol.get("mode", "enforce")
        raw = _read_payload(DEADLINE_SEC)
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict) or not payload.get("tool_name"):
            raise ValueError("payload missing tool_name")
        code, msg, rec = decide(payload, pol, agent)
        _disarm_deadline()
        write_log(rec)
        if msg:
            sys.stderr.write(msg + "\n")
        return code
    except BaseException as e:  # noqa: includes GateTimeout, SystemExit, KeyboardInterrupt
        _disarm_deadline()
        err = "%s: %s" % (type(e).__name__, e)
        try:
            write_log({"ts": datetime.datetime.now(TZ).isoformat(timespec="seconds"), "agent": agent,
                       "tool": payload.get("tool_name", "") if isinstance(payload, dict) else "",
                       "level": "ERR", "verdict": "error", "mode": mode, "error": redact(err, 300)})
        except BaseException:
            pass
        if mode == "shadow":
            return 0
        sys.stderr.write("GATE ERROR (fail-closed): %s. Tell the user the action gate failed; "
                         "they can inspect it with `cbp-gate tail`.\n" % redact(err, 300))
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
