"""NOX bounded native deployment: self-contained no-loss regression tests."""
import importlib.util
import base64
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import hashlib

path=Path(__file__).with_name("owner_native_lifeline.py")
spec=importlib.util.spec_from_file_location("owner_native_lifeline",path)
n=importlib.util.module_from_spec(spec);spec.loader.exec_module(n)

class InstallerTests(unittest.TestCase):
    def test_existing_mismatch_is_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"config";p.write_bytes(b"original")
            with self.assertRaisesRegex(RuntimeError,"HOLD_LIFELINE_EXISTING_FILE_CONFLICT"):
                n.preserve_or_write(p,b"other",0o600)
            self.assertEqual(p.read_bytes(),b"original")
    def test_matching_existing_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"same";p.write_bytes(b"same")
            self.assertFalse(n.preserve_or_write(p,b"same",0o600))
    def test_new_atomic_write(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"new";self.assertTrue(n.preserve_or_write(p,b"safe",0o600))
            self.assertEqual(p.read_bytes(),b"safe")
            self.assertEqual(p.stat().st_mode & 0o777,0o600)
    def test_concurrent_regular_file_or_dangling_link_never_replaced(self):
        # No-clobber publication must survive a competing owner creating the
        # destination AFTER initial path preflight but BEFORE atomic link.
        import os
        real_link = os.link
        for kind in ("file", "dangling_symlink"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as d:
                target = Path(d) / "owner-lifeline.conf"
                def competing_link(src, dst, **kwargs):
                    if kind == "file":
                        Path(dst).write_bytes(b"other-owner-config")
                    else:
                        Path(dst).symlink_to("missing-owner-config")
                    return real_link(src, dst, **kwargs)
                with patch.object(n.os, "link", side_effect=competing_link):
                    with self.assertRaisesRegex(RuntimeError,
                                                "HOLD_LIFELINE_CONCURRENT_FILE_CREATE"):
                        n.preserve_or_write(target, b"my-config", 0o600)
                if kind == "file":
                    self.assertEqual(target.read_bytes(), b"other-owner-config")
                else:
                    self.assertTrue(target.is_symlink())
                    self.assertEqual(os.readlink(target), "missing-owner-config")
                self.assertEqual(sorted(p.name for p in Path(d).iterdir()),
                                 ["owner-lifeline.conf"])

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);origin=root/"old";origin.write_bytes(b"keep")
            link=root/"link";link.symlink_to(origin)
            with self.assertRaisesRegex(RuntimeError,"HOLD_LIFELINE_PATH_SYMLINK"):
                n.preserve_or_write(link,b"replace",0o600)
            self.assertEqual(origin.read_bytes(),b"keep")
    def test_bundle_hash_and_limit(self):
        content=b"verified source value"
        n.BUNDLE={"nox_native_lifeline.py":{"content":base64.b64encode(content).decode(),
                      "sha256":hashlib.sha256(content).hexdigest()}}
        self.assertEqual(n.bytes_checked("nox_native_lifeline.py"),content)
        n.BUNDLE["nox_native_lifeline.py"]["sha256"]="0"*64
        with self.assertRaisesRegex(RuntimeError,"HOLD_LIFELINE_BUNDLE_DIGEST"):
            n.bytes_checked("nox_native_lifeline.py")
    def test_observer_can_stage_during_known_outage_without_restarting_anything(self):
        sample = {name: {"state": "RUNNING", "pid": 100 + i}
                  for i, name in enumerate(n.REQUIRED)}
        sample["nox-selfheal"] = {"state": "STOPPED", "pid": None}
        self.assertEqual(n.validate_baseline(sample), sample)
        self.assertEqual(sample["nox-selfheal"]["state"], "STOPPED")

    def test_observer_fails_closed_on_unknown_fatal_or_contradictory_service(self):
        good = {name: {"state": "RUNNING", "pid": 100 + i}
                for i, name in enumerate(n.REQUIRED)}
        for state, pid in (("UNKNOWN", None), ("FATAL", None),
                           ("STOPPED", 999), ("RUNNING", None)):
            snapshot = {k: dict(v) for k, v in good.items()}
            snapshot["nox-priority-scheduler"] = {"state": state, "pid": pid}
            with self.subTest(state=state, pid=pid):
                with self.assertRaisesRegex(RuntimeError, "HOLD_LIFELINE_CRITICAL_SERVICE_IDENTITY_UNSAFE"):
                    n.validate_baseline(snapshot)

    def test_supervisor_nonzero_rc_fail_closed_even_with_running_stdout(self):
        for state in ("RUNNING pid 901", "STOPPED"):
            with self.subTest(state=state), patch.object(
                n, "call", return_value=SimpleNamespace(
                    stdout=f"nox-dispatcher-t855u {state}\n", returncode=1
                )
            ):
                self.assertEqual(n.info("nox-dispatcher-t855u"),
                                 {"state": "UNKNOWN", "pid": None})

    def test_supervisor_contradictory_or_unknown_state_fail_closed(self):
        for line in ("RUNNING", "STOPPED pid 11", "EXITED pid 22",
                     "FATAL", "RUNNING pid 0"):
            with self.subTest(line=line), patch.object(
                n, "call", return_value=SimpleNamespace(
                    stdout=f"nox-dispatcher-t855u {line}\n", returncode=0
                )
            ):
                self.assertEqual(n.info("nox-dispatcher-t855u"),
                                 {"state": "UNKNOWN", "pid": None})

    def test_idempotent_lifeline_requires_exact_complete_existing_bundle(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            expected = tuple((root / name, content) for name, content in
                             (("guard.py", b"read-only"), ("policy.json", b"disabled"),
                              ("guard.conf", b"supervisor")))
            self.assertFalse(n.check_existing_installation(expected))
            expected[0][0].write_bytes(expected[0][1])
            with self.assertRaisesRegex(RuntimeError, "PARTIAL_INSTALL"):
                n.check_existing_installation(expected)
            for path, data in expected[1:]:
                path.write_bytes(data)
            self.assertTrue(n.check_existing_installation(expected))
            expected[2][0].write_bytes(b"other-owner-policy")
            with self.assertRaisesRegex(RuntimeError, "EXISTING_INSTALL_SOURCE_MISMATCH"):
                n.check_existing_installation(expected)
            self.assertEqual(expected[2][0].read_bytes(), b"other-owner-policy")

    def test_existing_mismatch_reports_hashes_not_private_contents(self):
        with tempfile.TemporaryDirectory() as d:
            files = [(Path(d) / n, b"expected") for n in ("script.py", "policy.json", "guard.conf")]
            for path, raw in files:
                path.write_bytes(raw)
            files[1][0].write_bytes(b"very-private-different-policy")
            with patch.object(n, "emit") as emit:
                with self.assertRaisesRegex(RuntimeError, "EXISTING_INSTALL_SOURCE_MISMATCH"):
                    n.check_existing_installation(files)
                report = emit.call_args.args[0]
                self.assertEqual(report["state"], "HOLD_EXISTING_LIFELINE_DIFF")
                self.assertTrue(report["changes_not_applied"])
                self.assertEqual([x["name"] for x in report["existing_source_fingerprints_only"]],
                                 ["policy.json"])
                self.assertNotIn("very-private", str(report))
                self.assertEqual(files[1][0].read_bytes(), b"very-private-different-policy")

    def test_exact_legacy_script_upgrade_preserves_prior_file_until_backup(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"nox_native_lifeline.py"
            old=b"known-old-source"
            new=b"reviewed-new-source"
            p.write_bytes(old)
            with self.assertRaisesRegex(RuntimeError,"HOLD_LIFELINE_LEGACY_SCRIPT_CHANGED"):
                n.replace_script_exact(p,b"not-old",new)
            self.assertEqual(p.read_bytes(),old)
            self.assertTrue(n.replace_script_exact(p,old,new))
            self.assertEqual(p.read_bytes(),new)
            self.assertEqual(p.stat().st_mode & 0o777,0o644)

    def test_failed_migration_rolls_back_only_with_stopped_guard(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"nox_native_lifeline.py"
            b=Path(d)/"backup.py"
            old=b"known-owned-baseline"
            new=b"verified-new-source"
            p.write_bytes(new)
            b.write_bytes(old)
            with patch.object(n,"SCRIPT",p), patch.object(n,"MIGRATED_SCRIPT_BACKUP",b), \
                 patch.object(n,"MIGRATED_SCRIPT_NEW_SHA",hashlib.sha256(new).hexdigest()), \
                 patch.object(n,"LEGACY_LIFELINE_SHA256",hashlib.sha256(old).hexdigest()), \
                 patch.object(n,"info",return_value={"state":"STOPPED","pid":None}), patch.object(n,"emit") as emit:
                n.recover_legacy_script()
                self.assertEqual(p.read_bytes(),old)
                self.assertTrue(emit.called)
            p.write_bytes(new)
            with patch.object(n,"SCRIPT",p), patch.object(n,"MIGRATED_SCRIPT_BACKUP",b), \
                 patch.object(n,"MIGRATED_SCRIPT_NEW_SHA",hashlib.sha256(new).hexdigest()), \
                 patch.object(n,"LEGACY_LIFELINE_SHA256",hashlib.sha256(old).hexdigest()), \
                 patch.object(n,"info",return_value={"state":"RUNNING","pid":22}):
                with self.assertRaisesRegex(RuntimeError,"HOLD_LIFELINE_LEGACY_ROLLBACK_GUARD_ACTIVE"):
                    n.recover_legacy_script()
                self.assertEqual(p.read_bytes(),new)

    def test_supervisor_rc3_exact_stopped_row_is_native_valid(self):
        for state in ("STOPPED", "EXITED"):
            with self.subTest(state=state), patch.object(n, "call", return_value=SimpleNamespace(
                stdout=f"nox-dispatcher-t855u {state} Not started\\n", returncode=3)):
                self.assertEqual(n.info("nox-dispatcher-t855u"),
                                 {"state": state, "pid": None})

    def test_supervisor_rc3_never_admits_running_error_or_pid(self):
        for row in ("RUNNING pid 999", "FATAL", "STOPPED pid 99",
                    "EXITED pid 10", "STOPPED Not started\\nevil RUNNING pid 12"):
            with self.subTest(row=row), patch.object(n, "call", return_value=SimpleNamespace(
                    stdout="nox-dispatcher-t855u " + row + "\\n", returncode=3)):
                self.assertEqual(n.info("nox-dispatcher-t855u"),
                                 {"state": "UNKNOWN", "pid": None})

    def test_supervisor_valid_rows_preserved(self):
        for state, tail, expected_pid in (
            ("RUNNING", "pid 321", 321),
            ("STOPPED", "", None),
            ("EXITED", "", None),
        ):
            with self.subTest(state=state), patch.object(
                n, "call", return_value=SimpleNamespace(
                    stdout=f"nox-dispatcher-t855u {state} {tail}\n", returncode=0
                )
            ):
                self.assertEqual(n.info("nox-dispatcher-t855u"),
                                 {"state": state, "pid": expected_pid})

    def test_wrong_supervisor_identity_rejected(self):
        with patch.object(n,"call",return_value=SimpleNamespace(stdout="evil RUNNING pid 1\n",returncode=0)):
            self.assertEqual(n.info("nox-dispatcher-t855u")["state"],"UNKNOWN")

if __name__=="__main__":unittest.main()
