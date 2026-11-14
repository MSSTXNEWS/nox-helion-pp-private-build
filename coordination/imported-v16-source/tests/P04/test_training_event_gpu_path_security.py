"""P04 real-module event/GPU lock path security regressions (no GPU or model)."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import types
import unittest
from unittest import mock

SOURCE = Path(__file__).resolve().parents[2] / "Packages" / "P04" / "train_qlora.py"
spec = importlib.util.spec_from_file_location("p04_event_gpu_paths", SOURCE)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class EventGpuPathSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def link(self, alias, target):
        try:
            alias.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not supported")

    def test_event_writer_keeps_resume_sequence(self):
        path = self.root / "safe" / "events.jsonl"
        writer = worker.EventWriter(path, "run1", "task1")
        writer.emit("task.started", "RUNNING", "start", "safe")
        worker.EventWriter(path, "run1", "task1").emit(
            "task.progress", "RUNNING", "step", "safe", 1, 2)
        rows = [json.loads(line) for line in path.read_text(encoding="utf8").splitlines()]
        self.assertEqual([x["event_sequence"] for x in rows], [1, 2])
        self.assertTrue(all(x["evidence_verified"] is False for x in rows))

    def test_grandparent_link_rejected_before_event_dir_creation(self):
        outside = self.root / "outside"
        outside.mkdir()
        self.link(self.root / "alias", outside)
        target = self.root / "alias" / "not-created" / "events.jsonl"
        with self.assertRaisesRegex(ValueError, "P04_PATH_REPARSE_ANCESTOR"):
            worker.EventWriter(target, "run1", "task1")
        self.assertFalse((outside / "not-created").exists())

    def test_event_emit_rechecks_after_grandparent_replacement(self):
        alias = self.root / "original"
        path = alias / "inner" / "events.jsonl"
        writer = worker.EventWriter(path, "run1", "task1")
        alias.rename(self.root / "relocated")
        outside = self.root / "outside"
        outside.mkdir()
        self.link(alias, outside)
        with self.assertRaisesRegex(ValueError, "P04_PATH_REPARSE_ANCESTOR"):
            writer.emit("task.started", "RUNNING", "start", "safe")
        self.assertFalse((outside / "inner").exists())

    def test_gpu_lock_works_then_refuses_second_worker(self):
        lock = self.root / "native" / "gpu-training.lock"
        fd = worker.acquire_gpu_lock(lock)
        try:
            self.assertTrue(lock.is_file())
            with self.assertRaisesRegex(RuntimeError, "GPU_TRAINING_QUEUE_BUSY"):
                worker.acquire_gpu_lock(lock)
        finally:
            os.close(fd)
            lock.unlink()

    def test_gpu_lock_grandparent_link_is_denied(self):
        outside = self.root / "outside"
        outside.mkdir()
        self.link(self.root / "alias", outside)
        lock = self.root / "alias" / "not-created" / "gpu.lock"
        with self.assertRaisesRegex(ValueError, "P04_PATH_REPARSE_ANCESTOR"):
            worker.acquire_gpu_lock(lock)
        self.assertFalse((outside / "not-created").exists())

    def test_windows_junction_reparse_attribute_is_denied(self):
        directory = self.root / "junction"
        directory.mkdir()
        real_lstat = Path.lstat
        flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        def fake_lstat(path, *args, **kwargs):
            if path == directory:
                return types.SimpleNamespace(st_mode=stat.S_IFDIR,
                                             st_file_attributes=flag)
            return real_lstat(path, *args, **kwargs)
        with mock.patch.object(worker.stat, "FILE_ATTRIBUTE_REPARSE_POINT",
                               flag, create=True):
            with mock.patch.object(Path, "lstat", fake_lstat):
                with self.assertRaisesRegex(ValueError, "P04_PATH_REPARSE_ANCESTOR"):
                    worker.reject_reparse_ancestors(directory / "not-created" / "events.jsonl")

    def test_unreadable_ancestor_rejected(self):
        directory = self.root / "unreadable"
        directory.mkdir()
        real_lstat = Path.lstat
        def fake_lstat(path, *args, **kwargs):
            if path == directory:
                raise PermissionError("synthetic")
            return real_lstat(path, *args, **kwargs)
        with mock.patch.object(Path, "lstat", fake_lstat):
            with self.assertRaisesRegex(ValueError, "P04_PATH_ANCESTOR_UNREADABLE"):
                worker.reject_reparse_ancestors(directory / "events.jsonl")

    def test_original_direct_event_symlink_still_fails(self):
        outside = self.root / "outside.txt"
        outside.write_text("untouched", encoding="utf8")
        link = self.root / "events.jsonl"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not supported")
        with self.assertRaises(ValueError):
            worker.EventWriter(link, "run1", "task1")
        self.assertEqual(outside.read_text(encoding="utf8"), "untouched")


if __name__ == "__main__":
    unittest.main()
