"""Tests for bin/gate-audit.py and `cbp-gate apply`. Run with the action-gate suite."""
import datetime
import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import tempfile
import unittest

import os as _os

# The action gate classifies POSIX-style paths taken from the command string. On Windows those do not
# line up with roots derived by os.path.realpath, so the gate degrades to record-only there and these
# expectations cannot hold. They still run in full on POSIX hosts.
_POSIX_ONLY = unittest.skipIf(os.name == "nt", "POSIX path semantics: gate is record-only on Windows")
_NEEDS_TTY = unittest.skipIf(os.name == "nt", "requires pty/termios (POSIX-only)")

# Deterministic, machine-independent policy inputs (no real identity in tests).
_os.environ.update({"CBP_TMP_PREFIX": "/tmp/kp-ut-", "CBP_SCRATCH_DIRS": "/tmp/kp-sbox",
                    "CBP_SELF_EMAILS": "you@example.com,user@example.com", "CBP_TZ": "UTC"})
_os.environ.pop("CBP_DELETE_ALLOW", None)
_os.environ.pop("CBP_GATED_AGENTS", None)
LAB = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # repo root
TZ = datetime.timezone.utc


def _load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    m = importlib.util.module_from_spec(spec)
    loader.exec_module(m)
    return m


audit = _load("gate_audit", os.path.join(LAB, "bin/gate-audit.py"))
kg = _load("cbp_gate", os.path.join(LAB, "bin/cbp-gate"))
ag = _load("action_gate", os.path.join(LAB, "bin/action-gate.py"))
TEST_CFG = {"CBP_TMP_PREFIX": "/tmp/kp-ut-", "CBP_SCRATCH_DIRS": "/tmp/kp-sbox",
            "CBP_SELF_EMAILS": "you@example.com,user@example.com", "CBP_TZ": "UTC"}


def _use_test_cfg(m):
    """The gate reads config from files only; tests inject a deterministic config in-process."""
    m.GATE_CFG.clear()
    m.GATE_CFG.update(TEST_CFG)
_use_test_cfg(ag)


def rec(cmd, level="L2", session="s1", verdict="allow", rule=None):
    return {"ts": datetime.datetime.now(TZ).isoformat(timespec="seconds"), "tool": "shell", "level": level,
            "verdict": verdict, "rule": rule, "session": session, "trigger": cmd, "summary": cmd,
            "agent": "pure", "latency_ms": 20}


class TestAudit(unittest.TestCase):
    def test_cmd_key(self):
        self.assertEqual(audit.cmd_key("make -j4 all"), "make")
        self.assertEqual(audit.cmd_key("git lfs pull"), "git lfs")
        self.assertEqual(audit.cmd_key("FOO=1 kubectl -n x krew list"), "kubectl krew")
        self.assertEqual(audit.cmd_key("python3 /opt/tools/report.py --x"), "python3 report.py")

    def test_relax_needs_count_and_sessions(self):
        recs = [rec("make all", session="s%d" % (i % 2)) for i in range(5)] + [rec("ninja -C b")] * 6
        props, stats = audit.audit(recs, 5, 2)
        keys = {p["evidence"]["key"]: p for p in props}
        self.assertIn("make", keys)
        self.assertNotIn("ninja", keys)  # one session only
        r = keys["make"]["rule"]
        self.assertEqual((r["level"], r["paths_under"]), ("L1", "write_roots"))
        self.assertTrue(re.match(r["cmd"], "make all"))
        self.assertFalse(re.match(r["cmd"], "makefoo"))
        self.assertEqual(kg.validate_proposal(keys["make"], set()), [])

    def test_risky_goes_to_tighten_not_relax(self):
        recs = [rec("curl -X POST https://x/api", session="s%d" % i) for i in range(6)]
        recs += [rec("ssh host uptime", session="s%d" % i) for i in range(6)]
        props, _ = audit.audit(recs, 5, 2)
        kinds = {(p["kind"], p["rule"]["id"]) for p in props}
        self.assertIn(("tighten", "l3-auto-http-write"), kinds)
        self.assertIn(("tighten", "l3-auto-ssh"), kinds)
        self.assertFalse(any(k == "relax" for k, _ in kinds))
        for p in props:
            self.assertEqual(kg.validate_proposal(p, set()), [], p)

    def test_stats_l3_samples(self):
        recs = [rec("git push", level="L3", verdict="block", rule="l3-git-push")] * 3
        _, stats = audit.audit(recs, 5, 2)
        self.assertEqual(stats["l3_deny_by_rule"][0]["rule"], "l3-git-push")
        self.assertEqual(stats["l3_deny_by_rule"][0]["count"], 3)


@_POSIX_ONLY
class TestApplyValidation(unittest.TestCase):
    def p(self, **rule):
        base = {"id": "l1-auto-make", "level": "L1", "tool": "shell", "cmd": "^make(\\s|$)", "paths_under": "write_roots"}
        base.update(rule)
        return {"action": "add_rule", "rule": {k: v for k, v in base.items() if v is not None}}

    def test_ok(self):
        self.assertEqual(kg.validate_proposal(self.p(), set()), [])

    def test_rejects(self):
        bad = [
            self.p(level="L0", id="l1-auto-make"),            # L0 not allowed
            self.p(paths_under=None),                         # missing path restriction
            self.p(cmd="make"),                               # not anchored
            self.p(cmd="^.*"),                                # too broad
            self.p(cmd="^make.*"),                            # .* allowed nowhere in L1
            self.p(tool="write"),                             # L1 auto only for shell
            self.p(id="l3-git-push"),                         # not an auto id
            self.p(id="l3-auto-make"),                        # prefix/level mismatch
            self.p(builtin=True),                             # unsupported key
            self.p(cmd="^make("),                             # bad regex
        ]
        for b in bad:
            self.assertNotEqual(kg.validate_proposal(b, set()), [], b)
        self.assertNotEqual(kg.validate_proposal(self.p(), {"l1-auto-make"}), [])
        self.assertNotEqual(kg.validate_proposal({"action": "remove_rule", "rule": {}}, set()), [])

    def test_l1_rule_cannot_lower_l3(self):
        # an auto L1 rule for git push would be shadowed by l3-git-push (DENY > L3 > L0 > L1)
        rule = {"id": "l1-auto-git-push", "level": "L1", "tool": "shell", "cmd": "^git\\s+push(\\s|$)",
                "paths_under": "write_roots"}
        self.assertEqual(kg.validate_proposal({"action": "add_rule", "rule": rule}, set()), [])
        tmp = tempfile.mkdtemp(prefix="kp-gate-ut-")
        ov = os.path.join(tmp, "local.json")
        with open(ov, "w") as f:
            json.dump({"rules": [rule]}, f)
        pol = ag.load_policy(local=ov)
        self.assertEqual(ag.classify("shell", {"command": "git push"}, LAB, pol)[:2], ("L3", "l3-git-push"))

    def test_overlay_write_validates_and_merges(self):
        tmp = tempfile.mkdtemp(prefix="kp-ov-ut-")
        old = (ag.POLICY_LOCAL, kg.DATA_DIR)
        ag.POLICY_LOCAL = os.path.join(tmp, "gate-policy.local.json"); kg.DATA_DIR = tmp
        try:
            ov = {"rules": [{"id": "l3-auto-ssh", "level": "L3", "tool": "shell", "cmd": "^ssh\\b"}], "mode": "enforce"}
            kg._write_overlay(ag, ov, "t")
            pol = ag.load_policy(local=ag.POLICY_LOCAL)
            self.assertEqual(pol["rules"][0]["id"], "l3-auto-ssh")
            self.assertEqual(pol["mode"], "enforce")
            with self.assertRaises(ValueError):          # invalid overlay is never written
                kg._write_overlay(ag, {"bogus_key": 1}, "t")
            self.assertEqual(json.load(open(ag.POLICY_LOCAL))["mode"], "enforce")
        finally:
            ag.POLICY_LOCAL, kg.DATA_DIR = old

    def test_apply_refuses_in_agent_or_without_tty(self):
        r = subprocess.run([sys.executable, os.path.join(LAB, "bin/cbp-gate"), "apply", "2026-01-01"],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=10,
                           env=dict(os.environ, CBP_SESSION_ID="x"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("refusing", r.stderr)


@_POSIX_ONLY
class TestAgentCannotApply(unittest.TestCase):
    def test_gate_denies_apply(self):
        pol = ag.load_policy(os.path.join(LAB, ".codebuddy/rules/gate-policy.json"), local=False)
        for c in ["cbp-gate apply 2026-10-30", "@ROOT@/bin/cbp-gate apply x P01"]:
            self.assertEqual(ag.classify("shell", {"command": c}, LAB, pol)[:2], ("DENY", "deny-cbp-gate"))
        self.assertEqual(ag.classify("shell", {"command": "python3 @ROOT@/bin/gate-audit.py --days 7"},
                                     LAB, pol)[0], "L1")


@_POSIX_ONLY
class TestCliPathsIgnoreEnv(unittest.TestCase):
    def test_cbp_gate_and_audit_use_hook_paths(self):
        code = ("import importlib.machinery as M,json;"
                "k=M.SourceFileLoader('k',%r).load_module();a=M.SourceFileLoader('a',%r).load_module();"
                "print(json.dumps([k.POLICY_PATH,k.DATA_DIR,str(k.ROOT),a.POLICY_PATH,a.DATA_DIR]))"
                ) % (os.path.join(LAB, "bin/cbp-gate"), os.path.join(LAB, "bin/gate-audit.py"))
        env = dict(os.environ, CBP_ROOT="/x", GATE_POLICY="/x.json", GATE_DATA="/x", CBP_DATA="/x")
        out = json.loads(subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                                        text=True, timeout=10).stdout.strip().splitlines()[-1])
        self.assertTrue(all(p.startswith(LAB) for p in out), out)



@_NEEDS_TTY
class TtyPrompt(unittest.TestCase):
    """cbp-gate approve/apply prompt on /dev/tty. Regression: text-mode "r+" on a tty raised
    io.UnsupportedOperation (not seekable) before any question was shown (2026-10-27)."""

    def _ask_in_pty(self, func, answer=b"hello\n"):
        import json as _j, pty, tempfile, time
        res = tempfile.mktemp(prefix="kg-tty-")
        pid, fd = pty.fork()
        if pid == 0:                                     # child: the pty is its controlling terminal
            try:
                out = {"ok": func()}
            except Exception as e:                       # noqa: BLE001 — report any failure to the parent
                out = {"err": repr(e)}
            with open(res, "w") as f:
                f.write(_j.dumps(out))
            os._exit(0)
        time.sleep(0.3)
        os.write(fd, answer)
        end = time.time() + 5
        while time.time() < end:
            try:
                if not os.read(fd, 1024):
                    break
            except OSError:
                break
        os.waitpid(pid, 0)
        with open(res) as f:
            out = _j.load(f)
        os.unlink(res)
        return out

    def test_tty_ask_reads_answer(self):
        self.assertEqual(self._ask_in_pty(lambda: kg._tty_ask("Q? ")), {"ok": "hello\n"})

    def test_old_rplus_pattern_fails(self):
        def old():
            with open("/dev/tty", "r+") as t:
                t.write("Q? ")
                return t.readline()
        self.assertIn("err", self._ask_in_pty(old))      # documents why _tty_ask uses two handles

    def test_no_rplus_left(self):
        src = open(os.path.join(LAB, "bin/cbp-gate"), encoding="utf-8").read()
        self.assertNotIn('open("/dev/tty", "r+")', src)

if __name__ == "__main__":
    unittest.main()
