#!/usr/bin/env python3
"""Offline exact tests for NOX Drive staging, never touching credentials or host."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

PATH = Path(__file__).with_name("nox_drive_prefetch.py")
SPEC = importlib.util.spec_from_file_location("nox_drive_prefetch", PATH)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class DrivePrefetchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.disk = self.root / "disk"
        self.dest = self.root / "dest"
        self.disk.mkdir(mode=0o700)
        self.dest.mkdir(mode=0o700)
        self.contents = b"known safe bytes for NOX test\n"
        self.asset = {
            "name": "testweights.gguf",
            "size": len(self.contents),
            "sha256": hashlib.sha256(self.contents).hexdigest()
        }
        self.m = {
            "schema": mod.SCHEMA,
            "remote": "noxdrive:NOX_COLD",
            "assets": [self.asset]
        }
        self.manifest = self.root / "manifest.json"
        self.manifest.write_text(json.dumps(self.m))
        self.expected = hashlib.sha256(self.manifest.read_bytes()).hexdigest()

    def test_valid_manifest_and_reject_tampering(self):
        self.assertEqual(mod.read_manifest(self.manifest, self.expected), self.m)
        self.manifest.write_text("{}")
        with self.assertRaisesRegex(mod.Hold, "MANIFEST_MISMATCH"):
            mod.read_manifest(self.manifest, self.expected)

    def test_name_reject_path_escape(self):
        self.m["assets"][0]["name"] = "../s03.gguf"
        self.manifest.write_text(json.dumps(self.m))
        check = hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        with self.assertRaisesRegex(mod.Hold, "ASSET_NAME"):
            mod.read_manifest(self.manifest, check)

    def test_plan_only_does_not_create_weight(self):
        class Opt:
            mode = "disk"
            ssd = None
            execute = False
        opts = Opt()
        opts.manifest = str(self.manifest)
        opts.manifest_sha = self.expected
        opts.destination = str(self.dest)
        result = mod.run(opts)
        self.assertEqual(result["state"], "PLAN_ONLY")
        self.assertFalse((self.dest / self.asset["name"]).exists())

    def test_ssd_verified_hit_copies_and_reuses(self):
        source = self.disk / self.asset["name"]
        source.write_bytes(self.contents)
        mod.receipt(source, self.asset, self.expected)
        with patch.object(mod, "requires_space", return_value=10000000000), \
             patch.object(mod, "stopped", return_value=False):
            a = mod.stage_one(self.m, self.asset, self.expected, self.dest, from_dir=self.disk)
            b = mod.stage_one(self.m, self.asset, self.expected, self.dest, from_dir=self.disk)
        self.assertEqual(a["result"], "VERIFIED_NEW")
        self.assertEqual(b["result"], "CACHE_HIT")
        self.assertEqual((self.dest / self.asset["name"]).read_bytes(), self.contents)

    def test_bad_source_receipt_does_not_publish(self):
        source = self.disk / self.asset["name"]
        source.write_bytes(b"corrupt")
        with patch.object(mod, "requires_space", return_value=10000000000), \
             patch.object(mod, "stopped", return_value=False):
            with self.assertRaisesRegex(mod.Hold, "SSD_NOT_VERIFIED"):
                mod.stage_one(self.m, self.asset, self.expected, self.dest, from_dir=self.disk)
        self.assertFalse((self.dest / self.asset["name"]).exists())

    def test_ram_floor_fails_closed(self):
        with patch.object(mod, "cgroup_raw_free", return_value=100):
            with self.assertRaisesRegex(mod.Hold, "CGROUP_RAM"):
                mod.requires_space(self.dest, len(self.contents), ram=True)

    def test_unbounded_or_unknown_cgroup_ram_is_held(self):
        cgroup = self.root / "cgroup"
        cgroup.mkdir(mode=0o700)
        (cgroup / "memory.max").write_text("max\n")
        (cgroup / "memory.current").write_text("1\n")
        self.assertEqual(mod.cgroup_raw_free(cgroup), 0)

        class Usage:
            free = 16 * mod.GiB

        with patch.object(mod.shutil, "disk_usage", return_value=Usage()):
            for bad in (None, True, float("inf"), "999"):
                with patch.object(mod, "cgroup_raw_free", return_value=bad):
                    with self.subTest(raw_free=bad):
                        with self.assertRaisesRegex(mod.Hold, "CGROUP_RAM"):
                            mod.requires_space(self.dest, 128, ram=True)
            self.assertEqual(mod.requires_space(self.dest, 128, ram=True,
                                                raw_free=8 * mod.GiB), Usage.free)

    def test_stop_halts_before_copy(self):
        with patch.object(mod, "stopped", return_value=True):
            with self.assertRaisesRegex(mod.Hold, "STOP"):
                mod.stage_one(self.m, self.asset, self.expected, self.dest, from_dir=self.disk)

    def test_stop_during_hash_does_not_publish_weight(self):
        name = self.asset["name"]
        source = self.disk / name
        source.write_bytes(self.contents)
        mod.receipt(source, self.asset, self.expected)
        hash_file = mod.sha_file
        stopped = False

        def arm_stop_during_hash(path):
            nonlocal stopped
            digest = hash_file(path)
            stopped = True
            return digest

        with patch.object(mod, "requires_space"), \
             patch.object(mod, "stopped", side_effect=lambda: stopped), \
             patch.object(mod, "sha_file", side_effect=arm_stop_during_hash):
            with self.assertRaisesRegex(mod.Hold, "HOLD_DRIVE_STOP"):
                mod.stage_one(self.m, self.asset, self.expected, self.dest, from_dir=self.disk)

        self.assertEqual(list(self.dest.iterdir()), [])
        self.assertEqual(source.read_bytes(), self.contents)


if __name__ == "__main__":
    unittest.main()
