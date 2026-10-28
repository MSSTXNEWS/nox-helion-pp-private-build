import importlib.util,tempfile,unittest,hashlib,json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('stage_wow200',ROOT/'stage_wow200.py')
wow=importlib.util.module_from_spec(spec);spec.loader.exec_module(wow)
class CanonicalWOWNativePath(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();base=Path(self.tmp.name)
  self.root=base/'R11';self.source=base/'wow200';self.assets=self.root/'Assets'
  (self.assets/'creative').mkdir(parents=True);(self.source/'runtime').mkdir(parents=True)
  (self.root/'NOX.P01.Shell.csproj').write_text('fixture')
  (self.assets/'index.html').write_text('<html><head></head><body>nox-orbit-stage nox-eclipse nox-orbit-core CONSCIOUSNESS FORGE</body></html>')
  (self.assets/'creative/studio.html').write_text('<html><head></head><body>STUDIO</body></html>')
  (self.assets/'creative/studio.js').write_text('fixture')
  self.saved_d02=wow.D02.copy();self.saved_manifest=wow.DONOR_MANIFEST_BLOB;self.saved_owner=wow.ACTIVE_OWNER_BLOBS.copy()
  for n in wow.D02:
   p=self.assets/n;p.write_bytes(('fixture:'+n).encode());wow.D02[n]=wow.digest(p)
  rels=sorted(wow.REQUIRED_DONORS)
  rels.extend('proposals/DUMMY/example_'+str(i)+'.mjs' for i in range(56-len(rels)))
  manifest={'schema':'NOX_WOW200_OWNER_BLOB_PIN_V1','count':56,'files':{}}
  for r in rels:
   p=self.source/r;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('/* '+r+' */')
   manifest['files'][r]=wow.gitsha(p.read_bytes())
  m=self.source/'DONOR_BLOBS.json';m.write_text(json.dumps(manifest));wow.DONOR_MANIFEST_BLOB=wow.gitsha(m.read_bytes())
  for n in ['nox-cinema.mjs','nox-cinema.css']:
   p=self.source/'canonical'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('/* active E01 fixture '+n+' */')
   wow.ACTIVE_OWNER_BLOBS[n]=wow.gitsha(p.read_bytes())
  for n in ['loader.mjs','stage.css','home-scene.mjs','home-guard.css']:
   src=ROOT/'runtime'/n
   p=self.source/'runtime'/n
   p.write_bytes(src.read_bytes())
 def tearDown(self):
  wow.D02.clear();wow.D02.update(self.saved_d02)
  wow.ACTIVE_OWNER_BLOBS.clear();wow.ACTIVE_OWNER_BLOBS.update(self.saved_owner)
  wow.DONOR_MANIFEST_BLOB=self.saved_manifest;self.tmp.cleanup()
 def test_exact_canonical_mount_while_preserving_legacy(self):
  outcome=wow.stage(self.root,self.source)
  self.assertEqual(outcome['donor_file_count'],56)
  self.assertTrue(outcome['home_E01_owner_renderer_staged'])
  self.assertIn("from '../canonical/nox-cinema.mjs'",(self.root/'Assets/creative/wow200/runtime/home-scene.mjs').read_text())
  page=(self.assets/'index.html').read_text()
  self.assertIn('creative/wow200/canonical/nox-cinema.css',page)
  self.assertNotIn('creative/wow200/proposals/NOX-CINEMA-FX/nox-cinema.css',page)
  self.assertTrue((self.root/'Assets/creative/wow200/proposals/NOX-CINEMA-FX/nox-cinema.mjs').exists())
 def test_modified_canonical_js_rejected_without_writing(self):
  (self.source/'canonical/nox-cinema.mjs').write_text('drift')
  with self.assertRaisesRegex(ValueError,'ACTIVE_E01_OWNER_SHA_HOLD'):wow.stage(self.root,self.source)
  self.assertFalse((self.root/'Assets/creative/wow200').exists())
 def test_missing_canonical_css_rejected_without_writing(self):
  (self.source/'canonical/nox-cinema.css').unlink()
  with self.assertRaisesRegex(ValueError,'ACTIVE_E01_OWNER_SHA_HOLD'):wow.stage(self.root,self.source)
  self.assertFalse((self.root/'Assets/creative/wow200').exists())
 def test_archive_manifest_change_rejected(self):
  (self.source/'DONOR_BLOBS.json').write_text('{}')
  with self.assertRaisesRegex(ValueError,'DONOR_MANIFEST_PIN_HOLD'):wow.stage(self.root,self.source)
  self.assertFalse((self.root/'Assets/creative/wow200').exists())
if __name__=='__main__':unittest.main()