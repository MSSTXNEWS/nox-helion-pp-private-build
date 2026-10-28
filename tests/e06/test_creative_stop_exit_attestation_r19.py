"""NOX V16 Creative STOP: fail-closed source contract for the original WPF owner.

The assertions deliberately inspect product C# and are NOT a Windows worker
execution or full descendant-process-tree termination test.
Run: python -m unittest discover -s tests/e06 -p test_creative_stop_exit_attestation_r19.py -v
"""
import re
import unittest
from pathlib import Path

SOURCE=Path(__file__).resolve().parents[2]/"integrations/creative/bridge/CreativeHostBridge.cs"

class CreativeStopSourceContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cs=SOURCE.read_text(encoding="utf-8-sig")
        cls.stop=cls.cs[
            cls.cs.index("private async Task<string> StopCreativeWorkerAsync()"):
            cls.cs.rindex("\n}")]

    def test_stop_response_awaits_verification_not_just_kill_request(self):
        self.assertIn("var stopState=await StopCreativeWorkerAsync();",self.cs)
        self.assertNotIn("StopCreativeWorker();",self.cs)

    def test_failed_exit_does_not_get_true_stop_ack(self):
        action=self.cs[self.cs.index('if (action=="stop")'):self.cs.index('if (action=="download")')]
        self.assertIn('if (stopState=="STOP_UNCONFIRMED")',action)
        self.assertRegex(action,r'stopState=="STOP_UNCONFIRMED"\)\s*PostMessage\(new \{kind="creativeResult",requestId,ok=false')
        self.assertIn("CREATIVE_WORKER_EXIT_NOT_CONFIRMED",action)
        self.assertIn("ok=true",action)
        self.assertIn("NATIVE_WORKER_EXIT_CONFIRMED",action)
        self.assertNotIn("NATIVE_PROCESS_TREE_TERMINATION_REQUESTED",action)

    def test_actual_worker_exit_must_be_confirmed_after_kill(self):
        self.assertIn("process.Kill(entireProcessTree:true);",self.stop)
        self.assertIn("await process.WaitForExitAsync(deadline.Token);",self.stop)
        self.assertIn("if (!process.HasExited)",self.stop)

    def test_kill_exception_is_fail_closed(self):
        self.assertRegex(self.stop,r'catch\(Exception ex\)\s*\{\s*WriteLog\("CREATIVE_WORKER_STOP_UNCONFIRMED "')
        self.assertIn('return "STOP_UNCONFIRMED";',self.stop)

    def test_kill_timeout_is_bounded(self):
        self.assertIn("new CancellationTokenSource(TimeSpan.FromSeconds(5))",self.stop)

    def test_unconfirmed_stop_keeps_pending_receipts_for_host_review(self):
        verify=self.stop.index("if (!process.HasExited)")
        error=self.stop.index('return "STOP_UNCONFIRMED";',verify)
        drain=self.stop.index("foreach(var pending in _creativePending.Keys)")
        self.assertLess(error,drain)

    def test_stop_serializes_with_original_worker_start_and_write(self):
        self.assertIn("await _creativeStartGate.WaitAsync();",self.stop)
        self.assertIn("await _creativeWriteGate.WaitAsync();",self.stop)
        self.assertIn("_creativeWriteGate.Release();",self.stop)
        self.assertIn("_creativeStartGate.Release();",self.stop)

    def test_no_active_worker_is_not_reported_as_stopped(self):
        self.assertIn('_creativePending.IsEmpty ? "NO_ACTIVE_WORKER" : "STOP_UNCONFIRMED"',self.stop)
        self.assertIn("NATIVE_NO_ACTIVE_WORKER",self.cs)

    def test_worker_object_cleared_only_after_exit(self):
        verified=self.stop.index("if (!process.HasExited)")
        clear=self.stop.index("_creativeWorker=null;")
        self.assertLess(verified,clear)
        self.assertIn("ReferenceEquals(_creativeWorker,process)",self.stop)

    def test_original_import_security_and_user_cancel_receipts_retained(self):
        self.assertIn("HoldApprovedCreativeWorker(path)",self.cs)
        self.assertIn("_creativePending.TryAdd(requestId!,0)",self.cs)
        self.assertIn('error="STOPPED_BY_USER"',self.stop)
        self.assertIn("OpenModelCenter();",self.cs)

if __name__=="__main__":
    unittest.main()
