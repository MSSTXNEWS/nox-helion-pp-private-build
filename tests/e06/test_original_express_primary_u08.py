"""Source-only fixtures; real Windows WebView2/UIA/E07 are distinct."""
import hashlib
import unittest
from unittest.mock import patch
import importlib.util
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "coordination/express/stage_original_five_primary.py"
SPEC = importlib.util.spec_from_file_location("nox_u08_stage_original_five_primary", SOURCE)
assert SPEC is not None and SPEC.loader is not None
target = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(target)


class FivePrimaryTests(unittest.TestCase):
    def setUp(self):
        self.raw = b'<html><body><a href="/chat">CHAT</a><main>ORIGINAL</main></body></html>'
        self.guard = (patch.object(target, 'ORIGINAL_BYTES', len(self.raw)),
                      patch.object(target, 'ORIGINAL_SHA256', hashlib.sha256(self.raw).hexdigest()))
        for item in self.guard: item.start()

    def tearDown(self):
        for item in reversed(self.guard): item.stop()

    def test_original_preserved_five_buttons_source_only(self):
        output, proof = target.publish(self.raw)
        self.assertIn(self.raw.split(b'</body>')[0], output)
        self.assertEqual(output.count(b'data-nox-primary='), 5)
        self.assertIn(b'prefers-reduced-motion', output)
        self.assertIn(b'event.isTrusted', output)
        self.assertIn(b'window.chrome.webview.postMessage', output)
        self.assertEqual(proof['installed_ui_automation'], 'NOT_RUN')
        self.assertIs(proof['release_accepted'], False)
        self.assertEqual(proof['source_sha256'], hashlib.sha256(self.raw).hexdigest())

    def test_tampered_bytes_rejected(self):
        with self.assertRaisesRegex(ValueError, 'SHA_HOLD'):
            target.publish(self.raw.replace(b'ORIGINAL', b'ORIGINA!'))

    def test_changed_length_rejected(self):
        with self.assertRaisesRegex(ValueError, 'BYTES_HOLD'):
            target.publish(self.raw + b'!')

    def test_malformed_or_duplicate_markup_rejected(self):
        for suffix in (b'</body>', b'id="nox-express-primary"'):
            changed = self.raw.replace(b'ORIGINAL', suffix)
            with patch.object(target, 'ORIGINAL_BYTES', len(changed)), patch.object(target, 'ORIGINAL_SHA256', hashlib.sha256(changed).hexdigest()):
                with self.assertRaises(ValueError): target.publish(changed)

    def test_renderer_does_not_fake_ack_or_disable_security(self):
        bad = ['NATIVE_PERMISSION_GRANTED', 'release_accepted": True', 'models.pull', 'training.start', 'window.open(', 'fetch(']
        for word in bad: self.assertNotIn(word, target.INSERT)

if __name__ == '__main__': unittest.main()
