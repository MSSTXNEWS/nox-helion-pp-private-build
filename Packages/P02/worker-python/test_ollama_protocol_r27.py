"""Ollama framing/protocol failures on exact stdlib client, offline adapters."""
import io
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from p02_runtime import OllamaClient, P02Error


class Reply(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.read_limits = []
    def readline(self, limit=-1):
        self.read_limits.append(limit)
        return super().readline(limit)
    def __iter__(self):
        while True:
            line = self.readline()
            if not line: return
            yield line


class Client(OllamaClient):
    def __init__(self, data):
        super().__init__()
        self.response = Reply(data)
    def _open(self, *_): return self.response


class OllamaProtocolTests(unittest.TestCase):
    def test_ndjson_line_allocation_is_bounded_before_read(self):
        client = Client(b' ' * (1024 * 1024 + 2) + b'\n')
        with self.assertRaises(P02Error):
            list(client.stream('local', [{'role': 'user', 'content': 'go'}]))
        self.assertEqual(client.response.read_limits, [1024 * 1024 + 1])

    def test_ambiguous_or_nonfinite_frames_never_publish(self):
        events = (
            b'{"message":{"content":"partial"},"done":false,"done":true}\n',
            b'{"message":{"content":"partial","content":"replacement"},"done":true}\n',
            b'{"message":{"content":"ok"},"done":true,"eval_duration":NaN}\n',
            b'{"message":{"content":"ok"},"done":true,"eval_duration":1e999}\n',
            b'{"message":{"content":"\\ud800"},"done":true}\n',
            '{"done":true}'.encode('utf-16'),
        )
        for event in events:
            with self.subTest(event=event[:100]):
                client = Client(event)
                with self.assertRaises(P02Error):
                    next(client.stream('local', [{'role': 'user', 'content': 'go'}]))

    def test_duplicate_model_registry_is_denied(self):
        client = Client(b'{"models":[],"models":[{"name":"untrusted"}]}')
        with self.assertRaises(P02Error): client.models()

    def test_http_200_midstream_error_remains_failure(self):
        client = Client(b'{"message":{"content":"partial"},"done":false}\n'
                        b'{"error":"provider failed"}\n')
        chunks = client.stream('local', [{'role': 'user', 'content': 'go'}])
        self.addCleanup(chunks.close)
        self.assertEqual(next(chunks)['delta'], 'partial')
        with self.assertRaisesRegex(P02Error, 'stream error'): next(chunks)

    def test_normal_finite_frames_remain_supported(self):
        client = Client(b'{"message":{"content":"Hola"},"done":false}\n'
                        b'{"message":{"content":""},"done":true,"total_duration":1.25}\n')
        self.assertEqual([x['delta'] for x in client.stream(
            'local', [{'role': 'user', 'content': 'go'}])], ['Hola', ''])


if __name__ == '__main__': unittest.main()
