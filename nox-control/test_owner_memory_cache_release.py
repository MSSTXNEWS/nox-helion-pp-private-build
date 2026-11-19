import ast
import contextlib
import hashlib
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import owner_memory_cleanup_entry as cleanup
import owner_storage_reclaim as storage


def process_census(used=()):
    return {"complete": True, "used": set(used), "active_package_manager": False}


def memory_sample(current, *, oom=0):
    return {
        "memory_bytes": current, "limit_bytes": 12 * 1024**3,
        "inactive_file_bytes": 6 * 1024**3, "shmem_bytes": 1024**3,
        "anon_bytes": 1024**3, "memory_psi": {"some": {"avg10": 0.0}},
        "events": {"oom": oom, "oom_kill": 0},
    }


class CacheReleaseTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        logs = self.root / "logs"
        logs.mkdir()
        self.path = logs / "native-debug.log.1"
        self.bytes = os.urandom(8 * 1024**2)
        with self.path.open("wb") as stream:
            stream.write(self.bytes)
            stream.flush()
            os.fsync(stream.fileno())
        self.info = self.path.stat()
        self.now = self.info.st_ctime + 3601
        self.enterContext(patch.object(storage, "ROOT", self.root))
        self.enterContext(patch.object(cleanup, "ROOT", self.root))

    def candidate(self):
        candidate, reason = storage.qualify(
            self.path, self.info, self.now, process_census(), cache_only=True
        )
        self.assertIsNone(reason)
        return candidate

    @contextlib.contextmanager
    def local_fixture(self, usage=None):
        # Test workspace has a world-writable ancestor. Keep production's
        # stronger directory walk unchanged and scope this FD to the fixture.
        with (
            patch.object(storage, "open_parent",
                         side_effect=lambda path: os.open(path.parent, os.O_DIRECTORY)),
            patch.object(storage, "process_usage",
                         return_value=usage if usage is not None else process_census()),
            patch.object(cleanup.time, "time", return_value=self.now),
        ):
            yield

    def test_advice_only_rotated_log_does_not_enter_deletion_allowlist(self):
        self.assertEqual(self.candidate()["category"], "INACTIVE_DEBUG_LOG_ROTATION")
        self.assertIsNone(storage.deletion_kind(self.path))

    def test_protected_and_active_file_categories_are_not_candidates(self):
        for path in (
            self.path.with_name("chat-memory.log.1"),
            self.path.with_name("native-debug.log"),
            self.path.with_name("core.8820"),
            self.root / "models" / "native-debug.log.1",
            self.root / "logs" / "checkpoints" / "native-debug.log.1",
            Path("/dev/shm/native-debug.log.1"),
        ):
            with self.subTest(path=path):
                self.assertIsNone(storage.cache_advice_kind(path))

    def test_actual_page_release_keeps_inode_size_and_hash(self):
        candidate = self.candidate()
        with self.local_fixture():
            result = cleanup.advise_candidate(storage, candidate, time.monotonic() + 4, len(self.bytes))
        self.assertGreater(result["observed_residency_reduction_bytes"], 0, result)
        self.assertEqual(storage.identity(self.path.stat()), candidate["identity"])
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).digest(),
                         hashlib.sha256(self.bytes).digest())
        print(f"Measured file page-cache reduction: {result['observed_residency_reduction_bytes']} bytes")

    def test_open_or_mapped_inode_vetoes_advice(self):
        candidate = self.candidate()
        use = process_census({(self.info.st_dev, self.info.st_ino)})
        with self.local_fixture(use), patch.object(os, "posix_fadvise") as advise:
            with self.assertRaisesRegex(RuntimeError, "FILE_IN_USE_OR_CHANGED"):
                cleanup.advise_candidate(storage, candidate, time.monotonic() + 4, len(self.bytes))
            advise.assert_not_called()

    def test_stop_marker_vetoes_advice(self):
        candidate = self.candidate()
        (self.root / "STOP").symlink_to(self.root / "missing")
        with self.local_fixture(), patch.object(os, "posix_fadvise") as advise:
            with self.assertRaisesRegex(RuntimeError, "HOLD_MEMORY_OWNER_STOP"):
                cleanup.advise_candidate(storage, candidate, time.monotonic() + 4, len(self.bytes))
            advise.assert_not_called()

    def test_tmpfs_descriptor_is_rejected(self):
        with tempfile.TemporaryFile(dir="/dev/shm") as stream:
            with self.assertRaisesRegex(RuntimeError, "FILE_NOT_ON_ALLOWLISTED_DISK_FILESYSTEM"):
                cleanup.require_disk_filesystem(stream.fileno())

    def test_positive_oom_delta_stops_the_batch(self):
        audit = {"process_scan": {"complete": True},
                 "cache_advice_candidates": [self.candidate(), self.candidate()]}
        governor = SimpleNamespace(sample=Mock(side_effect=[
            memory_sample(12 * 1024**3 - 64 * 1024**2),
            memory_sample(12 * 1024**3 - 128 * 1024**2, oom=1),
            memory_sample(12 * 1024**3 - 128 * 1024**2, oom=1),
        ]))
        result = {"attempted_range_bytes": 4096, "observed_residency_reduction_bytes": 4096}
        with (
            patch.object(storage, "reclaim_locks", side_effect=contextlib.nullcontext),
            patch.object(cleanup, "advise_candidate", return_value=result) as advise,
        ):
            receipt = cleanup.release_candidates(storage, governor, audit)
        advise.assert_called_once()
        self.assertEqual(receipt["page_cache_residency_reduction_bytes"], 4096)
        self.assertEqual(receipt["after"]["oom"], 1)
        self.assertTrue(receipt["cgroup_delta_includes_other_processes"])

    def test_zero_candidates_never_claims_page_recovery(self):
        audit = {"process_scan": {"complete": True}, "cache_advice_candidates": []}
        governor = SimpleNamespace(sample=Mock(return_value=memory_sample(11 * 1024**3)))
        with (
            patch.object(storage, "reclaim_locks", side_effect=contextlib.nullcontext),
            patch.object(cleanup, "advise_candidate") as advise,
        ):
            receipt = cleanup.release_candidates(storage, governor, audit)
        advise.assert_not_called()
        self.assertEqual(receipt["state"], "NO_ELIGIBLE_FILE_CACHE_RANGES")
        self.assertEqual(receipt["page_cache_residency_reduction_bytes"], 0)

    def test_five_gib_headroom_allows_a_bounded_batch(self):
        audit = {"process_scan": {"complete": True},
                 "cache_advice_candidates": [self.candidate()]}
        governor = SimpleNamespace(sample=Mock(return_value=memory_sample(7 * 1024**3)))
        with (
            patch.object(storage, "reclaim_locks", side_effect=contextlib.nullcontext),
            patch.object(cleanup, "advise_candidate", return_value={"attempted_range_bytes": 4096})
            as advise,
        ):
            receipt = cleanup.release_candidates(storage, governor, audit)
        advise.assert_called_once()
        self.assertEqual(receipt["target_headroom_bytes"], 8 * 1024**3)
        self.assertEqual(receipt["maximum_advice_range_bytes"], 2 * 1024**3)

    def test_eight_gib_headroom_avoids_unnecessary_advice(self):
        audit = {"process_scan": {"complete": True},
                 "cache_advice_candidates": [self.candidate()]}
        governor = SimpleNamespace(sample=Mock(return_value=memory_sample(4 * 1024**3)))
        with (
            patch.object(storage, "reclaim_locks", side_effect=contextlib.nullcontext),
            patch.object(cleanup, "advise_candidate") as advise,
        ):
            receipt = cleanup.release_candidates(storage, governor, audit)
        advise.assert_not_called()
        self.assertEqual(receipt["state"], "REQUESTED_CGROUP_HEADROOM_PRESENT")

    def test_owner_entry_does_not_invoke_any_data_deletion_path(self):
        tree = ast.parse(Path(cleanup.__file__).read_bytes())
        banned = {"reclaim", "unlink", "remove", "rmtree", "truncate", "kill"}
        by_name = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        for name in ("advise_candidate", "release_candidates"):
            calls = {
                node.func.attr for node in ast.walk(by_name[name])
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            }
            self.assertFalse(banned & calls)
        runner = by_name["go"]
        calls = [
            node for node in ast.walk(runner)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr in banned
        ]
        self.assertEqual(len(calls), 2)
        self.assertEqual(
            {ast.unparse(node.func) for node in calls},
            {"staged.unlink", "govern_path.unlink"},
        )


if __name__ == "__main__":
    unittest.main()
