"""NOX W1.03 E06 R19: read-only source regression for truthful Creative STOP.

TestID: E06-W1-03-R19-CREATIVE-STOP-ACK.
Only test against the pinned real C# owner Git blob; a source excerpt may be
used for LOCAL DIAGNOSTICS with NOX_SOURCE_EXCERPT_ONLY=1, never source acceptance.
No Windows executable or product file is written or run.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import re
import unittest

EXPECTED_OWNER_GIT_BLOB_SHA1 = "2e70b68b85f2c968a3a46b7d6befd4611a789d89"
SOURCE = Path(os.getenv("NOX_CREATIVE_BRIDGE_PATH", "integrations/creative/bridge/CreativeHostBridge.cs"))


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def source_parts(data: str) -> tuple[str, str]:
    dispatch_start = data.index("private async Task DispatchCreativeAsync(")
    dispatch_end = data.index("// Runtime payload consistency check", dispatch_start)
    dispatch = data[dispatch_start:dispatch_end]
    stop_start = dispatch.index('if (action=="stop")')
    stop_end = dispatch.index('if (action=="download")', stop_start)
    return dispatch, dispatch[stop_start:stop_end]


class CreativeStopTruthfulnessR19(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw = SOURCE.read_bytes()
        cls.git_blob = git_blob_sha1(raw)
        if os.getenv("NOX_SOURCE_EXCERPT_ONLY") != "1":
            if cls.git_blob != EXPECTED_OWNER_GIT_BLOB_SHA1:
                raise RuntimeError(
                    f"STALE_OWNER_PREIMAGE_HOLD expected={EXPECTED_OWNER_GIT_BLOB_SHA1} "
                    f"observed={cls.git_blob}; fetch PR162 latest HEAD before relying on results"
                )
        cls.source = raw.decode("utf-8-sig")
        cls.dispatch, cls.stop_branch = source_parts(cls.source)
        stop_start = cls.source.index("private async Task<bool> StopCreativeWorkerAsync()")
        cls.stop_method = cls.source[stop_start:]

    def test_01_duplicate_pending_admission_retained(self):
        self.assertRegex(self.dispatch, r"if\s*\(\s*!_creativePending\.TryAdd\(requestId!,0\)\s*\)")

    def test_02_pending_stop_fails_requests(self):
        self.assertIn("_creativePending.TryRemove(pending,out _)", self.stop_method)
        self.assertIn('error="STOPPED_BY_USER"', self.stop_method)

    def test_03_worker_hash_pin_retained(self):
        self.assertIn("HoldApprovedCreativeWorker(path)", self.source)
        self.assertIn("SHA256.HashData(handle)", self.source)

    def test_04_stop_success_cannot_be_unconditional(self):
        # Existing source reports success directly after an unchecked void stop.
        unconditional = re.search(
            r"StopCreativeWorker\(\)\s*;\s*PostMessage\(\s*new\s*\{"
            r"\s*kind=\"creativeResult\",\s*requestId,\s*ok=true",
            self.stop_branch, flags=re.S,
        )
        self.assertIsNone(unconditional,
                          "SOURCE RED: unconditional STOPPED ack without verified exit")

    def test_05_kill_error_must_not_be_ignored_for_ack(self):
        # The catch currently logs and returns normally while caller sends ok=true.
        swallowing = re.search(
            r"catch\s*\(Exception\s+ex\)\s*\{\s*"
            r"WriteLog\(\"CREATIVE_WORKER_STOP\s+\"\s*\+\s*ex.GetType\(\)\.Name\);\s*\}",
            self.stop_method,
        )
        if swallowing:
            self.assertNotIn("ok=true", self.stop_branch,
                             "SOURCE RED: Kill exception swallowed then STOP acknowledged")

    def test_06_stop_requires_exit_observation(self):
        # Waiting for native exit or demonstrating exited state is necessary
        # before issuing a definitive STOPPED acknowledgement; source-only gate.
        proof = re.search(r"\bWaitForExit(?:Async)?\s*\(|\bHasExited\s*\)\s*\{",
                          self.stop_branch + self.stop_method)
        self.assertIsNotNone(proof,
                             "SOURCE RED: no post-Kill exit verification before STOPPED")

    def test_07_stop_requires_gates_before_verified_success(self):
        self.assertIn("await _creativeStartGate.WaitAsync()", self.stop_method)
        self.assertIn("await _creativeWriteGate.WaitAsync()", self.stop_method)
        self.assertIn("await worker.WaitForExitAsync(timeout.Token)", self.stop_method)
        self.assertIn("if (!worker.HasExited)", self.stop_method)
        self.assertIn("var stopped=await StopCreativeWorkerAsync()", self.stop_branch)
        self.assertRegex(self.stop_branch, r'if\s*\(stopped\)[\s\S]*?ok=true')
        self.assertRegex(self.stop_branch, r'else[\s\S]*?ok=false')

    def test_08_failed_kill_does_not_dismiss_pending_requests(self):
        before = self.stop_method.index('catch (Exception ex)')
        end = self.stop_method.index('foreach(var pending', before)
        self.assertIn('return false;', self.stop_method[before:end])
        self.assertNotIn('TryRemove', self.stop_method[before:end])
        self.assertIn('CREATIVE_STOP_NOT_CONFIRMED', self.stop_branch)

    def test_09_prior_security_guards_preserved(self):
        self.assertIn('HoldApprovedCreativeWorker(path)', self.source)
        self.assertIn('if (!_creativePending.TryAdd(requestId!,0))', self.source)
        self.assertIn('Kill(entireProcessTree:true)', self.stop_method)
        self.assertIn('error="STOPPED_BY_USER"', self.stop_method)


if __name__ == "__main__":
    unittest.main(verbosity=2)
