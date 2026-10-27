"""Tests for bin/agent-trace.py (turn summary, budget brake, slow-turn note)."""
import importlib.machinery
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

import os as _os
# Deterministic, machine-independent policy inputs (no real identity in tests).
_os.environ.update({"CBP_TMP_PREFIX": "/tmp/kp-ut-", "CBP_SCRATCH_DIRS": "/tmp/kp-sbox",
                    "CBP_SELF_EMAILS": "you@example.com,user@example.com", "CBP_TZ": "UTC"})
_os.environ.pop("CBP_DELETE_ALLOW", None)
_os.environ.pop("CBP_GATED_AGENTS", None)
LAB = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # repo root


def _load():
    loader = importlib.machinery.SourceFileLoader("agent_trace", os.path.join(LAB, "bin/agent-trace.py"))
    spec = importlib.util.spec_from_loader("agent_trace", loader)
    m = importlib.util.module_from_spec(spec)
    loader.exec_module(m)
    return m


class TestTrace(unittest.TestCase):
    def setUp(self):
        self.at = _load()
        self.at.TRACE_DIR = tempfile.mkdtemp(prefix="kp-trace-ut-")
        self.clock = [1792740000.0]
        self.at.now = lambda: self.clock[0]

    def call(self, ev, agent, payload, env=None):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, env or {}, clear=False), \
                mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), \
                mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", err):
            if "CBP_TOOL_BUDGET" not in (env or {}):
                os.environ.pop("CBP_TOOL_BUDGET", None)
            code = self.at.main([ev, "--agent", agent])
        return code, out.getvalue(), err.getvalue()

    def tick(self, s):
        self.clock[0] += s

    def events(self):
        out = []
        for fn in os.listdir(self.at.TRACE_DIR):
            if fn.startswith("trace-"):
                out += [json.loads(l) for l in open(os.path.join(self.at.TRACE_DIR, fn))]
        return out

    def test_turn_split_model_vs_tool(self):
        S = {"session_id": "s1"}
        self.call("prompt", "pure", dict(S, prompt="hi"))
        self.tick(2.5)
        t1 = dict(S, tool_name="shell", tool_input={"command": "sleep 3"})
        self.call("pre", "pure", t1); self.tick(4.0); self.call("post", "pure", dict(t1, tool_response={"x": 1}))
        self.tick(2.0)
        t2 = dict(S, tool_name="shell", tool_input={"command": "run-agent.sh reviewer 'x'"})
        self.call("pre", "pure", t2); self.tick(60); self.call("post", "pure", t2)
        self.tick(3.5)
        self.call("stop", "pure", dict(S, assistant_response="done"))
        turn = [e for e in self.events() if e["ev"] == "turn"][0]
        self.assertEqual((turn["wall_s"], turn["tool_s"], turn["model_s"], turn["tools"]), (72.0, 64.0, 8.0, 2))
        self.assertEqual(turn["top"][0], [60.0, "run-agent reviewer"])
        # next prompt of the main agent gets a timing note on stdout (injected into the model)
        _, out, _ = self.call("prompt", "pure", dict(S, prompt="next"))
        self.assertIn("previous turn took 72.0s", out)
        self.assertIn("run-agent reviewer 60.0s", out)

    def test_parallel_tools_merge(self):
        S = {"session_id": "s2"}
        self.call("prompt", "pure", dict(S, prompt="p"))
        a = dict(S, tool_name="read", tool_input={"p": 1}); b = dict(S, tool_name="read", tool_input={"p": 2})
        self.call("pre", "pure", a); self.call("pre", "pure", b); self.tick(5)
        self.call("post", "pure", a); self.call("post", "pure", b); self.tick(1)
        self.call("stop", "pure", S)
        turn = [e for e in self.events() if e["ev"] == "turn"][0]
        self.assertEqual((turn["tool_s"], turn["model_s"], turn["tools"]), (5.0, 1.0, 2))

    def test_no_note_for_fast_turn_or_subagent(self):
        S = {"session_id": "s3"}
        self.call("prompt", "pure", dict(S, prompt="p")); self.tick(5); self.call("stop", "pure", S)
        self.assertEqual(self.call("prompt", "pure", dict(S, prompt="q"))[1], "")
        R = {"session_id": "r1"}
        self.call("prompt", "reviewer", dict(R, prompt="p")); self.tick(90); self.call("stop", "reviewer", R)
        self.assertEqual(self.call("prompt", "reviewer", dict(R, prompt="q"))[1], "")

    def test_budget_brake_explicit(self):
        S = {"session_id": "b1"}
        env = {"CBP_TOOL_BUDGET": "2"}
        self.call("prompt", "reviewer", dict(S, prompt="p"), env)
        codes = [self.call("pre", "reviewer", dict(S, tool_name="shell", tool_input={"command": "ls %d" % i}), env)[0]
                 for i in range(4)]
        self.assertEqual(codes, [0, 0, 2, 2])
        err = self.call("pre", "reviewer", dict(S, tool_name="read", tool_input={}), env)[2]
        self.assertIn("TOOL BUDGET REACHED", err)
        # new prompt (resume / next task) → fresh budget
        self.call("prompt", "reviewer", dict(S, prompt="again"), env)
        self.assertEqual(self.call("pre", "reviewer", dict(S, tool_name="shell", tool_input={"command": "ls"}), env)[0], 0)

    def test_default_budget_logs_only_and_main_unlimited(self):
        S = {"session_id": "b2"}
        self.call("prompt", "health-checker", dict(S, prompt="p"))
        codes = [self.call("pre", "health-checker", dict(S, tool_name="shell", tool_input={"command": str(i)}))[0]
                 for i in range(10)]
        self.assertEqual(set(codes), {0})
        over = [e for e in self.events() if e["ev"] == "budget_over"]
        self.assertEqual((len(over), over[0]["budget"], over[0]["enforced"]), (2, 8, False))
        M = {"session_id": "m1"}
        self.call("prompt", "pure", dict(M, prompt="p"), {"CBP_TOOL_BUDGET": "1"})
        codes = [self.call("pre", "pure", dict(M, tool_name="shell", tool_input={"command": str(i)}),
                           {"CBP_TOOL_BUDGET": "1"})[0] for i in range(3)]
        self.assertEqual(set(codes), {0})

    def test_state_per_agent_and_atomic(self):
        S = {"session_id": "shared"}
        env = {"CBP_TOOL_BUDGET": "1"}
        self.call("prompt", "reviewer", dict(S, prompt="p"), env)
        self.call("pre", "reviewer", dict(S, tool_name="shell", tool_input={"command": "a"}), env)
        # main agent prompt on the same session id must not reset the reviewer counter
        self.call("prompt", "pure", dict(S, prompt="main"))
        self.assertEqual(self.call("pre", "reviewer", dict(S, tool_name="shell", tool_input={"command": "b"}), env)[0], 2)
        sdir = os.path.join(self.at.TRACE_DIR, "state")
        self.assertFalse([f for f in os.listdir(sdir) if f.endswith(".tmp")])

    def test_note_shown_once(self):
        S = {"session_id": "n1"}
        self.call("prompt", "pure", dict(S, prompt="p")); self.tick(70); self.call("stop", "pure", S)
        self.assertIn("previous turn", self.call("prompt", "pure", dict(S, prompt="q"))[1])
        self.assertEqual(self.call("prompt", "pure", dict(S, prompt="r"))[1], "")

    def test_lock_timeout_fails_closed_only_with_explicit_budget(self):
        S = {"session_id": "lk"}
        def boom(*a, **k):
            raise self.at.LockTimeout("x")
        with mock.patch.object(self.at, "with_state", boom):
            self.assertEqual(self.call("pre", "reviewer", dict(S, tool_name="shell", tool_input={}), {"CBP_TOOL_BUDGET": "3"})[0], 2)
            self.assertEqual(self.call("pre", "reviewer", dict(S, tool_name="shell", tool_input={}))[0], 0)

    def test_bad_input_never_blocks(self):
        for raw in ["not json", "[1,2]", ""]:
            with mock.patch.object(sys, "stdin", io.StringIO(raw)):
                self.assertEqual(self.at.main(["pre", "--agent", "reviewer"]), 0)
        self.assertEqual(self.at.main(["bogus"]), 0)

    def test_label_redacts(self):
        self.assertEqual(self.at.label("shell", {"command": "curl -H token=abc x"}), "curl -H token=*** x")
        for cmd, secret in [("curl -H 'Authorization: Bearer abc123' u", "abc123"), ("curl -u user:hunter2 u", "hunter2"),
                            ("SERVICE_PAT=abcdef git fetch", "abcdef"), ("mysql -pS3cret db", "S3cret")]:
            self.assertNotIn(secret, self.at.label("shell", {"command": cmd}), cmd)
        self.assertEqual(self.at.label("shell", {"command": "@CLI@/bin/run-agent.sh html-generator 'x'"}),
                         "run-agent html-generator")


if __name__ == "__main__":
    unittest.main()
