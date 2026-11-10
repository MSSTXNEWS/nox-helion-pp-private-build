"""Original E06 SAME-VM/NSIS payload: deny parent junctions during 14-file admission.

These tests extract the original unchanged helpers without running a Windows
build or creating another Python/OneHost backend.
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import re
import stat
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2] / "coordination/e06/t06_local_onehost_bridge.py"


def original_admission():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    required = {"digest", "_no_reparse_components", "verify_mega814_payload_files"}
    nodes = [item for item in tree.body
             if isinstance(item, ast.FunctionDef) and item.name in required]
    if {n.name for n in nodes} != required:
        raise AssertionError("original NSIS helper missing: source patch is not staged")
    module = ast.Module(body=nodes, type_ignores=[])
    env = {"hashlib": hashlib, "re": re, "stat": stat}
    exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), env)
    return env["verify_mega814_payload_files"]


class OriginalNSISPayloadAncestorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.real = self.root / "real" / "Assets" / "mega814"
        self.real.mkdir(parents=True)
        entries = []
        for i in range(14):
            name = f"asset-{i:02d}.png"
            data = f"approved-fixture-{i}".encode("ascii")
            (self.real / name).write_bytes(data)
            entries.append({"name": name, "bytes": len(data),
                            "sha256": hashlib.sha256(data).hexdigest()})
        self.summary = {"files": entries}
        self.verify = original_admission()

    def tearDown(self):
        self.temp.cleanup()

    def test_14_distinct_pinned_assets_unchanged(self):
        self.assertEqual(self.verify(self.real, self.summary), 14)

    def test_redirected_parent_directory_is_not_trusted(self):
        alias = self.root / "redirect"
        try:
            alias.symlink_to(self.root / "real", target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"Symlink test unavailable: {error}")
        # Neither the packaged leaf nor any asset leaf is itself a symlink.
        with self.assertRaisesRegex(RuntimeError, "NOX_MEGA814_PACKAGE_PATH_UNTRUSTED"):
            self.verify(alias / "Assets" / "mega814", self.summary)

    def test_direct_package_symlink_remains_denied(self):
        alias = self.root / "redirect"
        try:
            alias.symlink_to(self.real, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"Symlink test unavailable: {error}")
        with self.assertRaisesRegex(RuntimeError, "NOX_MEGA814_PACKAGE_PATH_UNTRUSTED"):
            self.verify(alias, self.summary)

    def test_modified_asset_still_rejected(self):
        (self.real / "asset-00.png").write_bytes(b"tampered")
        with self.assertRaisesRegex(RuntimeError, "NOX_MEGA814_PAYLOAD_SHA_DRIFT"):
            self.verify(self.real, self.summary)

    def test_casefold_duplicate_still_rejected(self):
        self.summary["files"][1] = dict(self.summary["files"][0])
        with self.assertRaisesRegex(RuntimeError, "NOX_MEGA814_RESOURCE_NAME_INVALID_OR_DUPLICATE"):
            self.verify(self.real, self.summary)

    def test_invalid_digest_still_rejected(self):
        self.summary["files"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "NOX_MEGA814_PAYLOAD_SHA_DRIFT"):
            self.verify(self.real, self.summary)


if __name__ == "__main__":
    unittest.main()
