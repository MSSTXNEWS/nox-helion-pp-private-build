import unittest,tempfile,pathlib,hashlib
from scripts.INSTALL_WEB_SOURCE_LOCK import install, ASSETS
ROOT=pathlib.Path(__file__).resolve().parents[1]
STYLE='<link rel="stylesheet" href="./nox-learning-3axes.css" data-nox-v40="three-axis-evidence">'
SCRIPT='<script defer src="./nox-learning-3axes.js" data-nox-v40="three-axis-evidence"></script>'

class TestOriginalWebMutation(unittest.TestCase):
 def _original(self,base):
  for name in ('training.html','pc/training.html'):
   src=ROOT/'web/site'/name
   dest=pathlib.Path(base)/name;dest.parent.mkdir(parents=True,exist_ok=True)
   dest.write_text(src.read_text('utf8').replace(STYLE,'').replace(SCRIPT,''),encoding='utf8')
 def test_dry_run_preserves_full_web(self):
  with tempfile.TemporaryDirectory() as path:
   self._original(path)
   before=(pathlib.Path(path)/'training.html').read_bytes()
   out=install(path)
   self.assertEqual(out['state'],'READY_SOURCE_LOCK_ONLY')
   self.assertEqual((pathlib.Path(path)/'training.html').read_bytes(),before)
   self.assertFalse((pathlib.Path(path)/ASSETS[0]).exists())
 def test_apply_changes_exact_two_pages_with_backup(self):
  with tempfile.TemporaryDirectory() as path:
   self._original(path)
   result=install(path,True)
   self.assertEqual(result['state'],'INSTALLED_WEB_FILES_ONLY_SOURCE_VERIFIED')
   for name in ('training.html','pc/training.html'):
    self.assertEqual((pathlib.Path(path)/name).read_bytes(),(ROOT/'web/site'/name).read_bytes())
    self.assertTrue((pathlib.Path(path)/(name+'.nox41-original.bak')).is_file())
   for name in ASSETS:self.assertEqual((pathlib.Path(path)/name).read_bytes(),(ROOT/'web'/name).read_bytes())
 def test_conflicting_asset_rejected_without_any_write(self):
  with tempfile.TemporaryDirectory() as path:
   self._original(path)
   (pathlib.Path(path)/ASSETS[1]).write_text('SHOULD_BE_PRESERVED')
   before=(pathlib.Path(path)/'training.html').read_bytes()
   result=install(path,True)
   self.assertEqual(result['state'],'HOLD_ASSET_CONFLICT')
   self.assertEqual((pathlib.Path(path)/'training.html').read_bytes(),before)
   self.assertFalse((pathlib.Path(path)/'training.html.nox41-original.bak').exists())
 def test_source_lock_rejects_unexpected_prod_html(self):
  with tempfile.TemporaryDirectory() as path:
   self._original(path)
   (pathlib.Path(path)/'training.html').write_text('other version')
   self.assertEqual(install(path,True)['state'],'HOLD_BASELINE_SHA_MISMATCH')
