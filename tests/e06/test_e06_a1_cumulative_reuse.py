"""Exact A1/E06 duplicate source staging regression (source-only, no Windows E07)."""
from __future__ import annotations
import hashlib
import importlib.util
import json
import re
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

A1 = load(ROOT / 'coordination/e06/stage_a1_owner.py', 'a1_stage_verified_reuse')
E06 = load(ROOT / 'coordination/e06/stage_native_stdio.py', 'e06_stage_verified_reuse')

class CumulativeStage(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.repo = base / 'owner'
        self.target = base / 'disposable'
        self.repo.mkdir()
        self.target.mkdir()
        self.names = list(A1.REQUIRED)
        self.assertEqual(len(self.names), 10)
        self.preexisting = [x for x in self.names if x != 'worm_providers.py']
        self.assertEqual(len(self.preexisting), 9)
        pins = {}
        for name in self.names:
            file = self.repo / 'src/nox_selfbuilder' / name
            file.parent.mkdir(parents=True, exist_ok=True)
            raw = ("SOURCE_NAME = " + repr(name) + "\n").encode()
            file.write_bytes(raw)
            pins[name] = A1.git_blob(raw)
            if name in self.preexisting:
                existing = self.target / 'nox_selfbuilder' / name
                existing.parent.mkdir(parents=True, exist_ok=True)
                existing.write_bytes(raw)
        self.manifest = self.repo / 'coordination/e06/A1_BUILD_SOURCES.lock.json'
        self.manifest.parent.mkdir(parents=True)
        self.manifest.write_text(json.dumps({
            'schema': 'NOX-A1-ONEHOST-STAGE-LOCK-v1', 'sources': pins
        }), encoding='utf-8')

    def apply(self):
        return A1.stage(self.target, repo=self.repo, manifest_path=self.manifest)

    def test_reuse_nine_and_add_only_missing_provider(self):
        old = {
            name: (self.target / 'nox_selfbuilder' / name).read_bytes()
            for name in self.preexisting
        }
        receipt = self.apply()
        self.assertEqual(receipt['source_count'], 10)
        self.assertEqual(receipt['reused_staged_count'], 9)
        self.assertEqual(receipt['newly_staged_count'], 1)
        self.assertEqual(len(receipt['reused_runtime_paths']), 9)
        self.assertEqual([x['runtime_path'] for x in receipt['runtime_data_files']],
                         ['nox_selfbuilder/worm_providers.py'])
        for name, raw in old.items():
            self.assertEqual((self.target / 'nox_selfbuilder' / name).read_bytes(), raw)
        provider = self.target / 'nox_selfbuilder/worm_providers.py'
        self.assertEqual(receipt['runtime_data_files'][0]['sha256'],
                         hashlib.sha256(provider.read_bytes()).hexdigest())
        self.assertFalse(receipt['installed_exe_accepted'])
        self.assertFalse(receipt['native_activation_verified'])

    def test_reject_tampered_reused_source_before_provider_write(self):
        bad = self.target / 'nox_selfbuilder/worms.py'
        bad.write_bytes(b'UNTRUSTED = True\n')
        with self.assertRaisesRegex(ValueError, 'A1_STAGE_REUSED_SOURCE_SHA_HOLD'):
            self.apply()
        self.assertEqual(bad.read_bytes(), b'UNTRUSTED = True\n')
        self.assertFalse((self.target / 'nox_selfbuilder/worm_providers.py').exists())

    def test_reject_missing_original_before_any_new_write(self):
        (self.repo / 'src/nox_selfbuilder/worms.py').unlink()
        with self.assertRaisesRegex(ValueError, 'A1_SOURCE_REGULAR_FILE_REQUIRED'):
            self.apply()
        self.assertFalse((self.target / 'nox_selfbuilder/worm_providers.py').exists())

    def test_reject_symlinked_preexisting_source(self):
        target = self.target / 'nox_selfbuilder/worms.py'
        target.unlink()
        try:
            target.symlink_to(self.repo / 'src/nox_selfbuilder/worms.py')
        except OSError:
            self.skipTest('OS disallows fixture symlinks')
        with self.assertRaisesRegex(ValueError, 'A1_STAGE_REPARSE_OR_SYMLINK_HOLD'):
            self.apply()

    def test_live_checkout_ten_pins_identical_across_both_stages(self):
        manifest = json.loads((ROOT / 'coordination/e06/A1_BUILD_SOURCES.lock.json').read_text('utf-8'))
        pinned = manifest['sources']
        self.assertEqual(set(pinned), set(A1.REQUIRED))
        native = {Path(dest).name: digest for rel, dest, digest in E06.ADDONS
                  if rel.startswith('src/nox_selfbuilder/') and Path(dest).name in pinned}
        self.assertEqual(set(native), set(self.preexisting))
        for name, digest in pinned.items():
            path = ROOT / 'src/nox_selfbuilder' / name
            self.assertTrue(path.is_file(), name)
            self.assertEqual(A1.git_blob(path.read_bytes()), digest, name)
            if name in native:
                self.assertEqual(native[name], digest, name)

    def test_powershell_original_bundle_only_adds_one_non_duplicate(self):
        script = (ROOT / 'private_build.ps1').read_text('utf-8')
        for token in ('reused_staged_count -ne 9', 'newly_staged_count -ne 1',
                      'A1_VERIFIED_REUSE_MISSING_FROM_NATIVE_RUNTIME',
                      "Count + 1", 'A1_ONEHOST_NATIVE_STAGE_FAILED'):
            self.assertIn(token, script)


    def test_private_builder_pin_matches_reviewed_a1_stage(self):
        script = (ROOT / 'private_build.ps1').read_text('utf-8')
        pinned = re.findall(r"\$a1OwnerPin='([0-9a-f]{40})'", script)
        self.assertEqual(pinned, [A1.git_blob((ROOT / 'coordination/e06/stage_a1_owner.py').read_bytes())])
        self.assertIn("throw 'A1_ONEHOST_STAGE_SOURCE_PIN_HOLD'", script)

    def test_rewritten_manifest_and_sources_keep_real_file_identity(self):
        # Exercise the real readers after multiple updates, not a fresh-file-only proof.
        raw = self.manifest.read_bytes()
        src = self.repo / 'src/nox_selfbuilder/worms.py'
        source_bytes = src.read_bytes()
        for _ in range(12):
            self.manifest.write_bytes(raw)
            src.write_bytes(source_bytes)
            self.assertEqual(A1.trusted_manifest_bytes(self.manifest), raw)
            self.assertEqual(A1.trusted_source_bytes(src, self.repo), source_bytes)
        self.assertEqual(self.apply()['reused_staged_count'], 9)

    def test_noncanonical_manifest_is_rejected(self):
        alias = self.repo / 'different-lock.json'
        alias.write_bytes(self.manifest.read_bytes())
        with self.assertRaisesRegex(ValueError, 'A1_CANONICAL_SOURCE_LOCK_REQUIRED'):
            A1.stage(self.target, repo=self.repo, manifest_path=alias)


class WindowsFileMetadata(unittest.TestCase):
    @staticmethod
    def info(**changes):
        values = dict(st_dev=2, st_ino=7, st_size=16, st_mtime_ns=300,
                      st_ctime_ns=100, st_birthtime_ns=100)
        values.update(changes)
        return SimpleNamespace(**values)

    def test_windows_cross_api_ctime_difference_is_not_a_source_replacement(self):
        with patch.object(A1, '_WINDOWS_STAT', True):
            self.assertTrue(A1._same_named_descriptor(self.info(), self.info(st_ctime_ns=200)))

    def test_windows_identity_metadata_changes_still_fail_closed(self):
        with patch.object(A1, '_WINDOWS_STAT', True):
            for key in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_birthtime_ns'):
                with self.subTest(field=key):
                    self.assertFalse(A1._same_named_descriptor(
                        self.info(), self.info(**{key: getattr(self.info(), key)+1})))
            for value in (None, True, 100.0, '100'):
                self.assertFalse(A1._same_named_descriptor(
                    self.info(st_birthtime_ns=value), self.info(st_birthtime_ns=value)))

    def test_posix_change_time_remains_mandatory(self):
        with patch.object(A1, '_WINDOWS_STAT', False):
            self.assertFalse(A1._same_named_descriptor(self.info(), self.info(st_ctime_ns=200)))

    def test_in_read_descriptor_change_time_mutation_still_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'fixture.json'
            path.write_bytes(b'{"safe":true}')
            original_fstat = A1.os.fstat
            for kind in ('manifest', 'source'):
                count = [0]
                def changed(fd):
                    real = original_fstat(fd)
                    fields = {key: getattr(real, key) for key in
                              ('st_dev', 'st_ino', 'st_size', 'st_mode', 'st_mtime_ns', 'st_ctime_ns')}
                    count[0] += 1
                    if count[0] == 2:
                        fields['st_ctime_ns'] += 1
                    return SimpleNamespace(**fields)
                with self.subTest(reader=kind), \
                     patch.object(A1.os, 'fstat', side_effect=changed), \
                     patch.object(A1, '_same_named_descriptor', return_value=True):
                    with self.assertRaisesRegex(ValueError, 'CHANGED_DURING_READ'):
                        if kind == 'manifest':
                            A1.trusted_manifest_bytes(path)
                        else:
                            A1.trusted_source_bytes(path, root)
                self.assertEqual(count[0], 2)

if __name__ == '__main__':
    unittest.main()
