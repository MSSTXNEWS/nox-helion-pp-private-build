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


class FakeOpener:
    def __init__(self, responses=()):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        return self.responses.pop(0)


class ReadOnlyRangeContractTests(unittest.TestCase):
    def test_authoritative_immutable_metadata_matches_hf_tree(self):
        expected = {
            "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00001-of-00006.gguf":
                (5780704, "f356f198561f56df36f7ab92d7238a926646d76de992c34f15bcb939a5f529b9"),
            "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00002-of-00006.gguf":
                (39535781184, "25af3785ccf925f54137e1ead4c481a8952315dc0b1af6519a99407f67bce8f3"),
            "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00003-of-00006.gguf":
                (39736712000, "8168d0998fc494def2e1952d83c131425a108660aae9d29190f5a8670ab62b48"),
            "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00004-of-00006.gguf":
                (39036908384, "9eb9b4de1968f150dfc207eb31c27be9cd9b5666a9a6246bde8a22b184b4bee0"),
            "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00005-of-00006.gguf":
                (19923784832, "7e35f6b4e6fc46f6c4b152b593d84d683c5ece695ae6ad734f556198c041bec1"),
            "DeepSeek-V4.1-Flash-Engram-IQ4_NL.gguf":
                (110595290816, "3dac4c54893ad7aa89103c0028500eadc78e74112cef3a2930a97e67dc9fb4f3"),
        }
        actual = {row["path"]: (row["bytes"], row["sha256"])
                  for row in probe.PINNED_SOURCES}
        self.assertEqual(actual, expected)
        self.assertEqual(len(probe.PINNED_SOURCES), len(expected))
        shard5 = "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00005-of-00006.gguf"
        engram = "DeepSeek-V4.1-Flash-Engram-IQ4_NL.gguf"
        self.assertEqual(sum(row["path"] == shard5 for row in probe.PINNED_SOURCES), 1)
        self.assertEqual(sum(row["path"] == engram for row in probe.PINNED_SOURCES), 1)
        self.assertTrue(all(
            sum(row["path"] == f"DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-0000{i}-of-00006.gguf"
                for row in probe.PINNED_SOURCES) == 1
            for i in range(1, 6)))
        for row in probe.PINNED_SOURCES:
            self.assertEqual(row["revision"], "65d53bc8be65123e255ff02f3ded958b6dbf54fd")
            self.assertEqual(
                row["url"],
                f"https://huggingface.co/ISTA-DASLab/DeepSeek-V4.1-Flash-1017-GSQ-RCO-GGUF/resolve/{row['revision']}/{row['path']}")
            self.assertEqual(probe._resolve_pin(dict(row)), row)

    def test_arbitrary_or_mismatched_metadata_never_opens(self):
        pin = probe.PINNED_SOURCES[0]
        mutations = {
            "arbitrary URL": {"url": "https://huggingface.co/other/repo/file"},
            "wrong size": {"bytes": pin["bytes"] + 1},
            "wrong SHA": {"sha256": "0" * 64},
            "wrong revision": {"revision": "f" * 40},
            "wrong path": {"path": "other.gguf"},
        }
        for label, replacement in mutations.items():
            with self.subTest(label=label):
                supplied = {**pin, **replacement}
                opener = FakeOpener()
                with self.assertRaisesRegex(probe.ProbeHold, "^PIN_METADATA_MISMATCH$"):
                    probe.probe_one_byte(supplied, opener=opener)
                self.assertEqual(opener.requests, [])

    def test_exact_production_pin_reaches_only_head_and_one_byte_range(self):
        pin = probe.PINNED_SOURCES[0]
        etag = '"stable-etag"'
        opener = FakeOpener([
            FakeResponse(status=200, headers={
                "Content-Length": str(pin["bytes"]),
                "ETag": etag,
                "Content-Encoding": "identity",
            }),
            FakeResponse(bytes([127]), status=206, headers={
                "Content-Length": "1",
                "Content-Range": f"bytes 0-0/{pin['bytes']}",
                "ETag": etag,
                "Content-Encoding": "identity",
            }),
        ])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = probe.probe_one_byte(pin, opener=opener)

        requests = [request for request, _ in opener.requests]
        self.assertEqual([request.get_method() for request in requests], ["HEAD", "GET"])
        self.assertEqual(requests[0].full_url, pin["url"])
        self.assertEqual(requests[0].get_header("Accept-encoding"), "identity")
        self.assertEqual(requests[1].get_header("Range"), "bytes=0-0")
        self.assertEqual(requests[1].get_header("If-range"), etag)
        self.assertIsNone(requests[0].get_header("Authorization"))
        self.assertIsNone(requests[1].get_header("Authorization"))
        self.assertEqual(result["bytes_read"], 1)
        self.assertEqual(result["source_bytes"], pin["bytes"])
        self.assertEqual(result["source_sha256"], pin["sha256"])
        self.assertNotIn("url", result)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(opener.responses, [])


if __name__ == "__main__":
    unittest.main()
