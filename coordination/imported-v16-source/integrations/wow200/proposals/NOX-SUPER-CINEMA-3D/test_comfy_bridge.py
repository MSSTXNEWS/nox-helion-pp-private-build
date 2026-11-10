import importlib.util
import hashlib
import json
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("comfy_bridge", Path(__file__).with_name("comfy_bridge.py"))
cb = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = cb
spec.loader.exec_module(cb)

class Transport:
    def __init__(self):
        self.requests = []
        self.accept = {"prompt_id": "abcde123-1234-5678-9012-abcdefabcdef"}
    def request(self, method, path, data=None):
        self.requests.append((method, path, data))
        return self.accept

class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.workflow = {"6": {"class_type": "CLIPTextEncode", "inputs": {"text": "base"}}}
        canonical = json.dumps(self.workflow, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        self.digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        self.model = cb.ApprovedModel("FLUX2-klein4B", "a"*64, "Apache-2.0", True, True)
        self.transport = Transport()
        self.port = cb.ComfyImagePort(self.transport)
        self.kw = dict(workflow=self.workflow, workflow_digest=self.digest,
                       prompt_node="6", prompt="cinematic photography",
                       model=self.model, native_authorized=True,
                       rights_confirmed=True, client_id="nox-20261028")

    def test_approved_workflow_renders_queue_not_false_success(self):
        prepared = self.port.prepare(**self.kw)
        self.assertEqual(prepared["prompt"]["6"]["inputs"]["text"], "cinematic photography")
        self.assertEqual(self.workflow["6"]["inputs"]["text"], "base")
        result = self.port.submit(prepared, native_authorized=True)
        self.assertEqual(result["status"], "QUEUED_NOT_RENDERED")
        self.assertEqual(self.transport.requests[0][:2], ("POST", "/prompt"))

    def test_no_license_or_installed_weights(self):
        for model in [cb.ApprovedModel("FLUX2", "a"*64, "REVIEW_REQUIRED", True, True),
                      cb.ApprovedModel("FLUX2", "a"*64, "Apache-2.0", False, True),
                      cb.ApprovedModel("FLUX2", "b"*64, "Apache-2.0", True, False)]:
            with self.assertRaises(cb.Hold):
                self.port.prepare(**{**self.kw, "model": model})

    def test_no_native_consent(self):
        with self.assertRaises(cb.Denied):
            self.port.prepare(**{**self.kw, "native_authorized": False})
        with self.assertRaises(cb.Denied):
            self.port.prepare(**{**self.kw, "rights_confirmed": False})
        with self.assertRaises(cb.Denied):
            self.port.submit({"prompt": self.workflow, "client_id": "ab"}, native_authorized=False)

    def test_sha_binds_exact_workflow(self):
        with self.assertRaises(cb.Hold):
            self.port.prepare(**{**self.kw, "workflow_digest": "b"*64})

    def test_invalid_prompt_rejected(self):
        for value in ["", "\x00bad", "x"*8001]:
            with self.assertRaises(cb.Denied):
                self.port.prepare(**{**self.kw, "prompt": value})

    def test_missing_prompt_node(self):
        with self.assertRaises(cb.Hold):
            self.port.prepare(**{**self.kw, "prompt_node": "bad"})

    def test_pending_generation_not_claimed_as_finished(self):
        self.transport.accept = {}
        self.assertEqual(self.port.result("abcde123-1234-5678-9012-abcdefabcdef")["status"], "NOT_COMPLETE")

    def test_success_with_safe_image_names_only(self):
        pid = "abcde123-1234-5678-9012-abcdefabcdef"
        self.transport.accept = {pid: {"status": {"status_str": "success"}, "outputs": {
            "9": {"images": [{"filename": "output_001.png"}, {"filename": "../../secret.png"}]}}}}
        res = self.port.result(pid)
        self.assertEqual(res["status"], "RENDERED_IN_COMFY_NOT_IMPORTED")
        self.assertEqual(res["images"], [{"filename": "output_001.png", "type": "output"}])

    def test_no_remote_or_unsafe_endpoint(self):
        transport = cb.LocalTransport()
        for route in ["https://example.com/prompt", "/queue/clear", "/view?filename=hi.png", "/history/../bad"]:
            with self.assertRaises(cb.Denied):
                transport.request("GET", route)

if __name__ == "__main__":
    unittest.main()
