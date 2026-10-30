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

    def test_repeated_real_jsonl_process_does_not_crash(self):
        """True subprocess, not a direct serve_line mock; catches thread-set races."""
        import os
        import queue
        import subprocess
        import threading
        import uuid

        root = Path(__file__).resolve().parents[1]
        env = dict(os.environ, PYTHONPATH=str(root))
        process = subprocess.Popen(
            [sys.executable, str(root / "creative_worker.py"), self.temp.name],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", bufsize=1, env=env)
        received = queue.Queue()
        def read_responses():
            for line in process.stdout:
                received.put(line)
        reader = threading.Thread(target=read_responses, daemon=True)
        reader.start()
        payloads = [
            {"action": "cs5_overview"},
            {"action": "cs5_append", "project_id": "creative01", "block": "B02", "kind": "idea", "text": "Original idea"},
            {"action": "cs5_list", "project_id": "creative01"},
            {"action": "cs5_append", "project_id": "creative01", "block": "B05", "kind": "brand", "text": "Draft brand"},
            {"action": "cs5_export", "project_id": "creative01"},
            {"action": "catalog"},
            {"action": "project_files", "project_id": "creative01"},
        ]
        try:
            for payload in payloads:
                request_id = str(uuid.uuid4())
                process.stdin.write(json.dumps({"request_id": request_id, "payload": payload}) + "\n")
                process.stdin.flush()
                try:
                    line = received.get(timeout=8)
                except queue.Empty:
                    self.fail("NOX worker did not answer; exit=" + str(process.poll()))
                self.assertTrue(line, "worker closed its stdout")
                response = json.loads(line)
                self.assertEqual(response.get("request_id"), request_id)
                self.assertTrue(response.get("ok"), response)
        finally:
            if process.stdin and not process.stdin.closed:
                process.stdin.close()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        self.assertEqual(process.returncode, 0)

    def test_overload_error_retains_native_request_id(self):
        """Capacity rejection must not strand the WebView2 pending request."""
        from unittest.mock import patch
        import creative_worker

        class Busy:
            def is_alive(self):
                return True
        request_id = "00000000-0000-4000-8000-000000000017"
        inbound = json.dumps({"request_id": request_id,
                              "payload": {"action": "cs5_overview"}}) + "\n"
        output = io.StringIO()
        with patch.object(creative_worker, "THREADS", {Busy() for _ in range(16)}), \
             patch.object(creative_worker.sys, "stdin", io.StringIO(inbound)), \
             patch.object(creative_worker.sys, "stdout", output):
            status = creative_worker.main([self.temp.name])
        self.assertEqual(status, 0)
        result = json.loads(output.getvalue())
        self.assertFalse(result["ok"])
        self.assertEqual(result["request_id"], request_id)
        self.assertEqual(result["error"], "Worker task limit reached")

    def test_stop_rejects_new_record_in_same_worker(self):
        self.worker.stop()
        result = self.rpc({"action": "cs5_append", "project_id": "creative01",
                           "block": "B05", "kind": "brand", "text": "Must stay blocked"})
        self.assertFalse(result["ok"])
        self.assertIn("CS5_STOP_ACTIVE", result["error"])


if __name__ == "__main__":
    unittest.main()
