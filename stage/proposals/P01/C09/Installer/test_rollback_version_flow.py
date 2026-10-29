"""Rollback source-flow/contract model; not Windows registry or NSIS execution."""
from pathlib import Path
import re
import unittest

HERE = Path(__file__).parent


def rollback_flow(source, fail_rename=None, registry_fails=False):
    function = source.split('Function RestorePrevious\n')[1].split('FunctionEnd')[0]
    body = function[function.index('  Rename '):function.index('  NoPrevious:')]
    code = [x.strip() for x in body.splitlines() if x.strip() and not x.lstrip().startswith(';')]
    pc, error, renames = 0, False, 0
    versions = []
    for _ in range(100):
        if pc >= len(code):
            raise AssertionError('missing rollback return')
        fields = re.findall(r'"[^\"]*"|\S+', code[pc])
        op = fields[0]
        if op == 'Rename':
            renames += 1
            error |= renames == fail_rename
        elif op == 'IfErrors':
            dest = fields[1] if error else (fields[2] if len(fields) > 2 else '0')
            error = False
            pc += 1 if dest == '0' else int(dest)
            continue
        elif op == 'ClearErrors':
            error = False
        elif op == 'WriteRegStr':
            if fields[-2:] != ['"DisplayVersion"', '"$CheckResult"']:
                raise AssertionError('rollback version must come from verified backup output')
            if registry_fails:
                error = True
            else:
                versions.append('2.3.4')  # injected successful verifier output
        elif op == 'SetErrorLevel' or op == 'DetailPrint':
            pass
        elif op in ('Abort', 'Return'):
            return dict(success=op == 'Return', versions=versions, renames=renames)
        else:
            raise AssertionError('unmodelled rollback instruction: ' + code[pc])
        pc += 1
    raise AssertionError('rollback loop')


class RollbackVersionTests(unittest.TestCase):
    def setUp(self):
        self.setup = (HERE / 'NOX-HELION-Setup.nsi').read_text()

    def test_success_registers_restored_manifest_version(self):
        self.assertEqual(rollback_flow(self.setup), dict(success=True, versions=['2.3.4'], renames=2))

    def test_failed_renames_never_change_display_version(self):
        for failed in (1, 2):
            with self.subTest(rename=failed):
                result = rollback_flow(self.setup, fail_rename=failed)
                self.assertFalse(result['success'])
                self.assertEqual(result['versions'], [])

    def test_registry_failure_is_not_reported_as_success(self):
        self.assertFalse(rollback_flow(self.setup, registry_fails=True)['success'])

    def test_version_output_requires_successful_full_verification(self):
        verifier = (HERE / 'Verify-Payload.ps1').read_text()
        self.assertIn('[switch]$ReportVersion', verifier)
        output = verifier.index('[Console]::Out.Write([string]$m.version)')
        for guard in ('invalid version', 'sha mismatch', 'file count mismatch', 'entrypoint absent'):
            self.assertLess(verifier.index(guard), output)
        self.assertIn("else { 'P01_PAYLOAD_SHA256_PASS' }", verifier)
        call = next(line for line in self.setup.splitlines() if 'nsExec::ExecToStack' in line and '-Root "$BackupDir"' in line)
        self.assertIn('-AllowInstalledMetadata -ReportVersion', call)


if __name__ == '__main__':
    unittest.main()
