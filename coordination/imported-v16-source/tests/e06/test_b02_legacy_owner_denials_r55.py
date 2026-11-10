"""B02: source-contract parity for original legacy HOME owner ACK denials.

Source-level only; a passing check does not prove Windows GUI/IPC or E07.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
LEGACY = ROOT / "coordination/e06/MainWindow.NativeP02.cs"
BRIDGE = ROOT / "coordination/e06/OneHostP02WebView2Bridge.cs"


class LegacyOwnerDenialParity(unittest.TestCase):
    def test_reject_all_known_native_owner_denials_without_losing_positive_results(self):
        source = LEGACY.read_text(encoding="utf-8")
        bridge = BRIDGE.read_text(encoding="utf-8")
        section = source.split("private static bool LegacyOwnerStatusDenied(string? status)", 1)[1]
        section = section.split("private static bool LegacyOwnerDenial(", 1)[0]
        self.assertIn('LegacyOwnerStatusDenied(state)', source)
        self.assertIn("private static bool NativeOwnerStatusDenied(string? status)", bridge)
        self.assertIn('LegacyOwnerDenial(nativeStop.Result)', source)
        arrays = re.findall(r"foreach\s*\(var\s+\w+\s+in\s+new\[\]\s*\{([^}]*)\}", section, re.S)
        self.assertEqual(len(arrays), 2, "both fail-closed status inventories retained")
        suffixes, exact = [set(re.findall(r'"([^"]+)"', item)) for item in arrays]
        self.assertTrue(all(needle in section for needle in (
            'value.StartsWith("NOT_AUTHORIZED"',
            'value.StartsWith("NOT_AUTHENTICATED"',
            'Regex.Replace(status.Trim()',
        )))
        def denied(status):
            if not status or not status.strip():
                return True
            normalized = re.sub(r"[\s-]+", "_", status.strip()).upper()
            return (normalized in exact or
                    any(normalized.endswith(suffix) for suffix in suffixes) or
                    normalized.startswith(("NOT_AUTHORIZED", "NOT_AUTHENTICATED")))
        bad = (
            "HOLD", "DENIED", "OFFLINE", "FAILED", "ERROR",
            "CONSENT_PENDING", "NOT_AUTHORIZED", "NOT_AUTHENTICATED",
            "FORBIDDEN", "UNAVAILABLE", "AWAITING_CONSENT",
            "REJECTED", "CANCELLED", "BLOCKED", "REFUSED", "REVOKED",
            "ABORTED", "EXPIRED", "STOPPED", "NOT_READY", "NEEDS_CONSENT",
            "JOB_CANCELLED", "JOB_REVOKED", "JOB_EXPIRED", "JOB_STOPPED",
            "JOB_ABORTED", "JOB_REJECTED", "MODEL_BLOCKED", "OWNER_REFUSED",
            "OWNER-REVOKED", "CONSENT REQUIRED", "NOT_AUTHORIZED_ROLE",
            "NOT-AUTHENTICATED-SID", "OWNER_HOLD", "OWNER_MISMATCH",
        )
        good = ("PASS", "OK", "READY", "COMPLETED", "SUCCESS", "RUNNING", "QUEUED")
        for state in bad:
            with self.subTest(denial=state):
                self.assertTrue(denied(state), state)
        for state in good:
            with self.subTest(positive=state):
                self.assertFalse(denied(state), state)


if __name__ == "__main__":
    unittest.main()
