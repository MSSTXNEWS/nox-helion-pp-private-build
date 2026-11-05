"""Real disposable-file write/restore tests, not installed-Windows acceptance."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from nox_selfbuilder.firstcycle_native import NativeFirstCycle, FirstCycleHold, sha256

HEAD = "589417d5454a981eeaefd4a86792c2462c441c3a"
BEFORE = b"def summarize_status(items):\n    return len(items)\n"
AFTER = (b"def summarize_status(items):\n"
         b"    result = {'ready': 0, 'hold': 0}\n"
         b"    for item in items:\n"
         b"        if item.get('status') == 'READY':\n"
         b"            result['ready'] += 1\n"
         b"        else:\n"
         b"            result['hold'] += 1\n"
         b"    return result\n")
REL = "extensions/model_report/summary.py"


def run_isolated_test(source):
    with tempfile.TemporaryDirectory(prefix="nox-firstcycle-run-") as tmp:
        Path(tmp, "candidate.py").write_bytes(source)
        script = ("import runpy; f=runpy.run_path('candidate.py')['summarize_status']; "
                  "assert f([{'status':'READY'}, {'status':'HOLD'}]) == "
                  "{'ready': 1, 'hold': 1}")
        r = subprocess.run([sys.executable, "-I", "-B", "-c", script],
                           cwd=tmp, timeout=5, capture_output=True)
        return r.returncode == 0


class FirstCycleProof(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(prefix="nox-firstcycle-workspace-")
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.path = self.root / REL
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(BEFORE)
        self.allowed = {"selfbuilder.source.test", "selfbuilder.source.apply",
                        "selfbuilder.source.rollback"}
        self.stop = False
        self.seen = []

    def make(self, **options):
        ack = {"status": "SELFWRITE_ACK", "epoch": 1, "task_id": "NX03-TEST",
               "session": "test-owner", "source_head": HEAD, "path": REL,
               "candidate_sha256": sha256(AFTER), "preimage_sha256": sha256(BEFORE)}
        ack.update(options.pop("ack", {}))
        def grant(session, action, scope):
            self.seen.append(action)
            return session == "test-owner" and action in self.allowed and scope["task_id"] == "NX03-TEST"
        args = {
            "workspace": self.root, "source_head": HEAD, "task_id": "NX03-TEST",
            "session": "test-owner", "candidate": AFTER, "preimage_sha256": sha256(BEFORE),
            "candidate_sha256": sha256(AFTER), "native_ack": ack,
            "authorize": grant, "stopped": lambda: self.stop,
            "run_isolated_test": run_isolated_test,
        }
        args.update(options)
        return NativeFirstCycle(**args)

    def test_real_apply_then_exact_restore(self):
        cycle = self.make()
        self.assertEqual(cycle.test()["status"], "CANDIDATE_TESTED")
        self.assertEqual(cycle.apply()["status"], "SANDBOX_APPLIED")
        self.assertEqual(self.path.read_bytes(), AFTER)
        self.assertTrue(run_isolated_test(self.path.read_bytes()))
        result = cycle.rollback()
        self.assertEqual(result["status"], "SANDBOX_ROLLBACK_VERIFIED")
        self.assertEqual(self.path.read_bytes(), BEFORE)
        self.assertEqual(self.seen, ["selfbuilder.source.test", "selfbuilder.source.apply",
                                     "selfbuilder.source.rollback"])
        self.assertFalse(result["release_accepted"])

    def test_bad_sha(self):
        with self.assertRaises(FirstCycleHold):
            self.make(candidate_sha256="0" * 64)

    def test_bad_preimage(self):
        with self.assertRaises(FirstCycleHold):
            self.make(preimage_sha256="0" * 64)

    def test_wrong_ack(self):
        for bad in [{"session": "other"}, {"source_head": "a" * 40},
                    {"candidate_sha256": "0" * 64}, {"epoch": True},
                    {"status": "DENIED"}]:
            with self.subTest(bad=bad), self.assertRaises(FirstCycleHold):
                self.make(ack=bad)

    def test_grant_required_per_action(self):
        cycle = self.make()
        cycle.test()
        self.allowed.remove("selfbuilder.source.apply")
        with self.assertRaises(FirstCycleHold):
            cycle.apply()
        self.assertEqual(self.path.read_bytes(), BEFORE)

    def test_stop_before_test(self):
        cycle = self.make()
        self.stop = True
        with self.assertRaises(FirstCycleHold):
            cycle.test()
        self.assertEqual(self.path.read_bytes(), BEFORE)

    def test_changed_preimage(self):
        cycle = self.make()
        cycle.test()
        self.path.write_bytes(b"another writer")
        with self.assertRaises(FirstCycleHold):
            cycle.apply()
        self.assertEqual(self.path.read_bytes(), b"another writer")

    def test_changed_after_apply_blocks_rollback(self):
        cycle = self.make()
        cycle.test()
        cycle.apply()
        self.path.write_bytes(b"other writer")
        with self.assertRaises(FirstCycleHold):
            cycle.rollback()
        self.assertEqual(self.path.read_bytes(), b"other writer")

    def test_rollback_requires_new_grant(self):
        cycle = self.make()
        cycle.test()
        cycle.apply()
        self.allowed.remove("selfbuilder.source.rollback")
        with self.assertRaises(FirstCycleHold):
            cycle.rollback()
        self.allowed.add("selfbuilder.source.rollback")
        self.assertEqual(cycle.rollback()["sha256"], sha256(BEFORE))

    def test_target_and_symlink_denial(self):
        with self.assertRaises(FirstCycleHold):
            self.make(workspace=self.root / ".." / "..", candidate=AFTER)
        self.path.unlink()
        try:
            self.path.symlink_to(self.root / "escape.py")
        except OSError:
            self.skipTest("Symlink creation not permitted")
        with self.assertRaises(FirstCycleHold):
            self.make()


if __name__ == "__main__":
    unittest.main()
