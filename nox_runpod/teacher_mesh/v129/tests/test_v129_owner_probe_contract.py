import base64
import unittest

from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
from nox_runpod.teacher_mesh.v129 import read_native_s03_write_contract as v129


PIN = "SHA256:G4hmMllaT4uSfx+Gup9vjSySLXJT1cSc/9XePr7XmGc"
HOST = "203.0.113.8"
PORT = 24422
PUBLIC_KEY = base64.b64encode(b"offline ed25519 fixture").decode("ascii")


class V129OwnerProbeContractTests(unittest.TestCase):
    def test_v51_default_and_v129_explicit_completion_contracts_are_distinct(self):
        v129_output = ("NATIVE_V129_SOURCE={}\nNATIVE_V129_WRITER_CONTRACT={}\n"
                       "NATIVE_V129_SCHEMA={}\nNATIVE_READ_ONLY_COMPLETE=true")
        self.assertFalse(ssh.remote_output_complete(0, v129_output))
        self.assertTrue(ssh.remote_output_complete(0, v129_output, v129.V129_COMPLETION_MARKERS))
        self.assertFalse(ssh.remote_output_complete(2, v129_output, v129.V129_COMPLETION_MARKERS))
        self.assertFalse(ssh.remote_output_complete(0, "NATIVE_READ_ONLY_COMPLETE=true", ()))

    def test_v129_acceptance_requires_cleanup_and_all_metadata_receipts(self):
        lines = ["NATIVE_V129_SOURCE={}", "NATIVE_V129_WRITER_CONTRACT={}",
                 "NATIVE_V129_SCHEMA={}", "NATIVE_READ_ONLY_COMPLETE=true"]
        self.assertTrue(v129.source_read_accepted(True, True, lines))
        self.assertFalse(v129.source_read_accepted(True, False, lines))
        self.assertFalse(v129.source_read_accepted(True, True, lines[:-1]))
        self.assertFalse(v129.source_read_accepted(False, True, lines))

    def test_host_key_pin_accepts_only_one_exact_endpoint_key_and_fingerprint(self):
        scan = f"[{HOST}]:{PORT} ssh-ed25519 {PUBLIC_KEY}\n"
        fingerprint = f"256 {PIN} owner-host (ED25519)\n"
        self.assertTrue(ssh.exact_host_key_pin(scan, fingerprint, HOST, PORT, PIN))
        extra = scan + f"[{HOST}]:{PORT} ssh-ed25519 {PUBLIC_KEY}\n"
        self.assertFalse(ssh.exact_host_key_pin(extra, fingerprint, HOST, PORT, PIN))
        self.assertFalse(ssh.exact_host_key_pin(scan, fingerprint, "203.0.113.9", PORT, PIN))
        self.assertFalse(ssh.exact_host_key_pin(scan, f"256 {PIN}suffix owner (ED25519)\n",
                                                HOST, PORT, PIN))
        self.assertFalse(ssh.exact_host_key_pin(scan, fingerprint + f"256 {PIN} owner2 (ED25519)\n",
                                                HOST, PORT, PIN))

    def test_workflow_is_source_only_and_pins_ref_sha_and_actions(self):
        from pathlib import Path
        text = Path(".github/workflows/nox-v129-s03-write-contract-readonly.yml").read_text()
        self.assertIn("source_ref:", text)
        self.assertIn("source_sha:", text)
        self.assertIn("rev-parse", text)
        self.assertIn("HEAD", text)
        self.assertIn("github.repository", text)
        self.assertNotIn("native-readonly:", text)
        self.assertNotIn("NOX2:", text)
        self.assertNotIn("secrets.NOX2", text)
        self.assertIn("actions/checkout@11d5960a326750d5838078e36cf38b85af677262", text)
        self.assertIn("actions/setup-python@82c7e631bb3cdc910f68e0081d67478d79c6982d", text)


if __name__ == "__main__":
    unittest.main()
