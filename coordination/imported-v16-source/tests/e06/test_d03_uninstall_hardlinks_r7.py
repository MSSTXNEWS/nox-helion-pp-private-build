"""D03: original NSIS pre-uninstall owner must reject hardlink aliases."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
OWNER = ROOT / "coordination/e06/t06_uninstall_admission.py"


def owner():
    spec = importlib.util.spec_from_file_location("nox_d03_uninstall_hardlinks", OWNER)
    if spec is None or spec.loader is None:
        raise RuntimeError("D03_ORIGINAL_OWNER_SOURCE_MISSING")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class D03UninstallHardlinkAdmissionR7(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "installed"
        self.root.mkdir()
        self.names = [
            "NOX.P01.Shell.exe",
            "backend/nox_helion_private_candidate.exe",
            *(f"payload/part-{n}.dll" for n in range(10)),
        ]
        for name in self.names:
            leaf = self.root / name
            leaf.parent.mkdir(parents=True, exist_ok=True)
            leaf.write_bytes(b"verified-original-payload")
        self.inventory = {
            "schema": "NOX_P01_PAYLOAD_SHA256_V1",
            "files": [{"path": name} for name in self.names],
        }
        self.original_owner = owner()

    def test_normal_manifest_is_admitted_unchanged(self):
        result = self.original_owner.owned_payload_paths(self.root, self.inventory)
        self.assertEqual(len(result), 12)
        self.assertEqual((self.root / self.names[0]).read_bytes(),
                         b"verified-original-payload")

    def test_hardlink_outside_install_root_is_denied_without_deletion(self):
        owned = self.root / self.names[0]
        external_alias = Path(self.temp.name) / "unmanaged-user-data.dat"
        try:
            os.link(owned, external_alias)
        except OSError as error:
            self.skipTest(f"filesystem does not allow hardlinks: {error}")
        if owned.lstat().st_nlink < 2:
            self.skipTest("filesystem does not expose hardlink count")
        with self.assertRaisesRegex(
            RuntimeError, "T06_UNINSTALL_ORIGINAL_INVENTORY_PATH_HOLD"
        ):
            self.original_owner.owned_payload_paths(self.root, self.inventory)
        self.assertEqual(external_alias.read_bytes(), b"verified-original-payload")
        self.assertEqual(owned.read_bytes(), b"verified-original-payload")
        external_alias.unlink()
        self.assertEqual(
            len(self.original_owner.owned_payload_paths(self.root, self.inventory)),
            12,
        )

    def test_second_name_inside_install_root_is_also_denied(self):
        owned = self.root / self.names[1]
        unmanaged_alias = self.root / "user-custom-keep.bin"
        try:
            os.link(owned, unmanaged_alias)
        except OSError as error:
            self.skipTest(f"filesystem does not allow hardlinks: {error}")
        if owned.lstat().st_nlink < 2:
            self.skipTest("filesystem does not expose hardlink count")
        with self.assertRaisesRegex(
            RuntimeError, "T06_UNINSTALL_ORIGINAL_INVENTORY_PATH_HOLD"
        ):
            self.original_owner.owned_payload_paths(self.root, self.inventory)
        self.assertEqual(unmanaged_alias.read_bytes(), b"verified-original-payload")


if __name__ == "__main__":
    unittest.main()
