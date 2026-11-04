"""Local source regression tests for independent E07. No installer executed."""
from pathlib import Path
import importlib.util
import json
import hashlib
import tempfile
import sqlite3
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

if __name__=='__main__':unittest.main()
