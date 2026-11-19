import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import owner_native_operator as operator
import owner_refill_snapshot_transport as transport


class RefillSnapshotTransportTests(unittest.TestCase):
    source = "1" * 40
    request = 123

    @classmethod
    def setUpClass(cls):
        cls.private = rsa.generate_private_key(public_exponent=65537, key_size=4096)
        der = cls.private.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        cls.recipient = base64.urlsafe_b64encode(der).decode().rstrip("=")

    def records(self):
        rows = {name: {"fixture": "PRIVATE_REFILL_CANARY"} for _, name, _ in transport.MARKERS}
        rows["native_readback"] = {
            "schema": "NOX_SYSTEMIC_REFILL_NATIVE_READBACK_V1",
            "instance_id": 60509551,
            "owner_request_id": str(self.request),
            "owner_source_sha": self.source,
            "native_write_performed": False,
            "publication_authorized": False,
        }
        return rows

    def stdout(self, rows):
        lines = [
            f"NOX_MAINT_{marker}=" + json.dumps(rows[name])
            for marker, name, _ in transport.MARKERS
        ]
        return "\n".join([*lines, transport.COMPLETE]) + "\n"

    def test_ciphertext_and_published_receipt_hide_live_records(self):
        rows = self.records()
        with tempfile.TemporaryDirectory() as work, mock.patch.dict(os.environ, {"RUNNER_TEMP": work}):
            receipt = transport.save_encrypted_snapshot(
                self.stdout(rows), 0, self.recipient, self.request, self.source
            )
            artifact = Path(work) / transport.ARTIFACT_NAME
            raw = artifact.read_bytes()
            self.assertEqual(artifact.stat().st_mode & 0o777, 0o600)
            self.assertEqual(receipt["sha256"], hashlib.sha256(raw).hexdigest())
            self.assertNotIn(b"PRIVATE_REFILL_CANARY", raw)
            self.assertNotIn("PRIVATE_REFILL_CANARY", json.dumps(receipt))
            envelope = json.loads(raw)
            aad = {name: envelope[name] for name in
                   ("schema", "request_id", "source_sha", "recipient_sha256")}
            aes = self.private.decrypt(
                base64.b64decode(envelope["wrapped_key_b64"]),
                padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),
                             algorithm=hashes.SHA256(), label=transport.SCHEMA.encode()),
            )
            plaintext = AESGCM(aes).decrypt(
                base64.b64decode(envelope["nonce_b64"]),
                base64.b64decode(envelope["ciphertext_b64"]),
                transport._canonical(aad),
            )
            self.assertEqual(json.loads(plaintext), rows)
            with self.assertRaises(FileExistsError):
                transport.save_encrypted_snapshot(
                    self.stdout(rows), 0, self.recipient, self.request, self.source
                )

    def test_incomplete_duplicate_and_extra_output_are_rejected(self):
        stdout = self.stdout(self.records())
        cases = (
            stdout.replace(transport.COMPLETE, ""),
            stdout + "unexpected line\n",
            stdout.replace('"fixture": "PRIVATE_REFILL_CANARY"',
                           '"fixture": 1, "fixture": 2'),
        )
        for value in cases:
            with self.subTest(value=value), self.assertRaisesRegex(
                    RuntimeError, "HOLD_REFILL_SNAPSHOT_(OUTPUT_SHAPE|RECORD)"):
                transport.collect_snapshot(value, 0)
        with self.assertRaisesRegex(RuntimeError, "HOLD_REFILL_SNAPSHOT_SERVER_GATE"):
            transport.collect_snapshot(transport.HOLD_PREFIX + '{"reason":"PRIVATE_REFILL_CANARY"}\n', 2)

    def test_rejects_wrong_command_and_never_creates_an_artifact(self):
        rows = self.records()
        rows["native_readback"]["owner_request_id"] = str(self.request + 1)
        with tempfile.TemporaryDirectory() as work, mock.patch.dict(os.environ, {"RUNNER_TEMP": work}):
            with self.assertRaisesRegex(RuntimeError, "HOLD_REFILL_SNAPSHOT_COMMAND_BINDING"):
                transport.save_encrypted_snapshot(
                    self.stdout(rows), 0, self.recipient, self.request, self.source
                )
            self.assertEqual(list(Path(work).iterdir()), [])

    def test_owner_api_credential_is_never_passed_to_child_processes(self):
        with mock.patch.dict(os.environ, {"NOX2": "PRIVATE_API_CANARY", "PATH": "/fixture"}):
            with mock.patch.object(operator.subprocess, "run") as run:
                operator._safe_subprocess_run(["ssh"], env={"NOX2": "PRIVATE_ARG_CANARY"})
            with mock.patch.object(operator.subprocess, "check_output") as checked:
                operator._safe_subprocess_check_output(["git"])
        for child in (run, checked):
            self.assertEqual(child.call_args.kwargs["env"]["PATH"], "/fixture")
            self.assertNotIn("NOX2", child.call_args.kwargs["env"])

    def test_recipient_must_be_a_canonical_public_rsa_key(self):
        for invalid in (self.recipient + "=", "A" * 700, "A" * 20):
            with self.assertRaisesRegex(RuntimeError, "HOLD_REFILL_SNAPSHOT_RECIPIENT"):
                transport.load_recipient_key(invalid)


if __name__ == "__main__":
    unittest.main()
