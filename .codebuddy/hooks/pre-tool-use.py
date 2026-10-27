"""PreToolUse -> action gate.

This is the one hook that replaces real kiro machinery rather than adapting to it. The original
gate needed ``/dev/tty`` to ask the human for approval of an L3 action, because its host had no
native "ask the user" primitive. CodeBuddy does: ``permissionDecision: "ask"``. So the whole
tty reader, the approve CLI and the approval TTL store are gone — the host now owns that step.

Mapping:
    DENY            -> permissionDecision "deny"   (not approvable)
    L3 (block)      -> permissionDecision "ask"    (host prompts; user decides)
    everything else -> permissionDecision "allow"
    gate failure    -> "deny" in enforce mode (fail closed), "allow" in shadow
"""
import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _hooklib as h

GATE = h.ROOT / "bin" / "action-gate.py"


def load_gate():
    spec = importlib.util.spec_from_file_location("pure_action_gate", str(GATE))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ev = h.read_event()
    if not ev.get("tool_name"):
        h.emit(h.permission("allow", ""))

    gate = load_gate()
    payload = dict(ev)
    payload["tool_name"] = h.map_tool(ev.get("tool_name"))
    payload.setdefault("cwd", os.getcwd())

    agent = os.environ.get("CODEBUDDY_AGENT_NAME") or "pure"
    mode = "enforce"
    try:
        pol = gate.load_policy()
        mode = pol.get("mode", "enforce")
        code, msg, rec = gate.decide(payload, pol, agent)
        try:
            gate.write_log(rec)
        except Exception:
            pass
    except BaseException as e:                       # noqa: BLE001 - includes GateTimeout
        if mode == "shadow":
            h.emit(h.permission("allow", ""))
        h.emit(h.permission("deny",
                            "action gate failed (%s: %s) — refusing the call. "
                            "Inspect with `cbp-gate tail`." % (type(e).__name__, e)))

    verdict = (rec or {}).get("verdict") or "allow"
    reason = (msg or "").strip()

    if mode != "enforce":                            # shadow: record only, never stand in the way
        h.emit(h.permission("allow", ""))
    if verdict.startswith("would-"):                 # degraded platform: a record, not a decision
        h.emit(h.permission("allow", ""))

    if verdict == "deny":
        h.emit(h.permission("deny", reason or "denied by gate policy"))
    if verdict == "block":
        h.emit(h.permission("ask", reason or "L3 action — confirm before running"))
    h.emit(h.permission("allow", ""))


if __name__ == "__main__":
    main()
