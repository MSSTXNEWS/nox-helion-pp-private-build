"""EXPRESS03 R112: owner failure-family ACK must never be native OK."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
P02=ROOT/"Packages/P02/worker-python/p02_native_ingress.py"
STAGE=ROOT/"coordination/e06/stage_native_stdio.py"
spec=importlib.util.spec_from_file_location("p02_failed_prefix_r112", P02)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def git_blob(content):
    return hashlib.sha1(b"blob "+str(len(content)).encode("ascii")+bytes([0])+content).hexdigest()

class Owner:
    def __init__(self, result):
        self.result=result
    def execute(self, route, payload, session):
        return self.result

class NativeAckR112(unittest.TestCase):
    def invoke(self, result, route="helion.chat"):
        ingress=mod.NativeIngress(Owner(result), lambda: object(), expected_run_id="r112")
        frame={"protocol":"NOX-P02-NATIVE-v1", "requestId":"a"*32,
               "route":route, "payload":{"text":"hello"}, "runId":"r112"}
        return json.loads(ingress.handle(json.dumps(frame).encode()))

    def test_negative_family_never_native_ok(self):
        for status in ("FAILED_BY_OWNER","DENIED_BY_POLICY","REJECTED_BY_OWNER",
                       "OFFLINE_PROVIDER","NEEDS_AUTH_TOKEN"):
            for ok in (None,True):
                owner={"status":status}
                if ok is True:
                    owner["ok"]=True
                with self.subTest(owner=owner), self.assertRaisesRegex(
                        mod.ProtocolHold,"NATIVE_OWNER_RESULT_HOLD"):
                    self.invoke(owner)

    def test_prior_success_and_stop_contract(self):
        for owner in ({"status":"OK"},{"status":"QUEUED"},{"models":[]}):
            self.assertEqual(self.invoke(owner)["result"],owner)
        self.assertEqual(self.invoke({"status":"STOPPED"},"chat.stop")["status"],"OK")
        with self.assertRaises(mod.ProtocolHold):
            self.invoke({"status":"STOPPED"})

    def test_stager_exact_source_pin(self):
        raw=P02.read_bytes()
        token=("('Packages/P02/worker-python/p02_native_ingress.py', "
               "'p02_native_ingress.py', '"+git_blob(raw)+"')")
        self.assertEqual(STAGE.read_text(encoding="utf-8").count(token),1)

if __name__=="__main__":
    unittest.main()
