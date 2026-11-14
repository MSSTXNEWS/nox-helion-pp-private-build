"""Source regression: original T06 Windows overlay must reuse approved P02 JSON guard.
This is structural source verification, not a native Windows or E07 PASS.
"""
from pathlib import Path
import hashlib
import json
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / 'coordination/e06/t06_windows_overlay/NativePythonPipe.cs'
DONOR = ROOT / 'Packages/P02/worker-chat/NativePythonPipe.cs'
COMPILER = ROOT / 'coordination/e06/t06_compile_original_wpf_p02.py'


def git_blob(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def guard(src):
    start = src.index('    private static void RequireUnambiguousJson(JsonElement node)')
    brace = src.index('{', start)
    depth = 0
    for i in range(brace, len(src)):
        if src[i] == '{':
            depth += 1
        elif src[i] == '}':
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
    raise AssertionError('Missing C# guard closure')


class T06OverlayJsonBoundary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.overlay = OVERLAY.read_text(encoding='utf-8')
        cls.donor = DONOR.read_text(encoding='utf-8')
        cls.compiler = COMPILER.read_text(encoding='utf-8')

    def test_exact_approved_recursive_method(self):
        approved = guard(self.donor)
        self.assertEqual(approved, guard(self.overlay))
        self.assertIn('node.EnumerateArray()', approved)
        self.assertIn('NATIVE_JSON_DUPLICATE_FIELD_DENIED', approved)

    def test_page_payload_rejected_before_dispatch(self):
        code = self.overlay.split('public async Task<NativePipeResult> RequestAsync', 1)[1]
        code = code.split('private async Task ReadPumpAsync', 1)[0]
        self.assertEqual(1, code.count('RequireUnambiguousJson(data);'))
        self.assertLess(code.index('RequireUnambiguousJson(data);'),
                        code.index('foreach (var prop in data.EnumerateObject())'))
        self.assertLess(code.index('RequireUnambiguousJson(data);'),
                        code.index('JsonSerializer.SerializeToUtf8Bytes'))

    def test_native_reply_rejected_before_identity_or_ack(self):
        code = self.overlay.split('private async Task ReadPumpAsync', 1)[1]
        self.assertEqual(1, code.count('RequireUnambiguousJson(root);'))
        self.assertLess(code.index('RequireUnambiguousJson(root);'),
                        code.index('root.TryGetProperty("protocol"'))
        self.assertLess(code.index('RequireUnambiguousJson(root);'),
                        code.index('root.TryGetProperty("status"'))

    def test_existing_windows_staging_pin_and_no_loss(self):
        m = re.search(r'"NativePythonPipe\.cs"\s*:\s*"([0-9a-f]{40})"', self.compiler)
        self.assertIsNotNone(m)
        self.assertEqual(git_blob(OVERLAY.read_bytes()), m.group(1))
        self.assertIn('"chat.stop"', self.overlay)
        self.assertIn('NATIVE_SESSION_FRAME_WINDOW_EXHAUSTED', self.overlay)

    def test_duplicate_json_fixture_is_ambiguous(self):
        attacker = '{"status":"HOLD","status":"OK","result":{"sid":"fake","sid":"real"}}'
        self.assertEqual('OK', json.loads(attacker)['status'])
        def reject_pairs(pairs):
            out = {}
            for key, value in pairs:
                if key in out:
                    raise ValueError('NATIVE_JSON_DUPLICATE_FIELD_DENIED')
                out[key] = value
            return out
        with self.assertRaisesRegex(ValueError, 'NATIVE_JSON_DUPLICATE_FIELD_DENIED'):
            json.loads(attacker, object_pairs_hook=reject_pairs)


if __name__ == '__main__':
    unittest.main()
