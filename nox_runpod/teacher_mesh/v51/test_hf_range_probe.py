import contextlib
import hashlib
import io
import unittest
from unittest.mock import patch

from nox_runpod.teacher_mesh.v51 import hf_range_probe as probe


class FakeResponse(io.BytesIO):
    def __init__(self, body=b"", status=200, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = headers or {}
        self.read_sizes = []

    def read(self, size=-1):
        self.read_sizes.append(size)
        return super().read(size)


class FakeOpener:
    def __init__(self, responses=()):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        return self.responses.pop(0)


class ReadOnlyRangeContractTests(unittest.TestCase):
    payload = b"fixture-source-content"
    pin = {
        "revision": "0123456789abcdef0123456789abcdef01234567",
        "path": "fixture.gguf",
        "url": "https://huggingface.co/test/model/resolve/0123456789abcdef0123456789abcdef01234567/fixture.gguf",
        "bytes": len(payload) + 100,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }

    def test_missing_authoritative_pin_fails_closed_before_opener(self):
        opener = FakeOpener()
        with patch.object(probe, "PINNED_SOURCES", ()):
            with self.assertRaisesRegex(probe.ProbeHold, "^PIN_METADATA_UNAVAILABLE$"):
                probe.probe_one_byte(self.pin, opener=opener)
        self.assertEqual(opener.requests, [])

    def test_arbitrary_or_mismatched_metadata_never_opens(self):
        mutations = {
            "arbitrary URL": {"url": "https://huggingface.co/other/repo/file"},
            "wrong size": {"bytes": self.pin["bytes"] + 1},
            "wrong SHA": {"sha256": "0" * 64},
            "wrong revision": {"revision": "f" * 40},
            "wrong path": {"path": "other.gguf"},
        }
        for label, replacement in mutations.items():
            with self.subTest(label=label):
                supplied = {**self.pin, **replacement}
                opener = FakeOpener()
                with patch.object(probe, "PINNED_SOURCES", (self.pin,)):
                    with self.assertRaisesRegex(probe.ProbeHold, "^PIN_METADATA_MISMATCH$"):
                        probe.probe_one_byte(supplied, opener=opener)
                self.assertEqual(opener.requests, [])

    def test_exact_test_fixture_pin_reaches_only_head_and_one_byte_range(self):
        etag = '"stable-etag"'
        opener = FakeOpener([
            FakeResponse(status=200, headers={
                "Content-Length": str(self.pin["bytes"]),
                "ETag": etag,
                "Content-Encoding": "identity",
            }),
            FakeResponse(bytes([127]), status=206, headers={
                "Content-Length": "1",
                "Content-Range": f"bytes 0-0/{self.pin['bytes']}",
                "ETag": etag,
                "Content-Encoding": "identity",
            }),
        ])
        output = io.StringIO()
        with patch.object(probe, "PINNED_SOURCES", (self.pin,)), contextlib.redirect_stdout(output):
            result = probe.probe_one_byte(self.pin, opener=opener)

        requests = [request for request, _ in opener.requests]
        self.assertEqual([request.get_method() for request in requests], ["HEAD", "GET"])
        self.assertEqual(requests[0].get_header("Accept-encoding"), "identity")
        self.assertEqual(requests[1].get_header("Range"), "bytes=0-0")
        self.assertEqual(requests[1].get_header("If-range"), etag)
        self.assertIsNone(requests[0].get_header("Authorization"))
        self.assertIsNone(requests[1].get_header("Authorization"))
        self.assertEqual(result["bytes_read"], 1)
        self.assertEqual(result["source_bytes"], self.pin["bytes"])
        self.assertEqual(result["source_sha256"], self.pin["sha256"])
        self.assertNotIn("url", result)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(opener.responses, [])


if __name__ == "__main__":
    unittest.main()
