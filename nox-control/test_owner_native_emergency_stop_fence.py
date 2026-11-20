"""Source-only regressions for the emergency STOP drain and request fence."""
from __future__ import annotations

import configparser
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest


SOURCE = Path(__file__).with_name("owner_native_emergency_stop.py")
REPO = SOURCE.parents[1]
SPEC = importlib.util.spec_from_file_location("owner_native_emergency_stop", SOURCE)
E = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(E)


class EmergencyStopFenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        state = self.root / "state"
        dispatcher = state / "dispatcher"
        dispatcher.mkdir(parents=True)
        self.lock_path = state / "owner_maintenance.lock"
        self.lock_path.write_bytes(b"")
        self.lock_path.chmod(0o600)
        self.state_path = dispatcher / "state.json"
        self.write_tasks({})
        E.ROOT = self.root
        E.STOP = self.root / "STOP"
        E.MAINTENANCE = state / "OWNER_MAINTENANCE.flag"
        E.LOCK = self.lock_path
        E.DISPATCHER_STATE = self.state_path
        E.OWNER_UID = os.geteuid()
        E.root_directory = lambda path: path.stat()
        E.PHASE = {key: False for key in E.PHASE}
        E.MARKERS = {}
        E.DRAIN_POLL_SECONDS = 0.002

    def tearDown(self):
        self.tmp.cleanup()

    def write_tasks(self, tasks):
        self.state_path = getattr(self, "state_path", self.root / "state/dispatcher/state.json")
        self.state_path.write_text(json.dumps({"tasks": tasks}, sort_keys=True))
        self.state_path.chmod(0o600)

    def arm_fence(self, request=501, source="a" * 40):
        fd = E.acquire_lock(fcntl.LOCK_SH, phase_key="shared_drain_lock")
        try:
            fence = E.ensure_owner_fence(request, source)
            E.verify_request_fence(request, source, fence)
            return fence
        finally:
            E.release_lock(fd, "shared_drain_lock")

    def test_dispatcher_shared_lease_drains_before_exclusive_owner_lock(self):
        self.write_tasks({
            "done-1": {"id": "done-1", "status": "done", "owner_claim": {"nonce": "old"}},
            "pending-1": {"id": "pending-1", "status": "pending"},
        })
        fence = self.arm_fence()
        dispatcher_fd = os.open(self.lock_path, os.O_RDONLY)
        fcntl.flock(dispatcher_fd, fcntl.LOCK_SH)
        observed_fence = []

        def release_dispatcher_lease():
            time.sleep(0.04)
            E.verify_request_fence(501, "a" * 40, fence)
            observed_fence.append(True)
            fcntl.flock(dispatcher_fd, fcntl.LOCK_UN)
            os.close(dispatcher_fd)

        release_thread = threading.Thread(target=release_dispatcher_lease)
        release_thread.start()
        owner_fd, drain = E.wait_for_drain_and_exclusive_lock(
            501, "a" * 40, fence, timeout=0.5)
        try:
            self.assertEqual(drain["active_claim_count"], 0)
            self.assertTrue(observed_fence)
            self.assertTrue(E.PHASE["claims_terminal"])
            contender = os.open(self.lock_path, os.O_RDONLY)
            try:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(contender, fcntl.LOCK_SH | fcntl.LOCK_NB)
            finally:
                os.close(contender)
        finally:
            E.release_lock(owner_fd, "owner_lock")
            release_thread.join(timeout=1)

    def test_running_or_claimed_task_holds_without_owner_lock(self):
        self.write_tasks({
            "active": {"id": "active", "status": "running",
                       "owner_claim": {"pid": 4321, "nonce": "claim"}},
            "pending": {"id": "pending", "status": "pending"},
        })
        fence = self.arm_fence()
        with self.assertRaisesRegex(RuntimeError, "ACTIVE_CLAIMS_DRAIN_TIMEOUT"):
            E.wait_for_drain_and_exclusive_lock(501, "a" * 40, fence, timeout=0.02)
        self.assertTrue(self.lock_path.exists())
        self.assertTrue(E.STOP.exists())
        self.assertTrue(E.MAINTENANCE.exists())

    def test_terminal_claims_do_not_override_held_shared_owner_lease(self):
        self.write_tasks({"done": {"id": "done", "status": "done"}})
        fence = self.arm_fence()
        dispatcher_fd = os.open(self.lock_path, os.O_RDONLY)
        fcntl.flock(dispatcher_fd, fcntl.LOCK_SH)
        try:
            with self.assertRaisesRegex(RuntimeError, "OWNER_LOCK_BUSY_TIMEOUT"):
                E.wait_for_drain_and_exclusive_lock(501, "a" * 40, fence, timeout=0.02)
        finally:
            fcntl.flock(dispatcher_fd, fcntl.LOCK_UN)
            os.close(dispatcher_fd)

    def test_fence_cleanup_requires_verified_success_and_request_cas(self):
        fence = self.arm_fence()
        with self.assertRaisesRegex(RuntimeError, "FENCE_CLEANUP_BEFORE_SUCCESS"):
            E.remove_request_fence_after_success(501, "a" * 40, fence,
                                                 verified_success=False)
        self.assertTrue(E.STOP.exists())
        removed = E.remove_request_fence_after_success(
            501, "a" * 40, fence, verified_success=True)
        self.assertTrue(removed["STOP"]["removed"])
        self.assertTrue(removed["MAINTENANCE"]["removed"])
        self.assertFalse(E.STOP.exists())
        self.assertFalse(E.MAINTENANCE.exists())

    def test_foreign_replacement_is_never_deleted(self):
        fence = self.arm_fence()
        E.STOP.write_text("foreign owner request\n")
        with self.assertRaisesRegex(RuntimeError, "FENCE_CLEANUP_CONTENT_CHANGED"):
            E.remove_request_fence_after_success(501, "a" * 40, fence,
                                                 verified_success=True)
        self.assertEqual(E.STOP.read_text(), "foreign owner request\n")

    def test_main_supervisor_config_inline_semicolon_comment_contract(self):
        # PR #580 aligned this exact parser with Supervisor's ';' inline-comment
        # syntax after the read-only owner route rejected the configured socket.
        source = SOURCE.read_text()
        self.assertIn(
            'inline_comment_prefixes=(";",)',
            source,
        )
        parser = configparser.ConfigParser(
            interpolation=None, strict=True, inline_comment_prefixes=(";",))
        parser.read_string(
            "[unix_http_server]\n"
            "file=/run/supervisor.sock ; unix RPC socket\n"
            "chmod=0600 ; private mode\n"
            "[rpcinterface:supervisor]\n"
            "supervisor.rpcinterface_factory=supervisor.rpcinterface:make_main_rpcinterface ; fixed RPC factory\n"
            "[supervisorctl]\n"
            "serverurl=unix:///run/supervisor.sock ; matching endpoint\n"
            "[include]\n"
            "files=/etc/supervisor/conf.d/*.conf ; pinned include glob\n"
        )
        self.assertEqual(parser.get("unix_http_server", "file"),
                         "/run/supervisor.sock")
        self.assertEqual(parser.get("unix_http_server", "chmod"), "0600")
        self.assertEqual(parser.get("supervisorctl", "serverurl"),
                         "unix:///run/supervisor.sock")
        self.assertEqual(parser.get("include", "files"),
                         "/etc/supervisor/conf.d/*.conf")

    def test_owner_route_points_to_the_exact_reviewed_emergency_source(self):
        operator = (REPO / "nox-control/owner_native_operator.py").read_text()
        workflow = (REPO / ".github/workflows/nox-owner-maintenance-command.yml").read_text()
        self.assertEqual(E.SOURCE_BASELINE_GIT_BLOB,
                         "30517fa6b03457fabdcf8a3b402d7fbc790ee826")
        self.assertIn("'emergency_stop': 'nox-control/owner_native_emergency_stop.py'",
                      operator)
        self.assertIn("emergency_stop_preflight|emergency_stop|deploy", workflow)
        self.assertIn("nox-control/owner_native_'+a+'.py", workflow)
        self.assertIn('"stop", SUPERVISOR_SERVICE', SOURCE.read_text())


if __name__ == "__main__":
    unittest.main()
