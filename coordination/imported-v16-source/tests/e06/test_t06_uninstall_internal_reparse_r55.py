"""Source-only T06/NSIS original uninstall provenance: reparse ancestry must HOLD.

The exact existing t06_uninstall_admission.py is imported. No Windows install,
real registry, WPF, or independent E07 is claimed by these offline tests.
"""
from __future__ import annotations

import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "coordination" / "e06"))
from t06_uninstall_admission import owned_payload_paths, verify_original_uninstall


class _MissingRegistry:
    KEY_WOW64_32KEY, KEY_WOW64_64KEY = 0x200, 0x100
    KEY_READ = 0x20019
    HKEY_CURRENT_USER = object()
    def __init__(self): self.views = []
    def OpenKey(self, key, name, zero, flags):
        self.views.append(flags & 0x300)
        raise FileNotFoundError(name)


class OriginalUninstallInternalReparseR55(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.install = self.root / 'NOX HELION'
        self.install.mkdir()
        self.names = ['NOX.P01.Shell.exe', 'Backend/NOX_HELION_PRIVATE_CANDIDATE.exe'] + [
            f'Assets/original_{n:02d}.bin' for n in range(10)]
        self.inventory = {'schema': 'NOX_P01_PAYLOAD_SHA256_V1',
                          'files': [{'path': name} for name in self.names]}
        for name in self.names:
            p = self.install.joinpath(*name.split('/'))
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b'original')
        for name in ('payload.sha256.json', 'nox-p01-owned.txt', 'Uninstall.exe'):
            (self.install / name).write_bytes(b'metadata')

    def _symlink(self, link: Path, target: Path):
        try:
            link.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('test OS disallows directory symlinks')

    def _clean(self):
        for name in self.names:
            self.install.joinpath(*name.split('/')).unlink()
        for name in ('payload.sha256.json', 'nox-p01-owned.txt', 'Uninstall.exe'):
            (self.install / name).unlink()

    def test_normal_original_manifest_and_samevm_uninstall_accepts(self):
        owned = owned_payload_paths(self.install, self.inventory)
        personal = self.install / 'untracked-owner-document.txt'
        personal.write_text('keep me', encoding='utf-8')
        self._clean()
        registry = _MissingRegistry()
        verify_original_uninstall(self.install, owned, registry)
        self.assertEqual(registry.views, [0x200, 0x100])
        self.assertEqual(personal.read_text('utf-8'), 'keep me')

    def test_redirected_assets_within_same_install_root_denied(self):
        original = self.install / 'Assets'
        moved = self.install / 'OriginalAssets'
        original.rename(moved)
        self._symlink(original, moved)
        with self.assertRaisesRegex(RuntimeError, 'T06_UNINSTALL_ORIGINAL_INVENTORY_PATH_HOLD'):
            owned_payload_paths(self.install, self.inventory)

    def test_root_has_symlink_parent_denied(self):
        physical_parent = self.root / 'real'
        physical_parent.mkdir()
        physical_install = physical_parent / 'NOX HELION'
        self.install.rename(physical_install)
        linked_parent = self.root / 'alias'
        self._symlink(linked_parent, physical_parent)
        with self.assertRaisesRegex(RuntimeError, 'T06_UNINSTALL_ORIGINAL_INVENTORY_HOLD'):
            owned_payload_paths(linked_parent / 'NOX HELION', self.inventory)

    def test_after_removal_new_redirected_assets_dir_never_certifies_uninstall(self):
        owned = owned_payload_paths(self.install, self.inventory)
        self._clean()
        old_assets = self.install / 'Assets'
        old_assets.rmdir()
        substitute = self.install / 'empty-but-untrusted-assets'
        substitute.mkdir()
        self._symlink(old_assets, substitute)
        with self.assertRaisesRegex(RuntimeError, 'T06_CONSERVATIVE_UNINSTALL_MANIFEST_FILE_REMAINS'):
            verify_original_uninstall(self.install, owned, _MissingRegistry())

    def test_metadata_redirected_leaf_never_certifies_uninstall(self):
        owned = owned_payload_paths(self.install, self.inventory)
        self._clean()
        outside = self.root / 'gone'
        self._symlink(self.install / 'Uninstall.exe', outside)
        with self.assertRaisesRegex(RuntimeError, 'T06_CONSERVATIVE_UNINSTALL_METADATA_REMAINS'):
            verify_original_uninstall(self.install, owned, _MissingRegistry())


if __name__ == '__main__': unittest.main()
