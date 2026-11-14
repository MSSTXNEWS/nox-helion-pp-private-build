import importlib.util
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('stage',ROOT/'integrations/wow200/stage_wow200.py')
stage=importlib.util.module_from_spec(spec);spec.loader.exec_module(stage)
class MenuStage(unittest.TestCase):
    def test_atomic_current_source(self):
        plans=stage.menu_stage_plan(ROOT,Path('target'))
        self.assertEqual(len(plans),4)
        self.assertEqual({p[1].name for p in plans},{'selfbuilder-menu-v2.mjs','selfbuilder-menu-v2.css','onehost-menu-bindings.mjs','menu_v2_existing_routes.json'})
    def test_partial_source_or_changed_css_cannot_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for path in stage.MENU_V2_SHA256:
                p=root/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/path).read_bytes())
            (root/'ui/selfbuilder-menu-v2.css').write_text('different')
            with self.assertRaisesRegex(ValueError,'ATOMIC_SOURCE_PIN_HOLD'):stage.menu_stage_plan(root,root/'dest')
            self.assertFalse((root/'dest').exists())
if __name__=='__main__':unittest.main()
