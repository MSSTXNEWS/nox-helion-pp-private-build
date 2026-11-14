#!/usr/bin/env python3
"""B02 SOURCE_ONLY contract: original native owner ACK needs factual result.

Run under E06 source tests: python -m unittest tests/e06/test_b02_native_missing_receipt_holds.py
This is a source-level regression, NOT installed Windows/IPC acceptance.
"""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "coordination/e06/OneHostP02WebView2Bridge.cs"
LEGACY = ROOT / "coordination/e06/MainWindow.NativeP02.cs"


class NativeOwnerReceiptGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bridge = BRIDGE.read_text(encoding="utf-8")
        cls.legacy = LEGACY.read_text(encoding="utf-8")

    def test_owner_and_pipe_require_factual_non_null_receipt(self):
        for guard in (
            "ownerResult.Result is JsonElement ownerReceipt",
            "ownerReceipt.ValueKind is not (JsonValueKind.Undefined or JsonValueKind.Null)",
            "result.Result is JsonElement nativeReceipt",
            "nativeReceipt.ValueKind is not (JsonValueKind.Undefined or JsonValueKind.Null)",
        ):
            with self.subTest(guard=guard):
                self.assertEqual(self.bridge.count(guard), 1)

    def test_native_denial_and_stop_revocation_remain_in_owner_paths(self):
        for token in (
            "NativeResultExplicitlyDenied(ownerResult.Result)",
            "NativeResultExplicitlyDenied(result.Result)",
            "Interlocked.Increment(ref _streamEpoch)",
            "_nativeAcl(_ownerWindowsSid, route)",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.bridge)

    def test_legacy_stop_and_chat_require_factual_result(self):
        for guard in (
            "nativeStop.Result is not JsonElement stopReceipt",
            "stopReceipt.ValueKind is JsonValueKind.Undefined or JsonValueKind.Null",
            "result.Result is not JsonElement legacyReceipt",
            "legacyReceipt.ValueKind is JsonValueKind.Undefined or JsonValueKind.Null",
            "LegacyOwnerDenial(result.Result)",
        ):
            with self.subTest(guard=guard):
                self.assertEqual(self.legacy.count(guard), 1)


if __name__ == "__main__":
    unittest.main()
