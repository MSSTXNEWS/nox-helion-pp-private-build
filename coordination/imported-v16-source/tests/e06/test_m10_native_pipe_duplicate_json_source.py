"""M10 original NativePythonPipe duplicate JSON security source regression.

Scope: existing Windows x64 NOX HELION EXPRESS INTEGRATOR only.
This is a fail-closed SOURCE CONTRACT test; not a .NET or installed EXE test.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
PIPE = ROOT / "Packages/P02/worker-chat/NativePythonPipe.cs"


class NativePipeDuplicateJsonSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PIPE.read_text(encoding="utf-8")

    def test_exact_one_recursive_uniqueness_guard(self):
        s = self.source
        self.assertEqual(s.count("private static void RequireUnambiguousJson("), 1)
        self.assertIn("new HashSet<string>(StringComparer.Ordinal)", s)
        self.assertIn("!keys.Add(property.Name)", s)
        self.assertIn('throw new NativePipeHold("NATIVE_JSON_DUPLICATE_FIELD_DENIED")', s)
        self.assertIn("RequireUnambiguousJson(property.Value);", s)
        self.assertIn("RequireUnambiguousJson(item);", s)

    def test_outbound_denied_before_frame_write_and_busy_side_effect(self):
        s = self.source
        serialized = s.index("JsonSerializer.SerializeToElement(payload)")
        guard = s.index("RequireUnambiguousJson(data);")
        busy = s.index("Interlocked.CompareExchange(ref _busy")
        framed = s.index("JsonSerializer.SerializeToUtf8Bytes(new")
        self.assertLess(serialized, guard)
        self.assertLess(guard, busy)
        self.assertLess(busy, framed)

    def test_inbound_denied_before_trusting_status_or_event(self):
        s = self.source
        decoded = s.index("var root = doc.RootElement;")
        guard = s.index("RequireUnambiguousJson(root);")
        protocol = s.index('root.TryGetProperty("protocol"')
        delivery = s.index('if (value == "EVENT")')
        self.assertLess(decoded, guard)
        self.assertLess(guard, protocol)
        self.assertLess(protocol, delivery)

    def test_prior_owner_only_a1_ticket_separation_no_loss(self):
        s = self.source
        self.assertIn("RequestWpfApprovedA1Async(", s)
        self.assertIn("allowNativeA1Ticket: false", s)
        self.assertIn("allowNativeA1Ticket: true", s)
        self.assertIn("PAGE_A1_OWNER_TICKET_DENIED", s)
        self.assertIn("A1_NATIVE_OWNER_TICKET_ENVELOPE_HOLD", s)
        self.assertIn("FaultAll(\"NATIVE_OUTPUT_TRANSPORT_FAILED\")", s)


if __name__ == "__main__":
    unittest.main()
