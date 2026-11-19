"""No network: Hub metadata role and remote-code gate fixtures."""
import json
import unittest
from unittest.mock import patch
from nox_runpod.teacher_mesh.v78.internet_teacher_bridge import fetch_hub_metadata

ENDPOINT="https://huggingface.co/api/models/org/model"
class _Response:
    status=200
    def __init__(self,payload):
        self.payload=payload
    def geturl(self):return ENDPOINT
    def read(self,maxlen):return json.dumps(self.payload).encode()
    def __enter__(self):return self
    def __exit__(self,*args):return False

class HubMetadataTests(unittest.TestCase):
    def metadata(self,**fields):
        return {"id":"org/model","sha":"a"*40,"gated":False,
                "license":"apache-2.0","siblings":[{"rfilename":"model.safetensors"},{"rfilename":"config.json"}],
                "config":{"architectures":["SafeModel"]},**fields}
    def call(self,payload):
        class Opener:
            def open(self,req,timeout):
                assert req.full_url==ENDPOINT
                return _Response(payload)
        with patch("urllib.request.build_opener",return_value=Opener()):
            return fetch_hub_metadata("org/model")
    def test_metadata_pinned_only(self):
        result=self.call(self.metadata())
        self.assertEqual(result["state"],"CANDIDATE_REVIEWED_NOT_INSTALLED")
        self.assertTrue(result["metadata_file_list_checked"])
        self.assertFalse(result["downloaded"])
        self.assertFalse(result["full_code_audit_completed"])
    def test_missing_file_inventory_holds(self):
        payload=self.metadata()
        del payload["siblings"]
        self.assertEqual(self.call(payload)["state"],"HOLD_REMOTE_CODE_METADATA_NOT_AVAILABLE")
    def test_custom_python_holds(self):
        payload=self.metadata()
        payload["siblings"].append({"rfilename":"modeling_custom.py"})
        self.assertEqual(self.call(payload)["state"],"HOLD_REMOTE_CODE")
    def test_auto_map_holds(self):
        payload=self.metadata()
        payload["config"]={"auto_map":{"AutoModel":"modeling_x.X"}}
        self.assertEqual(self.call(payload)["state"],"HOLD_REMOTE_CODE")

if __name__=="__main__":unittest.main()
