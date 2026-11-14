from pathlib import Path
from tempfile import TemporaryDirectory
import json,unittest
from nox_prime_core_matrix_v1 import matrix
class CoreMatrixTests(unittest.TestCase):
    def test_all_eight_have_distinct_true_status(self):
        with TemporaryDirectory() as root:
            d=matrix(root,["qwen3:8b"],2,True)
            self.assertEqual(len(d["capabilities"]),8)
            self.assertEqual(d["capabilities"]["CORE"]["status"],"INFERENCE_AVAILABLE")
            self.assertFalse(d["capabilities"]["CONSCIOUSNESS"]["subjective_consciousness_verified"])
            self.assertFalse(d["capabilities"]["NEXUS"]["native_s03_writable"])
            self.assertEqual(d["capabilities"]["NEXUS"]["historical_episodes"],2)
    def test_no_model_no_fake_ready(self):
        with TemporaryDirectory() as root:
            d=matrix(root,[],0,False)
            self.assertEqual(d["capabilities"]["CORE"]["status"],"HOLD")
            self.assertEqual(d["capabilities"]["VOICE"]["status"],"HOLD")
    def test_hash_receipt_not_tts_inference(self):
        with TemporaryDirectory() as root:
            path=Path(root)/"brain"/"voice"/"receipts"/"qwen3_06_customvoice.json"
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps({"id":"qwen3_06_customvoice","status":"DOWNLOADED_AND_HASHED"}),encoding="utf-8")
            v=matrix(root,["qwen3:8b"])["capabilities"]["VOICE"]
            self.assertEqual(v["status"],"WEIGHTS_ONLY")
            self.assertFalse(v["inference_tested"])
if __name__=='__main__':unittest.main()
