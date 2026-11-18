import hashlib
import importlib.util
import os
import struct
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('witness', Path(__file__).with_name('owner_model_identity_witness.py'))
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)


def gguf(p):
    keys = {'general.name': b'NOX TEST', 'tokenizer.ggml.model': b'llama',
            'tokenizer.chat_template': b'{{ messages }}'}
    b = b'GGUF' + struct.pack('<IQQ', 3, 2, len(keys))
    for key, value in keys.items():
        k = key.encode()
        b += struct.pack('<Q', len(k)) + k + struct.pack('<IQ', 8, len(value)) + value
    p.write_bytes(b)


class WitnessTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        self.root = Path(self.d.name)
        self.file = self.root / 'model.gguf'
        gguf(self.file)
        self.pid = 1234
        self.proc = self.root / 'proc'
        p = self.proc / str(self.pid)
        p.mkdir(parents=True)
        self.p = p
        self.ticks = 42
        self._stat(self.ticks)
        (p / 'cmdline').write_bytes(b'llama-server\0-m\0' + os.fsencode(self.file) + b'\0--api-key\0SECRET\0')
        st = self.file.stat()
        self.maps_line = f'00400000-00500000 r--p 00000000 {os.major(st.st_dev):02x}:{os.minor(st.st_dev):02x} {st.st_ino} {self.file}\n'
        (p / 'maps').write_text(self.maps_line)

    def _stat(self, ticks):
        fields = ['S'] + ['0'] * 50
        fields[19] = str(ticks)
        (self.p / 'stat').write_text(f'{self.pid} (model worker) ' + ' '.join(fields))

    def test_exact_live_inode_and_tokenizer_digest(self):
        out = w.witness(self.pid, self.ticks, proc_root=self.proc)
        self.assertEqual(out['state'], 'MAPPED_GGUF_METADATA_VERIFIED')
        self.assertEqual(out['gguf']['metadata']['tokenizer.chat_template']['sha256'],
                         hashlib.sha256(b'{{ messages }}').hexdigest())
        self.assertTrue(out['file_inode_mapped_by_pid'])
        self.assertIsNone(out['loaded_model_sha256'])
        self.assertNotIn('SECRET', str(out))

    def test_stale_pid_rejected(self):
        self.assertEqual(w.witness(self.pid, self.ticks + 1, proc_root=self.proc)['reason'],
                         'PID_START_TICKS_MISMATCH')

    def test_unmapped_file_does_not_prove_serving(self):
        (self.p / 'maps').write_text('00400000-00500000 r-xp 00000000 00:00 0\n')
        out = w.witness(self.pid, self.ticks, proc_root=self.proc)
        self.assertEqual(out['state'], 'MODEL_FILE_NOT_MAPPED_UNKNOWN_LOAD')

    def test_bad_gguf_is_unknown_not_pass(self):
        self.file.write_bytes(b'not a gguf')
        out = w.witness(self.pid, self.ticks, proc_root=self.proc)
        self.assertEqual(out['state'], 'UNKNOWN')
        self.assertEqual(out['reason'], 'NOT_GGUF')

    def test_large_vocab_before_template(self):
        k = b'tokenizer.ggml.tokens'
        b = b'GGUF' + struct.pack('<IQQ', 3, 0, 2)
        b += struct.pack('<Q', len(k)) + k + struct.pack('<IIQ', 9, 8, 5000)
        b += (struct.pack('<Q', 1) + b'x') * 5000
        k = b'tokenizer.chat_template'
        b += struct.pack('<Q', len(k)) + k + struct.pack('<IQ', 8, 4) + b'chat'
        self.file.write_bytes(b)
        out = w.witness(self.pid, self.ticks, proc_root=self.proc)
        self.assertEqual(out['state'], 'MAPPED_GGUF_METADATA_VERIFIED')
        self.assertEqual(out['gguf']['metadata']['tokenizer.chat_template']['sha256'], hashlib.sha256(b'chat').hexdigest())

    def test_budget_prevents_large_token_array(self):
        b = b'GGUF' + struct.pack('<IQQ', 3, 0, 1)
        k = b'tokenizer.ggml.tokens'
        b += struct.pack('<Q', len(k)) + k + struct.pack('<IIQ', 9, 8, 9999999)
        self.file.write_bytes(b)
        out = w.witness(self.pid, self.ticks, proc_root=self.proc)
        self.assertEqual(out['reason'], 'GGUF_ARRAY_COUNT_BUDGET')


if __name__ == '__main__':
    unittest.main()
