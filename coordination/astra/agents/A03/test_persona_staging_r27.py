"""Execute the real Persona stager against synthetic local ZIPs, no build."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / 'integrations/creative/stage_persona_media.py'
spec = importlib.util.spec_from_file_location('persona_r27', SOURCE)
ps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ps)


def bundle(path, marker=b'original'):
    entries, files = [], {}
    for name in (*ps.ACTIVE, *ps.BLOCKED):
        row = dict(id=name, status='APPROVED_SOURCE' if name in ps.ACTIVE else 'IDENTITY_CONFLICT_HOLD',
                   approved_for_active_persona=name in ps.ACTIVE)
        for kind, ext in [('loop', 'mp4'), ('poster', 'jpg')]:
            filename = f'NOX_PERSONA_{name}_{kind}.{ext}'
            data = marker + name.encode() + kind.encode()
            files[filename] = data
            row[kind+'_filename'] = filename
            row[kind+'_sha256'] = hashlib.sha256(data).hexdigest()
        entries.append(row)
    files['PERSONA_MOTION_MANIFEST.json'] = json.dumps(dict(
        schema='NOX_PERSONA_PARALLAX_SILENT_LOOP_V1', entries=entries)).encode()
    with zipfile.ZipFile(path, 'w') as z:
        for name, data in files.items(): z.writestr(name, data)
    return path


class PersonaStagingR27(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base/'stage'
        (self.root/'Assets/creative').mkdir(parents=True)
        (self.root/'NOX.P01.Shell.csproj').write_text('original host')
        self.bundle = bundle(self.base/'media.zip')
        self.pin = hashlib.sha256(self.bundle.read_bytes()).hexdigest()
        self.patch = patch.object(ps, 'PINNED_BUNDLE_SHA256', self.pin)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_valid_media_preserves_face_count_and_pin(self):
        receipt = ps.stage(self.root, self.bundle)
        self.assertEqual(receipt['source_bundle_sha256'], self.pin)
        self.assertEqual(receipt['media_files'], 8)
        self.assertEqual(receipt['active_count'], 4)
        self.assertEqual(receipt['identity_candidate_hold'], 1)

    def test_symlink_assets_parent_rejected_before_external_write(self):
        shutil.rmtree(self.root/'Assets')
        outside = self.base/'outside'
        outside.mkdir()
        (self.root/'Assets').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'REPARSE'):
            ps.stage(self.root, self.bundle)
        self.assertEqual(list(outside.iterdir()), [])

    def test_symlink_stage_root_rejected_without_following_it(self):
        alias = self.base/'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'REPARSE'):
            ps.stage(alias, self.bundle)
        self.assertFalse((self.root/'Assets/creative/personas').exists())

    def test_symlink_host_marker_rejected(self):
        marker = self.root/'NOX.P01.Shell.csproj'
        marker.unlink()
        target = self.base/'other-host'
        target.write_text('other host')
        marker.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'REPARSE'):
            ps.stage(self.root, self.bundle)

    def test_zip_replacement_after_hash_never_changes_staged_bytes(self):
        replacement = bundle(self.base/'replacement.zip', b'changed')
        real_sha = ps.sha
        changed = False
        def replace_after_hash(data):
            nonlocal changed
            digest = real_sha(data)
            if not changed:
                changed = True
                self.bundle.write_bytes(replacement.read_bytes())
            return digest
        with patch.object(ps, 'sha', replace_after_hash):
            receipt = ps.stage(self.root, self.bundle)
        output = self.root/'Assets/creative/personas/NOX_PERSONA_KV_loop.mp4'
        self.assertEqual(output.read_bytes(), b'originalKVloop')
        self.assertEqual(receipt['source_bundle_sha256'], self.pin)


if __name__ == '__main__': unittest.main()
