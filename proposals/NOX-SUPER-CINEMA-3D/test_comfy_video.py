import hashlib
import json
import unittest
from comfy_video_bridge import ComfyVideoPort, NativeVideoPreflight, Denied, Hold

PID = "abcde123-1234-5678-9012-abcdefabcdef"
class FakeTransport:
    def __init__(self):
        self.requests = []
        self.answer = {"prompt_id": PID}
    def request(self, method, route, payload=None):
        self.requests.append((method, route, payload))
        return self.answer

class VideoModelTests(unittest.TestCase):
    def setUp(self):
        self.transport = FakeTransport()
        self.port = ComfyVideoPort(self.transport)
        self.workflow = {"6": {"class_type": "CLIPTextEncode", "inputs": {"text": "base"}}}
        s = json.dumps(self.workflow, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        self.digest = hashlib.sha256(s.encode("utf8")).hexdigest()
        self.permit = NativeVideoPreflight(
            model_id="wan21-t2v-1.3b", workflow_sha256=self.digest,
            model_sha256="a"*64, installed=True, license_verified=True,
            trusted_native=True, user_consent=True,
            current_gpu_vram_free_gb=12, measured_required_vram_gb=10,
            gpu_training_active=False
        )
        self.args = dict(model_id="wan21-t2v-1.3b", operation="t2v",
                         workflow=self.workflow, workflow_digest=self.digest,
                         prompt_node="6", prompt="film photograph quality",
                         client_id="NOX-VIDEO-123", preflight=self.permit,
                         user_rights_confirmed=True)

    def test_demo_catalog_without_license_clearance_or_weights(self):
        previews = self.port.demo_catalog()
        self.assertEqual(len(previews), 12)
        self.assertTrue(all(x["status"] == "PREVIEW_ONLY_NO_INFERENCE" for x in previews))
        self.assertTrue(all(x["networkRequest"] is False for x in previews))
        self.assertTrue(all(x["weightsDownloaded"] is False for x in previews))
        self.assertEqual(len(self.transport.requests), 0)
        # The license-review candidate is visible in the visual catalog, not executable.
        candidate = self.port.demo_model("cogvideox-5b", "t2v")
        self.assertEqual(candidate["mode"], "DEMO_CATALOG_ONLY")
        self.assertTrue(candidate["licenseReviewBeforeExecution"])

    def test_demo_cannot_claim_real_generation_or_invalid_operations(self):
        item = self.port.demo_model("wan21-t2v-1.3b")
        self.assertFalse(item["modelInstalled"])
        self.assertFalse(item["gpuUsed"])
        with self.assertRaises(Denied):
            self.port.demo_model("unknown-model")
        with self.assertRaises(Denied):
            self.port.demo_model("wan21-t2v-1.3b", "voiceclone")
        # The actual generation path still rejects unverified checkpoints.
        with self.assertRaises(Hold):
            self.port.prepare_video(**{**self.args, "preflight": None})

    def test_exact_12_model_catalog_is_hold_until_installed(self):
        models = self.port.visible_models()
        self.assertEqual(len(models), 12)
        self.assertEqual(len({m["id"] for m in models}), 12)
        self.assertTrue(all(m["status"] == "CATALOG_ONLY_HOLD" for m in models))

    def test_existing_comfyui_queue_and_true_status(self):
        ready = self.port.prepare_video(**self.args)
        self.assertEqual(ready["status"], "READY_TO_QUEUE_NOT_RENDERED")
        self.assertEqual(ready["prepared"]["prompt"]["6"]["inputs"]["text"], "film photograph quality")
        self.assertEqual(self.workflow["6"]["inputs"]["text"], "base")
        sent = self.port.queue_video(ready, native_authorized=True)
        self.assertEqual(sent["status"], "QUEUED_NOT_RENDERED")
        self.assertEqual(sent["prompt_id"], PID)
        self.assertEqual(self.transport.requests[0][:2], ("POST", "/prompt"))

    def test_unmeasured_gpu_vram_not_inferred_from_16_or_24_gb_ram(self):
        for free in (0, -1, 5000):
            fake = NativeVideoPreflight(**{**vars(self.permit), "current_gpu_vram_free_gb": free})
            with self.assertRaises(Hold):
                self.port.prepare_video(**{**self.args, "preflight": fake})
        too_small = NativeVideoPreflight(**{**vars(self.permit), "current_gpu_vram_free_gb": 8})
        with self.assertRaisesRegex(Hold, "NOT_ENOUGH_FREE_GPU_VRAM"):
            self.port.prepare_video(**{**self.args, "preflight": too_small})

    def test_training_priority_and_rights(self):
        active = NativeVideoPreflight(**{**vars(self.permit), "gpu_training_active": True})
        with self.assertRaises(Hold):
            self.port.prepare_video(**{**self.args, "preflight": active})
        with self.assertRaises(Denied):
            self.port.prepare_video(**{**self.args, "user_rights_confirmed": False})
        with self.assertRaises(Hold):
            self.port.prepare_video(**{**self.args, "preflight": None})

    def test_unreviewed_model_license_hold(self):
        fake = NativeVideoPreflight(**{**vars(self.permit), "model_id":"cogvideox-5b"})
        with self.assertRaisesRegex(Hold, "CHECKPOINT_LICENSE_REVIEW_REQUIRED"):
            self.port.prepare_video(**{**self.args, "model_id":"cogvideox-5b",
                                       "preflight": fake})

    def test_no_fabricated_model_download_or_video_success(self):
        self.transport.answer = {}
        self.assertEqual(self.port.video_result(PID), {"status":"NOT_COMPLETE", "videos":[]})

    def test_video_result_filters_unsafe_names_and_types(self):
        self.transport.answer = {PID:{"status":{"status_str":"success"},
                                      "outputs":{"25":{"gifs":[
                                       {"filename":"movie_001.mp4","type":"output"},
                                       {"filename":"../../private.mp4","type":"output"},
                                       {"filename":"cache.mov","type":"output"},
                                       {"filename":"in.mp4","type":"input"},
                                       {"filename":"final.webm","type":"output"}]}}}}
        out = self.port.video_result(PID)
        self.assertEqual(out["status"], "RENDERED_IN_COMFY_NOT_IMPORTED")
        self.assertEqual([v["filename"] for v in out["videos"]],["movie_001.mp4","final.webm"])

    def test_finished_comfy_status_without_video_is_hold(self):
        self.transport.answer = {PID: {"status": {"status_str": "success"},
                                       "outputs": {"5": {"gifs": []}}}}
        out = self.port.video_result(PID)
        self.assertEqual(out, {"status":"OUTPUT_MISSING_HOLD", "videos":[]})

    def test_workflow_digest_immutable_and_budget_bounded(self):
        with self.assertRaises(Hold):
            self.port.prepare_video(**{**self.args, "workflow_digest":"b"*64})
        for patch in [{"frames": 1000}, {"width": 8191}, {"height": 235},
                      {"width": 511}, {"frames": True}]:
            with self.assertRaises(Denied):
                self.port.prepare_video(**{**self.args, **patch})

    def test_cannot_call_unsupported_operation(self):
        with self.assertRaises(Denied):
            self.port.prepare_video(**{**self.args, "operation":"voiceclone"})
        with self.assertRaises(Denied):
            self.port.prepare_video(**{**self.args, "model_id":"fake"})

    def test_queue_unverified_payload_denied(self):
        with self.assertRaises(Denied):
            self.port.queue_video({"prompt":self.workflow}, native_authorized=True)
        ready = self.port.prepare_video(**self.args)
        with self.assertRaises(Denied):
            self.port.queue_video(ready, native_authorized=False)

if __name__ == "__main__":
    unittest.main()
