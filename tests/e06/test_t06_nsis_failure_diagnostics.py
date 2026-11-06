"""Portable guard tests for NSIS diagnostics, not native installer acceptance."""
import importlib.util
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / 'coordination/e06/t06_nsis_failure_diagnostics.py'
spec = importlib.util.spec_from_file_location('nox_nsis_failure_diagnostic_test', MODULE)
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)


class PostmortemGuards(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.local = self.root / 'local'
        self.local.mkdir()
        self.stage = self.local / 'Programs/NOX HELION.__p01_stage'
        self.stage.mkdir(parents=True)
        (self.stage / 'payload.sha256.json').write_text('{}')
        self.verifier = self.root / 'stage/proposals/P01/C09/Installer/Verify-Payload.ps1'
        self.verifier.parent.mkdir(parents=True)
        self.verifier.write_bytes(b"'fixture, not executed'\n")
        self.failure = {'reason': 'T06_NSIS_SILENT_INSTALL_FAILED', 'phase': 'HOLD',
                        'release_accepted': False, 'setup_sha256': 'a'*64, 'build_id': 'fixture'}
        self.evidence = {'setup_sha256': 'a'*64, 'build_id': 'fixture'}
        self.calls = []
        def require(condition, code):
            if not condition:
                raise ValueError(code)
        def runner(args, timeout):
            self.calls.append((args, timeout))
            return {'code': 1, 'stdout_tail': '', 'stderr_tail': 'fixture verification error'}
        self.owner = types.SimpleNamespace(ROOT=self.root, OUTPUT=self.root,
            require=require, strict_receipt=lambda *args: dict(self.failure),
            candidate_gate=lambda: dict(self.evidence),
            plain_parents=lambda p, base: not p.is_symlink(),
            regular=lambda p: p.is_file() and not p.is_symlink(), run=runner)
        self.env = {'GITHUB_ACTIONS': 'true', 'RUNNER_OS': 'Windows',
            'NOX_E07_CI_WINDOWS_DISPOSABLE': 'YES', 'GITHUB_RUN_ID': '123',
            'LOCALAPPDATA': str(self.local), 'SystemRoot': str(self.root / 'Windows')}
        self.patch = patch.object(diag.subprocess, 'check_output', return_value=self.verifier.read_bytes())
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def collect(self):
        return diag.collect(self.owner, platform_name='win32', env=self.env)

    def test_only_reviewed_verifier_runs_and_failure_remains_failure(self):
        before = (self.stage / 'payload.sha256.json').read_bytes()
        report = self.collect()
        self.assertEqual(report['original_failure'], 'T06_NSIS_SILENT_INSTALL_FAILED')
        self.assertFalse(report['release_accepted'])
        self.assertEqual(report['phase'], 'DIAGNOSTIC_ONLY')
        self.assertEqual(report['verifications'][0]['code'], 1)
        self.assertEqual(len(self.calls), 1)
        argv, timeout = self.calls[0]
        self.assertEqual(argv[0], 'powershell.exe')
        self.assertEqual(argv[argv.index('-File')+1], str(self.verifier))
        self.assertNotIn('/S', argv)
        self.assertNotIn('-AllowInstalledMetadata', argv)
        self.assertEqual((self.stage / 'payload.sha256.json').read_bytes(), before)
        self.assertEqual(timeout, 100)

    def test_requires_explicit_disposable_windows_environment(self):
        for key in ('GITHUB_ACTIONS', 'RUNNER_OS', 'NOX_E07_CI_WINDOWS_DISPOSABLE', 'GITHUB_RUN_ID'):
            with self.subTest(key=key):
                env = dict(self.env)
                env.pop(key)
                with self.assertRaisesRegex(ValueError, 'DISPOSABLE_WINDOWS_ONLY'):
                    diag.collect(self.owner, platform_name='win32', env=env)
        with self.assertRaisesRegex(ValueError, 'DISPOSABLE_WINDOWS_ONLY'):
            diag.collect(self.owner, platform_name='linux', env=self.env)
        self.assertEqual(self.calls, [])

    def test_mismatched_failure_does_not_execute_anything(self):
        self.failure['reason'] = 'OTHER_FAILURE'
        with self.assertRaisesRegex(ValueError, 'NO_MATCHING_FAILURE'):
            self.collect()
        self.assertEqual(self.calls, [])

    def test_wrong_setup_or_build_id_is_rejected(self):
        for key in ('setup_sha256', 'build_id'):
            old = self.failure[key]
            self.failure[key] = 'wrong'
            with self.assertRaisesRegex(ValueError, 'SETUP_IDENTITY_HOLD'):
                self.collect()
            self.failure[key] = old
        self.assertEqual(self.calls, [])

    def test_unsafe_stage_is_not_inspected_or_executed(self):
        self.owner.plain_parents = lambda path, base: path != self.stage
        with self.assertRaisesRegex(ValueError, 'REPARSE_HOLD'):
            self.collect()
        self.assertEqual(self.calls, [])

    def test_modified_committed_verifier_is_rejected(self):
        self.verifier.write_bytes(b'changed unreviewed verifier')
        with self.assertRaisesRegex(ValueError, 'VERIFIER_BYTES_HOLD'):
            self.collect()
        self.assertEqual(self.calls, [])

    def test_no_manifest_means_no_probe_or_installer_retry(self):
        (self.stage / 'payload.sha256.json').unlink()
        result = self.collect()
        self.assertEqual(result['verifications'], [])
        self.assertEqual(self.calls, [])

    def test_optional_x86_probe_has_same_script_and_readonly_arguments(self):
        wow = Path(self.env['SystemRoot']) / 'SysWOW64/WindowsPowerShell/v1.0/powershell.exe'
        wow.parent.mkdir(parents=True)
        wow.write_bytes(b'fixture not executed')
        result = self.collect()
        self.assertEqual([item['architecture'] for item in result['verifications']], ['native', 'x86'])
        self.assertEqual(self.calls[0][0][1:], self.calls[1][0][1:])
        self.assertEqual(self.calls[1][0][0], str(wow))

    def test_update_backup_firstfail_is_readonly_not_no_loss_acceptance(self):
        self.failure['reason'] = 'T06_UPDATE_BACKUP_MANIFEST_VERIFY_HOLD'
        (self.stage / 'payload.sha256.json').unlink()
        previous = self.local / 'Programs/NOX HELION.__p01_previous'
        previous.mkdir()
        expected = b"NOX_G4_UNMANAGED_INSTALL_DATA_NOLOSS\\n"
        probe = previous / 'nox-g4-unmanaged-123.bin'
        probe.write_bytes(expected)
        calls = []
        def verify(slot, name, frozen_bytes, inode, base):
            calls.append((slot, name, frozen_bytes, inode, base))
            return {'status': 'PASS_DIAGNOSTIC_ONLY',
                    'manifest_files_checked': 101}
        self.owner.verify_exact_probe_slot = verify
        report = self.collect()
        check = report['update_backup_diagnostic']
        self.assertEqual(check['first_failure'], 'NONE_IN_CURRENT_SNAPSHOT')
        self.assertFalse(check['pre_update_user_inode_verified'])
        self.assertFalse(check['release_accepted'])
        self.assertEqual(report['original_failure'], self.failure['reason'])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], previous)
        self.assertEqual(calls[0][2], expected)
        self.assertEqual(self.calls, [])  # no PowerShell, Setup or native action

    def test_update_backup_original_owner_failure_stays_visible_and_hold(self):
        self.failure['reason'] = 'T06_UPDATE_BACKUP_MANIFEST_VERIFY_HOLD'
        (self.stage / 'payload.sha256.json').unlink()
        previous = self.local / 'Programs/NOX HELION.__p01_previous'
        previous.mkdir()
        (previous / 'nox-g4-unmanaged-123.bin').write_bytes(b"NOX_G4_UNMANAGED_INSTALL_DATA_NOLOSS\\n")
        self.owner.verify_exact_probe_slot = lambda *args: (
            (_ for _ in ()).throw(RuntimeError(
                'T06_EXACT_PROBE_SLOT_OWNED_SHA_HOLD')))
        proof = self.collect()['update_backup_diagnostic']
        self.assertEqual(proof['first_failure'],
                         'T06_EXACT_PROBE_SLOT_OWNED_SHA_HOLD')
        self.assertFalse(proof['release_accepted'])
        self.assertFalse(proof['pre_update_user_inode_verified'])
        self.assertEqual(self.calls, [])

    def test_update_backup_missing_does_not_become_silent_success(self):
        self.failure['reason'] = 'T06_ORIGINAL_NSIS_UPDATE_BACKUP_HOLD'
        (self.stage / 'payload.sha256.json').unlink()
        self.owner.verify_exact_probe_slot = lambda *args: self.fail(
            'owner should not execute without an existing backup')
        proof = self.collect()['update_backup_diagnostic']
        self.assertEqual(proof['first_failure'], 'BACKUP_NOT_PRESENT')
        self.assertFalse(proof['release_accepted'])
        self.assertEqual(self.calls, [])

    def test_rollback_original_failure_is_readonly_never_release(self):
        self.failure['reason'] = 'T06_ORIGINAL_NSIS_ROLLBACK_NOLOSS_HOLD'
        self.failure['installer_lifecycle'] = {'rollback': {'code': 1}}
        (self.stage / 'payload.sha256.json').unlink()
        installed = self.local / 'Programs/NOX HELION'
        saved = self.local / 'Programs/NOX HELION.__p01_rollback_saved'
        installed.mkdir()
        saved.mkdir()
        (installed / 'nox-p01-owned.txt').write_text('NOXHELION.P01 V16')
        before = (installed / 'nox-p01-owned.txt').read_bytes()
        result = self.collect()
        self.assertEqual(result['original_failure'], self.failure['reason'])
        self.assertFalse(result['release_accepted'])
        self.assertEqual(result['phase'], 'DIAGNOSTIC_ONLY')
        diag = result['rollback_diagnostic']
        self.assertEqual(diag['original_exit_code'], 1)
        self.assertTrue(diag['restored_slot_present'])
        self.assertTrue(diag['saved_slot_present'])
        self.assertFalse(diag['previous_slot_present'])
        self.assertTrue(diag['restored_owner_marker_present'])
        self.assertFalse(diag['user_data_no_loss_accepted'])
        self.assertFalse(diag['release_accepted'])
        self.assertEqual((installed / 'nox-p01-owned.txt').read_bytes(), before)
        self.assertEqual(self.calls, [])

    def test_rollback_missing_original_receipt_never_invents_exit_or_evidence(self):
        self.failure['reason'] = 'T06_ORIGINAL_NSIS_ROLLBACK_NOLOSS_HOLD'
        (self.stage / 'payload.sha256.json').unlink()
        result = self.collect()
        diag = result['rollback_diagnostic']
        self.assertIsNone(diag['original_exit_code'])
        self.assertFalse(diag['restored_slot_present'])
        self.assertFalse(diag['saved_slot_present'])
        self.assertFalse(diag['restored_owner_marker_present'])
        self.assertFalse(diag['user_data_no_loss_accepted'])
        self.assertEqual(self.calls, [])

    def test_workflow_keeps_original_failure_and_collects_evidence(self):
        workflow = (ROOT / '.github/workflows/nox-v16-e06-d02-onehost.yml').read_text()
        start = workflow.index('      - name: Read-only NSIS failure evidence')
        end = workflow.index('      - name: Download exact Microsoft', start)
        step = workflow[start:end]
        self.assertIn('if: failure()', step)
        self.assertIn('python coordination/e06/t06_nsis_failure_diagnostics.py', step)
        self.assertIn("throw 'T06_INSTALLED_NATIVE_LIFECYCLE_HOLD'", workflow[:start])
        self.assertNotIn('continue-on-error', workflow)
        self.assertIn('work/e06/onehost-wow-diagnostic/T06_NSIS_FAILURE_DIAGNOSTICS.json', workflow[end:])
        self.assertEqual(workflow.count('test_t06_nsis_failure_diagnostics.py'), 2)


if __name__ == '__main__':
    unittest.main()
