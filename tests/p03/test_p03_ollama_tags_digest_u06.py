"""Actual official Ollama /api/tags bare digest: metadata only, not rights or weights."""
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

SOURCE=(Path(__file__).resolve().parents[2]/"Packages"/"P03"/"Source"/"python-host"/"p03_onehost_port.py")
spec=importlib.util.spec_from_file_location("p03_u06_ollama_digest",SOURCE)
assert spec and spec.loader
p03=importlib.util.module_from_spec(spec)
spec.loader.exec_module(p03)
TAG="qwen3:0.6b"
HEX="0a8c266910232fd3291e71e5ba1e058cc5af9d411192cf88b6d30e92b6e73163"

class OllamaTagDigestTest(unittest.TestCase):
    def get(self,digest,models=None):
        payload={"models":models if models is not None else [{"name":TAG,"digest":digest}]}
        class P02:
            def _open(self,path):
                if path!="/api/tags":raise AssertionError("ONLY_EXISTING_P02")
                return io.BytesIO(json.dumps(payload).encode("utf-8"))
        port=p03.P03OneHostPort.__new__(p03.P03OneHostPort)
        port.ollama=P02()
        scope=SimpleNamespace(tenant="a",principal="owner",chat_id="c",
                              allowed=frozenset({"models.digest"}))
        return port.digest(scope,{"modelTag":TAG})

    def test_actual_bare_64_hex_without_verification_promotion(self):
        result=self.get(HEX)
        self.assertEqual(result["ollamaReportedManifestDigest"],"sha256:"+HEX)
        self.assertIs(result["independentlyVerified"],False)
        self.assertIs(result["licenseVerified"],False)
        self.assertEqual(result["source"],"existing P02 transport /api/tags")

    def test_legacy_prefixed_and_uppercase_digest(self):
        self.assertEqual(self.get("sha256:"+HEX)["ollamaReportedManifestDigest"],"sha256:"+HEX)
        self.assertEqual(self.get(HEX.upper())["ollamaReportedManifestDigest"],"sha256:"+HEX)

    def test_invalid_digests_fail_closed(self):
        for bad in (True,1,"","sha1:"+HEX,"SHA256:"+HEX,HEX[:-1],HEX+"0",
                    "g"*64," "+HEX,"sha256:"+HEX+" ","sha256:sha256:"+HEX):
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(p03.P03PortHold):self.get(bad)

    def test_missing_digest_remains_unknown(self):
        result=self.get(None)
        self.assertIsNone(result["ollamaReportedManifestDigest"])
        self.assertIs(result["independentlyVerified"],False)
        self.assertIs(result["licenseVerified"],False)

    def test_duplicate_or_unrelated_model_fails(self):
        for rows in ([{"name":TAG,"digest":HEX}]*2,
                     [{"name":"different:7b","digest":HEX}]):
            with self.assertRaises(p03.P03PortHold):self.get(HEX,models=rows)

if __name__=="__main__":unittest.main()
