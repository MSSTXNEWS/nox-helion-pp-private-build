import contextlib
import io
import unittest

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
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        return self.responses.pop(0)


class ReadOnlyRangeContractTests(unittest.TestCase):
    source = {
        "url": "https://huggingface.co/owner/model/resolve/immutable/shard.gguf",
        "bytes": 123456789,
        "sha256": "a" * 64,
    }

    def test_head_then_exact_single_byte_range_without_writes_or_output(self):
        etag = '"stable-etag"'
        opener = FakeOpener([
            FakeResponse(status=200, headers={"Content-Length": str(self.source["bytes"]),
                                               "ETag": etag, "Content-Encoding": "identity"}),
            FakeResponse(b"\x7f", status=206, headers={"Content-Length": "1",
                                                        "Content-Range": f"bytes 0-0/{self.source['bytes']}",
                                                        "ETag": etag, "Content-Encoding": "identity"}),
        ])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = probe.probe_one_byte(self.source, opener=opener)

        requests = [request for request, _ in opener.requests]
        self.assertEqual([request.get_method() for request in requests], ["HEAD", "GET"])
        self.assertEqual(requests[0].get_header("Accept-encoding"), "identity")
        self.assertEqual(requests[1].get_header("Range"), "bytes=0-0")
        self.assertEqual(requests[1].get_header("If-range"), etag)
        self.assertIsNone(requests[0].get_header("Authorization"))
        self.assertIsNone(requests[1].get_header("Authorization"))
        self.assertEqual(result, {
            "head_status": 200,
            "range_status": 206,
            "content_range": f"bytes 0-0/{self.source['bytes']}",
            "content_length": 1,
            "bytes_read": 1,
            "strong_etag_match": True,
            "source_bytes": self.source["bytes"],
            "source_sha256": self.source["sha256"],
        })
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn("url", result)
        self.assertNotIn("token", result)
        self.assertEqual(opener.responses, [])

    def test_rejects_bad_head_and_weak_etag_before_range(self):
        for headers in (
            {"Content-Length": "1", "ETag": '"stable-etag"'},
            {"Content-Length": str(self.source["bytes"]), "ETag": 'W/"weak"'},
        ):
            with self.subTest(headers=headers):
                opener = FakeOpener([FakeResponse(status=200, headers=headers)])
                with self.assertRaises(probe.ProbeHold):
                    probe.probe_one_byte(self.source, opener=opener)
                self.assertEqual(len(opener.requests), 1)

    def test_rejects_full_response_or_bad_range_without_reading_payload(self):
        etag = '"stable-etag"'
        for status, content_range, body in (
            (200, f"bytes 0-0/{self.source['bytes']}", b"ignored"),
            (206, f"bytes 0-0/{self.source['bytes'] + 1}", b"ignored"),
        ):
            with self.subTest(status=status, content_range=content_range):
                range_response = FakeResponse(body, status=status, headers={
                    "Content-Length": "1",
                    "Content-Range": content_range,
                    "ETag": etag,
                    "Content-Encoding": "identity",
                })
                opener = FakeOpener([
                    FakeResponse(status=200, headers={
                        "Content-Length": str(self.source["bytes"]), "ETag": etag}),
                    range_response,
                ])
                with self.assertRaises(probe.ProbeHold):
                    probe.probe_one_byte(self.source, opener=opener)
                self.assertEqual(range_response.read_sizes, [])


if __name__ == "__main__":
    unittest.main()
