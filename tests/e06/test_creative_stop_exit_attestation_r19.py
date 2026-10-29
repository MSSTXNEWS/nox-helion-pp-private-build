"""NOX V16 Creative STOP: original WPF owner verified-exit contract.

These are source-structure regressions, NOT compiled C# or Windows process
E2E tests. Real kill-failure, pending dispatch and child termination remain
mandatory Windows source/installer acceptance tasks.
Run: python -m unittest discover -s tests/e06 -p test_creative_stop_exit_attestation_r19.py -v
"""
import unittest
from pathlib import Path

SOURCE=Path(__file__).resolve().parents[2]/"integrations/creative/bridge/CreativeHostBridge.cs"


class CreativeStopSourceContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cs=SOURCE.read_text(encoding="utf-8-sig")
        cls.action=cls.cs[
            cls.cs.index('if (action=="stop")'):
            cls.cs.index('if (action=="download")')]
        cls.stop=cls.cs[
            cls.cs.index("private async Task<string> StopCreativeWorkerAsync()"):
            cls.cs.rindex("\n}")]

    def test_stop_awaits_worker_verification(self):
        self.assertIn("var stopResult=await StopCreativeWorkerAsync();",self.action)
        self.assertNotIn("StopCreativeWorker();",self.cs)

    def test_unconfirmed_exit_emits_failure_not_success(self):
        self.assertIn('error="CREATIVE_STOP_NOT_CONFIRMED"',self.action)
        self.assertIn('if (stopResult=="STOPPED" || stopResult=="NO_ACTIVE_WORKER")',self.action)
        self.assertIn('ok=false',self.action)

    def test_success_distinguishes_exited_worker_from_no_worker(self):
        self.assertIn('status=stopResult',self.action)
        self.assertIn('"NATIVE_WORKER_EXIT_VERIFIED"',self.action)
        self.assertIn('"NATIVE_NO_ACTIVE_WORKER"',self.action)
        self.assertNotIn('"NATIVE_PROCESS_TREE_TERMINATION_REQUESTED"',self.action)

    def test_worker_exit_actually_waited_for(self):
        self.assertIn("worker.Kill(entireProcessTree:true);",self.stop)
        self.assertIn("await worker.WaitForExitAsync(timeout.Token);",self.stop)
        self.assertIn("if (!worker.HasExited)",self.stop)

    def test_timeout_bounded_and_failure_fails_closed(self):
        self.assertIn("new CancellationTokenSource(TimeSpan.FromSeconds(5))",self.stop)
        self.assertIn('"CREATIVE_WORKER_STOP_UNCONFIRMED "',self.stop)
        self.assertEqual(self.stop.count('return "STOP_UNCONFIRMED";'),3)

    def test_unowned_queued_request_with_no_worker_is_hold(self):
        self.assertIn('if (worker is null && !_creativePending.IsEmpty)',self.stop)
        self.assertIn('return "STOP_UNCONFIRMED";',self.stop)
        self.assertIn('return worker is null ? "NO_ACTIVE_WORKER" : "STOPPED";',self.stop)

    def test_stop_uses_original_start_and_write_gates(self):
        self.assertIn("await _creativeStartGate.WaitAsync();",self.stop)
        self.assertIn("await _creativeWriteGate.WaitAsync();",self.stop)
        self.assertIn("_creativeStartGate.Release();",self.stop)
        self.assertIn("_creativeWriteGate.Release();",self.stop)

    def test_pending_drained_only_after_verified_exit(self):
        self.assertLess(self.stop.index("if (!worker.HasExited)"),
                        self.stop.index("foreach(var pending in _creativePending.Keys)"))
        self.assertIn('error="STOPPED_BY_USER"',self.stop)

    def test_exact_worker_pointer_reset_only_after_exit(self):
        self.assertLess(self.stop.index("if (!worker.HasExited)"),
                        self.stop.index("_creativeWorker=null;"))
        self.assertIn("ReferenceEquals(_creativeWorker,worker)",self.stop)

    def test_original_function_lock_and_integrity_retained(self):
        self.assertIn("HoldApprovedCreativeWorker(path)",self.cs)
        self.assertIn("SHA256.HashData(handle)",self.cs)
        self.assertIn("_creativePending.TryAdd(requestId!,0)",self.cs)
        self.assertIn("OpenModelCenter();",self.cs)


if __name__=="__main__":
    unittest.main()
