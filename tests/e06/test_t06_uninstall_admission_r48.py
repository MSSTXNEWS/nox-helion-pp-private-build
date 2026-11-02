"""Offline fail-closed regression of original NSIS SAME-VM uninstall admission."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "coordination" / "e06"))
from t06_uninstall_admission import (owned_payload_paths,
    original_nsis_uninstall_registration_absent, verify_original_uninstall)


class FakeRegistry:
    KEY_WOW64_32KEY = 0x0200
    KEY_WOW64_64KEY = 0x0100
    KEY_READ = 0x20019
    HKEY_CURRENT_USER = object()

    def __init__(self, present_views=(), denied=False):
        self.present_views = set(present_views)
        self.denied = denied
        self.checked = []

    def OpenKey(self, root, key, reserved, flags):
        assert root is self.HKEY_CURRENT_USER
        assert key.endswith(r"Uninstall\NOXHELION.P01")
        view = flags & (self.KEY_WOW64_32KEY | self.KEY_WOW64_64KEY)
        self.checked.append(view)
        if self.denied:
            raise PermissionError("access denied")
        if view in self.present_views:
            return object()
        raise FileNotFoundError(key)

    def CloseKey(self, handle):
        pass


class OriginalNsisUninstallAdmission(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.install = Path(self.temp.name) / "NOX HELION"
        self.install.mkdir()
        names = ["NOX.P01.Shell.exe", "Backend/NOX_HELION_PRIVATE_CANDIDATE.exe"]
        names += [f"Assets/original_{n:02d}.bin" for n in range(10)]
        self.inventory = {"schema": "NOX_P01_PAYLOAD_SHA256_V1",
                          "files": [{"path": name} for name in names]}
        for name in names:
            file = self.install.joinpath(*name.split("/"))
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(b"original")
        for meta in ("payload.sha256.json", "nox-p01-owned.txt", "Uninstall.exe"):
            (self.install / meta).write_bytes(b"original-metadata")

    def _remove_owned(self, paths):
        for path in paths:
            path.unlink()
        for meta in ("payload.sha256.json", "nox-p01-owned.txt", "Uninstall.exe"):
            (self.install / meta).unlink()

    def test_all_owned_files_and_registry_removed_preserves_untracked(self):
        owned = owned_payload_paths(self.install, self.inventory)
        personal = self.install / "user-untracked.dat"
        personal.write_bytes(b"retain")
        self._remove_owned(owned)
        registry = FakeRegistry()
        verify_original_uninstall(self.install, owned, registry)
        self.assertEqual(registry.checked, [0x0200, 0x0100])
        self.assertEqual(personal.read_bytes(), b"retain")

    def test_one_leftover_manifest_file_blocks_false_pass(self):
        owned = owned_payload_paths(self.install, self.inventory)
        self._remove_owned(owned[1:])
        with self.assertRaisesRegex(RuntimeError, "MANIFEST_FILE_REMAINS"):
            verify_original_uninstall(self.install, owned, FakeRegistry())

    def test_leftover_uninstaller_metadata_blocks_false_pass(self):
        owned = owned_payload_paths(self.install, self.inventory)
        self._remove_owned(owned)
        (self.install / "Uninstall.exe").write_bytes(b"stale")
        with self.assertRaisesRegex(RuntimeError, "METADATA_REMAINS"):
            verify_original_uninstall(self.install, owned, FakeRegistry())

    def test_registry_entry_32_or_64_blocks_pass(self):
        owned = owned_payload_paths(self.install, self.inventory)
        self._remove_owned(owned)
        for view in (0x0200, 0x0100):
            with self.subTest(view=view), self.assertRaisesRegex(RuntimeError, "REGISTRY_REMAINS"):
                verify_original_uninstall(self.install, owned, FakeRegistry({view}))

    def test_registry_permission_error_is_not_absence(self):
        with self.assertRaises(PermissionError):
            original_nsis_uninstall_registration_absent(FakeRegistry(denied=True))

    def test_path_traversal_duplicate_or_omitted_binary_is_rejected(self):
        for mutation in (lambda i: i["files"].__setitem__(2, {"path": "../escape"}),
                         lambda i: i["files"].__setitem__(2, {"path": "NOX.p01.shell.EXE"}),
                         lambda i: i["files"].__setitem__(0, {"path": "Assets/original_00.bin"})):
            inventory = json.loads(json.dumps(self.inventory))
            mutation(inventory)
            with self.subTest(inventory=inventory["files"][:3]), self.assertRaises(RuntimeError):
                owned_payload_paths(self.install, inventory)


if __name__ == "__main__":
    unittest.main()
