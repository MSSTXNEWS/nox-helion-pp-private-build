import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import build_unified_bundle as bundle


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def plan(self, payload=b"verified payload"):
        source = self.root / "input.bin"
        source.write_bytes(payload)
        stat = source.stat()
        return {"status": bundle.STATUS, "archive_root": "NOX_UNIFIED", "coverage": {},
                "entries": [{"archive_path": "NOX_UNIFIED/input.bin", "size_bytes": len(payload),
                             "sha256": hashlib.sha256(payload).hexdigest(), "method": "ZIP_STORED",
                             "source": {"kind": "file", "path": str(source), "size_bytes": stat.st_size,
                                        "mtime_ns": stat.st_mtime_ns}}]}

    def test_stored_zip64_offsets_extract_only_selected_member(self):
        plan = self.plan()
        output = self.root / "kit.zip"
        receipt = bundle.build(plan, output, reserve=0, progress=lambda _: None)
        self.assertEqual(receipt["status"], bundle.STATUS)
        sidecar = json.loads(Path(str(output) + ".offsets.json").read_text())
        record = next(x for x in sidecar["entries"] if x["path"].endswith("/input.bin"))
        with output.open("rb") as stream:
            stream.seek(record["data_offset"])
            self.assertEqual(stream.read(record["bytes"]), b"verified payload")
        with zipfile.ZipFile(output) as archive:
            self.assertTrue(all(i.compress_type == zipfile.ZIP_STORED for i in archive.infolist()))
            self.assertIn(b"PRIMARY_WEIGHTS_MISSING", archive.read("NOX_UNIFIED/00_README_PRIMARY_WEIGHTS_MISSING.md"))

    def test_zip_member_streaming_without_extraction(self):
        source = self.root / "wheels.zip"
        with zipfile.ZipFile(source, "w") as archive:
            archive.writestr("original/a.whl", b"wheel bytes")
        stat = source.stat()
        plan = {"status": bundle.STATUS, "archive_root": "NOX_UNIFIED", "coverage": {}, "entries": [{
            "archive_path": "NOX_UNIFIED/wheels/a.whl", "size_bytes": 11,
            "sha256": hashlib.sha256(b"wheel bytes").hexdigest(), "method": "ZIP_STORED",
            "source": {"kind": "zip_member", "path": str(source), "member": "original/a.whl",
                       "size_bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns,
                       "archive_sha256": bundle.digest(source)}}]}
        output = self.root / "kit.zip"
        bundle.build(plan, output, reserve=0, progress=lambda _: None)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(archive.read("NOX_UNIFIED/wheels/a.whl"), b"wheel bytes")
        self.assertFalse((self.root / "original").exists())

    def test_wrong_member_hash_does_not_publish(self):
        plan = self.plan()
        plan["entries"][0]["sha256"] = "0" * 64
        output = self.root / "kit.zip"
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            bundle.build(plan, output, reserve=0, progress=lambda _: None)
        self.assertFalse(output.exists())
        self.assertTrue(Path(str(output) + ".partial").exists())

    def test_reserve_holds_before_creating_archive(self):
        plan = self.plan()
        output = self.root / "kit.zip"
        with patch.object(bundle.shutil, "disk_usage", return_value=type("Disk", (), {"free": 100})()):
            with self.assertRaises(OSError):
                bundle.build(plan, output, reserve=8 * 1024**3)
        self.assertFalse(Path(str(output) + ".partial").exists())

    def test_path_traversal_and_overwrite_refused(self):
        plan = self.plan()
        plan["entries"][0]["archive_path"] = "NOX_UNIFIED/../../bad"
        with self.assertRaises(ValueError):
            bundle.preflight(plan, self.root / "kit.zip", reserve=0)
        plan = self.plan()
        output = self.root / "existing.zip"
        output.write_bytes(b"owner data")
        with self.assertRaises(FileExistsError):
            bundle.preflight(plan, output, reserve=0)
        self.assertEqual(output.read_bytes(), b"owner data")

    def test_coordination_refresh_adds_latest_launch_profile(self):
        plan = self.plan()
        coordination = self.root / "coordination"
        coordination.mkdir()
        (coordination / "LAUNCH_QUEUE_RU.md").write_text("current launch queue")
        (coordination / "system_runtime_profile.json").write_text('{"version":28}')
        refreshed = bundle.refresh_coordination(plan, coordination)
        names = {x["archive_path"] for x in refreshed["entries"]}
        self.assertIn("NOX_UNIFIED/02_program/LAUNCH_QUEUE_RU.md", names)
        self.assertIn("NOX_UNIFIED/05_runtime_design/system_runtime_profile.json", names)
        self.assertEqual(len(plan["entries"]), 1)


if __name__ == "__main__":
    unittest.main()
