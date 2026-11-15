"""Dedicated V144 source checks; optional V140 real archive supplied via NOX_V140_ZIP."""
import importlib.util
import json
import os
import pathlib
import subprocess
import tempfile
import unittest
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('v144', HERE / 'v144_windows_backup_owner_guard.py')
v144 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v144)


class V144Contract(unittest.TestCase):
    def test_failclosed_rejected_anchors(self):
        for target in v144.TARGETS[:2]:
            with self.assertRaisesRegex(ValueError,'HOLD_ORIGINAL_WINDOWS_BACKUP_ANCHOR'):
                v144.patched(target, b"const nonsense = 1;")

    def test_exact_original_backups_only(self):
        for target in v144.TARGETS[:2]:
            before = (v144.ANCHOR + "\nconst x = " + v144.OLD_ACTION + ';').encode()
            result = v144.patched(target, before).decode()
            self.assertEqual(result.count("await api('/api/install/backup',{});"), 0)
            self.assertEqual(result.count("await api('/api/install/backup', {confirm:true})"), 1)
            self.assertIn('HOLD_WINDOWS_BACKUP_WRONG_HOST_OR_ANONYMOUS',result)
            self.assertIn('HOLD_WINDOWS_BACKUP_OWNER_CAPABILITY_UNVERIFIED',result)
            self.assertIn('HOLD_WINDOWS_BACKUP_NATIVE_SHA_RECEIPT_UNVERIFIED',result)

    def test_v145_original_route_host_proof_blocks_onehost_as_windows(self):
        # The canonical original V29.3 manifest is evidence of route
        # provenance, not a claim that a Windows PC handler exists.
        manifest = json.loads((HERE.parent/'NOX_WEB_V293_92_ROUTE_HOST_PLAN.json').read_text())
        routes = {item['route']:item for item in manifest['functions']}
        self.assertEqual(len(routes), 92)
        self.assertEqual(routes['/api/nox/status']['host_boundary'], 'EXISTING_ONEHOST')
        for path in ('/api/install/backup','/api/install/capabilities'):
            self.assertEqual(routes[path]['host_boundary'], 'WINDOWS_OWNER_PC_REQUIRED_NOT_VAST_METRICS')
            self.assertEqual(routes[path]['source_runtime_status'], 'NO_DIRECT_NATIVE_MATCH_IN_BASELINE')
        self.assertIn("identity?.windows_owner_pc !== true", v144.GUARD)
        self.assertIn("HOLD_WINDOWS_BACKUP_OWNER_IDENTITY_UNVERIFIED", v144.GUARD)

    def test_v23_fallback_only_calls_guard(self):
        before = ("const r = " + v144.FALLBACK_OLD + ';').encode()
        result = v144.patched(v144.TARGETS[2], before).decode()
        self.assertNotIn(v144.FALLBACK_OLD,result)
        self.assertIn('HOLD_WINDOWS_BACKUP_GUARD_NOT_BOUND',result)

    @unittest.skipUnless(os.environ.get('NOX_V140_ZIP'), 'exact V140 archive not mounted in this runner')
    def test_full_source_v140_unchanged_1129(self):
        original = pathlib.Path(os.environ['NOX_V140_ZIP'])
        self.assertEqual(v144.file_sha(original),v144.INPUT_SHA256)
        with tempfile.TemporaryDirectory() as work:
            candidate = pathlib.Path(work)/'guard.zip'
            report = v144.build(original,candidate)
            self.assertEqual(report['input_members'],1132)
            self.assertEqual(report['output_members'],1136)
            self.assertEqual(report['untouched_original_members'],1129)
            self.assertEqual(report['patched_original_members'],3)
            self.assertTrue(report['rollback_verified'])
            with zipfile.ZipFile(candidate) as z:
                for target in v144.TARGETS:
                    source=z.read(target).decode()
                    if target.endswith('workspace-pages.js'):
                        self.assertEqual(source.count('NOX_WINDOWS_BACKUP_V144 = Object.freeze'),1)
                        self.assertEqual(source.count("await api('/api/install/backup',{})"),0)
                    else:
                        self.assertNotIn(v144.FALLBACK_OLD,source)
            self.assertFalse(report['windows_E2E_verified'])
            self.assertFalse(report['native_owner_cookie_verified'])


if __name__=='__main__':
    unittest.main()
