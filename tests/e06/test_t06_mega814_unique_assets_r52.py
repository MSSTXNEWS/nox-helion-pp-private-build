"""Original T06 14-asset NSIS source receipt: unique physical SHA-pinned files.
Source-only regression, not Windows installer or visual/E07 acceptance.
"""
import ast
import hashlib
import pathlib
import re
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE = ROOT / "coordination/e06/t06_local_onehost_bridge.py"


def load_verified_function():
    original = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    candidates = [n for n in original.body if isinstance(n, ast.FunctionDef)
                  and n.name == "verify_mega814_payload_files"]
    if len(candidates) != 1:
        raise AssertionError("Exactly one original NSIS asset admission helper required")
    module = ast.Module(body=candidates, type_ignores=[])
    ast.fix_missing_locations(module)
    def digest(file):
        return hashlib.sha256(file.read_bytes()).hexdigest()
    scope = {"re": re, "digest": digest}
    exec(compile(module, str(SOURCE), "exec"), scope)
    return scope["verify_mega814_payload_files"]


class Mega814UniqueAssetsR52(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.verify = staticmethod(load_verified_function())

    def make_assets(self, folder):
        entries = []
        for index in range(14):
            name = f"original-cinema-{index:02d}.mjs"
            payload = f"APPROVED-ASSET-{index:02d}".encode("ascii")
            (folder / name).write_bytes(payload)
            entries.append({"name": name, "bytes": len(payload),
                            "sha256": hashlib.sha256(payload).hexdigest()})
        return {"files": entries}

    def test_fourteen_distinct_hash_matched_assets(self):
        with tempfile.TemporaryDirectory() as t:
            folder = pathlib.Path(t)
            manifest = self.make_assets(folder)
            self.assertEqual(self.verify(folder, manifest), 14)

    def test_duplicate_rows_cannot_fake_fourteen_distinct_assets(self):
        with tempfile.TemporaryDirectory() as t:
            folder = pathlib.Path(t)
            manifest = self.make_assets(folder)
            manifest["files"][-1] = dict(manifest["files"][0])
            with self.assertRaisesRegex(RuntimeError, "DUPLICATE"):
                self.verify(folder, manifest)

    def test_casefold_and_win32_stream_aliases_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            folder = pathlib.Path(t)
            manifest = self.make_assets(folder)
            manifest["files"][1]["name"] = manifest["files"][0]["name"].upper()
            with self.assertRaisesRegex(RuntimeError, "DUPLICATE"):
                self.verify(folder, manifest)
            manifest = self.make_assets(folder)
            manifest["files"][0]["name"] += ":alternate-stream"
            with self.assertRaisesRegex(RuntimeError, "NAME_INVALID"):
                self.verify(folder, manifest)

    def test_mismatched_bytes_or_digest_denied(self):
        with tempfile.TemporaryDirectory() as t:
            folder = pathlib.Path(t)
            manifest = self.make_assets(folder)
            (folder / manifest["files"][3]["name"]).write_bytes(b"tampered")
            with self.assertRaisesRegex(RuntimeError, "SHA_DRIFT"):
                self.verify(folder, manifest)

    def test_reparse_or_symlink_asset_denied(self):
        with tempfile.TemporaryDirectory() as t:
            folder = pathlib.Path(t)
            manifest = self.make_assets(folder)
            target = folder / manifest["files"][2]["name"]
            target.unlink()
            try:
                target.symlink_to(folder / manifest["files"][0]["name"])
            except (OSError, NotImplementedError):
                self.skipTest("symlink unavailable on this host")
            with self.assertRaisesRegex(RuntimeError, "SHA_DRIFT"):
                self.verify(folder, manifest)


if __name__ == "__main__":
    unittest.main()
