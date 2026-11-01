"""Exactly ONE A1 staging owner; prevent duplicate staging and stale OneHost pin."""
import json
import unittest
from pathlib import Path
import importlib.util
import re
ROOT=Path(__file__).resolve().parents[2]
A1=ROOT/'coordination/e06/stage_a1_owner.py'
NATIVE=ROOT/'coordination/e06/stage_native_stdio.py'
BUILD=ROOT/'private_build.ps1'
LOCK=ROOT/'coordination/e06/A1_BUILD_SOURCES.lock.json'

class NativeAUnion(unittest.TestCase):
    def test_only_original_a1_owner_physically_stages_ten_modules(self):
        native=NATIVE.read_text('utf-8')
        build=BUILD.read_text('utf-8')
        self.assertNotIn('sources.append((destination,payload))',native)
        self.assertNotIn('a1_source_staged_count',native)
        self.assertIn("$a1StageJson=@(& $venvPython -I $a1Script $source)",build)
        self.assertIn('$a1Stage.source_count -ne 10',build)
        self.assertIn('ONEHOST_NATIVE_DATA_PATH_OR_SHA_INVALID',build)
        self.assertIn("'--hidden-import','nox_selfbuilder.a1_initiative_bridge'",build)
    def test_a1_source_lock_exact_ten_current_blobs(self):
        spec=importlib.util.spec_from_file_location('stage_a1_owner',A1)
        mod=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        data=json.loads(LOCK.read_text('utf-8'))
        self.assertEqual(set(data['sources']),set(mod.REQUIRED))
        self.assertEqual(len(mod.REQUIRED),10)
        for name,pin in data['sources'].items():
            source=ROOT/'src/nox_selfbuilder'/name
            self.assertEqual(mod.git_blob(source.read_bytes()),pin)
    def test_onehost_builder_repin_used_by_original_stage(self):
        spec=importlib.util.spec_from_file_location('stage_a1_owner',A1)
        mod=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        native=NATIVE.read_text('utf-8')
        match=re.search(r"\('src/nox_selfbuilder/onehost_builder.py', 'nox_selfbuilder/onehost_builder.py', '([0-9a-f]{40})'\)",native)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1),mod.git_blob(
           (ROOT/'src/nox_selfbuilder/onehost_builder.py').read_bytes()))
if __name__=='__main__':unittest.main()
