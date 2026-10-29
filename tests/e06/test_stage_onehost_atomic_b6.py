"""B6: real temporary-filesystem fault injection; no Windows/runtime acceptance."""
import importlib.util
import pathlib
import tempfile
import unittest
from unittest.mock import patch

MODULE = pathlib.Path(__file__).resolve().parents[2] / "coordination/e06/stage_onehost.py"
spec = importlib.util.spec_from_file_location("b6_stage", MODULE)
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)


class AtomicStageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.original = self.root / "bridge.cs"
        self.addon = self.root / "addon.cs"
        self.receipt = self.root / "receipt.json"
        self.original.write_bytes(b"\xef\xbb\xbfold\r\n")
        self.before = self.original.read_bytes()
        self.lock = self.root / ".e06-stage.lock"

    def run_stage(self):
        stage.commit_stage(self.original, self.before, b"patched\n",
                           self.addon, b"addon", self.receipt, b'{"ok":true}\n')

    def assert_restored(self):
        self.assertEqual(self.original.read_bytes(), self.before)
        self.assertEqual({p.name for p in self.root.iterdir()}, {"bridge.cs"})

    def test_success_readback(self):
        self.run_stage()
        self.assertEqual(self.original.read_bytes(), b"patched\n")
        self.assertEqual(self.addon.read_bytes(), b"addon")
        self.assertEqual(self.receipt.read_bytes(), b'{"ok":true}\n')
        self.assertEqual(len(list(self.root.iterdir())), 3)

    def test_prepare_and_publish_fault_matrix(self):
        # Seven independent fail-once boundaries: four prepares, two links, rename.
        for boundary in range(7):
            with self.subTest(boundary=boundary):
                prepare, link, replace = stage._prepare, stage.os.link, stage.os.replace
                counter = [0]
                def fault(function):
                    def wrapped(*args, **kwargs):
                        n = counter[0]
                        counter[0] += 1
                        if n == boundary:
                            raise OSError("injected")
                        return function(*args, **kwargs)
                    return wrapped
                with patch.object(stage, "_prepare", fault(prepare)), \
                     patch.object(stage.os, "link", fault(link)), \
                     patch.object(stage.os, "replace", fault(replace)):
                    with self.assertRaises(OSError):
                        self.run_stage()
                self.assert_restored()

    def test_disk_write_failure_removes_partial_temporary(self):
        fsync = stage.os.fsync
        calls = [0]
        def fail(fd):
            calls[0] += 1
            if calls[0] == 2:
                raise OSError("disk-full-on-temp-flush")
            return fsync(fd)
        with patch.object(stage.os, "fsync", fail):
            with self.assertRaises(OSError):
                self.run_stage()
        self.assert_restored()

    def test_foreign_receipt_race_never_clobbered_or_deleted(self):
        link = stage.os.link
        def race(src, dst):
            if dst == self.receipt:
                self.receipt.write_bytes(b"foreign receipt")
            return link(src, dst)
        with patch.object(stage.os, "link", race):
            with self.assertRaises(FileExistsError):
                self.run_stage()
        self.assertEqual(self.receipt.read_bytes(), b"foreign receipt")
        self.assertEqual(self.original.read_bytes(), self.before)
        self.assertFalse(self.addon.exists())
        self.assertFalse(self.lock.exists())

    def test_foreign_bridge_after_publish_preserves_recovery(self):
        link = stage.os.link
        def race(src, dst):
            if dst == self.receipt:
                self.original.write_bytes(b"foreign bridge")
                raise OSError("receipt denied")
            return link(src, dst)
        with patch.object(stage.os, "link", race):
            with self.assertRaisesRegex(RuntimeError, "ROLLBACK_CONFLICT_HOLD"):
                self.run_stage()
        self.assertEqual(self.original.read_bytes(), b"foreign bridge")
        self.assertTrue(self.lock.exists())
        self.assertFalse(self.addon.exists())
        self.assertTrue(any(p.read_bytes() == self.before
                            for p in self.root.glob(".bridge.cs.e06-*")))

    def test_rollback_failure_preserves_recovery(self):
        link, replace = stage.os.link, stage.os.replace
        calls = [0]
        def fail_receipt(src, dst):
            if dst == self.receipt:
                raise OSError("receipt denied")
            return link(src, dst)
        def fail_rollback(src, dst):
            calls[0] += 1
            if calls[0] == 2:
                raise OSError("rollback denied")
            return replace(src, dst)
        with patch.object(stage.os, "link", fail_receipt), \
             patch.object(stage.os, "replace", fail_rollback):
            with self.assertRaisesRegex(RuntimeError, "ROLLBACK_CONFLICT_HOLD"):
                self.run_stage()
        self.assertTrue(self.lock.exists())
        self.assertTrue(any(p.read_bytes() == self.before
                            for p in self.root.glob(".bridge.cs.e06-*")))

    def test_existing_lock_rejects_second_writer(self):
        self.lock.write_bytes(b"foreign lock")
        with self.assertRaises(FileExistsError):
            self.run_stage()
        self.assertEqual(self.lock.read_bytes(), b"foreign lock")
        self.assertEqual(self.original.read_bytes(), self.before)

    def test_preimage_drift_after_prepare_no_clobber(self):
        prepare = stage._prepare
        calls = [0]
        def drift(path, raw):
            result = prepare(path, raw)
            calls[0] += 1
            if calls[0] == 4:
                self.original.write_bytes(b"foreign early")
            return result
        with patch.object(stage, "_prepare", drift):
            with self.assertRaisesRegex(RuntimeError, "PREIMAGE_SHA_HOLD"):
                self.run_stage()
        self.assertEqual(self.original.read_bytes(), b"foreign early")
        self.assertEqual({p.name for p in self.root.iterdir()}, {"bridge.cs"})


if __name__ == "__main__":
    unittest.main()
