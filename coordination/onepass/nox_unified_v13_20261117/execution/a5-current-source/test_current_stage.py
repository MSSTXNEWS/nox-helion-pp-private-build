from pathlib import Path
import importlib.util,json,tempfile,unittest
SOURCE=Path(__file__).resolve().parents[2]/'integration/owner_mini_source/stage_current_source.py'
spec=importlib.util.spec_from_file_location('stage',SOURCE);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Admission(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name);self.root=self.base/'source';self.root.mkdir();(self.root/'site').mkdir();(self.root/'site/index.html').write_text('actual source');self.lock=self.root/m.MANIFEST;self.lock.parent.mkdir(parents=True);self.write_manifest({'site/index.html':m.sha(b'actual source')})
 def write_manifest(self,files):
  self.lock.write_text(json.dumps({'schema':m.SCHEMA,'native_accepted':False,'files':files},sort_keys=True));self.pin=m.sha(self.lock.read_bytes())
 def test_exact_stage_readback_and_no_overwrite(self):
  out=self.base/'stage';r=m.stage(self.root,out,self.pin);self.assertTrue(r['stage_ready']);self.assertFalse(r['native_accepted']);self.assertEqual((out/'site/index.html').read_text(),'actual source');self.assertRaises(FileExistsError,m.stage,self.root,out,self.pin)
 def test_wrong_manifest_pin(self):
  self.assertRaisesRegex(ValueError,'HOLD_CURRENT_MANIFEST_SHA',m.stage,self.root,self.base/'stage','0'*64);self.assertFalse((self.base/'stage').exists())
 def test_unpinned_stage(self):self.assertRaisesRegex(ValueError,'HOLD_EXPLICIT_CURRENT_SHA',m.stage,self.root,self.base/'stage',None)
 def test_changed_source(self):
  (self.root/'site/index.html').write_text('drift');self.assertRaisesRegex(ValueError,'HOLD_CURRENT_FILE_SHA',m.verify,self.root,self.pin)
 def test_traversal(self):
  self.write_manifest({'../outside':m.sha(b'x')});self.assertRaisesRegex(ValueError,'HOLD_UNSAFE_SOURCE_PATH',m.verify,self.root,self.pin)
 def test_symlink(self):
  (self.root/'site/link').symlink_to('index.html');self.write_manifest({'site/link':m.sha(b'actual source')});self.assertRaisesRegex(ValueError,'HOLD_SOURCE_SYMLINK',m.verify,self.root,self.pin)
 def test_stage_inside_source(self):self.assertRaisesRegex(ValueError,'HOLD_STAGE_OUTSIDE_SOURCE',m.stage,self.root,self.root/'stage',self.pin)
 def test_native_claim_rejected(self):
  raw=json.loads(self.lock.read_text());raw['native_accepted']=True;self.lock.write_text(json.dumps(raw));self.assertRaisesRegex(ValueError,'HOLD_SOURCE_SCHEMA',m.verify,self.root)
 def test_compile_python_source(self):
  p=self.root/'integration/owner_mini_source/bad.py';p.write_text('def invalid:');self.write_manifest({str(p.relative_to(self.root)):m.sha(p.read_bytes())});self.assertRaises(SyntaxError,m.verify,self.root,self.pin)
if __name__=='__main__':unittest.main()
