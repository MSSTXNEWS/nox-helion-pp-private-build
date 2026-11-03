"""BOOST V5 staging-runtime provenance. Source-only; never an installed E07 proof.
The cached 3.13.2 offline installer is NOT the original BOOST wrapper's
pinned Python 3.12.10 staging interpreter. Keep that distinction explicit.
"""
import ast
import json
import re
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
INPUTS = ROOT / 'coordination/express/NOX_BOOST_V5_RELEASE_INPUTS.json'
WRAPPER = ROOT / 'coordination/e06/build_onehost_with_boost.ps1'
STAGER = ROOT / 'coordination/e06/boost_v4_stage.py'
LOCK = ROOT / 'coordination/wow-exec-v1/downloads/NOX_R11_DEPENDENCY_LOCK.json'
class BoostV5PythonProvenanceR95(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v5 = json.loads(INPUTS.read_text(encoding='utf-8'))
        cls.wrapper = WRAPPER.read_text(encoding='utf-8')
        cls.stager = STAGER.read_text(encoding='utf-8')
        cls.lock = json.loads(LOCK.read_text(encoding='utf-8'))
    def test_pinned_staging_python_is_not_offline_installer(self):
        required = re.search(r"\$pythonVersion\s+-cne\s+'(\d+\.\d+\.\d+)'", self.wrapper)
        self.assertIsNotNone(required, 'BOOST_PINNED_STAGER_RUNTIME_MISSING')
        stage = self.v5['boost_staging_python']
        self.assertEqual(stage['required_version'], required.group(1))
        self.assertEqual(stage['verification'], 'NOT_VERIFIED_IN_BOOST_CACHE')
        self.assertEqual(stage['source'], 'coordination/e06/build_onehost_with_boost.ps1')
        self.assertEqual(self.v5['offline_toolchains']['python']['role'], 'OFFLINE_INSTALLER_CACHE_NOT_BOOST_STAGER')
        self.assertNotEqual(self.v5['offline_toolchains']['python']['version'], required.group(1))
    def test_both_cache_archive_hashes_match_live_stager(self):
        sha = dict(re.findall(r'\b(EXPECTED_CACHE_SHA|COMPACT_CACHE_SHA)\s*=\s*"([a-f0-9]{64})"', self.stager))
        self.assertEqual(sha['EXPECTED_CACHE_SHA'], self.v5['verified_cache']['monolith']['sha256'])
        self.assertEqual(sha['COMPACT_CACHE_SHA'], self.v5['verified_cache']['onehost_fast']['sha256'])
        self.assertFalse(self.v5['verified_cache']['onehost_fast']['onehost_executed'])
    def test_d02_four_approved_sha_are_all_pinned(self):
        node = ast.parse(self.stager)
        values = [ast.literal_eval(assign.value) for assign in node.body
                  if isinstance(assign, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == 'APPROVED_D02'
                          for target in assign.targets)]
        self.assertEqual(len(values), 1)
        self.assertEqual(set(values[0]), {'home.png', 'menu.png', 'core01.png', 'menu_sections.png'})
        self.assertTrue(all(re.fullmatch(r'[a-f0-9]{64}', s) for s in values[0].values()))
        self.assertEqual(self.v5['verified_cache']['onehost_fast']['d02_images'], len(values[0]))
    def test_offline_nuget_dependency_count_not_authenticode_proof(self):
        packages = [f for f in self.lock['files'] if f['kind'] == 'nuget']
        self.assertEqual(len(packages), 16)
        self.assertEqual(len({f['path'].casefold() for f in packages}), 16)
        self.assertEqual(self.v5['verified_cache']['onehost_fast']['nuget_packages'], 16)
        self.assertEqual(self.lock['oss_review']['librehardwaremonitorlib_nuget_signature'], 'INDEPENDENT_VERIFICATION_HOLD')
        self.assertTrue(all(re.fullmatch(r'[a-f0-9]{64}', f['sha256']) and f['size'] > 0 for f in packages))
    def test_no_release_promotion_from_cache_receipts(self):
        self.assertFalse(self.v5['source']['full_head_snapshot_in_cache'])
        self.assertIn('UNVERIFIED', self.v5['gates']['G1'])
        self.assertIn('NOT_VERIFIED', self.v5['gates']['G3'])
        self.assertIn('NOT_PASS', self.v5['gates']['G4'])
        self.assertTrue(self.v5['boost_staging_python']['missing_runtime_blocks_build'])
if __name__ == '__main__':
    unittest.main()
