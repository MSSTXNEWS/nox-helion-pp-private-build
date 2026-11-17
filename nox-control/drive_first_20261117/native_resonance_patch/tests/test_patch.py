import importlib.util
import fcntl
import os
from html.parser import HTMLParser
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('native_patch', ROOT / 'native_minimal_patch.py')
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)
ORIGINAL = (ROOT / 'source_before/resonance.html').read_bytes()


class Markup(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.tags = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'data-nox-native-fix' in attrs:
            return
        attrs.pop('data-nox-readability-fix', None)
        self.tags.append((tag, attrs))


class PatchTests(unittest.TestCase):
    def run_patch(self, action, site, **kwargs):
        return patch.run(action, site, maintenance_lock_path=site.parent / 'owner_maintenance.lock', **kwargs)

    def fixture(self, base):
        site = Path(base) / 'site'
        (site / 'pc').mkdir(parents=True)
        target = site / 'pc/resonance.html'
        target.write_bytes(ORIGINAL)
        return site, target

    def test_apply_idempotency_backup_and_exact_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            site, target = self.fixture(tmp)
            self.assertEqual(self.run_patch('check', site)['status'], 'READY')
            self.assertEqual([p.name for p in (site / 'pc').iterdir()], ['resonance.html'])
            receipt = self.run_patch('apply', site)
            self.assertEqual(receipt['status'], 'APPLIED')
            self.assertEqual(Path(receipt['backup']).read_bytes(), ORIGINAL)
            self.assertEqual(patch.digest(target.read_bytes()), patch.AFTER_SHA)
            self.assertEqual(self.run_patch('apply', site)['status'], 'ALREADY_APPLIED')
            self.assertEqual(self.run_patch('rollback', site)['status'], 'ROLLED_BACK')
            self.assertEqual(target.read_bytes(), ORIGINAL)

    def test_cas_and_foreign_asset_and_rollback_guards(self):
        with tempfile.TemporaryDirectory() as tmp:
            site, target = self.fixture(tmp)
            target.write_bytes(ORIGINAL + b'\n')
            with self.assertRaisesRegex(ValueError, 'SHA differs'):
                self.run_patch('apply', site)
            self.assertEqual(target.read_bytes(), ORIGINAL + b'\n')
            self.assertFalse(any((site / 'pc' / name).exists() for name in patch.ASSETS))
            target.write_bytes(ORIGINAL)
            asset = site / 'pc' / next(iter(patch.ASSETS))
            asset.write_text('foreign owner content')
            with self.assertRaisesRegex(ValueError, 'asset collision'):
                self.run_patch('apply', site)
            self.assertEqual(target.read_bytes(), ORIGINAL)
            asset.unlink()
            self.run_patch('apply', site)
            changed = target.read_bytes() + b'<!-- concurrent owner edit -->'
            target.write_bytes(changed)
            with self.assertRaisesRegex(ValueError, 'rollback refuses'):
                self.run_patch('rollback', site)
            self.assertEqual(target.read_bytes(), changed)

    def test_late_asset_collision_never_clobbers_foreign_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            site, target = self.fixture(tmp)
            original_write = patch.atomic_write
            collided = []
            def race(path, data, mode, **kwargs):
                if kwargs.get('no_clobber') and not collided:
                    path.write_bytes(b'late foreign file')
                    collided.append(path)
                return original_write(path, data, mode, **kwargs)
            with mock.patch.object(patch, 'atomic_write', side_effect=race):
                with self.assertRaisesRegex(ValueError, 'late asset collision'):
                    self.run_patch('apply', site)
            self.assertEqual(collided[0].read_bytes(), b'late foreign file')
            self.assertEqual(target.read_bytes(), ORIGINAL)

    def test_existing_maintenance_lock_blocks_and_inherited_fd_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            site, target = self.fixture(tmp)
            lockfile = site.parent / 'owner_maintenance.lock'
            with lockfile.open('w') as lease:
                fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaises(BlockingIOError):
                    self.run_patch('apply', site)
                self.assertEqual(target.read_bytes(), ORIGINAL)
                result = self.run_patch('apply', site, maintenance_lock_fd=lease.fileno())
                self.assertEqual(result['status'], 'APPLIED')
                os.fstat(lease.fileno())
                with lockfile.open('r') as other:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_original_markup_handlers_and_assets_preserved(self):
        updated = patch.transform(ORIGINAL)
        self.assertEqual(Markup(ORIGINAL.decode()).tags, Markup(updated.decode()).tags)
        self.assertNotIn(b'LOCAL', updated)
        self.assertNotIn(b'127.0.0.1', updated)
        self.assertEqual(updated, (ROOT / 'source_after/resonance.html').read_bytes())
        for name, text in patch.ASSETS.items():
            self.assertEqual(text.encode(), (ROOT / 'pc' / name).read_bytes())


if __name__ == '__main__':
    unittest.main(verbosity=2)
