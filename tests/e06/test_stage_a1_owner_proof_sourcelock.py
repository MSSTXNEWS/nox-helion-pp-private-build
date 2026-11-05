"""Regression: original A1 WPF HMAC proof must match E06 50-addon source pin.

Run inside the EXISTING NOX Express checkout, without native Windows or model
weights. Does not enable A1, create a native owner, or claim E07 acceptance.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
STAGE_PATH = ROOT / 'coordination/e06/stage_native_stdio.py'
PROOF_PATH = 'src/nox_selfbuilder/a1_wpf_owner_proof.py'
A1_SOURCE_PATHS = (
    'coordination/e06/e06_native_stdio_owner.py',
    'src/nox_selfbuilder/a1_native_command.py',
    'src/nox_selfbuilder/a1_existing_components.py',
    'src/nox_selfbuilder/firstboot_coordinator.py',
    'src/nox_selfbuilder/a1_initiative_bridge.py',
    'src/nox_selfbuilder/a1_official_catalog.py',
    PROOF_PATH,
)


def load_original_stage():
    spec = importlib.util.spec_from_file_location('nox_e06_a1_pin_under_test', STAGE_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError('E06_ORIGINAL_STAGE_MISSING')
    stage = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stage)
    return stage


class OriginalA1OwnerProofPin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stage = load_original_stage()
        cls.pins = {source: (target, git_sha)
                    for source, target, git_sha in cls.stage.ADDONS}

    def test_all_original_a1_ingress_and_firstboot_pins_match_source(self):
        """A stale HMAC proof pin blocks staging before any Python owner boot."""
        for source in A1_SOURCE_PATHS:
            with self.subTest(source=source):
                self.assertIn(source, self.pins)
                target, pinned_sha = self.pins[source]
                actual = ROOT / source
                self.assertTrue(actual.is_file() and not actual.is_symlink())
                data = actual.read_bytes()
                self.assertEqual(pinned_sha, self.stage.git_blob(data))
                self.assertEqual(self.stage.pinned_bytes(actual, pinned_sha), data)
                self.assertTrue(target.endswith('.py'))
                compile(data, str(actual), 'exec')

    def test_hmac_is_the_single_reviewed_wpf_source(self):
        """Do not revive orphan ECDSA verification or grant user/page config."""
        target, pin = self.pins[PROOF_PATH]
        self.assertEqual(target, 'nox_selfbuilder/a1_wpf_owner_proof.py')
        proof = (ROOT / PROOF_PATH).read_text(encoding='utf-8')
        self.assertIn('class A1WpfOwnerProof:', proof)
        self.assertIn('hmac.compare_digest(', proof)
        self.assertEqual(pin, self.stage.git_blob((ROOT / PROOF_PATH).read_bytes()))
        self.assertIn('serve_existing_store(original_store, args.run_id, args.data_dir)',
                      self.stage.STAGED_MODE)
        self.assertNotIn('native_a_owner_components=', self.stage.STAGED_MODE)

    def test_tampered_owner_proof_never_passes_pinned_bytes(self):
        source = (ROOT / PROOF_PATH).read_bytes()
        pin = self.pins[PROOF_PATH][1]
        with tempfile.TemporaryDirectory() as dirname:
            changed = Path(dirname) / 'a1_wpf_owner_proof.py'
            changed.write_bytes(source + b'\n# SOURCELOCK_TAMPERED\n')
            with self.assertRaisesRegex(RuntimeError, 'E06_NATIVE_OWNER_BLOB_SHA_HOLD'):
                self.stage.pinned_bytes(changed, pin)


if __name__ == '__main__':
    unittest.main()
