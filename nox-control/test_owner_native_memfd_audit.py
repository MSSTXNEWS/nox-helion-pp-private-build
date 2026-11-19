from __future__ import annotations

import ast
import os
from pathlib import Path
import stat
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import owner_native_memfd_audit as audit
import owner_native_operator as operator

FIXTURE_INODE = 131095


class MemfdAuditTests(unittest.TestCase):
    def test_dynamic_script_candidate_does_not_require_historical_pid(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "731234").mkdir()
            (root / "731234" / "cmdline").write_bytes(
                b"/venv/bin/python3\0/root/nox/engram_ram/engram_memfd_holder.py\0")
            (root / "498569").mkdir()
            (root / "498569" / "cmdline").write_bytes(b"python3\0other.py\0")
            candidates, scanned, unreadable = audit.holder_script_candidates(root)
        self.assertEqual(candidates, [731234])
        self.assertEqual(scanned, 2)
        self.assertEqual(unreadable, 0)

    def test_maps_accepts_exact_memfd_label_with_optional_leading_slash(self):
        device = os.makedev(0, 1)
        for label in (audit.MEMFD_LABEL, "/" + audit.MEMFD_LABEL):
            raw = ("00400000-00401000 r--s 00000000 00:01 "
                   f"{FIXTURE_INODE} {label}\n").encode()
            rows, truncated, consumed = audit._maps_memfd_rows(raw, device, FIXTURE_INODE)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["path_kind"], "EXACT_ENGRAM_MEMFD")
            self.assertFalse(truncated)
            self.assertEqual(consumed, len(raw))

    def test_maps_bind_to_dynamically_discovered_inode(self):
        discovered_inode = 987654
        raw = ("00400000-00401000 r--s 00000000 00:01 "
               f"{discovered_inode} {audit.MEMFD_LABEL}\n").encode()
        rows, truncated, _ = audit._maps_memfd_rows(
            raw, os.makedev(0, 1), discovered_inode)
        self.assertEqual(len(rows), 1)
        self.assertFalse(truncated)

    def test_maps_same_label_with_wrong_inode_holds(self):
        raw = ("00400000-00401000 r--s 00000000 00:01 131096 "
               f"{audit.MEMFD_LABEL}\n").encode()
        with self.assertRaisesRegex(audit.Hold, "HOLD_MEMFD_MAP_IDENTITY_MISMATCH"):
            audit._maps_memfd_rows(raw, os.makedev(0, 1), FIXTURE_INODE)

    def test_maps_same_label_with_wrong_device_holds(self):
        raw = ("00400000-00401000 r--s 00000000 00:02 "
               f"{FIXTURE_INODE} {audit.MEMFD_LABEL}\n").encode()
        with self.assertRaisesRegex(audit.Hold, "HOLD_MEMFD_MAP_IDENTITY_MISMATCH"):
            audit._maps_memfd_rows(raw, os.makedev(0, 1), FIXTURE_INODE)

    def test_maps_exact_inode_with_unknown_label_holds(self):
        raw = ("00400000-00401000 r--s 00000000 00:01 "
               f"{FIXTURE_INODE} /unexpected-label\n").encode()
        with self.assertRaisesRegex(audit.Hold, "HOLD_MEMFD_MAP_LABEL_MISMATCH"):
            audit._maps_memfd_rows(raw, os.makedev(0, 1), FIXTURE_INODE)

    def test_maps_oversize_line_is_marked_truncated(self):
        rows, truncated, _ = audit._maps_memfd_rows(
            b"x" * 4097, os.makedev(0, 1), FIXTURE_INODE)
        self.assertEqual(rows, [])
        self.assertTrue(truncated)

    def test_fd_census_requires_exact_label_inode_size_and_regular_file(self):
        with tempfile.TemporaryDirectory() as temp:
            fd_dir = Path(temp) / "731234" / "fd"
            fd_dir.mkdir(parents=True)
            (fd_dir / "9").touch()
            identity = {"pid": 731234}
            fake_stat = SimpleNamespace(st_ino=FIXTURE_INODE,
                                        st_size=audit.MEMFD_SIZE,
                                        st_dev=os.makedev(0, 1),
                                        st_mode=stat.S_IFREG | 0o600)
            with mock.patch.object(audit.os, "readlink",
                                   return_value="/" + audit.MEMFD_LABEL), \
                 mock.patch.object(audit.os, "stat", return_value=fake_stat):
                result = audit.fd_memfd_identity(Path(temp), identity,
                                                 {"entries": 0, "bytes": 0})
        self.assertEqual(result["matching_fd_count"], 1)
        self.assertEqual(result["match"]["inode"], fake_stat.st_ino)
        self.assertNotIn("target", result["match"])

    def test_fd_census_accepts_duplicate_descriptors_for_one_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            fd_dir = Path(temp) / "731234" / "fd"
            fd_dir.mkdir(parents=True)
            (fd_dir / "9").touch()
            (fd_dir / "10").touch()
            fake_stat = SimpleNamespace(st_ino=FIXTURE_INODE, st_size=audit.MEMFD_SIZE,
                                        st_dev=os.makedev(0, 1),
                                        st_mode=stat.S_IFREG | 0o600)
            with mock.patch.object(audit.os, "readlink",
                                   return_value="/" + audit.MEMFD_LABEL), \
                 mock.patch.object(audit.os, "stat", return_value=fake_stat):
                result = audit.fd_memfd_identity(Path(temp), {"pid": 731234},
                                                 {"entries": 0, "bytes": 0})
        self.assertEqual(result["matching_fd_count"], 2)
        self.assertEqual(result["fd_numbers"], [9, 10])

    def test_fd_census_holds_on_two_dynamic_identities(self):
        with tempfile.TemporaryDirectory() as temp:
            fd_dir = Path(temp) / "731234" / "fd"
            fd_dir.mkdir(parents=True)
            (fd_dir / "9").touch()
            (fd_dir / "10").touch()
            first_stat = SimpleNamespace(st_ino=FIXTURE_INODE, st_size=audit.MEMFD_SIZE,
                                         st_dev=os.makedev(0, 1),
                                         st_mode=stat.S_IFREG | 0o600)
            second_stat = SimpleNamespace(st_ino=FIXTURE_INODE + 1,
                                          st_size=audit.MEMFD_SIZE,
                                          st_dev=os.makedev(0, 1),
                                          st_mode=stat.S_IFREG | 0o600)
            with mock.patch.object(audit.os, "readlink",
                                   return_value="/" + audit.MEMFD_LABEL), \
                 mock.patch.object(audit.os, "stat",
                                   side_effect=[first_stat, first_stat,
                                                second_stat, second_stat]):
                with self.assertRaisesRegex(audit.Hold, "HOLD_MEMFD_FD_IDENTITY_AMBIGUOUS"):
                    audit.fd_memfd_identity(Path(temp), {"pid": 731234},
                                            {"entries": 0, "bytes": 0})

    def test_fd_mismatch_is_a_hold(self):
        with tempfile.TemporaryDirectory() as temp:
            fd_dir = Path(temp) / "731234" / "fd"
            fd_dir.mkdir(parents=True)
            (fd_dir / "9").touch()
            fake_stat = SimpleNamespace(st_ino=FIXTURE_INODE + 1,
                                        st_size=audit.MEMFD_SIZE - 1,
                                        st_dev=os.makedev(0, 1),
                                        st_mode=stat.S_IFREG | 0o600)
            with mock.patch.object(audit.os, "readlink",
                                   return_value="/" + audit.MEMFD_LABEL), \
                 mock.patch.object(audit.os, "stat", return_value=fake_stat):
                with self.assertRaisesRegex(audit.Hold, "HOLD_MEMFD_FD_IDENTITY_MISMATCH"):
                    audit.fd_memfd_identity(Path(temp), {"pid": 731234},
                                            {"entries": 0, "bytes": 0})

    def test_fd_link_change_during_snapshot_holds(self):
        with tempfile.TemporaryDirectory() as temp:
            fd_dir = Path(temp) / "731234" / "fd"
            fd_dir.mkdir(parents=True)
            (fd_dir / "9").touch()
            fake_stat = SimpleNamespace(st_ino=FIXTURE_INODE, st_size=audit.MEMFD_SIZE,
                                        st_dev=os.makedev(0, 1),
                                        st_mode=stat.S_IFREG | 0o600)
            with mock.patch.object(audit.os, "readlink",
                                   side_effect=["/" + audit.MEMFD_LABEL,
                                                "/memfd:other (deleted)"]), \
                 mock.patch.object(audit.os, "stat", return_value=fake_stat):
                with self.assertRaisesRegex(audit.Hold, "HOLD_FD_IDENTITY_UNSTABLE"):
                    audit.fd_memfd_identity(Path(temp), {"pid": 731234},
                                            {"entries": 0, "bytes": 0})

    def test_fd_entry_limit_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            fd_dir = Path(temp) / "731234" / "fd"
            fd_dir.mkdir(parents=True)
            (fd_dir / "9").touch()
            (fd_dir / "10").touch()
            with mock.patch.object(audit, "MAX_FD_ENTRIES_PER_PID", 1), \
                 mock.patch.object(audit.os, "readlink", return_value="/not-a-memfd"):
                with self.assertRaisesRegex(audit.Hold, "HOLD_FD_CENSUS_LIMIT"):
                    audit.fd_memfd_identity(Path(temp), {"pid": 731234},
                                            {"entries": 0, "bytes": 0})

    def test_owner_operator_dispatches_dedicated_pinned_action(self):
        self.assertEqual(operator.FILES["memfd_audit"],
                         "nox-control/owner_native_memfd_audit.py")
        self.assertIn("memfd_audit", operator.FILES)

    def test_proc_start_tick_parser_handles_parenthesis_in_comm(self):
        raw = b"123 (worker ) nested) S 7 8 9 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 456\n"
        self.assertEqual(audit._parse_start_ticks(raw, 123), 456)

    def test_source_has_no_remote_mutation_or_supervisor_transport(self):
        tree = ast.parse(Path(audit.__file__).read_text())
        imported = {alias.name.split(".")[0]
                    for node in ast.walk(tree)
                    if isinstance(node, (ast.Import, ast.ImportFrom))
                    for alias in node.names}
        self.assertFalse(imported & {"subprocess", "socket", "xmlrpc"})
        calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    calls.append(node.func.attr)
                elif isinstance(node.func, ast.Name):
                    calls.append(node.func.id)
        self.assertFalse({"kill", "unlink", "write_text", "write_bytes", "system"} & set(calls))
        source = Path(audit.__file__).read_text().lower()
        self.assertNotIn("supervisorctl", source)
        self.assertNotIn("sigterm", source)


if __name__ == "__main__":
    unittest.main()
