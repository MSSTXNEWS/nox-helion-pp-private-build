"""Offline regression for 2A05: ephemeral probes may never be silently persisted."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
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


def run_sample(write=None):
    text = "Ответ NOX 👍"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    receipts = {"status": "SKIPPED", "s03_write_returned": False, "s03_readback_verified": False}
    if write is not None:
        receipts = write

    def opener(request, timeout):
        assert timeout == 400
        rid = json.loads(request.data)["request_id"]
        common = {"request_id": rid, "stream_id": "a" * 32}
        a = {**common, "event_seq": 1, "message": {"content": text}, "done": False}
        b = {**common, "event_seq": 2, "message": {"content": ""}, "done": True,
             "done_reason": "stop", "frames": 1, "digest": digest, "model": "NOX",
             "completion_receipt": {"status": "GENERATED", "upstream_done": True},
             "memory_history": {"status": "SKIPPED", "reason": "ephemeral"},
             "memory_write_receipt": receipts}
        return FakeResponse([(json.dumps(row, ensure_ascii=False) + "\n").encode()
                             for row in (a, b)])

    clock = iter((10.0, 11.0, 12.0))
    return bench._sample(0, clock=lambda: next(clock), opener=opener)


class EphemeralBenchmarkGuardTest(unittest.TestCase):
    def test_valid_receipt_measures_without_s03_write(self):
        result = run_sample()
        self.assertEqual(result["s03_write"], "SKIPPED_EPHEMERAL")
        self.assertEqual(result["chunks"], 1)
        self.assertEqual(result["ttft_s"], 1.0)

    def test_confirmed_write_risk_fails_closed(self):
        with self.assertRaisesRegex(bench.UnsafeEphemeralWriteReceipt,
                                    "BENCH_EPHEMERAL_WRITE_RISK"):
            run_sample({"status": "WRITE_RETURNED_UNVERIFIED",
                        "s03_write_returned": True, "s03_readback_verified": False})

    def test_unknown_receipt_is_not_success(self):
        with self.assertRaisesRegex(ValueError, "TERMINAL_RECEIPT_NOT_EPHEMERAL_GENERATED"):
            run_sample({"status": "SKIPPED", "s03_readback_verified": False})

    def test_batch_stops_on_first_possible_write(self):
        output = io.StringIO()
        with mock.patch.object(bench, "_sample",
                               side_effect=bench.UnsafeEphemeralWriteReceipt("BENCH_EPHEMERAL_WRITE_RISK")) as sampler:
            with contextlib.redirect_stdout(output):
                code = bench.main(["--model-sha", "a" * 64,
                                   "--route-sha", "b" * 40, "--s03-revision", "S03-1",
                                   "--samples", "20"])
        self.assertEqual(code, 2)
        self.assertEqual(sampler.call_count, 1)
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], "HOLD_EPHEMERAL_WRITE_RISK")
        self.assertEqual(result["completed"], 0)
        self.assertFalse(result["native_acceptance"])


if __name__ == "__main__":
    unittest.main()
