"""M10 original WPF/OneHost C# A1 ticket isolation: source contract only; Windows NOT_RUN."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
P=ROOT/"Packages"/"P02"/"worker-chat"/"NativePythonPipe.cs"
W=ROOT/"coordination"/"e06"/"MainWindow.NativeP02.cs"

class A1TicketIsolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=P.read_text(encoding="utf-8")
        cls.w=W.read_text(encoding="utf-8")

    def test_renderer_generic_path_denies_ticket(self):
        self.assertIn("allowNativeA1Ticket: false",self.p)
        self.assertIn('data.TryGetProperty("a1_wpf_ticket", out _)',self.p)
        self.assertIn("PAGE_A1_OWNER_TICKET_DENIED",self.p)

    def test_exact_private_action_and_envelope(self):
        self.assertIn('action is not ("selfbuilder.a1.boot" or "selfbuilder.a1.tick")',self.p)
        self.assertIn('route != "chat.commands"',self.p)
        self.assertIn('if (fields != 2)',self.p)
        self.assertIn("A1_NATIVE_OWNER_TICKET_ENVELOPE_HOLD",self.p)

    def test_no_second_host_or_protocol(self):
        self.assertIn('protocol = "NOX-P02-NATIVE-v1"',self.p)
        self.assertNotIn("HttpListener",self.p)
        self.assertNotIn("Process.Start",self.p)

    def test_hmac_remains_wpf_owned(self):
        self.assertIn("CreateA1PrivateConsentReceipt(a1Name)",self.w)
        self.assertIn("RequestWpfApprovedA1Async(a1Name,ticket,cancel)",self.w)
        self.assertIn("HMACSHA256.HashData",self.w)
        self.assertNotIn("ECDsa.Create",self.w)

    def test_stop_still_revokes_proof(self):
        self.assertIn("Interlocked.Increment(ref _a1OwnerStopEpoch);",self.w)
        self.assertIn("CryptographicOperations.ZeroMemory(_a1OwnerProofKey);",self.w)
        self.assertIn("A1_WPF_FRESH_CONSENT_REQUIRED",self.w)

    def test_private_api_is_only_bridge_call(self):
        self.assertEqual(self.p.count("RequestWpfApprovedA1Async("),1)
        self.assertEqual(self.p.count("allowNativeA1Ticket: true"),1)
        self.assertEqual(self.w.count("RequestWpfApprovedA1Async("),1)

if __name__=="__main__":
    unittest.main()
