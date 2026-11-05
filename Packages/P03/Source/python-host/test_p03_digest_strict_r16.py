"""P03 R16: real p03_onehost_port.digest source tests, no Ollama download/CI/EXE."""
import io
import json
import unittest
from types import SimpleNamespace
from p03_onehost_port import P03OneHostPort, P03PortHold, P03PortDenied

class LocalTagsOnly:
    def __init__(self, body):
        self.body = body
        self.opened = []
    def _open(self, path):
        self.opened.append(path)
        if path != "/api/tags":
            raise AssertionError("No other endpoint may be used")
        return io.BytesIO(self.body)

class P03StrictOllamaDigestR16Tests(unittest.TestCase):
    tag = "qwen3:4b"
    pin = "sha256:" + "a" * 64
    @staticmethod
    def session(allowed=frozenset({"models.digest"})):
        return SimpleNamespace(tenant="t", principal="p", chat_id="c",
                               allowed=allowed, private_approved=frozenset())
    def read(self, body, allowed=frozenset({"models.digest"})):
        p = object.__new__(P03OneHostPort)
        p.native_approve = None
        p.ollama = LocalTagsOnly(body)
        result = p.digest(self.session(allowed), {"modelTag": self.tag})
        self.assertEqual(p.ollama.opened, ["/api/tags"])
        return result
    def test_r16_01_duplicate_root_models_holds(self):
        payload = ('{"models":[],"models":[{"name":"qwen3:4b","digest":"%s"}]}' % self.pin).encode()
        with self.assertRaises(P03PortHold): self.read(payload)
    def test_r16_02_duplicate_digest_in_row_holds(self):
        payload = ('{"models":[{"name":"qwen3:4b","digest":"broken","digest":"%s"}]}' % self.pin).encode()
        with self.assertRaises(P03PortHold): self.read(payload)
    def test_r16_03_nan_metadata_holds(self):
        payload = ('{"models":[{"name":"qwen3:4b","digest":"%s","extra":NaN}]}' % self.pin).encode()
        with self.assertRaises(P03PortHold): self.read(payload)
    def test_r16_04_exponent_overflow_holds(self):
        payload = ('{"models":[{"name":"qwen3:4b","digest":"%s","extra":1e999}]}' % self.pin).encode()
        with self.assertRaises(P03PortHold): self.read(payload)
    def test_r16_05_valid_digest_keeps_unverified_licensing(self):
        payload = json.dumps({"models":[{"name":self.tag,"digest":self.pin}]}).encode()
        result = self.read(payload)
        self.assertEqual(result["ollamaReportedManifestDigest"], self.pin)
        self.assertFalse(result["independentlyVerified"])
        self.assertFalse(result["licenseVerified"])
    def test_r16_06_malformed_sha_still_holds(self):
        with self.assertRaises(P03PortHold):
            self.read(b'{"models":[{"name":"qwen3:4b","digest":"sha256:bad"}]}')
    def test_r16_07_no_route_scope_no_metadata_read(self):
        with self.assertRaises(P03PortDenied):
            self.read(b'{"models":[]}', allowed=frozenset())

if __name__ == "__main__": unittest.main(verbosity=2)
