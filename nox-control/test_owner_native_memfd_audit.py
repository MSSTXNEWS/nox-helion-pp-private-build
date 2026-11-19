from __future__ import annotations

import ast
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

import owner_native_memfd_audit as audit
import owner_native_operator as operator

FIXTURE_INODE = 131095


def write_proc(root: Path, pid: int, *, argv: bytes,
               ticks: int = 12345, memfd: Path | None = None,
               maps: bool = False, exe_path: str = "/usr/bin/python3") -> Path:
    base = root / str(pid)
    (base / "fd").mkdir(parents=True)
    fields = ["S", "1", "1"] + ["0"] * 16 + [str(ticks)]
    (base / "stat").write_text(f"{pid} (python3) " + " ".join(fields) + "\n")
    (base / "cmdline").write_bytes(argv)
    (base / "cgroup").write_text("0::/user.slice/nox.scope\n")
    (base / "exe").symlink_to(exe_path)
    (base / "cwd").symlink_to("/relocated/engram-holder")
    if memfd is not None:
        (base / "fd" / "9").symlink_to(memfd)
        info = memfd.stat()
        major, minor = os.major(info.st_dev), os.minor(info.st_dev)
        maps_text = ("00400000-00401000 r--s 00000000 "
                     f"{major:02x}:{minor:02x} {info.st_ino} "
                     f"/{audit.MEMFD_LABEL}\n")
    else:
        maps_text = ""
    (base / "maps").write_text(maps_text if maps else "")
    return base


def make_memfd_fixture(root: Path) -> Path:
    path = root / audit.MEMFD_LABEL
    with path.open("wb") as stream:
        stream.truncate(audit.MEMFD_SIZE)
    return path


def holder_argv(path: str = "/moved/location/engram_memfd_holder.py") -> bytes:
    return b"/opt/venv/bin/python3\0" + path.encode() + b"\0"


class MemfdAuditTests(unittest.TestCase):
    def test_python_executable_basename_is_accepted_for_holder(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "proc"
            root.mkdir()
            write_proc(root, 777010, argv=holder_argv(), exe_path="/opt/python/bin/python")
            identity = audit.proc_identity(root, 777010)
        self.assertEqual(identity["pid"], 777010)
        self.assertEqual(identity["start_ticks"], 12345)

    def test_arbitrary_executable_basename_is_rejected_for_holder(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "proc"
            root.mkdir()
            write_proc(root, 777011, argv=holder_argv(), exe_path="/opt/bin/custom-runtime")
            with self.assertRaisesRegex(audit.Hold, "HOLD_HOLDER_EXECUTABLE_SHAPE"):
                audit.proc_identity(root, 777011)

    def test_safe_executable_basename_is_bounded_and_rejects_paths_or_unsafe_text(self):
        self.assertEqual(audit.safe_executable_basename("custom-runtime"), "custom-runtime")
        self.assertIsNone(audit.safe_executable_basename("/opt/bin/custom-runtime"))
        self.assertIsNone(audit.safe_executable_basename("bad name\nsecret"))
        self.assertIsNone(audit.safe_executable_basename("x" * 65))

    def test_executable_shape_receipt_contains_only_safe_basename(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "proc"
            root.mkdir()
            memfd = make_memfd_fixture(Path(temp))
            write_proc(root, 777012, argv=holder_argv(), memfd=memfd,
                       exe_path="/private/path/custom-runtime")
            with self.assertRaisesRegex(
                    audit.Hold, "HOLD_MEMFD_OWNER_SCRIPT_IDENTITY_UNVERIFIED") as raised:
                audit.run_audit(root)
        failure = raised.exception.diagnostics["candidate_identity_failures"][0]
        self.assertEqual(failure["failure_code"], "HOLD_HOLDER_EXECUTABLE_SHAPE")
        self.assertEqual(failure["executable_basename"], "custom-runtime")
        encoded = json.dumps(raised.exception.diagnostics, sort_keys=True)
        self.assertNotIn("/private/path", encoded)
        self.assertNotIn("custom-runtime\n", encoded)

    def test_holder_path_is_matched_by_basename(self):
        self.assertEqual(audit._script_path_token(holder_argv()),
                         b"/moved/location/engram_memfd_holder.py")
        self.assertIsNone(audit._script_path_token(b"python3\0other.py\0"))
        self.assertIsNone(audit._script_path_token(
            holder_argv() + b"/another/path/engram_memfd_holder.py\0"))

    def test_current_pid_is_discovered_by_fd_and_receipt_redacts_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "proc"
            root.mkdir()
            memfd = make_memfd_fixture(Path(temp))
            expected_inode = memfd.stat().st_ino
            holder_pid = 777777
            write_proc(root, holder_pid, argv=holder_argv(), memfd=memfd, maps=True)
            write_proc(root, 777778, argv=b"python3\0ordinary_worker.py\0")
            result = audit.run_audit(root)
            encoded = json.dumps(result, sort_keys=True)
        self.assertTrue(result["complete"])
        self.assertEqual(result["holder"]["pid"], holder_pid)
        self.assertEqual(result["holder"]["start_ticks"], 12345)
        self.assertEqual(result["memfd"]["inode"], expected_inode)
        self.assertEqual(result["scan_counters"]["script_basename_candidate_pids"], 1)
        self.assertEqual(result["scan_counters"]["fd_pids_scanned"], 2)
        self.assertNotIn("/moved/location", encoded)
        self.assertNotIn("engram_memfd_holder.py", encoded)
        self.assertNotIn(audit.MEMFD_LABEL, encoded)

    def test_complete_zero_fd_and_zero_maps_reports_no_reference(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "proc"
            root.mkdir()
            write_proc(root, 777001, argv=b"python3\0worker.py\0")
            result = audit.run_audit(root)
        self.assertTrue(result["complete"])
        self.assertEqual(result["state"], "NO_EXACT_MEMFD_REFERENCE_COMPLETE_CENSUS")
        self.assertEqual(result["fd_census"]["matching_owner_pid_count"], 0)
        self.assertEqual(result["maps_census"]["mapping_processes"], [])

    def test_maps_only_reference_without_fd_is_partial_and_reports_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "proc"
            root.mkdir()
            memfd = make_memfd_fixture(Path(temp))
            base = write_proc(root, 777002, argv=b"python3\0worker.py\0")
            info = memfd.stat()
            major, minor = os.major(info.st_dev), os.minor(info.st_dev)
            (base / "maps").write_text(
                "00400000-00401000 r--s 00000000 "
                f"{major:02x}:{minor:02x} {info.st_ino} /{audit.MEMFD_LABEL}\n")
            with self.assertRaisesRegex(audit.Hold,
                                        "HOLD_MEMFD_MAPS_FOUND_WITHOUT_FD_IDENTITY") as raised:
                audit.run_audit(root)
        mapping = raised.exception.diagnostics["maps_census"]["mapping_processes"][0]
        self.assertEqual(mapping["pid"], 777002)
        self.assertEqual(mapping["mappings"][0]["inode"], info.st_ino)
        self.assertEqual(mapping["mapping_count"], 1)

    def test_two_exact_fd_owners_are_ambiguous(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "proc"
            root.mkdir()
            memfd = make_memfd_fixture(Path(temp))
            write_proc(root, 777003, argv=holder_argv(), memfd=memfd)
            write_proc(root, 777004, argv=holder_argv("/new/path/engram_memfd_holder.py"),
                       memfd=memfd)
            with self.assertRaisesRegex(audit.Hold, "HOLD_MEMFD_OWNER_PID_AMBIGUOUS"):
                audit.run_audit(root)
        self.assertEqual(audit.LAST_SCAN["exact_fd_owner_pids"], 2)

    def test_candidate_identity_failure_receipt_is_sanitized_and_binds_stable_fd(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "proc"
            root.mkdir()
            memfd = make_memfd_fixture(Path(temp))
            memfd_stat = memfd.stat()
            write_proc(root, 777007, argv=holder_argv(), memfd=memfd)
            secret_error = PermissionError("private /root/path and raw argv")
            with mock.patch.object(audit, "proc_identity", side_effect=secret_error):
                with self.assertRaisesRegex(
                        audit.Hold, "HOLD_MEMFD_OWNER_SCRIPT_IDENTITY_UNVERIFIED") as raised:
                    audit.run_audit(root)
        diagnostics = raised.exception.diagnostics
        failure = diagnostics["candidate_identity_failures"][0]
        self.assertEqual(failure["pid"], 777007)
        self.assertEqual(failure["start_ticks"], 12345)
        self.assertEqual(failure["exact_fd_count"], 1)
        self.assertEqual(failure["device"], memfd_stat.st_dev)
        self.assertEqual(failure["inode"], memfd_stat.st_ino)
        self.assertEqual(failure["failure_code"], "HOLD_HOLDER_IDENTITY_UNREADABLE")
        encoded = json.dumps(diagnostics, sort_keys=True)
        self.assertNotIn("private", encoded)
        self.assertNotIn("/root/path", encoded)
        self.assertNotIn("raw argv", encoded)

    def test_candidate_hold_code_is_allowlisted_and_global_read_errors_are_separate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "proc"
            root.mkdir()
            memfd = make_memfd_fixture(Path(temp))
            write_proc(root, 777008, argv=holder_argv(), memfd=memfd)
            write_proc(root, 777009, argv=b"python3\0ordinary_worker.py\0")
            original = audit._read

            def unreadable_other_pid(path, limit):
                if path.parent.name == "777009" and path.name == "stat":
                    raise PermissionError("do not disclose this text")
                return original(path, limit)

            with mock.patch.object(audit, "_read", side_effect=unreadable_other_pid), \
                 mock.patch.object(audit, "proc_identity",
                                   side_effect=audit.Hold("HOLD_HOLDER_SCRIPT_SHAPE")):
                with self.assertRaisesRegex(
                        audit.Hold, "HOLD_MEMFD_OWNER_SCRIPT_IDENTITY_UNVERIFIED") as raised:
                    audit.run_audit(root)
        diagnostics = raised.exception.diagnostics
        self.assertEqual(diagnostics["global_identity_unreadable_pids"], 1)
        failure = diagnostics["candidate_identity_failures"][0]
        self.assertEqual(failure["failure_code"], "HOLD_HOLDER_SCRIPT_SHAPE")
        self.assertNotIn("do not disclose", json.dumps(diagnostics))

    def test_fd_and_maps_limits_are_partial_with_counters(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "proc"
            root.mkdir()
            memfd = make_memfd_fixture(Path(temp))
            write_proc(root, 777005, argv=holder_argv(), memfd=memfd, maps=True)
            with mock.patch.object(audit, "MAX_FD_ENTRIES_TOTAL", 0):
                with self.assertRaisesRegex(audit.Hold, "HOLD_CENSUS_LIMIT"):
                    audit.run_audit(root)
            self.assertTrue(audit.LAST_SCAN["limits_hit"])
            with mock.patch.object(audit, "MAX_MAPS_BYTES_TOTAL", 1):
                with self.assertRaisesRegex(audit.Hold, "HOLD_MAPS_CENSUS_TRUNCATED"):
                    audit.run_audit(root)
        self.assertTrue(audit.LAST_SCAN["maps_truncated"])

    def test_unreadable_cmdline_still_gets_fd_scanned_and_holds_partial(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "proc"
            root.mkdir()
            write_proc(root, 777006, argv=b"python3\0worker.py\0")
            original = audit._read

            def unreadable_holder_cmdline(path, limit):
                if path.name == "cmdline":
                    raise PermissionError("fixture")
                return original(path, limit)

            with mock.patch.object(audit, "_read", side_effect=unreadable_holder_cmdline):
                with self.assertRaisesRegex(audit.Hold, "HOLD_GLOBAL_CENSUS_PARTIAL"):
                    audit.run_audit(root)
        self.assertEqual(audit.LAST_SCAN["cmdline_unreadable_pids"], 1)
        self.assertEqual(audit.LAST_SCAN["fd_pids_scanned"], 1)

    def test_failure_receipt_exposes_counts_and_only_sanitized_diagnostics(self):
        output = io.StringIO()
        audit.LAST_SCAN = {"fd_pids_scanned": 4, "fd_unreadable_entries": 1,
                           "maps_truncated": True}
        with mock.patch.dict(os.environ, {"NOX_OWNER_SOURCE_SHA": "a" * 40,
                                          "NOX_OWNER_REQUEST_ID": "445"}), \
             mock.patch.object(audit.os, "geteuid", return_value=0), \
             mock.patch.object(audit, "run_audit",
                               side_effect=audit.Hold("HOLD_GLOBAL_CENSUS_PARTIAL",
                                                     {"candidate_category": "UNREADABLE"})), \
             redirect_stdout(output):
            result_code = audit.main()
        self.assertEqual(result_code, 2)
        receipt_line = output.getvalue().splitlines()[0]
        receipt = json.loads(receipt_line.split("=", 1)[1])
        self.assertFalse(receipt["complete"])
        self.assertTrue(receipt["partial"])
        self.assertEqual(receipt["scan_counters"]["fd_pids_scanned"], 4)
        self.assertEqual(receipt["diagnostics"], {"candidate_category": "UNREADABLE"})
        self.assertNotIn("/root/nox", receipt_line)

    def test_maps_identity_parser_binds_device_inode_and_exact_label(self):
        device = os.makedev(0, 1)
        inode = 987654
        raw = ("00400000-00401000 r--s 00000000 00:01 "
               f"{inode} /{audit.MEMFD_LABEL}\n").encode()
        rows, truncated, _ = audit._maps_memfd_rows(raw, device, inode)
        self.assertEqual(rows[0]["inode"], inode)
        self.assertEqual(rows[0]["device"], device)
        self.assertFalse(truncated)

    def test_maps_wrong_identity_and_oversize_line_fail_closed(self):
        raw = ("00400000-00401000 r--s 00000000 00:02 "
               f"{FIXTURE_INODE} /{audit.MEMFD_LABEL}\n").encode()
        with self.assertRaisesRegex(audit.Hold, "HOLD_MEMFD_MAP_IDENTITY_MISMATCH"):
            audit._maps_memfd_rows(raw, os.makedev(0, 1), FIXTURE_INODE)
        _rows, truncated, _ = audit._maps_memfd_rows(
            b"x" * 4097, None, None)
        self.assertTrue(truncated)

    def test_owner_operator_dispatches_exact_owner_action(self):
        self.assertEqual(operator.FILES["memfd_audit"],
                         "nox-control/owner_native_memfd_audit.py")

    def test_start_tick_parser_handles_parenthesis_in_comm(self):
        fields = ["S", "7", "8"] + ["0"] * 16 + ["456"]
        raw = ("123 (worker ) nested) " + " ".join(fields) + "\n").encode()
        self.assertEqual(audit._parse_start_ticks(raw, 123), 456)

    def test_source_has_no_remote_mutation_or_raw_path_export(self):
        tree = ast.parse(Path(audit.__file__).read_text())
        imported = {alias.name.split(".")[0]
                    for node in ast.walk(tree)
                    if isinstance(node, (ast.Import, ast.ImportFrom))
                    for alias in node.names}
        self.assertFalse(imported & {"subprocess", "socket", "xmlrpc"})
        calls = [node.func.attr if isinstance(node.func, ast.Attribute)
                 else node.func.id if isinstance(node.func, ast.Name) else ""
                 for node in ast.walk(tree) if isinstance(node, ast.Call)]
        self.assertFalse({"kill", "unlink", "write_text", "write_bytes", "system"} & set(calls))
        source = Path(audit.__file__).read_text().lower()
        self.assertNotIn("supervisorctl", source)
        self.assertNotIn("sigterm", source)


if __name__ == "__main__":
    unittest.main()
