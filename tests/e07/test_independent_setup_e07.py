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
    def test_u05_e888_original_candidate_pins_do_not_replace_legacy(self):
        source = FILE.read_text(encoding="utf-8")
        case = source.split("def setup_lock_original(", 1)[1].split("def manifest_owner(", 1)[0]
        self.assertIn('frozen in ("legacy", "e888")', case)
        self.assertIn("e888941626191c17d19d372889b1f96842c15e1b", case)
        self.assertIn("96ff9b47ca12a21017374e527786eda8b8fbf2b0e62cc6cfea1f59182cc8e61b", case)
        self.assertIn("1af961a3937d930a5f4684dd1cc88890b81b1e1ec61abfcfa3e72b250ca12683", case)
        self.assertIn("expected_home_bytes = 99768", case)
        self.assertIn("expected_owned_files = 485", case)
        self.assertIn("expected_source = ORIGINAL_E06_SOURCE", case)
        self.assertIn("expected_setup_sha = ORIGINAL_E06_SETUP_SHA", case)
        self.assertIn("expected_home_bytes = 99762", case)
        with self.assertRaisesRegex(MOD.Hold, "E07_ORIGINAL_PIN_KIND_HOLD"):
            MOD.setup_lock_original(Path("none.exe"), Path("none"), frozen="unverified")
        workflow = (ROOT / ".github/workflows/nox-express-independent-e07-candidate.yml").read_text(encoding="utf-8")
        # Active independent E07 must use the physically verified frozen FULL
        # D02 producer. Historic originals remain source-pinned, not selected.
        self.assertIn("run-id: 41872700529", workflow)
        self.assertIn("name: nox-v16-e06-onehost-diagnostic-41872700529", workflow)
        self.assertIn("path: input-verified-834", workflow)
        self.assertNotIn("run-id: 41867828741", workflow)
        self.assertIn("--artifact-kind d02", workflow)
        self.assertIn('"original-e888"', source)
        self.assertIn('"original-30a"', source)

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
        got=MOD.classify_primary_button_names(["✦ CHAT","INSTALL","MODELS","LEARN","SETTINGS"])
        self.assertEqual(got["status"],"PASS")
        self.assertEqual(got["actions_invoked"],0)
        self.assertEqual(got["buttons_missing"],[])

    def test_uia_rejects_near_matches_missing_and_untrusted(self):
        got=MOD.classify_primary_button_names(["CHAT","INSTALL NOW","MODELS","LEARN","SETTINGS"])
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
                "LEARN", "SETTINGS"], "treeCount": 5, "treeScanned": 5,
                "targetTypes": [f"{name}|ControlType.Button|VISIBLE_ENABLED"
                                for name in MOD._UIA_MAIN_BUTTONS]}
        self.assertEqual(MOD.classify_primary_uia_evidence(good)["status"], "PASS")
        for bad in ({"treeCount": False, "treeScanned": 1, "targetTypes": []},
                    {"treeCount": 2, "treeScanned": 3, "targetTypes": []},
                    {"treeCount": 1, "treeScanned": 1,
                     "targetTypes": ["OTHER|ControlType.Text|VISIBLE_ENABLED"]}):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(MOD.Hold, "E07_UIA_DIAGNOSTIC_UNTRUSTED_HOLD"):
                    MOD.classify_primary_uia_evidence({**good, **bad})

    def test_u01_label_only_or_nonbutton_roles_cannot_fake_uia_pass(self):
        # Regress the old false-positive: five strings with zero physical Button
        # roles were erroneously promoted to a complete E07 UIA presence PASS.
        names = list(MOD._UIA_MAIN_BUTTONS)
        base = {"schema": "NOX-E07-UIA-V1", "labels": names,
                "treeCount": 16, "treeScanned": 16, "targetTypes": []}
        label_only = MOD.classify_primary_uia_evidence(base)
        self.assertEqual(label_only["status"], "HOLD")
        self.assertEqual(label_only["buttons_missing"], names)
        self.assertEqual(label_only["actions_invoked"], 0)
        bad_roles = [f"{name}|ControlType.Text|VISIBLE_ENABLED" for name in names]
        text_only = MOD.classify_primary_uia_evidence({**base, "targetTypes": bad_roles})
        self.assertEqual(text_only["status"], "HOLD")
        self.assertEqual(text_only["buttons_missing"], names)
        mixed = [f"{name}|ControlType.Button|VISIBLE_ENABLED" for name in names[:-1]]
        mixed.append(f"{names[-1]}|ControlType.Button|DISABLED")
        partial = MOD.classify_primary_uia_evidence({**base, "targetTypes": mixed})
        self.assertEqual(partial["status"], "HOLD")
        self.assertEqual(partial["buttons_missing"], ["SETTINGS"])
        # Real, role-qualified same-root witnesses still pass even if the
        # separate filtered-label enumeration races and returns no labels.
        positive = MOD.classify_primary_uia_evidence({
            **base, "labels": [],
            "targetTypes": [f"{name}|ControlType.Button|VISIBLE_ENABLED"
                            for name in names]})
        self.assertEqual(positive["status"], "PASS")
        self.assertEqual(positive["buttons_missing"], [])
        self.assertEqual(positive["actions_invoked"], 0)

    def test_u01_duplicate_primary_uia_button_roles_cannot_pass(self):
        # Five distinct names are not proof of five unambiguous controls.
        names = list(MOD._UIA_MAIN_BUTTONS)
        targets = [f"{name}|ControlType.Button|VISIBLE_ENABLED"
                   for name in names]
        base = {"schema": "NOX-E07-UIA-V1", "labels": names,
                "treeCount": 12, "treeScanned": 12, "targetTypes": targets}
        exact = MOD.classify_primary_uia_evidence(base)
        self.assertEqual(exact["status"], "PASS")
        self.assertEqual(exact["buttons_duplicate"], [])
        self.assertEqual(exact["actions_invoked"], 0)
        duplicate_install = MOD.classify_primary_uia_evidence({
            **base, "targetTypes": targets +
            ["INSTALL|ControlType.Button|VISIBLE_ENABLED"]})
        self.assertEqual(duplicate_install["status"], "HOLD")
        self.assertEqual(duplicate_install["buttons_missing"], [])
        self.assertEqual(duplicate_install["buttons_duplicate"], ["INSTALL"])
        self.assertEqual(duplicate_install["actions_invoked"], 0)
        duplicate_chat = MOD.classify_primary_uia_evidence({
            **base, "targetTypes": targets +
            ["CHAT|ControlType.Button|VISIBLE_ENABLED"]})
        self.assertEqual(duplicate_chat["status"], "HOLD")
        self.assertEqual(duplicate_chat["buttons_duplicate"], ["CHAT"])
        text_only = MOD.classify_primary_uia_evidence({
            **base, "targetTypes": targets +
            ["INSTALL|ControlType.Text|VISIBLE_ENABLED"]})
        self.assertEqual(text_only["status"], "PASS")
        self.assertEqual(text_only["buttons_duplicate"], [])

    def test_uia_windows_bound_read_only_and_offscreen_rejection(self):
        source=FILE.read_text(encoding="utf-8")
        for needle in ("FromHandle([IntPtr]","ControlType]::Button",
                       "$current.IsEnabled", "$current.IsOffscreen",
                       "$current.BoundingRectangle", "five_primary_buttons",
                       '"visual_e07": "HOLD"'):
            self.assertIn(needle,source)
        # Read-only button enumeration remains non-actuating. A separate, explicitly
        # gated CHAT-only UIA action probe is allowed to invoke, never E07 PASS.
        readonly=source.split("def observe_original_primary_buttons(",1)[1].split(
            "\ndef classify_chat_invoke_witness(",1)[0]
        self.assertNotIn("InvokePattern",readonly)
        action=source.split("def observe_chat_input(",1)[1].split(
            "\ndef original_wpf_hwnd(",1)[0]
        self.assertIn("InvokePattern",action)
        self.assertNotIn("MODELS",action.split('ps = r"""',1)[1].split('"""',1)[0])
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
                    MOD.installed_file_sha_locked(payload,root.resolve(strict=True),7,
                        hashlib.sha256(b'payload').hexdigest())
            self.assertEqual(payload.read_bytes(),b'payload')


    def test_windows_fd_ctime_discrepancy_keeps_path_ctime_and_inode_guards(self):
        # Fixture based on actual Windows runner 41778686243: ONLY the
        # os.fstat creation/change-time view can differ from path.lstat.
        # File identity (dev/ino/size/mtime), pathname ctime and SHA remain pinned.
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            payload=root/'native.dll'
            raw=b'unchanged-installed-payload'
            payload.write_bytes(raw)
            real_fstat=MOD.os.fstat
            def biased_fd_stat(fd):
                original=real_fstat(fd)
                keys=('st_mode','st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')
                values={key:getattr(original,key) for key in keys}
                values['st_ctime_ns'] += 100000000
                return SimpleNamespace(**values)
            with patch.object(MOD.os,'fstat',side_effect=biased_fd_stat):
                got=MOD.installed_file_sha_locked(payload,root.resolve(strict=True),
                        len(raw),hashlib.sha256(raw).hexdigest())
            self.assertEqual(got,hashlib.sha256(raw).hexdigest())
            self.assertEqual(payload.read_bytes(),raw)

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
            scratch=home/"nox-e07-native-store"
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
            # Scope the synthetic fixture to the exact isolated runner temp.
            # Do not weaken the production junction, ancestor or path guards.
            with patch.dict(MOD.os.environ, {"RUNNER_TEMP": str(home)}):
                with patch.object(MOD.subprocess,"run",side_effect=run_fixture):
                    proof=MOD.native_store_stop_probe(backend,scratch)
            self.assertEqual(proof["status"],"PASS")
            self.assertEqual(proof["empty_history_restart"],"PASS")
            self.assertEqual(proof["history_restart"],"NOT_TESTED")
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
        self.assertEqual(MOD.SOURCE_SHA,"834c443de53fd2c214750ed3c868133b70648c42")
        self.assertEqual(MOD.SETUP_SHA,"4f78cd587e05bb1db49496a9a182225e8301bd5d84fee58a8022e9383a17c41e")
        self.assertEqual(MOD.SETUP_SIZE,169665062)
        self.assertEqual(MOD.E06_BUILD_ID,"NOX-V16-8a95972242fb9dc445f5fbe0")
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
        good["uninstall_owned_files_checked"] = 1007
        self.assertTrue(MOD.samevm_lifecycle_verified(good))
        for invalid in (None, False, 0, "1007", [], (),
                        {"uninstall_owned_files_checked": 1007},
                        {"uninstall_owned_files_checked": True}):
            with self.subTest(invalid=invalid):
                self.assertFalse(MOD.samevm_lifecycle_verified(invalid))
        for field, value in (("uninstall_owned_files_checked", 1006),
                             ("uninstall_owned_files_checked", "1007"),
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
        self.assertIn('stages["uninstall_owned_files_checked"] == expected_owned_files', source)
        self.assertNotIn('smoke.get("uninstall_owned_files_checked")', source)

    def test_u04_chat_input_witness_never_forges_route_or_model(self):
        candidate={"schema":"NOX-E07-CHAT-INPUT-v2","action":"CHAT",
                   "invoked":True,"sameHwndAlive":True,
                   "beforeChatHeading":False,"afterChatHeading":False}
        proof=MOD.classify_chat_invoke_witness(candidate)
        self.assertEqual(proof["actions_invoked"],1)
        self.assertEqual(proof["navigation_verified"],"NOT_TESTED")
        self.assertEqual(proof["visual_e07"],"HOLD")
        self.assertEqual(proof["model_inference"],"NOT_TESTED")
        for key,value in (("action","INSTALL"),("invoked",False),("invoked",1),
                          ("sameHwndAlive",False),("sameHwndAlive",1),
                          ("schema","NOX-E07-CHAT-INPUT-v1"),
                          ("beforeChatHeading",1),("afterChatHeading",1)):
            bad=dict(candidate);bad[key]=value
            with self.subTest(key=key,value=value):
                with self.assertRaisesRegex(MOD.Hold,"E07_CHAT_ACTION_UNTRUSTED_HOLD"):
                    MOD.classify_chat_invoke_witness(bad)
        with self.assertRaisesRegex(MOD.Hold,"E07_CHAT_ACTION_UNTRUSTED_HOLD"):
            MOD.classify_chat_invoke_witness(dict(candidate,navigation_verified="PASS"))

    def test_u04_chat_navigation_requires_new_visible_heading_from_same_hwnd(self):
        base={"schema":"NOX-E07-CHAT-INPUT-v2","action":"CHAT",
              "invoked":True,"sameHwndAlive":True,
              "beforeChatHeading":False,"afterChatHeading":False}
        unseen=MOD.classify_chat_invoke_witness(base)
        self.assertEqual(unseen["navigation_verified"],"NOT_TESTED")
        self.assertEqual(unseen["navigation_proof"],"NONE")
        preexisting=MOD.classify_chat_invoke_witness({**base,
                                                      "beforeChatHeading":True,
                                                      "afterChatHeading":True})
        self.assertEqual(preexisting["navigation_verified"],"NOT_TESTED")
        appeared=MOD.classify_chat_invoke_witness({**base,"afterChatHeading":True})
        self.assertEqual(appeared["navigation_verified"],"PASS")
        self.assertEqual(appeared["navigation_proof"],"NEW_VISIBLE_UIA_CHAT_HEADING")
        self.assertEqual(appeared["visual_e07"],"HOLD")
        self.assertEqual(appeared["model_inference"],"NOT_TESTED")
        self.assertEqual(appeared["actions_invoked"],1)
        source=FILE.read_text(encoding="utf-8")
        ps=source.split("def observe_chat_input(",1)[1].split(
            "\ndef original_wpf_hwnd(",1)[0]
        for needle in ("Test-ChatHeading $root", "$beforeHeading=Test-ChatHeading $root",
                       "$afterHeading=Test-ChatHeading $fresh",
                       "ControlType]::Text", "IsOffscreen", "sameHwndAlive=$alive"):
            self.assertIn(needle,ps)




    def test_u11_readonly_primary_navigation_requires_four_genuine_fresh_routes(self):
        labels = ("INSTALL", "MODELS", "LEARN", "SETTINGS")
        base = {"schema":"NOX-E07-PRIMARY-NAV-v2","actions":[
            {"action":name,"invoked":True,"sameHwndAlive":True,
             "beforeDestination":False,"afterDestination":True} for name in labels]}
        proof = MOD.classify_readonly_primary_navigation_witness(base)
        self.assertEqual(proof["status"],"OBSERVED")
        self.assertEqual(proof["actions_invoked"],4)
        self.assertEqual(proof["navigation_verified"],"PASS")
        self.assertEqual(proof["model_inference"],"NOT_TESTED")
        self.assertEqual(proof["visual_e07"],"HOLD")
        self.assertIs(proof["release_accepted"],False)
        # The physical witness MUST observe the actual original destination
        # as a VISIBLE screen plus a freshly FOCUSED existing control.
        # INSTALL/MODELS/LEARN may share R11's original CONTROL CENTER,
        # but focus the distinct approved buttons and never trigger mutation.
        wire=FILE.read_text(encoding="utf-8")
        for original in ("$headingVisible=($name -eq 'INSTALL')", "УСТАНОВИТЬ NOX",
                         "NOX · CONTROL CENTER", "МОДЕЛИ И КОМПОНЕНТЫ",
                         "ЗАПУСТИТЬ ОБУЧЕНИЕ", "СИСТЕМА",
                         "← НАЗАД В МЕНЮ", "$v.HasKeyboardFocus",
                         "Test-RealDestination $root $name",
                         "Test-RealDestination $fresh $name"):
            self.assertIn(original,wire)
        for index in range(4):
            for change in ({"afterDestination":False},{"beforeDestination":True},
                           {"invoked":False},{"sameHwndAlive":False}):
                actions=[dict(x) for x in base["actions"]]
                actions[index].update(change)
                actual=MOD.classify_readonly_primary_navigation_witness(
                    dict(base,actions=actions))
                self.assertEqual(actual["navigation_verified"],"HOLD")
                self.assertIs(actual["release_accepted"],False)
        for bad in (dict(base,schema="NOX-E07-PRIMARY-NAV-v0"),
                    dict(base,actions=base["actions"][:3]),
                    dict(base,actions=base["actions"]*2),
                    dict(base,actions=[dict(x,invoked=1) for x in base["actions"]]),
                    dict(base,actions=[dict(x,action="CHAT") for x in base["actions"]]),
                    dict(base,release_accepted=True)):
            with self.assertRaisesRegex(MOD.Hold,"E07_PRIMARY_NAV_"):
                MOD.classify_readonly_primary_navigation_witness(bad)

    def test_u11_safe_navigation_only_for_pinned_original_candidate(self):
        source = FILE.read_text(encoding="utf-8")
        self.assertIn('safe_nav=physical_nav or frozen_source == "e888941626191c17d19d372889b1f96842c15e1b"', source)
        self.assertIn('physical_nav=args.artifact_kind in ("original-30a", "d02")', source)
        guarded = source.split("def observe_readonly_primary_navigation(",1)[1].split(
            "\ndef original_wpf_hwnd(",1)[0]
        self.assertIn("InvokePattern",guarded)
        self.assertIn("Test-RealDestination",guarded)
        self.assertIn("Get-SameRoot",guarded)
        self.assertNotIn("models.pull",guarded)
        self.assertNotIn("training.start",guarded)
        self.assertNotIn("installer",guarded.lower())
        self.assertIn('"visual_e07": "HOLD"',source)


    def test_u09_native_inventory_scratch_fails_closed_before_onehost(self):
        # Source-level safety preflight; NEVER installed model / IPC / E07 PASS.
        with tempfile.TemporaryDirectory() as temp, patch.dict(
                MOD.os.environ, {"RUNNER_TEMP": temp}):
            root = Path(temp)
            backend = root / "backend.exe"
            backend.write_bytes(b"MZ-fake-test-only")
            scratch = root / "nox-e07-native-data"
            orig = getattr(Path, "is_junction", lambda unused: False)
            with patch.object(MOD.subprocess, "run",
                              side_effect=AssertionError("unsafe native launch")):
                with self.assertRaisesRegex(
                        MOD.Hold, "E07_NATIVE_INVENTORY_SCRATCH_COLLISION"):
                    MOD.framed_backend(backend, root / "unapproved-name")
                for blocked in (scratch, scratch.parent):
                    with self.subTest(blocked=str(blocked)):
                        with patch.object(Path, "is_junction",
                                          lambda path, blocked=blocked:
                                              path == blocked or orig(path),
                                          create=True):
                            with self.assertRaisesRegex(
                                    MOD.Hold, "E07_NATIVE_INVENTORY_SCRATCH_COLLISION"):
                                MOD.framed_backend(backend, scratch)
                scratch.mkdir()
                with self.assertRaisesRegex(
                        MOD.Hold, "E07_NATIVE_INVENTORY_SCRATCH_COLLISION"):
                    MOD.framed_backend(backend, scratch)
                scratch.rmdir()
            # Clean, exact, fresh runner slot reaches the REAL existing
            # subprocess route. Test double deliberately aborts before IPC.
            with patch.object(MOD.subprocess, "run",
                              side_effect=AssertionError("preflight admitted")):
                with self.assertRaisesRegex(AssertionError, "preflight admitted"):
                    MOD.framed_backend(backend, scratch)
        with tempfile.TemporaryDirectory() as temp, patch.dict(
                MOD.os.environ, {}, clear=True):
            backend = Path(temp) / "backend.exe"
            backend.write_bytes(b"MZ-fake-test-only")
            with self.assertRaisesRegex(
                    MOD.Hold, "E07_NATIVE_INVENTORY_SCRATCH_COLLISION"):
                MOD.framed_backend(backend, Path(temp) / "nox-e07-native-data")

    def test_u04_native_store_scratch_avoids_reparse_and_untrusted_paths(self):
        # Local preflight proof; NOT physical SQLite, model, IPC or E07 PASS.
        import os
        with tempfile.TemporaryDirectory() as temp, patch.dict(
                os.environ, {"RUNNER_TEMP":temp}):
            root=Path(temp)
            backend=root/"backend.exe"
            backend.write_bytes(b"MZ-fake-test-only")
            scratch=root/"nox-e07-native-store"
            orig=getattr(Path,"is_junction",lambda unused:False)
            for blocked in (scratch,scratch.parent):
                with self.subTest(blocked=str(blocked)):
                    with patch.object(Path,"is_junction",
                                      lambda path, blocked=blocked:
                                          path == blocked or orig(path),create=True):
                        with patch.object(MOD.subprocess,"run",
                                          side_effect=AssertionError("executed")):
                            with self.assertRaisesRegex(MOD.Hold,
                                                       "E07_NATIVE_STORE_SCRATCH_COLLISION"):
                                MOD.native_store_stop_probe(backend,scratch)
            with self.assertRaisesRegex(MOD.Hold,
                                       "E07_NATIVE_STORE_SCRATCH_COLLISION"):
                MOD.native_store_stop_probe(backend,root/"unapproved-name")
            scratch.mkdir()
            with self.assertRaisesRegex(MOD.Hold,
                                       "E07_NATIVE_STORE_SCRATCH_COLLISION"):
                MOD.native_store_stop_probe(backend,scratch)
            scratch.rmdir()
            with patch.object(MOD.subprocess,"run",
                              side_effect=AssertionError("past safe preflight")):
                with self.assertRaisesRegex(AssertionError,"past safe preflight"):
                    MOD.native_store_stop_probe(backend,scratch)
        with tempfile.TemporaryDirectory() as temp, patch.dict(
                os.environ, {},clear=True):
            backend=Path(temp)/"backend.exe"
            backend.write_bytes(b"MZ-fake-test-only")
            with self.assertRaisesRegex(MOD.Hold,
                                       "E07_NATIVE_STORE_SCRATCH_COLLISION"):
                MOD.native_store_stop_probe(backend,
                                            Path(temp)/"nox-e07-native-store")

if __name__=='__main__':unittest.main()
