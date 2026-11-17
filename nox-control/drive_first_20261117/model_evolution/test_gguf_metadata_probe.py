from pathlib import Path
import struct
import tempfile
import unittest
from gguf_metadata_probe import inspect_gguf, InvalidGGUF


def string(value):
    data = value.encode()
    return struct.pack('<Q', len(data)) + data


def entry(key, kind, value):
    return string(key) + struct.pack('<I', kind) + value


class ProbeTests(unittest.TestCase):
    def test_valid_metadata_skips_vocab_and_never_reads_tensor_region(self):
        metadata = b''.join([
            entry('general.architecture', 8, string('llama')),
            entry('general.name', 8, string('Fixture, not native model')),
            entry('llama.context_length', 4, struct.pack('<I', 32768)),
            entry('llama.attention.head_count', 4, struct.pack('<I', 32)),
            entry('llama.attention.head_count_kv', 4, struct.pack('<I', 8)),
            entry('llama.rope.scaling.type', 8, string('yarn')),
            entry('llama.rope.freq_base', 6, struct.pack('<f', 10000)),
            entry('general.quantization_version', 4, struct.pack('<I', 2)),
            entry('tokenizer.ggml.tokens', 9, struct.pack('<IQ', 8, 2) + string('x' * 4096) + string('y' * 4096)),
        ])
        header = struct.pack('<4sIQQ', b'GGUF', 3, 1, 9) + metadata
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'fixture.gguf'
            path.write_bytes(header + b'TENSOR_DATA_MUST_NOT_BE_READ' * 100)
            result = inspect_gguf(path)
        self.assertEqual(result['model_context_declared'], 32768)
        self.assertEqual(result['metadata']['llama.attention.head_count_kv'], 8)
        self.assertEqual(result['metadata_end_offset'], len(header))
        self.assertGreaterEqual(result['bytes_seek_skipped'], 8192)
        self.assertLess(result['bytes_read'], 1024)
        self.assertFalse(result['tensor_data_read'])
        self.assertNotIn('tokenizer.ggml.tokens', result['metadata'])
        self.assertIsNone(result['runtime_per_sequence_context'])

    def test_malformed_truncated_and_budget_exceeding_headers_hold(self):
        candidates = [b'GGUF', struct.pack('<4sIQQ', b'GGUF', 3, 0, 1) + struct.pack('<Q', 5000),
                      struct.pack('<4sIQQ', b'GGUF', 3, 0, 1) + entry('bad.array', 9, struct.pack('<IQ', 4, 1_000_001)),
                      struct.pack('<4sIQQ', b'GGUF', 3, 0, 1) + entry('bad.kind', 999, b'')]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'broken.gguf'
            for data in candidates:
                with self.subTest(data=data[:24]):
                    path.write_bytes(data)
                    with self.assertRaises(InvalidGGUF):
                        inspect_gguf(path)


if __name__ == '__main__':
    unittest.main(verbosity=2)
