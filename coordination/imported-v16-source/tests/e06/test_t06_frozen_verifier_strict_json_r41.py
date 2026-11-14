"""Source-only R41 guard for the original frozen Windows EXE verifier.

Does NOT build, run, install, or attest any Windows binary or E07 result.
"""
from __future__ import annotations
import importlib.util
import pathlib
import struct
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

VERIFIER = pathlib.Path(__file__).resolve().parents[2] / "coordination/e06/t06_verify_frozen_candidate.py"
spec = importlib.util.spec_from_file_location("nox_t06_frozen_verifier_r41", VERIFIER)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class R41FrozenVerifierStrictJson(unittest.TestCase):
    def test_valid_hold_and_normal_finite_numbers(self):
        reply = verifier.strict_json_object(
            b'{"status":"HOLD","result":{"values":[-2.5,1e2]}}', "R41_JSON_HOLD")
        self.assertEqual(reply["status"], "HOLD")
        self.assertEqual(reply["result"]["values"], [-2.5, 100.0])

    def test_nested_duplicate_nonfinite_invalid_utf8_and_scalar_failclosed(self):
        cases = (
            b'{"status":"HOLD","status":"OK"}',
            b'{"result":{"models":[],"models":["forged"]}}',
            b'{"release_accepted":false,"release_accepted":true}',
            b'{"value":NaN}', b'{"value":Infinity}', b'{"value":-Infinity}',
            b'{"value":1e10000}', b'{"status":"HOLD"', b'[]',
            b'null', b'"OK"', bytes([255]), b'',
        )
        for raw in cases:
            with self.subTest(raw=raw), self.assertRaisesRegex(RuntimeError, "R41_JSON_HOLD"):
                verifier.strict_json_object(raw, "R41_JSON_HOLD")

    def test_receipt_preserves_false_and_rejects_duplicate_oversize_and_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            proof = pathlib.Path(tmp) / "proof.json"
            proof.write_text('{"release_accepted":false}', encoding="utf-8")
            self.assertIs(verifier.strict_receipt(proof, "R41_RECEIPT_HOLD")["release_accepted"], False)
            proof.write_text('{"release_accepted":false,"release_accepted":true}', encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "R41_RECEIPT_HOLD"):
                verifier.strict_receipt(proof, "R41_RECEIPT_HOLD")
            proof.write_bytes(b"x" * 1_048_577)
            with self.assertRaisesRegex(RuntimeError, "R41_RECEIPT_HOLD"):
                verifier.strict_receipt(proof, "R41_RECEIPT_HOLD")
            proof.write_text('{"release_accepted":false}', encoding="utf-8")
            alias = pathlib.Path(tmp) / "alias.json"
            try:
                alias.symlink_to(proof)
            except (OSError, NotImplementedError):
                return  # Windows symlink permission may be unavailable.
            with self.assertRaisesRegex(RuntimeError, "R41_RECEIPT_HOLD"):
                verifier.strict_receipt(alias, "R41_RECEIPT_HOLD")

    def test_real_request_function_mocked_only_to_regress_ambiguous_frame(self):
        nonce = "fedcba0987654321fedcba0987654321"
        run_id = "NOX-R41-UNIT-ONLY"
        body = (
            '{"protocol":"NOX-P02-NATIVE-v1","runId":"' + run_id +
            '","requestId":"' + nonce +
            '","status":"HOLD","status":"OK"}'
        ).encode("utf-8")
        wire = struct.pack(">I", len(body)) + body
        fake = SimpleNamespace(returncode=0, stdout=wire, stderr=b"")
        with patch.object(verifier.subprocess, "run", return_value=fake) as mocked:
            with self.assertRaisesRegex(RuntimeError, "R66_FROZEN_REPLY_AMBIGUOUS_JSON_HOLD"):
                verifier.request(pathlib.Path("fake-not-executed.exe"), "chat.model",
                                 run_id, nonce, pathlib.Path("."))
            mocked.assert_called_once()

    def test_original_verifier_only_has_single_guarded_json_decoder(self):
        source = VERIFIER.read_text(encoding="utf-8")
        self.assertEqual(source.count("json.loads("), 1)
        self.assertIn('reply = strict_json_object(raw[4:], "R66_FROZEN_REPLY_AMBIGUOUS_JSON_HOLD")', source)
        self.assertEqual(source.count("strict_receipt("), 9)  # definition + 8 evidence reads
        self.assertNotIn("json.loads(raw[4:].decode", source)


if __name__ == "__main__":
    unittest.main()
