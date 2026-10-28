"""V16 SOURCE QA — independent RED regression for existing P02 native pipe.

Pinned source at audit: Packages/P02/worker-python/p02_framed_worker.py
Git blob d65279cd166fdf4bda503f5b02e39d6ab2f5eaee.

Expected fix: the outer byte-frame routing probe must never raise RecursionError
on a deeply nested WebView JSON frame. It must return HOLD, then continue to
serve a subsequent well-formed frame. This test imports the actual owner
module; no copy of its implementation or separate server is permitted.

Run from repository root:
  python -m unittest discover -s qa/source_ready -p 'test_p02_framed_json_depth_r01.py' -v
Expected on current pre-fix source: RED / RecursionError.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
P02 = ROOT / "Packages" / "P02" / "worker-python"
sys.path.insert(0, str(P02))
from p02_native_ingress import NativeIngress, MAX_INPUT
from p02_framed_worker import serve_native_frames

RUN_ID = "NOX-V16-SOURCE-QA-DEPTH"


class ExistingDispatcher:
    def __init__(self):
        self.calls = 0

    def execute(self, route, payload, session):
        self.calls += 1
        return {"owner": "P02", "route": route}


def framed(payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + payload


def read_all_frames(payload: bytes) -> list[dict]:
    stream = io.BytesIO(payload)
    responses = []
    while stream.tell() < len(payload):
        header = stream.read(4)
        if len(header) != 4:
            raise AssertionError("Malformed reply frame header")
        size = struct.unpack(">I", header)[0]
        body = stream.read(size)
        if len(body) != size:
            raise AssertionError("Truncated reply body")
        responses.append(json.loads(body))
    return responses


class NativeDepthBoundaryRegression(unittest.TestCase):
    def test_deep_json_does_not_crash_native_pipe_or_drop_next_request(self):
        # The worker's preliminary json.loads() currently executes BEFORE
        # NativeIngress's MAX_JSON_NESTING=512 policy, and only catches
        # (ValueError, UnicodeError), not RecursionError.
        depth = max(3000, sys.getrecursionlimit() + 500)
        if depth * 2 + 1 > MAX_INPUT:
            self.skipTest("Interpreter recursion limit exceeds bounded native frame")
        invalid_json = b"[" * depth + b"0" + b"]" * depth
        good_json = json.dumps({
            "protocol": "NOX-P02-NATIVE-v1",
            "requestId": "a" * 32,
            "route": "chat.model",
            "payload": {},
            "runId": RUN_ID,
        }, separators=(",", ":")).encode("utf-8")
        dispatcher = ExistingDispatcher()
        ingress = NativeIngress(dispatcher, lambda: object(), expected_run_id=RUN_ID)
        output = io.BytesIO()
        request_stream = io.BytesIO(framed(invalid_json) + framed(good_json))
        count = serve_native_frames(ingress, request_stream, output, drain_timeout=3.0)
        answers = read_all_frames(output.getvalue())
        self.assertEqual(count, 2)
        self.assertEqual(len(answers), 2)
        self.assertEqual(answers[0]["status"], "HOLD")
        self.assertEqual(answers[1]["status"], "OK")
        self.assertEqual(answers[1]["result"]["route"], "chat.model")
        self.assertEqual(dispatcher.calls, 1)


if __name__ == "__main__":
    unittest.main()
