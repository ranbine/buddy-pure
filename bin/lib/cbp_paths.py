"""Unified path resolver for codebuddy-pure.

Usage (from any script in bin/):

    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
    from cbp_paths import P, ROOT, CLI_HOME

    P["CBP_RULES"]          # -> pathlib.Path (absolute)
    P.get("CBP_HISTORY")

Resolution order (later wins):
    1. config/paths.env   — repo-relative defaults (tracked)
    2. config/local.env   — machine overrides (gitignored)
    3. process environment
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("CBP_ROOT") or Path(__file__).resolve().parents[2])


def _parse(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


_rel = _parse(ROOT / "config" / "paths.env")
if not _rel:
    raise RuntimeError(f"cbp_paths: missing or empty {ROOT / 'config' / 'paths.env'}")

LOCAL = _parse(ROOT / "config" / "local.env")

P: dict[str, Path] = {}
for _k, _v in _rel.items():
    override = os.environ.get(_k) or LOCAL.get(_k)
    P[_k] = Path(os.path.expanduser(override)) if override else ROOT / _v


def setting(key: str, default: str = "") -> str:
    """Non-path setting from env > local.env > default."""
    return os.environ.get(key) or LOCAL.get(key) or default


CLI_HOME = Path(os.path.expanduser(setting("CBP_CLI_HOME", "~/.codebuddy")))
CLI_BIN = setting("CBP_CLI_BIN", "cbp-cli")


def tz():
    """Report timezone from CBP_TZ (IANA name, e.g. "Asia/Shanghai"); unset → machine local time."""
    import datetime
    try:
        from zoneinfo import ZoneInfo        # Python ≥ 3.9
    except ImportError:
        return datetime.datetime.now().astimezone().tzinfo
    name = setting("CBP_TZ")
    if name:
        try:
            return ZoneInfo(name)
        except Exception:
            pass
    try:                                    # machine zone incl. DST rules (not a fixed offset)
        with open("/etc/localtime", "rb") as f:
            return ZoneInfo.from_file(f)
    except Exception:
        return datetime.datetime.now().astimezone().tzinfo


_LOCAL_JSON = None


def local(key, default=None):
    """Domain/personal extensions from config/local.json (gitignored). See config/local.example.json."""
    global _LOCAL_JSON
    if _LOCAL_JSON is None:
        import json
        path = ROOT / "config" / "local.json"
        try:
            _LOCAL_JSON = json.loads(path.read_text(encoding="utf-8"))
        except OSError:
            _LOCAL_JSON = {}
        except ValueError as e:
            import sys
            print("cbp_paths: ignoring bad %s: %s" % (path, e), file=sys.stderr)
            _LOCAL_JSON = {}
        if not isinstance(_LOCAL_JSON, dict):
            import sys
            print("cbp_paths: ignoring %s (top level must be an object)" % path, file=sys.stderr)
            _LOCAL_JSON = {}
    return _LOCAL_JSON.get(key, default)


def _warn(key, want):
    import sys
    print("cbp_paths: config/local.json %r must be %s; ignored" % (key, want), file=sys.stderr)


def local_list(key, item=str):
    """local(key) as a list whose items are all `item`; anything else → [] (+ warning)."""
    v = local(key, [])
    if isinstance(v, list) and all(isinstance(x, item) for x in v):
        return list(v)
    _warn(key, "a list of %s" % item.__name__)
    return []


def local_dict(key, value=str):
    """local(key) as a dict str → `value`; anything else → {} (+ warning)."""
    v = local(key, {})
    if isinstance(v, dict) and all(isinstance(k, str) and isinstance(x, value) for k, x in v.items()):
        return dict(v)
    _warn(key, "an object of str → %s" % value.__name__)
    return {}
