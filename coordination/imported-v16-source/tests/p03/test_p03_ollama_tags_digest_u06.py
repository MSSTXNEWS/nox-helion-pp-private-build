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


# This actual native-ingress test executes the original P02 byte-framed handler
# and the existing P03 owner license method. It never grants pull rights.
INGRESS_SOURCE=(Path(__file__).resolve().parents[2]/"Packages"/"P02"/"worker-python"/"p02_native_ingress.py")
ingress_spec=importlib.util.spec_from_file_location("p02_u06_license_read", INGRESS_SOURCE)
assert ingress_spec and ingress_spec.loader
native_ingress=importlib.util.module_from_spec(ingress_spec)
ingress_spec.loader.exec_module(native_ingress)

class P03NativeLicenseReadTest(unittest.TestCase):
    def _setup(self, *, enabled=True, owner=3):
        port=p03.P03OneHostPort.__new__(p03.P03OneHostPort)
        port.family_cards=({"id":"qwen3","name":"Qwen3"},)
        scope=SimpleNamespace(tenant="local",principal="owner",chat_id="default",
                              allowed=frozenset({"models.licenses"}))
        bound=SimpleNamespace(owner=owner, evidence_id="P03_SOURCELOCK_RECEIPT",
                              call=port.licenses, available=lambda: True)
        dispatcher=SimpleNamespace(routes={"models.licenses":{"owner":3}},
                                   ports={"models.licenses":bound})
        dispatcher.execute=lambda route,payload,session: dispatcher.ports[route].call(session,payload)
        ingress=native_ingress.NativeIngress(dispatcher,lambda:scope,
                         expected_run_id="u06-native-license-run",
                         allow_modelcenter_reads=enabled)
        return ingress,dispatcher

    def _frame(self,route="models.licenses",payload=None):
        return json.dumps({"protocol":"NOX-P02-NATIVE-v1",
                           "runId":"u06-native-license-run",
                           "requestId":"a"*32,"route":route,
                           "payload":{} if payload is None else payload}).encode("utf-8")

    def test_native_licensediscovery_reaches_original_owner_without_rights(self):
        ingress,_=self._setup()
        answer=json.loads(ingress.handle(self._frame()))
        self.assertEqual(answer["status"],"OK")
        proof=answer["result"]
        self.assertIs(proof["licenseEvidenceVerified"],False)
        self.assertEqual(proof["models"][0]["reviewStatus"],"REVIEW_REQUIRED")
        self.assertIs(proof["models"][0]["downloadEligible"],False)
        self.assertIsNone(proof["models"][0]["license"])

    def test_native_license_read_requires_owner_optin_and_receipt(self):
        for opts in ({"enabled":False},{"owner":2}):
            with self.subTest(opts=opts):
                ingress,_=self._setup(**opts)
                with self.assertRaises(native_ingress.ProtocolHold):
                    ingress.handle(self._frame())

    def test_native_license_read_requires_exact_bound_owner_port(self):
        ingress,dispatcher=self._setup()
        dispatcher.ports["models.licenses"].evidence_id=""
        with self.assertRaises(native_ingress.ProtocolHold):
            ingress.handle(self._frame())

    def test_browser_cannot_assert_license_authorization(self):
        ingress,_=self._setup()
        with self.assertRaises(native_ingress.ProtocolHold):
            ingress.handle(self._frame(payload={"licenseVerified":True}))

    def test_no_model_mutations_admitted_by_readonly_gate(self):
        for route in ("models.pull","models.queue","models.cancel",
                      "models.retry","models.gguf.import"):
            with self.subTest(route=route):
                ingress,_=self._setup()
                with self.assertRaises(native_ingress.ProtocolHold):
                    ingress.handle(self._frame(route=route))

if __name__=="__main__":unittest.main()
