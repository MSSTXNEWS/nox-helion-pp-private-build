"""G2-A R30: check exact byte count on native frame writes (isolated Python)."""
from __future__ import annotations

import importlib.util
import io
import json
import pathlib
import struct
import sys
import types
import unittest
from unittest.mock import patch


class _Hold(Exception):
    pass


class _NativeIngress:
    run_id = "g2a-framing-regression"

    def handle(self, data: bytes) -> bytes:
        self.calls = getattr(self, "calls", 0) + 1
        return b'{"status":"OK"}'


_MISSING = object()


class _ShortWriter:
    def __init__(self, chunk=1, bad=_MISSING):
        self.chunk, self.bad = chunk, bad
        self.data = bytearray()
        self.flushes = 0
        self.calls = 0

    def write(self, data):
        self.calls += 1
        if self.bad is not _MISSING:
            return self.bad
        size = min(self.chunk, len(data))
        self.data.extend(data[:size])
        return size

    def flush(self):
        self.flushes += 1


def _module():
    # Stub only the existing native host dependency: assert that the framing
    # code itself is taken from the actual same-directory source under test.
    dep = types.ModuleType("p02_native_ingress")
    dep.MAX_INPUT, dep.MAX_OUTPUT = 65536, 65536
    dep.NativeIngress, dep.ProtocolHold = _NativeIngress, _Hold
    dep._enforce_json_depth = lambda _raw: None
    path = pathlib.Path(__file__).with_name("p02_framed_worker.py")
    spec = importlib.util.spec_from_file_location("p02_framed_worker_r30_g2a", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"p02_native_ingress": dep}):
        spec.loader.exec_module(module)
    return module


def _request_frame():
    request = {"protocol": "NOX-P02-NATIVE-v1", "requestId": "a" * 32,
               "route": "chat.stop", "runId": _NativeIngress.run_id,
               "payload": {}}
    payload = json.dumps(request, separators=(",", ":")).encode("utf-8")
    return struct.pack(">I", len(payload)) + payload


class FramedWriteRegression(unittest.TestCase):
    def test_short_writes_emit_complete_header_and_payload(self):
        ingress, writer = _NativeIngress(), _ShortWriter(chunk=1)
        self.assertEqual(_module().serve_native_frames(ingress, io.BytesIO(_request_frame()), writer), 1)
        expected = b'{"status":"OK"}'
        self.assertEqual(bytes(writer.data), struct.pack(">I", len(expected)) + expected)
        self.assertEqual(writer.flushes, 1)
        self.assertEqual(ingress.calls, 1)

    def test_full_write_path_unchanged(self):
        ingress, writer = _NativeIngress(), _ShortWriter(chunk=4096)
        self.assertEqual(_module().serve_native_frames(ingress, io.BytesIO(_request_frame()), writer), 1)
        self.assertEqual(writer.flushes, 1)
        self.assertEqual(writer.calls, 2)

    def test_non_progress_and_invalid_counts_fail_closed(self):
        for bad in (0, None, True, -1, 999999):
            with self.subTest(bad=bad):
                ingress, writer = _NativeIngress(), _ShortWriter(bad=bad)
                with self.assertRaises(_Hold):
                    _module().serve_native_frames(ingress, io.BytesIO(_request_frame()), writer)
                self.assertEqual(writer.flushes, 0)

    def test_stop_priority_does_not_spawn_background_dispatch(self):
        ingress, writer = _NativeIngress(), _ShortWriter(chunk=2)
        self.assertEqual(_module().serve_native_frames(ingress, io.BytesIO(_request_frame()), writer), 1)
        self.assertEqual(ingress.calls, 1)
        self.assertGreater(writer.calls, 2)


if __name__ == "__main__":
    unittest.main()
