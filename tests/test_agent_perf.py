"""Tests for bin/agent-perf.py using synthetic session / gate / run-log fixtures."""
import datetime
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest

import os as _os
# Deterministic, machine-independent policy inputs (no real identity in tests).
_os.environ.update({"CBP_TMP_PREFIX": "/tmp/kp-ut-", "CBP_SCRATCH_DIRS": "/tmp/kp-sbox",
                    "CBP_SELF_EMAILS": "you@example.com,user@example.com", "CBP_TZ": "UTC"})
_os.environ.pop("CBP_DELETE_ALLOW", None)
_os.environ.pop("CBP_GATED_AGENTS", None)
LAB = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # repo root
UTC = datetime.timezone.utc


def _load():
    loader = importlib.machinery.SourceFileLoader("agent_perf", os.path.join(LAB, "bin/agent-perf.py"))
    spec = importlib.util.spec_from_loader("agent_perf", loader)
    m = importlib.util.module_from_spec(spec)
    loader.exec_module(m)
    return m


class TestAgentPerf(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="kp-perf-ut-")
        self.sess = os.path.join(self.tmp, "sessions")
        self.gate = os.path.join(self.tmp, "gate")
        os.makedirs(self.sess)
        os.makedirs(self.gate)
        self.runs = os.path.join(self.tmp, "runs.jsonl")
        ap = _load()
        ap.SESS_DIR, ap.GATE_DIR, ap.RUNS_LOG = self.sess, self.gate, self.runs
        self.ap = ap
        self.now = datetime.datetime.now(UTC).replace(microsecond=0)

    def session(self, sid, start, wall, turns, tools_per_turn=1, tool="shell", cwd="/x"):
        c = start
        u = start + datetime.timedelta(seconds=wall)
        z = lambda d: d.strftime("%Y-%m-%dT%H:%M:%S.123456789Z")  # noqa: E731
        with open(os.path.join(self.sess, sid + ".json"), "w") as f:
            json.dump({"session_id": sid, "cwd": cwd, "created_at": z(c), "updated_at": z(u), "title": "t-" + sid}, f)
        with open(os.path.join(self.sess, sid + ".jsonl"), "w") as f:
            f.write(json.dumps({"version": "v1", "kind": "Prompt", "data": str({"content": []})}) + "\n")
            for _ in range(turns):
                content = [{"kind": "toolUse", "data": str({"toolUseId": "x", "name": tool})}] * tools_per_turn
                f.write(json.dumps({"version": "v1", "kind": "AssistantMessage", "data": str({"content": content})}) + "\n")
                f.write(json.dumps({"version": "v1", "kind": "ToolResults", "data": str({"content": ["y" * 500]})}) + "\n")

    def gate_rec(self, sid, agent):
        with open(os.path.join(self.gate, "decisions-2026-10.jsonl"), "a") as f:
            f.write(json.dumps({"session": sid, "agent": agent, "ts": self.now.isoformat()}) + "\n")

    def run_rec(self, agent, start, wall, outcome="ok", timeout=300, cwd="/x", resume=""):
        with open(self.runs, "a") as f:
            f.write(json.dumps({"ts": start.isoformat(), "agent": agent, "start_epoch": start.timestamp(),
                                "wall_s": wall, "outcome": outcome, "timeout_s": timeout, "cwd": cwd,
                                "resume": resume, "task": "task-" + agent}) + "\n")

    def test_join_flags_and_summary(self):
        t = self.now - datetime.timedelta(hours=2)
        self.session("s-rev", t + datetime.timedelta(seconds=2), 60, 6)            # gate + run-agent
        self.gate_rec("s-rev", "reviewer")
        self.run_rec("reviewer", t, 63)
        self.session("s-html", t + datetime.timedelta(minutes=10, seconds=1), 400, 16, tool="write")  # run-agent only
        self.run_rec("html-generator", t + datetime.timedelta(minutes=10), 402)
        self.session("s-main", t, 3000, 50)                                         # main agent: excluded
        self.gate_rec("s-main", "pure")
        self.session("s-slow", t + datetime.timedelta(minutes=30), 250, 5)         # native delegate (gate only)
        self.gate_rec("s-slow", "health-checker")
        self.run_rec("html-generator", t + datetime.timedelta(minutes=50), 600, outcome="timeout", timeout=600)
        rows = self.ap.collect(1)
        by = {(r["agent"], r["session"]): r for r in rows}
        self.assertNotIn(("pure", "s-main"), by)
        rev = by[("reviewer", "s-rev")]
        self.assertEqual((rev["turns"], rev["tool_uses"], rev["via"], rev["e2e_s"], rev["flags"]), (6, 6, "run-agent", 63, []))
        html = by[("html-generator", "s-html")]
        self.assertIn("OVER_BUDGET", html["flags"])  # 16 tool calls > 15
        self.assertEqual(html["tools"], {"write": 16})
        slow = by[("health-checker", "s-slow")]
        self.assertEqual(slow["via"], "other")
        self.assertIn("SLOW_TURN", slow["flags"])    # 50 s/turn
        to = by[("html-generator", "")]
        self.assertEqual((to["outcome"], to["flags"]), ("timeout", ["TIMEOUT"]))
        summ = self.ap.summarize(rows)
        self.assertEqual(summ["html-generator"]["runs"], 2)
        self.assertEqual(summ["html-generator"]["timeouts"], 1)
        self.assertEqual(summ["reviewer"]["median_s_per_turn"], 10.0)

    def test_join_window_and_agent_mismatch(self):
        t = self.now - datetime.timedelta(hours=1)
        self.session("s-a", t + datetime.timedelta(seconds=60), 30, 3)   # outside 20 s window
        self.gate_rec("s-a", "reviewer")
        self.run_rec("reviewer", t, 90)
        self.session("s-b", t + datetime.timedelta(minutes=5, seconds=3), 30, 3)  # gate says reviewer, run says html
        self.gate_rec("s-b", "reviewer")
        self.run_rec("html-generator", t + datetime.timedelta(minutes=5), 33)
        rows = self.ap.collect(1)
        sessions = {(r["agent"], r["session"], r["via"]) for r in rows}
        self.assertIn(("reviewer", "s-a", "other"), sessions)
        self.assertIn(("reviewer", "s-b", "other"), sessions)
        self.assertEqual(sum(1 for r in rows if r["session"] == ""), 2)  # both run records unmatched

    def test_parallel_runs_closest_and_gateless(self):
        t = self.now - datetime.timedelta(hours=1)
        self.run_rec("reviewer", t, 30)
        self.run_rec("html-generator", t + datetime.timedelta(seconds=1), 30)
        self.session("sB", t + datetime.timedelta(seconds=3), 25, 3)   # no gate record → html (closest free)
        self.session("sA", t + datetime.timedelta(seconds=2), 25, 3)
        self.gate_rec("sA", "reviewer")
        by = {r["session"]: r for r in self.ap.collect(1)}
        self.assertEqual((by["sA"]["agent"], by["sA"]["via"]), ("reviewer", "run-agent"))
        self.assertEqual((by["sB"]["agent"], by["sB"]["via"]), ("html-generator", "run-agent"))
        self.assertNotIn("", by)

    def test_gate_confirmed_pairs_win_regardless_of_order(self):
        t = self.now - datetime.timedelta(hours=1)
        self.run_rec("reviewer", t, 30)
        self.run_rec("html-generator", t + datetime.timedelta(seconds=0.5), 30)
        self.session("sB", t + datetime.timedelta(seconds=1), 25, 3)   # gate-less, closer to the reviewer run
        self.session("sA", t + datetime.timedelta(seconds=2), 25, 3)
        self.gate_rec("sA", "reviewer")
        by = {r["session"]: r for r in self.ap.collect(1)}
        self.assertEqual((by["sA"]["agent"], by["sA"]["via"]), ("reviewer", "run-agent"))
        self.assertEqual((by["sB"]["agent"], by["sB"]["via"]), ("html-generator", "run-agent"))
        self.assertNotIn("", by)

    def test_cwd_must_match(self):
        t = self.now - datetime.timedelta(hours=1)
        self.run_rec("reviewer", t, 30, cwd="/a")
        self.session("s-kp", t + datetime.timedelta(seconds=2), 25, 3, cwd="/b")  # ungated session elsewhere
        rows = self.ap.collect(1)
        self.assertEqual([(r["session"], r["agent"]) for r in rows], [("", "reviewer")])

    def test_resume_uses_run_wall(self):
        old = self.now - datetime.timedelta(hours=5)
        self.session("s-res", old, 4 * 3600, 8)                  # created long ago, updated now
        self.gate_rec("s-res", "reviewer")
        os.utime(os.path.join(self.sess, "s-res.json"), (old.timestamp(), old.timestamp()))
        self.run_rec("reviewer", self.now - datetime.timedelta(minutes=5), 80, resume="s-res")
        rows = self.ap.collect(1)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r["session"], r["wall_s"], r["via"]), ("s-res", 80, "run-agent/resume"))
        self.assertEqual(r["flags"], [])  # session-wide counts → no budget / s-per-turn flags
        self.assertIsNone(r["s_per_turn"])

    def test_odd_files_do_not_crash(self):
        t = self.now - datetime.timedelta(hours=1)
        self.session("s-ok", t, 20, 2)
        self.gate_rec("s-ok", "reviewer")
        with open(os.path.join(self.sess, "s-list.json"), "w") as f:
            json.dump([1, 2], f)
        with open(os.path.join(self.sess, "s-naive.json"), "w") as f:
            json.dump({"created_at": t.strftime("%Y-%m-%dT%H:%M:%S"), "updated_at": t.strftime("%Y-%m-%dT%H:%M:%S.5")}, f)
        with open(os.path.join(self.sess, "s-naive.jsonl"), "wb") as f:
            f.write(b'42\n{"kind":"AssistantMessage","data":"[1,2]"}\n\xff\xfe bad utf8\n')
        self.gate_rec("s-naive", "reviewer")
        with open(self.runs, "a") as f:
            f.write("[1]\n" + json.dumps({"agent": "reviewer", "start_epoch": "x"}) + "\n")
        with open(os.path.join(self.gate, "decisions-2026-10.jsonl"), "a") as f:
            f.write("7\n")
        rows = self.ap.collect(1)
        self.assertEqual({r["session"] for r in rows}, {"s-ok", "s-naive"})
        self.assertEqual(self.ap._ts("2026-10-23T02:59:53.1Z").microsecond, 100000)

    def test_old_sessions_ignored(self):
        old = self.now - datetime.timedelta(days=30)
        self.session("s-old", old, 30, 3)
        self.gate_rec("s-old", "reviewer")
        os.utime(os.path.join(self.sess, "s-old.json"), (old.timestamp(), old.timestamp()))
        self.assertEqual(self.ap.collect(7), [])


if __name__ == "__main__":
    unittest.main()
