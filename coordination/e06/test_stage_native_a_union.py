"""Source gate: stage_native_stdio must copy exact A1 modules on same host."""
import json
import unittest
from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[2]
SCRIPT=ROOT/'coordination/e06/stage_native_stdio.py'
LOCK=ROOT/'coordination/e06/A1_BUILD_SOURCES.lock.json'

class NativeAUnion(unittest.TestCase):
    def test_pinned_a1_stages_with_existing_python_owner(self):
        text=SCRIPT.read_text('utf-8')
        self.assertIn('from stage_a1_owner import REQUIRED as a_required',text)
        self.assertIn("sources.append((destination,payload))",text)
        self.assertIn("a_blob(payload)!=expected",text)
        self.assertIn('a1_source_staged_count=len(a_required)',text)
        self.assertIn("a1_native_activation_verified=False",text)
        self.assertIn("with target.open(\"xb\")",text)
        self.assertIn("created.append((target,data))",text)
    def test_exact_source_lock_has_all_ten_files(self):
        spec=importlib.util.spec_from_file_location('stage_a1_owner',
             ROOT/'coordination/e06/stage_a1_owner.py')
        m=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        data=json.loads(LOCK.read_text('utf-8'))
        self.assertEqual(set(data['sources']),set(m.REQUIRED))
        self.assertEqual(len(m.REQUIRED),10)
        for name,pin in data['sources'].items():
            source=ROOT/'src/nox_selfbuilder'/name
            self.assertTrue(source.is_file())
            self.assertEqual(m.git_blob(source.read_bytes()),pin)
    def test_updated_native_owner_builder_blob_pin(self):
        text=SCRIPT.read_text('utf-8')
        import re
        match=re.search(r"\('src/nox_selfbuilder/onehost_builder.py', 'nox_selfbuilder/onehost_builder.py', '([0-9a-f]{40})'\)",text)
        self.assertIsNotNone(match)
        spec=importlib.util.spec_from_file_location('stage_a1_owner',
              ROOT/'coordination/e06/stage_a1_owner.py')
        mod=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(match.group(1),mod.git_blob(
            (ROOT/'src/nox_selfbuilder/onehost_builder.py').read_bytes()))
if __name__=='__main__':unittest.main()
