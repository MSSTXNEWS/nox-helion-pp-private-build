"""R124: Frozen producer OFFLINE_HOLD must not become installed-model PASS.

Tests exercise exact original same-VM smoke module; they do not simulate E07.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import types
import unittest
from unittest import mock

SOURCE = Path(__file__).resolve().parents[2] / "coordination/e06/t06_samevm_installed_smoke.py"
SPEC = importlib.util.spec_from_file_location("nox_r124_real_smoke", SOURCE)
assert SPEC and SPEC.loader
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


class FrozenModelInventoryReceipt(unittest.TestCase):
    @staticmethod
    def offline():
        return {"native_modelcenter_installed_read_only": "PROVIDER_OFFLINE_HOLD",
                "models_installed_uses_original_local_discovery": False,
                "modelcenter_provider_offline_verified": True,
                "frozen_chat_model_response_status": "OK",
                "real_ollama_model_inference_tested": False}

    def test_trusted_offline_receipt_is_a_hold_not_installed_pass(self):
        self.assertEqual(smoke.verified_native_model_inventory_state(self.offline()),
                         "PROVIDER_OFFLINE_HOLD")

    def test_real_installed_inventory_pass_is_unchanged(self):
        receipt = self.offline()
        receipt.update(native_modelcenter_installed_read_only="PASS",
                       models_installed_uses_original_local_discovery=True,
                       modelcenter_provider_offline_verified=False)
        self.assertEqual(smoke.verified_native_model_inventory_state(receipt),
                         "INSTALLED_INVENTORY_PASS")

    def test_non_verifiable_offline_and_conflicting_evidence_hold(self):
        for key, value in (("models_installed_uses_original_local_discovery", True),
                           ("modelcenter_provider_offline_verified", False),
                           ("frozen_chat_model_response_status", "HOLD"),
                           ("real_ollama_model_inference_tested", True),
                           ("native_modelcenter_installed_read_only", "PASS")):
            with self.subTest(key=key):
                receipt = self.offline()
                receipt[key] = value
                with self.assertRaisesRegex(RuntimeError, "T06_BRIDGE_NATIVE_MODEL_INVENTORY_HOLD"):
                    smoke.verified_native_model_inventory_state(receipt)

    def test_no_implicit_pass_from_missing_status_fields(self):
        with self.assertRaisesRegex(RuntimeError, "T06_BRIDGE_NATIVE_MODEL_INVENTORY_HOLD"):
            smoke.verified_native_model_inventory_state({})

    @staticmethod
    def answer(status, *, error_code=None, result=None):
        reply = {"protocol": "NOX-P02-NATIVE-v1",
                 "runId": "NOX-P02-INSTALLED-CANDIDATE-20261030",
                 "requestId": "aa55bb66cc77dd88ee99ff0011223344",
                 "status": status, "result": result}
        if error_code is not None:
            reply["errorCode"] = error_code
        body = json.dumps(reply).encode("utf-8")
        return struct.pack(">I", len(body)) + body

    def test_installed_real_provider_hold_is_honest_and_frame_authenticated(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "backend.exe"
            binary.write_bytes(b"frozen-original-binary-test-fixture")
            response = types.SimpleNamespace(returncode=0,
                stdout=self.answer("HOLD", error_code="NATIVE_PROVIDER_HOLD", result=None))
            receipt = {"native_source_receipt":
                       "ORIGINAL_FROZEN_MODELCENTER_PROVIDER_OFFLINE_HOLD_NOT_E07"}
            with mock.patch.object(smoke, "ON_LOCAL_BRIDGE", True), \
                 mock.patch.object(smoke.subprocess, "run", return_value=response) as proc:
                verified = smoke.framed(binary, Path(tmp) / "data", receipt)
            self.assertEqual(verified["status"], "PROVIDER_OFFLINE_HOLD")
            self.assertEqual(verified["route"], "models.installed")
            self.assertFalse(verified["model_inventory_route_verified"])
            self.assertTrue(verified["run_id_matched"])
            self.assertEqual(proc.call_count, 1)

    def test_installed_hold_never_bypasses_frame_or_offline_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "backend.exe"
            binary.write_bytes(b"test-frozen-exe")
            offline_marker = {"native_source_receipt":
                              "ORIGINAL_FROZEN_MODELCENTER_PROVIDER_OFFLINE_HOLD_NOT_E07"}
            cases = [
                ("HOLD", "UNRELATED", None, offline_marker),
                ("HOLD", "NATIVE_PROVIDER_HOLD", [], offline_marker),
                ("HOLD", "NATIVE_PROVIDER_HOLD", None, {}),
                ("OK", None, None, offline_marker),
            ]
            for status, code, result, receipt in cases:
                with self.subTest(status=status, code=code, result=result, receipt=receipt):
                    response = types.SimpleNamespace(returncode=0,
                        stdout=self.answer(status, error_code=code, result=result))
                    with mock.patch.object(smoke, "ON_LOCAL_BRIDGE", True), \
                         mock.patch.object(smoke.subprocess, "run", return_value=response):
                        with self.assertRaisesRegex(RuntimeError,
                                "T06_INSTALLED_BACKEND_FRAME_IDENTITY_OR_MODEL_HOLD"):
                            smoke.framed(binary, Path(tmp) / "data", receipt)

    def test_installed_genuine_models_response_remains_pass_not_live_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "backend.exe"
            binary.write_bytes(b"test-frozen-exe")
            response = types.SimpleNamespace(returncode=0,
                stdout=self.answer("OK", result={"models": []}))
            with mock.patch.object(smoke, "ON_LOCAL_BRIDGE", True), \
                 mock.patch.object(smoke.subprocess, "run", return_value=response):
                verified = smoke.framed(binary, Path(tmp) / "data", {})
            self.assertEqual(verified["status"], "PASS")
            self.assertTrue(verified["model_inventory_route_verified"])
            self.assertIs(verified["real_model_inference_tested"], False)


if __name__ == "__main__":
    unittest.main()
