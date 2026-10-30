"""Offline P01 source regression. No actual browser, WinGet, deletion outside temp or Windows runner."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import p01_windows_owner_ports as m


class Tests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name)
        self.bookmarks = self.root / "Microsoft" / "Edge" / "User Data" / "Default" / "Bookmarks"
        self.bookmarks.parent.mkdir(parents=True)
        self.bookmarks.write_text(json.dumps({"roots": {"bookmark_bar": {"children": [
            {"name": "Example", "url": "https://example.org/info"},
            {"name": "Local", "url": "http://localhost/admin"}
        ]}}}), encoding="utf-8")
        self.cache = self.root / "NOX-HELION" / "cache"
        self.cache.mkdir(parents=True)
        (self.cache / ".nox-owner").write_bytes(b"NOXHELION.P01 V16\n")
        self.owned = self.cache / "nox-old.cache"
        self.owned.write_bytes(b"obsolete")
        now = time.time()
        os.utime(self.owned, (now - 90000, now - 90000))
        self.winget = self.root / "winget.exe"
        self.winget.write_bytes(b"trusted-test-stand-in-for-pinned-winget")
        self.plan = m.TrustedUpdatePlan(self.winget, hashlib.sha256(self.winget.read_bytes()).hexdigest(),
                                        "Microsoft.EdgeWebView2Runtime", frozenset({"Microsoft.EdgeWebView2Runtime"}))
        self.enabled, self.allowed, self.stopped = True, True, False
        self.mode = "inspect"
        self.url = "https://example.org/info"
        self.browser_calls, self.winget_calls = [], []
        def open_browser(url):
            self.browser_calls.append(url)
            return True
        def run_winget(argv, **kwargs):
            self.winget_calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0, "ok", "")
        self.port = m.P01WindowsOwnerPorts(
            native_permission=lambda _session, _route: self.allowed,
            native_stop=lambda: self.stopped,
            native_select_url=lambda _session: self.url,
            native_select_bookmarks=lambda _session: (self.root, self.bookmarks),
            native_select_update=lambda _session: self.plan,
            native_select_cache=lambda _session: (self.root, self.cache, self.mode),
            windows_ready=lambda: self.enabled,
            browser_open=open_browser, winget_run=run_winget)

    def test_browser_opens_only_native_https_and_never_claims_page_loaded(self):
        result = self.port.open_browser("trusted-session", {})
        self.assertEqual(self.browser_calls, ["https://example.org/info"])
        self.assertEqual(result["status"], "SYSTEM_BROWSER_OPEN_REQUESTED_NOT_PAGE_LOADED")
        self.assertIs(result["accepted"], False)

    def test_browser_blocks_local_private_and_untrusted_page_input(self):
        for url in ("http://example.org", "https://127.0.0.1/admin", "https://localhost", 
                    "https://10.2.3.4", "https://example.org:444/x", "https://u:p@example.org", "file:///tmp/x"):
            self.url = url
            with self.subTest(url=url), self.assertRaises(m.OwnerDenied):
                self.port.open_browser("trusted-session", {})
        self.assertEqual(self.browser_calls, [])
        with self.assertRaises(m.OwnerDenied):
            self.port.open_browser("trusted-session", {"url": "https://example.org"})

    def test_browser_native_consent_and_stop_revocation(self):
        self.allowed = False
        with self.assertRaises(m.OwnerDenied):
            self.port.open_browser("session", {})
        self.allowed = True
        self.stopped = True
        with self.assertRaises(m.OwnerHold):
            self.port.open_browser("session", {})
        self.assertEqual(self.browser_calls, [])

    def test_bookmarks_are_read_only_https_filtered_and_private(self):
        result = self.port.bookmarks("session", {})
        self.assertEqual(result["items"], [{"title": "Example", "url": "https://example.org/info"}])
        self.assertIs(result["accepted"], False)
        self.assertIn("LOCAL_BOOKMARKS_READ", result["status"])
        self.assertTrue(self.bookmarks.exists())

    def test_bookmarks_do_not_accept_native_selection_outside_browser_profile(self):
        other = self.root / "NOX-HELION" / "cache" / "Bookmarks"
        other.write_text("{}")
        self.port.select_bookmarks = lambda _: (self.root, other)
        with self.assertRaises(m.OwnerDenied):
            self.port.bookmarks("session", {})

    def test_bookmarks_duplicate_members_and_large_file_fail_closed(self):
        self.bookmarks.write_text('{"roots":{},"ROOTS":{}}')
        with self.assertRaises(m.OwnerHold):
            self.port.bookmarks("session", {})
        self.bookmarks.write_bytes(b"x" * (m.MAX_BOOKMARK_FILE + 1))
        with self.assertRaises(m.OwnerHold):
            self.port.bookmarks("session", {})

    def test_bookmarks_reject_symlink(self):
        other = self.root / "safe.json"
        other.write_text("{}")
        self.bookmarks.unlink()
        try: self.bookmarks.symlink_to(other)
        except OSError: self.skipTest("Host cannot create symlinks")
        with self.assertRaises(m.OwnerHold):
            self.port.bookmarks("session", {})

    def test_winget_reuses_pinned_binary_and_needs_version_attestation(self):
        result = self.port.update("session", {})
        self.assertEqual(len(self.winget_calls), 1)
        argv, kwargs = self.winget_calls[0]
        self.assertEqual(argv[:4], (str(self.winget), "upgrade", "--id", "Microsoft.EdgeWebView2Runtime"))
        self.assertIs(kwargs["shell"], False)
        self.assertIs(result["accepted"], False)

    def test_winget_hash_drift_and_unapproved_package_fail_closed(self):
        self.winget.write_bytes(b"changed")
        with self.assertRaises(m.OwnerHold):
            self.port.update("session", {})
        self.winget.write_bytes(b"trusted-test-stand-in-for-pinned-winget")
        self.plan = m.TrustedUpdatePlan(self.winget, self.plan.sha256, "unapproved.package", self.plan.approved_package_ids)
        with self.assertRaises(m.OwnerDenied):
            self.port.update("session", {})
        self.assertEqual(self.winget_calls, [])

    def test_native_update_permission_revoked_no_process(self):
        self.allowed = False
        with self.assertRaises(m.OwnerDenied):
            self.port.update("session", {})
        self.assertEqual(self.winget_calls, [])

    def test_pc_inspection_never_deletes_files(self):
        result = self.port.pc_control("session", {})
        self.assertEqual(result["eligibleFiles"], 1)
        self.assertEqual(result["eligibleBytes"], 8)
        self.assertTrue(self.owned.exists())

    def test_pc_cleanup_only_owned_aged_cache_and_not_arbitrary_files(self):
        unowned = self.cache / "personal-document.txt"
        unowned.write_text("user")
        too_new = self.cache / "nox-new.cache"
        too_new.write_bytes(b"recent")
        self.mode = "clean"
        result = self.port.pc_control("session", {})
        self.assertEqual(result["deletedFiles"], 1)
        self.assertEqual(result["reclaimedBytes"], 8)
        self.assertIs(result["accepted"], False)
        self.assertFalse(self.owned.exists())
        self.assertTrue(unowned.exists())
        self.assertTrue(too_new.exists())

    def test_pc_cleanup_requires_marker_and_new_native_consent(self):
        self.mode = "clean"
        (self.cache / ".nox-owner").write_bytes(b"wrong\n")
        with self.assertRaises(m.OwnerHold):
            self.port.pc_control("session", {})
        (self.cache / ".nox-owner").write_bytes(b"NOXHELION.P01 V16\n")
        self.allowed = False
        with self.assertRaises(m.OwnerDenied):
            self.port.pc_control("session", {})
        self.assertTrue(self.owned.exists())

    def test_pc_root_outside_nox_only_is_denied(self):
        other = self.root / "User Documents"
        other.mkdir()
        self.port.select_cache = lambda _: (self.root, other, "clean")
        with self.assertRaises(m.OwnerDenied):
            self.port.pc_control("session", {})

    def test_missing_windows_gate_and_web_page_payload_fail(self):
        self.enabled = False
        with self.assertRaises(m.OwnerHold):
            self.port.bookmarks("session", {})
        self.enabled = True
        for method in (self.port.bookmarks, self.port.open_browser, self.port.update, self.port.pc_control):
            with self.subTest(method=method.__name__), self.assertRaises(m.OwnerDenied):
                method("session", {"unsafe": "path"})

    def test_bookmark_read_detects_same_size_file_change(self):
        real_fstat = os.fstat
        calls = []
        def drifted_fstat(fd):
            current = real_fstat(fd)
            calls.append(current)
            if len(calls) != 2:
                return current
            # Deterministic mid-read metadata drift, without rewriting an
            # open file (Windows sharing modes may prohibit concurrent writes).
            return types.SimpleNamespace(st_mode=current.st_mode,
                st_dev=current.st_dev, st_ino=current.st_ino,
                st_size=current.st_size, st_mtime_ns=current.st_mtime_ns + 1,
                st_file_attributes=getattr(current, 'st_file_attributes', 0))
        with patch.object(m.os, 'fstat', side_effect=drifted_fstat):
            with self.assertRaises(m.OwnerHold):
                self.port.bookmarks('session', {})
        self.assertGreaterEqual(len(calls), 2)

    def test_pc_inspect_revoked_while_scanning_denied(self):
        def revoke_after_clock():
            self.allowed=False
            return time.time()
        self.port.clock=revoke_after_clock
        with self.assertRaises(m.OwnerDenied):
            self.port.pc_control("session", {})

    def test_browser_recheck_after_os_callback_revoked(self):
        def revoke_after_open(url):
            self.allowed=False
            self.browser_calls.append(url)
            return True
        self.port.browser_open=revoke_after_open
        with self.assertRaises(m.OwnerDenied):
            self.port.open_browser("session", {})
        self.assertEqual(self.browser_calls,["https://example.org/info"])

    def test_winget_stdstreams_are_bounded_not_captured(self):
        self.port.update("session", {})
        _, kwargs=self.winget_calls[0]
        self.assertIs(kwargs["stdin"], subprocess.DEVNULL)
        self.assertIs(kwargs["stdout"], subprocess.DEVNULL)
        self.assertIs(kwargs["stderr"], subprocess.DEVNULL)
        self.assertNotIn("capture_output", kwargs)

    def test_existing_single_host_atomic_binder_is_called_not_new_server(self):
        observed = []
        def bind(host, owner, provider, methods, *, receipt, probe):
            observed.append((host, owner, provider, methods, receipt, probe))
            return frozenset(methods)
        fake = types.SimpleNamespace(bind_owner_methods=bind)
        with patch.dict(sys.modules, {"native_bridge": fake}):
            h = object()
            bound = self.port.register(h, receipt="a" * 64)
        self.assertEqual(len(bound), 4)
        self.assertEqual(observed[0][0], h)
        self.assertEqual(observed[0][1], 1)
        self.assertEqual(observed[0][3], {
            "browser.open": "open_browser", "browser.bookmarks": "bookmarks",
            "system.update": "update", "system.pc_control": "pc_control"})
        self.assertTrue(callable(observed[0][-1]))

if __name__ == "__main__": unittest.main()
