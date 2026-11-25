"""Offline regression for 2A05: ephemeral probes may never be silently persisted."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import unittest
from urllib.error import HTTPError, URLError
from unittest import mock

spec = importlib.util.spec_from_file_location("bench_2a05", Path(__file__).with_name("bench.py"))
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


class FakeResponse:
    status = 200

    def __init__(self, lines):
        self.lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        return iter(self.lines)


class BoundedReadResponse:
    """Simulate the public urllib HTTPResponse.readline(size) interface."""
    status = 200

    def __init__(self, raw):
        self.source = io.BytesIO(raw)
        self.read_limits = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def readline(self, size=-1):
        self.read_limits.append(size)
        return self.source.readline(size)

    def __iter__(self):
        raise AssertionError("unbounded wire iterator must not be consumed")


def run_sample(write=None, token=None, model="NOX"):
    text = "Ответ NOX 👍"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    receipts = {"status": "SKIPPED", "s03_write_returned": False, "s03_readback_verified": False}
    if write is not None:
        receipts = write

    def opener(request, timeout):
        assert timeout == 400
        if token is not None:
            assert request.get_header('X-nox-token') == token
        rid = json.loads(request.data)["request_id"]
        common = {"request_id": rid, "stream_id": "a" * 32}
        a = {**common, "event_seq": 1, "message": {"content": text}, "done": False}
        b = {**common, "event_seq": 2, "message": {"content": ""}, "done": True,
             "done_reason": "stop", "frames": 1, "digest": digest, "model": model,
             "completion_receipt": {"status": "GENERATED", "upstream_done": True},
             "memory_history": {"status": "SKIPPED", "reason": "ephemeral"},
             "memory_write_receipt": receipts}
        return FakeResponse([(json.dumps(row, ensure_ascii=False) + "\n").encode()
                             for row in (a, b)])

    clock = iter((10.0, 11.0, 12.0))
    return bench._sample(0, clock=lambda: next(clock), opener=opener, auth_token=token)


class EphemeralBenchmarkGuardTest(unittest.TestCase):
    def test_real_http_reader_enforces_wire_cap_before_parsing(self):
        normal = BoundedReadResponse(b'{"event_seq":1}\n')
        self.assertEqual(list(bench._bounded_ndjson_lines(normal)),
                         [b'{"event_seq":1}\n'])
        self.assertEqual(normal.read_limits,
                         [bench.MAX_NDJSON_FRAME_BYTES + 1] * 2)

        # One malformed upstream line is larger than the declared 1 MiB
        # budget. Never allocate/read an unbounded HTTPResponse.__iter__ line.
        giant = BoundedReadResponse(b'x' * (bench.MAX_NDJSON_FRAME_BYTES + 100))
        with self.assertRaisesRegex(ValueError, "OVERSIZED_FRAME"):
            list(bench._bounded_ndjson_lines(giant))
        self.assertEqual(giant.read_limits,
                         [bench.MAX_NDJSON_FRAME_BYTES + 1])

    def test_cumulative_wire_bytes_and_frame_count_are_bounded(self):
        # Thousands of individually legal frames must not accumulate in RAM.
        small = json.dumps({"event_seq": 1}).encode("ascii") + bytes([10])
        with mock.patch.object(bench, "MAX_NDJSON_STREAM_BYTES", len(small) * 2):
            response = BoundedReadResponse(small * 3)
            with self.assertRaisesRegex(ValueError, "OVERSIZED_STREAM"):
                list(bench._bounded_ndjson_lines(response))
            self.assertEqual(len(response.read_limits), 3)

        with mock.patch.object(bench, "MAX_NDJSON_STREAM_FRAMES", 2):
            response = BoundedReadResponse(small * 3)
            with self.assertRaisesRegex(ValueError, "OVERSIZED_STREAM"):
                list(bench._bounded_ndjson_lines(response))
            self.assertEqual(len(response.read_limits), 3)

    def test_valid_receipt_measures_without_s03_write(self):
        result = run_sample()
        self.assertEqual(result["s03_write"], "SKIPPED_EPHEMERAL")
        self.assertEqual(result["chunks"], 1)
        self.assertEqual(result["ttft_s"], 1.0)

    def test_private_owner_web_token_header_is_not_logged_or_returned(self):
        token = "private-bench-credential-no-log"
        result = run_sample(token=token)
        self.assertEqual(result["s03_write"], "SKIPPED_EPHEMERAL")
        self.assertNotIn(token, json.dumps(result))

    def test_local_owner_token_file_missing_valid_and_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            token_file = Path(folder) / "web_token"
            with mock.patch.object(bench, "OWNER_WEB_TOKEN_FILE", str(token_file)):
                self.assertIsNone(bench._owner_web_token())
                token_file.write_text("sealed-owner-token\n", encoding="ascii")
                self.assertEqual(bench._owner_web_token(), "sealed-owner-token")
                token_file.unlink()
                target = Path(folder) / "other_file"
                target.write_text("never-follow-this-token", encoding="ascii")
                os.symlink(target, token_file)
                with self.assertRaisesRegex(ValueError, "HOLD_WEB_TOKEN_UNVERIFIED"):
                    bench._owner_web_token()

    def test_owner_token_hold_prevents_all_benchmark_posts(self):
        output = io.StringIO()
        with mock.patch.object(bench, "_owner_web_token",
                               side_effect=ValueError("HOLD_WEB_TOKEN_UNVERIFIED")), \
             mock.patch.object(bench, "_sample") as sampler:
            with contextlib.redirect_stdout(output):
                code = bench.main(["--model-sha", "a" * 64,
                                   "--route-sha", "b" * 40,
                                   "--s03-revision", "S03-1", "--samples", "20"])
        self.assertEqual(code, 2)
        sampler.assert_not_called()
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "HOLD_WEB_TOKEN_UNVERIFIED")
        self.assertEqual(report["completed"], 0)
        self.assertFalse(report["native_acceptance"])

    def test_local_authenticated_probe_does_not_follow_redirect(self):
        seen = []
        class RedirectHandler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                seen.append((self.command, self.path))
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(302)
                self.send_header("Location", "/unexpected")
                self.send_header("Content-Length", "0")
                self.end_headers()
            def do_GET(self):
                seen.append((self.command, self.path))
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()

        with HTTPServer(("127.0.0.1", 0), RedirectHandler) as server:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                url = f"http://127.0.0.1:{server.server_port}/api/chat"
                with mock.patch.object(bench, "URL", url):
                    with self.assertRaises(HTTPError) as error:
                        bench._sample(0, auth_token="fixture-not-a-real-token")
                    self.assertEqual(error.exception.code, 302)
                    error.exception.close()
                self.assertEqual(seen, [("POST", "/api/chat")])
            finally:
                server.shutdown()
                worker.join(timeout=2)

    def test_confirmed_write_risk_fails_closed(self):
        with self.assertRaisesRegex(bench.UnsafeEphemeralWriteReceipt,
                                    "BENCH_EPHEMERAL_WRITE_RISK"):
            run_sample({"status": "WRITE_RETURNED_UNVERIFIED",
                        "s03_write_returned": True, "s03_readback_verified": False})

    def test_unknown_receipt_is_not_success(self):
        with self.assertRaisesRegex(bench.UnsafeEphemeralWriteReceipt, "BENCH_EPHEMERAL_WRITE_RISK"):
            run_sample({"status": "SKIPPED", "s03_readback_verified": False})

    def test_malformed_terminal_receipt_and_missing_model_fail_closed(self):
        with self.assertRaisesRegex(bench.UnsafeEphemeralWriteReceipt, "BENCH_EPHEMERAL_WRITE_RISK"):
            run_sample(write=["SKIPPED"])
        for model in (None, [], "", " "):
            with self.subTest(model=model):
                with self.assertRaisesRegex(ValueError, "MODEL_ID_UNVERIFIED"):
                    run_sample(model=model)

    def test_batch_stops_on_ambiguous_post_even_without_a_receipt(self):
        # A transport error or an incomplete NDJSON frame may arrive AFTER
        # S03 was written. Neither permits issuing another benchmark POST.
        for failure in (URLError("connection reset"), ValueError("TRUNCATED_FRAME")):
            with self.subTest(failure=type(failure).__name__):
                output = io.StringIO()
                with mock.patch.object(bench, "_owner_web_token", return_value=None), \
                     mock.patch.object(bench, "_sample", side_effect=failure) as sampler:
                    with contextlib.redirect_stdout(output):
                        code = bench.main(["--model-sha", "a" * 64,
                                           "--route-sha", "b" * 40,
                                           "--s03-revision", "S03-1", "--samples", "20"])
                self.assertEqual(code, 2)
                self.assertEqual(sampler.call_count, 1)
                result = json.loads(output.getvalue())
                self.assertEqual(result["status"], "HOLD_PROBE_OUTCOME_UNKNOWN")
                self.assertEqual(result["completed"], 0)
                self.assertEqual(result["errors"][0]["sample"], 1)
                self.assertIsNone(result["s03_writes"])
                self.assertIsNone(result["latency_s"])
                self.assertFalse(result["native_acceptance"])

    def test_batch_stops_on_first_possible_write(self):
        output = io.StringIO()
        with mock.patch.object(bench, "_owner_web_token", return_value=None), \
             mock.patch.object(bench, "_sample",
                               side_effect=bench.UnsafeEphemeralWriteReceipt("BENCH_EPHEMERAL_WRITE_RISK")) as sampler:
            with contextlib.redirect_stdout(output):
                code = bench.main(["--model-sha", "a" * 64,
                                   "--route-sha", "b" * 40, "--s03-revision", "S03-1",
                                   "--samples", "20"])
        self.assertEqual(code, 2)
        self.assertEqual(sampler.call_count, 1)
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], "HOLD_EPHEMERAL_WRITE_RISK")
        self.assertIsNone(result["s03_writes"])
        self.assertIsNone(result["latency_s"])
        self.assertEqual(result["completed"], 0)
        self.assertFalse(result["native_acceptance"])


if __name__ == "__main__":
    unittest.main()
