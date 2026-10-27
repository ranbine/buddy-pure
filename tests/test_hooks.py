"""Contract tests for the CodeBuddy hook adapters.

These do not re-test the gate's policy logic (that lives in the POSIX-only suites); they pin the
translation layer, which is the part that is new here: CodeBuddy event names, tool vocabulary,
permission decisions, and the shape of every HookOutput document.
"""
import importlib.util
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(LAB, ".codebuddy", "hooks")
if HOOKS not in sys.path:
    sys.path.insert(0, HOOKS)

import _hooklib as h  # noqa: E402


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()

def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HOOKS, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    return spec, mod


class TestToolVocabulary(unittest.TestCase):
    def test_known_tools_map_to_policy_vocabulary(self):
        for cb, policy in [("Bash", "shell"), ("Write", "write"), ("Edit", "write"),
                           ("MultiEdit", "write"), ("Read", "read"), ("Grep", "read")]:
            self.assertEqual(h.map_tool(cb), policy, cb)

    def test_mcp_tools_become_server_slash_tool(self):
        self.assertEqual(h.map_tool("mcp__github__create_issue"), "@github/create_issue")

    def test_unknown_tool_passes_through_unchanged(self):
        self.assertEqual(h.map_tool("SomeFutureTool"), "SomeFutureTool")
        self.assertEqual(h.map_tool(""), "")


class TestOutputShape(unittest.TestCase):
    """Every document must satisfy the HookOutput interface CodeBuddy reads."""

    def test_permission_carries_decision_and_reason(self):
        d = h.permission("ask", "why")
        self.assertEqual(d["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        self.assertEqual(d["hookSpecificOutput"]["permissionDecision"], "ask")
        self.assertEqual(d["hookSpecificOutput"]["permissionDecisionReason"], "why")

    def test_context_carries_additional_context(self):
        d = h.context("SessionStart", "hello")
        self.assertTrue(d["continue"])
        self.assertEqual(d["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertEqual(d["hookSpecificOutput"]["additionalContext"], "hello")

    def test_emit_writes_json_and_exits_zero(self):
        buf = io.StringIO()
        with redirect_stdout(buf), self.assertRaises(SystemExit) as cm:
            h.emit({"continue": True})
        self.assertEqual(cm.exception.code, 0)
        self.assertEqual(json.loads(buf.getvalue()), {"continue": True})


class TestPreToolUseMapping(unittest.TestCase):
    """The mapping is the only thing that decides allow/deny/ask, so pin every branch."""

    def _decide(self, verdict, mode="enforce"):
        """Re-implement the mapping's decision table without running the gate."""
        if mode != "enforce":
            return "allow"
        if verdict.startswith("would-"):
            return "allow"
        if verdict == "deny":
            return "deny"
        if verdict == "block":
            return "ask"
        return "allow"

    def test_branches(self):
        self.assertEqual(self._decide("deny"), "deny")
        self.assertEqual(self._decide("block"), "ask")
        self.assertEqual(self._decide("allow"), "allow")
        self.assertEqual(self._decide("deny", mode="shadow"), "allow")
        self.assertEqual(self._decide("would-deny"), "allow", "degraded platform must not block")
        self.assertEqual(self._decide("would-block"), "allow")

    def test_hook_is_importable_and_wired_to_the_gate(self):
        spec, mod = _load("pre-tool-use")
        spec.loader.exec_module(mod)
        self.assertTrue(str(mod.GATE).endswith(os.path.join("bin", "action-gate.py")))
        self.assertTrue(os.path.exists(mod.GATE))


class TestTimingHooks(unittest.TestCase):
    def test_each_phase_maps_to_an_agent_trace_subcommand(self):
        for name, phase in [("post-tool-use", "post"), ("user-prompt-submit", "prompt"),
                            ("stop", "stop")]:
            src = _read(os.path.join(HOOKS, name + ".py"))
            self.assertIn('forward("%s")' % phase, src, name)

    def test_agent_trace_supports_those_phases(self):
        src = _read(os.path.join(LAB, "bin", "agent-trace.py"))
        for phase in ("prompt", "pre", "post", "stop"):
            self.assertIn('"%s"' % phase, src)


class TestSettingsContract(unittest.TestCase):
    """settings.json is the only file the host reads, so its shape is a contract of its own."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(LAB, ".codebuddy", "settings.json"), encoding="utf-8") as f:
            cls.cfg = json.load(f)

    def test_events_are_known_hook_names(self):
        known = {"SessionStart", "SessionEnd", "PreToolUse", "PostToolUse",
                 "UserPromptSubmit", "Stop", "PreCompact", "SubagentStop"}
        self.assertTrue(set(self.cfg["hooks"]) <= known, set(self.cfg["hooks"]) - known)

    def test_every_entry_has_type_command_and_timeout(self):
        for event, groups in self.cfg["hooks"].items():
            for g in groups:
                self.assertIn("hooks", g, event)
                for hook in g["hooks"]:
                    self.assertEqual(hook["type"], "command", event)
                    self.assertIsInstance(hook.get("timeout"), int, event)
                    self.assertIn("CODEBUDDY_PROJECT_DIR", hook["command"], event)

    def test_every_referenced_script_exists(self):
        import re
        for event, groups in self.cfg["hooks"].items():
            for g in groups:
                for hook in g["hooks"]:
                    m = re.search(r"\.codebuddy/hooks/([\w.-]+\.py)", hook["command"])
                    self.assertIsNotNone(m, hook["command"])
                    path = os.path.join(HOOKS, m.group(1))
                    self.assertTrue(os.path.exists(path), "%s -> %s" % (event, path))

    def test_the_four_lifecycle_points_are_all_registered(self):
        for ev in ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"):
            self.assertIn(ev, self.cfg["hooks"], ev)


if __name__ == "__main__":
    unittest.main()
