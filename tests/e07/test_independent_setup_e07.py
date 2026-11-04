"""Local source regression tests for independent E07. No installer executed."""
from pathlib import Path
import importlib.util
import json
import hashlib
import tempfile
import sqlite3
import sys
from contextlib import closing
import struct
from unittest.mock import patch
import unittest

ROOT=Path(__file__).resolve().parents[2]
FILE=ROOT/'coordination/e07/independent_setup_e07.py'
SPEC=importlib.util.spec_from_file_location('nox_e07_independent',FILE)
MOD=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

class IndependentE07(unittest.TestCase):
    def test_fresh_webview_markers_require_exact_log_events(self):
        line = "[2026-11-04 05:00:00] INIT_BEGIN\n" + \
               "[2026-11-04 05:00:01] NAV_START\n" + \
               "[2026-11-04 05:00:02] NAV_OK\n" + \
               "[2026-11-04 05:00:03] P02_ORIGINAL_NATIVE_PIPE_HANDSHAKE_OK\n"
        flags = MOD.wpf_marker_flags(line)
        self.assertTrue(flags["NAV_OK"])
        self.assertTrue(flags["P02_ORIGINAL_NATIVE_PIPE_HANDSHAKE_OK"])
        self.assertFalse(any(flags[x] for x in MOD._WPF_FATAL))
    def test_unprefixed_or_embedded_nav_ok_not_admitted(self):
        invalid="NAV_OK\nnoise NAV_OK\n[2026] NOTE NAV_OK\n"
        self.assertFalse(MOD.wpf_marker_flags(invalid)["NAV_OK"])
        failed="[2026] NAV_OK\n[2026] NAV_FAIL SomeError\n"
        flags=MOD.wpf_marker_flags(failed)
        self.assertTrue(flags["NAV_FAIL"])
        self.assertTrue(any(flags[x] for x in MOD._WPF_FATAL))

    def test_exact_five_button_presence_is_not_click_acceptance(self):
        got=MOD.classify_primary_button_names(["✦ CHAT","INSTALL","MODELS","LEARN","REPORTS"])
        self.assertEqual(got["status"],"PASS")
        self.assertEqual(got["actions_invoked"],0)
        self.assertEqual(got["buttons_missing"],[])

    def test_uia_rejects_near_matches_missing_and_untrusted(self):
        got=MOD.classify_primary_button_names(["CHAT","INSTALL NOW","MODELS","LEARN","REPORTS"])
        self.assertEqual(got["status"],"HOLD")
        self.assertEqual(got["buttons_missing"],["INSTALL"])
        for invalid in ("CHAT INSTALL",["CHAT",object()]):
            with self.assertRaisesRegex(MOD.Hold,"E07_UIA_UNTRUSTED_LABELS"):
                MOD.classify_primary_button_names(invalid)

    def test_structural_uia_text_never_becomes_button_pass(self):
        evidence = MOD.classify_primary_uia_evidence({
            "schema": "NOX-E07-UIA-V1", "labels": [],
            "treeCount": 31, "treeScanned": 31,
            "targetTypes": ["CHAT|ControlType.Text|VISIBLE_ENABLED",
                            "MODELS|ControlType.Custom|VISIBLE_ENABLED"]})
        self.assertEqual(evidence["status"], "HOLD")
        self.assertEqual(evidence["buttons_missing"], list(MOD._UIA_MAIN_BUTTONS))
        self.assertEqual(evidence["actions_invoked"], 0)
        self.assertEqual(evidence["uia_tree_scanned"], 31)

    def test_structural_uia_schema_is_bounded_and_fail_closed(self):
        good = {"schema": "NOX-E07-UIA-V1", "labels": ["CHAT", "INSTALL", "MODELS",
                "LEARN", "REPORTS"], "treeCount": 5, "treeScanned": 5, "targetTypes": []}
        self.assertEqual(MOD.classify_primary_uia_evidence(good)["status"], "PASS")
        for bad in ({"treeCount": False, "treeScanned": 1, "targetTypes": []},
                    {"treeCount": 2, "treeScanned": 3, "targetTypes": []},
                    {"treeCount": 1, "treeScanned": 1,
                     "targetTypes": ["OTHER|ControlType.Text|VISIBLE_ENABLED"]}):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(MOD.Hold, "E07_UIA_DIAGNOSTIC_UNTRUSTED_HOLD"):
                    MOD.classify_primary_uia_evidence({**good, **bad})

    def test_uia_windows_bound_read_only_and_offscreen_rejection(self):
        source=FILE.read_text(encoding="utf-8")
        for needle in ("FromHandle([IntPtr]","ControlType]::Button",
                       "$current.IsEnabled", "$current.IsOffscreen",
                       "$current.BoundingRectangle", "five_primary_buttons",
                       '"visual_e07": "HOLD"'):
            self.assertIn(needle,source)
        self.assertNotIn("InvokePattern",source)
        with patch.object(MOD.sys,"platform","linux"):
            with self.assertRaisesRegex(MOD.Hold,"E07_UIA_NOT_WINDOWS_OR_BAD_HWND"):
                MOD.observe_original_primary_buttons(8)

    def test_sha_pins_and_candidate_only(self):
        self.assertRegex(MOD.SETUP_SHA,r'^[0-9a-f]{64}$')
        self.assertRegex(MOD.SOURCE_SHA,r'^[0-9a-f]{40}$')
        self.assertGreater(MOD.SETUP_SIZE,1048576)
        source=FILE.read_text(encoding='utf-8')
        self.assertIn('"release_accepted":False',source)
        self.assertIn('"independent_e07":"HOLD"',source)
    def test_missing_setup_cannot_be_accepted(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            with self.assertRaisesRegex(MOD.Hold,'E07_SOURCE_ARTIFACT_NOT_REGULAR'):
                MOD.setup_lock(root/'absent.exe',root/'absent.json')
    def test_manifest_rejects_traversal_without_deletion(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            (root/'nox-p01-owned.txt').write_text('NOXHELION.P01 V16\n')
            manifest={'schema':'NOX_P01_PAYLOAD_SHA256_V1','entrypoint':'NOX.P01.Shell.exe',
                      'files':[{'path':'../outside.dat','bytes':1,'sha256':'0'*64}]}
            (root/'payload.sha256.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(MOD.Hold,'E07_MANIFEST_UNSAFE_PATH'):
                MOD.manifest_owner(root)
            self.assertTrue((root/'payload.sha256.json').is_file())
    def test_manifest_verifies_real_hash(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            (root/'nox-p01-owned.txt').write_text('NOXHELION.P01 V16\n')
            data=b'legitimate-test-payload'
            (root/'entry.exe').write_bytes(data)
            manifest={'schema':'NOX_P01_PAYLOAD_SHA256_V1','entrypoint':'NOX.P01.Shell.exe',
                      'files':[{'path':'entry.exe','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}]}
            (root/'payload.sha256.json').write_text(json.dumps(manifest))
            _,files=MOD.manifest_owner(root)
            self.assertEqual(files,(root/'entry.exe',))

    def test_manifest_rejects_same_bytes_replacement_between_resolve_and_open(self):
        # Real temporary files: the previous pathname-only SHA loop accepted
        # this same-byte replacement without binding its inode/ctime.
        import os
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / 'nox-p01-owned.txt').write_text('NOXHELION.P01 V16' + chr(10))
            payload = root / 'entry.exe'
            original = b'owned-file-original-bytes'
            payload.write_bytes(original)
            manifest = {'schema':'NOX_P01_PAYLOAD_SHA256_V1',
                        'entrypoint':'NOX.P01.Shell.exe',
                        'files':[{'path':'entry.exe','bytes':len(original),
                                  'sha256':hashlib.sha256(original).hexdigest()}]}
            (root/'payload.sha256.json').write_text(json.dumps(manifest))
            real_open = MOD.os.open
            did_swap = []
            def replace_on_descriptor_open(path, flags, *args, **kwargs):
                if Path(path) == payload and not did_swap:
                    substitute = root/'same-bytes-other-inode.tmp'
                    substitute.write_bytes(original)
                    os.replace(substitute, payload)
                    did_swap.append(True)
                return real_open(path, flags, *args, **kwargs)
            with patch.object(MOD.os, 'open', side_effect=replace_on_descriptor_open):
                with self.assertRaisesRegex(MOD.Hold,
                                            'E07_INSTALLED_FILE_OPEN_IDENTITY_HOLD'):
                    MOD.manifest_owner(root)
            self.assertEqual(did_swap, [True])
            self.assertEqual(payload.read_bytes(), original)


    def test_installed_file_os_denial_remains_a_scoped_hold(self):
        import errno
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            payload=root/'native.dll'
            payload.write_bytes(b'payload')
            real_open=MOD.os.open
            def deny_only_payload(path,flags,*args,**kwargs):
                if Path(path)==payload:
                    raise PermissionError(errno.EACCES,'simulated access denied')
                return real_open(path,flags,*args,**kwargs)
            with patch.object(MOD.os,'open',side_effect=deny_only_payload):
                with self.assertRaisesRegex(MOD.Hold,
                                            'E07_INSTALLED_FILE_IO_13_HOLD'):
                    MOD.installed_file_sha_locked(payload,root,7,
                        hashlib.sha256(b'payload').hexdigest())
            self.assertEqual(payload.read_bytes(),b'payload')

    def test_manifest_detects_mutated_file(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            (root/'nox-p01-owned.txt').write_text('NOXHELION.P01 V16\n')
            (root/'entry.exe').write_bytes(b'x')
            manifest={'schema':'NOX_P01_PAYLOAD_SHA256_V1','entrypoint':'NOX.P01.Shell.exe',
                      'files':[{'path':'entry.exe','bytes':1,'sha256':'0'*64}]}
            (root/'payload.sha256.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(MOD.Hold,'E07_INSTALLED_FILE_SHA_HOLD'):
                MOD.manifest_owner(root)

    def test_uninstall_no_loss_preserves_unmanaged_install_data(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); install=root/"NOX HELION"; install.mkdir()
            witness=install/"unmanaged.txt"; witness.write_bytes(b"keep-me")
            MOD.verify_uninstall_no_loss(install,root/"stage",root/"previous",
                                          (install/"removed-owned.dll",),witness,b"keep-me")
            self.assertEqual(witness.read_bytes(),b"keep-me")

    def test_uninstall_no_loss_rejects_changed_or_deleted_unmanaged(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); install=root/"NOX HELION"; install.mkdir()
            witness=install/"unmanaged.txt"; witness.write_bytes(b"tampered")
            for _ in range(2):
                with self.assertRaisesRegex(MOD.Hold,"UNOWNED_DATA_LOSS_HOLD"):
                    MOD.verify_uninstall_no_loss(install,root/"stage",root/"previous",
                                                  (),witness,b"original")
                witness.unlink(missing_ok=True)

    def test_uninstall_no_loss_rejects_owned_residue(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); install=root/"NOX HELION"; install.mkdir()
            witness=install/"unmanaged.txt"; witness.write_bytes(b"keep")
            owned=install/"owned.dll"; owned.write_bytes(b"should-have-gone")
            with self.assertRaisesRegex(MOD.Hold,"OWNED_RESIDUE_HOLD"):
                MOD.verify_uninstall_no_loss(install,root/"stage",root/"previous",
                                              (owned,),witness,b"keep")

    def test_uninstall_no_loss_rejects_stage_and_previous_residue(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); install=root/"NOX HELION"; install.mkdir()
            witness=install/"unmanaged.txt"; witness.write_bytes(b"keep")
            for name in ("stage","previous"):
                stale=root/name; stale.mkdir()
                with self.assertRaisesRegex(MOD.Hold,"STAGE_OR_PREVIOUS_RESIDUE_HOLD"):
                    MOD.verify_uninstall_no_loss(install,root/"stage",root/"previous",
                                                  (),witness,b"keep")
                stale.rmdir()

    def test_independent_sqlite_stop_requires_actual_installed_native_exe(self):
        with tempfile.TemporaryDirectory() as t:
            home=Path(t)
            with self.assertRaisesRegex(MOD.Hold,"E07_NATIVE_STORE_EXE_MISSING"):
                MOD.native_store_stop_probe(home/"missing.exe",home/"isolated")

    def test_independent_sqlite_stop_source_mock_no_model_pass(self):
        # Synthetic protocol fixture: source test only, never Windows/E07 PASS.
        with tempfile.TemporaryDirectory() as t:
            home=Path(t)
            backend=home/"native.exe"
            backend.write_bytes(b"fixture-not-a-real-windows-binary")
            scratch=home/"isolated"
            calls=[]
            def run_fixture(args,**kwargs):
                wire=kwargs["input"]
                frame_bytes=struct.unpack(">I",wire[:4])[0]
                request=json.loads(wire[4:])
                self.assertEqual(frame_bytes,len(wire)-4)
                calls.append(request)
                if not scratch.exists():
                    scratch.mkdir()
                    with closing(sqlite3.connect(scratch/"helion.sqlite3")) as db:
                        db.execute("PRAGMA user_version=4")
                        db.execute("CREATE TABLE core_chat_turns (id INTEGER)")
                reply={"protocol":request["protocol"],"requestId":request["requestId"],
                       "runId":request["runId"],"status":"OK",
                       "result":{"messages":[]} if request["route"]=="chat.history"
                                else {"stopRequested":True}}
                data=json.dumps(reply).encode("utf-8")
                return type("MockCompletedProcess",(),{
                    "returncode":0,"stdout":struct.pack(">I",len(data))+data})()
            with patch.object(MOD.subprocess,"run",side_effect=run_fixture):
                proof=MOD.native_store_stop_probe(backend,scratch)
            self.assertEqual(proof["status"],"PASS")
            self.assertEqual(proof["active_stream_stop"],"NOT_TESTED")
            self.assertEqual(proof["real_model_inference"],"NOT_TESTED")
            self.assertEqual([v["route"] for v in calls],
                             ["chat.history","chat.history","chat.stop"])
            self.assertEqual(len({v["requestId"] for v in calls}),3)

    def test_original_wpf_witness_is_mandatory(self):
        with tempfile.TemporaryDirectory() as home:
            with patch.object(MOD, "_WPF_WITNESS_PATH", Path(home)/"missing.py"):
                with self.assertRaisesRegex(MOD.Hold, "E07_ORIGINAL_WPF_WITNESS_MISSING"):
                    MOD.original_wpf_hwnd(42)

    def test_original_wpf_witness_rejects_non_windows(self):
        if sys.platform != "win32":
            self.assertIsNone(MOD.original_wpf_hwnd(42))

    def test_gui_requires_original_wpf_class_not_generic_visible_pid(self):
        source=FILE.read_text(encoding="utf-8")
        self.assertIn("handle = original_wpf_hwnd(proc.pid)", source)
        self.assertIn("require(original_wpf_hwnd(proc.pid) == handle", source)
        self.assertNotIn("if pid.value == proc.pid and user32.IsWindowVisible(hwnd)", source)
        witness=(ROOT/"coordination/e06/t06_windows_hwnd_witness.py").read_text("utf-8")
        self.assertIn('_WPF_CLASS_PREFIX = "HwndWrapper["', witness)
        self.assertIn("_MIN_GUI_CLIENT_WIDTH = 160", witness)
        self.assertIn("_visible_window_for_pid(pid, user32, callback_type)", witness)


    def test_new_e06_setup_identity_and_receipt_rejects_duplicates(self):
        self.assertEqual(MOD.SOURCE_SHA,"c35c1d330b36900c61d41f65661c535dcd6fc78a")
        self.assertEqual(MOD.SETUP_SHA,"af87a6181dee5e04d2a83bc33e738aec16534fa32bc407b40c009ab169129879")
        self.assertEqual(MOD.SETUP_SIZE,169590852)
        self.assertEqual(MOD.E06_BUILD_ID,"NOX-V16-4a0070cdb51d1d2d37a8d295")
        with tempfile.TemporaryDirectory() as home:
            path=Path(home)/"E07_BUILT_HANDOFF.json"
            path.write_text('{"source_commit_sha1":"a","source_commit_sha1":"b"}')
            with self.assertRaisesRegex(MOD.Hold,"E07_E06_RECEIPT_DUPLICATE_FIELD"):
                MOD._read_locked_e06_json(path)
            path.write_text('{"value":NaN}')
            with self.assertRaisesRegex(MOD.Hold,"E07_E06_RECEIPT_NONFINITE_NUMBER"):
                MOD._read_locked_e06_json(path)

    def test_wrong_e06_receipt_holds_before_install(self):
        with tempfile.TemporaryDirectory() as home:
            root=Path(home)
            setup=root/"NOX-HELION-V16-DIAGNOSTIC-SETUP.exe"
            receipt=root/"E07_BUILT_HANDOFF.json"
            setup.write_bytes(b"MZdiagnostic-synthetic")
            receipt.write_text('{"schema":"invalid"}')
            with self.assertRaisesRegex(MOD.Hold,"E07_E06_RECEIPT_NOT_REGULAR"):
                MOD.setup_lock(setup,receipt)


    def test_e06_nested_lifecycle_malformed_receipt_is_a_clean_hold(self):
        # Source fixture only; does not assert Windows installation or release.
        good = {key: {"code": 0} for key in
                ("install", "verify", "update", "rollback", "uninstall")}
        good["uninstall_owned_files_checked"] = 1004
        self.assertTrue(MOD.samevm_lifecycle_verified(good))
        for invalid in (None, False, 0, "1004", [], (),
                        {"uninstall_owned_files_checked": 1004},
                        {"uninstall_owned_files_checked": True}):
            with self.subTest(invalid=invalid):
                self.assertFalse(MOD.samevm_lifecycle_verified(invalid))
        for field, value in (("uninstall_owned_files_checked", 1003),
                             ("uninstall_owned_files_checked", "1004"),
                             ("uninstall_owned_files_checked", True),
                             ("install", {"code": True}),
                             ("rollback", {}),
                             ("uninstall", None)):
            bad = dict(good)
            bad[field] = value
            with self.subTest(field=field, value=value):
                self.assertFalse(MOD.samevm_lifecycle_verified(bad))

    def test_smoke_owned_count_is_nested_in_installer_lifecycle(self):
        source = FILE.read_text(encoding="utf-8")
        self.assertIn('type(stages.get("uninstall_owned_files_checked")) is int', source)
        self.assertIn('stages["uninstall_owned_files_checked"] == 1004', source)
        self.assertNotIn('smoke.get("uninstall_owned_files_checked")', source)

if __name__=='__main__':unittest.main()
