#!/usr/bin/env python3
"""1A01: bound upstream SSE wire volume before memory/S03 acceptance.

No model, server or S03 writes. Real production line decoder under a small
injected test budget; no 16 MiB fixture allocation or network is needed.
"""
import asyncio
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nox_webapi as W


class ByteStream:
    def __init__(self, chunks):
        self.chunks = chunks

    async def aiter_bytes(self, chunk_size=4096):
        for chunk in self.chunks:
            yield chunk


class LegacyLines:
    async def aiter_lines(self):
        for line in ("data: one", "data: two", "data: three"):
            yield line


async def collect(response):
    result = []
    async for line in W._bounded_upstream_sse_lines(response):
        result.append(line)
    return result


class UpstreamSseWireBudgetTest(unittest.TestCase):
    def test_normal_chunked_unicode_and_crlf_preserved(self):
        with mock.patch.object(W, "MAX_UPSTREAM_SSE_TOTAL_BYTES", 100):
            got = asyncio.run(collect(ByteStream(
                [b"data: \\xf0\\x9f", b"\\x8c\\x8d\\r", b"\\n", b"data: ok\\n"])))
        self.assertEqual(got, ["data: 🌍", "data: ok"])

    def test_repeated_small_sse_metadata_cannot_run_unbounded(self):
        with mock.patch.object(W, "MAX_UPSTREAM_SSE_TOTAL_BYTES", 20):
            with self.assertRaisesRegex(ValueError, "UPSTREAM_SSE_TOTAL_TOO_LONG"):
                asyncio.run(collect(ByteStream([b":comment\\n"] * 4)))

    def test_legacy_line_reader_uses_same_global_cap(self):
        with mock.patch.object(W, "MAX_UPSTREAM_SSE_TOTAL_BYTES", 19):
            with self.assertRaisesRegex(ValueError, "UPSTREAM_SSE_TOTAL_TOO_LONG"):
                asyncio.run(collect(LegacyLines()))

    def test_per_line_limit_is_still_enforced(self):
        with mock.patch.object(W, "MAX_UPSTREAM_SSE_TOTAL_BYTES", 200), \
             mock.patch.object(W, "MAX_UPSTREAM_SSE_LINE_BYTES", 8):
            with self.assertRaisesRegex(ValueError, "UPSTREAM_SSE_LINE_TOO_LONG"):
                asyncio.run(collect(ByteStream([b"data: too-long\\n"])))


if __name__ == "__main__":
    unittest.main()
