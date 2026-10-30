"""CS5 local JSON-lines Worker route regression; no Windows/HTTP or model downloads."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from creative_worker import serve_line
from nox_fastpack.engine import Studio


class WorkerRoutes(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.worker = Studio(self.temp.name)

    def rpc(self, payload):
        envelope = {"request_id": "00000000-0000-4000-8000-000000000001", "payload": payload}
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            serve_line(self.worker, json.dumps(envelope, ensure_ascii=False))
        return json.loads(output.getvalue())

    def test_five_blocks_routed_without_second_worker(self):
        overview = self.rpc({"action": "cs5_overview"})
        self.assertTrue(overview["ok"])
        self.assertEqual(len(overview["data"]["blocks"]), 5)
        saved = self.rpc({"action": "cs5_append", "project_id": "creative01",
                          "block": "B02", "kind": "idea", "text": "Original user idea"})
        self.assertTrue(saved["ok"])
        self.assertEqual(saved["data"]["status"], "SAVED_LOCAL_NOT_E11")
        history = self.rpc({"action": "cs5_list", "project_id": "creative01"})
        self.assertEqual(history["data"]["count"], 1)

    def test_original_studio_dispatch_not_intercepted(self):
        original = self.rpc({"action": "route_chat", "text": "Новый проект без команды"})
        self.assertTrue(original["ok"])
        self.assertEqual(original["data"]["handled"], False)

    def test_stop_rejects_new_record_in_same_worker(self):
        self.worker.stop()
        result = self.rpc({"action": "cs5_append", "project_id": "creative01",
                           "block": "B05", "kind": "brand", "text": "Must stay blocked"})
        self.assertFalse(result["ok"])
        self.assertIn("CS5_STOP_ACTIVE", result["error"])


if __name__ == "__main__":
    unittest.main()
