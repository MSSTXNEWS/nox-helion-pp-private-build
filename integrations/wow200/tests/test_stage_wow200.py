import json, tempfile, unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stage_wow200 import stage, D02, gitsha, digest
class WowStageTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  self.stage=self.root/'stage/R11'; self.src=self.root/'src'
  (self.stage/'Assets/creative').mkdir(parents=True)
  (self.stage/'NOX.P01.Shell.csproj').write_text('<Project/>')
  (self.stage/'Assets/creative/studio.html').write_text('<html><head></head><body><section id="screen-immersive"></section></body></html>')
  (self.stage/'Assets/creative/studio.js').write_text('// original')
  self.preimages=dict(D02)
  for n in D02:
   sample=("approved D02 fixture: "+n).encode()
   (self.stage/'Assets'/n).write_bytes(sample)
   D02[n]=digest(self.stage/'Assets'/n)
  manifest={}
  for i in range(50):
   rel=f'proposals/NOX-WOW151-200/fake_{i:02}.mjs'
   p=self.src/rel;p.parent.mkdir(parents=True,exist_ok=True);b=f'// archived cue {i}\n'.encode();p.write_bytes(b)
   manifest[rel]=gitsha(b)
  for rel in ['runtime/loader.mjs','runtime/stage.css']:
   p=self.src/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('// sample')
  (self.src/'DONOR_BLOBS.json').write_text(json.dumps({'schema':'NOX_WOW200_OWNER_BLOB_PIN_V1','files':manifest}))
 def tearDown(self):
  D02.clear();D02.update(self.preimages)
  self.tmp.cleanup()
 def test_additive_preimage_and_readback(self):
  original={n:digest(self.stage/'Assets'/n) for n in D02}
  receipt=stage(self.stage,self.src)
  self.assertEqual(len(receipt['files']),53)
  self.assertEqual({n:digest(self.stage/'Assets'/n) for n in D02},original)
  html=(self.stage/'Assets/creative/studio.html').read_text()
  self.assertIn('wow200/runtime/loader.mjs',html)
  self.assertIn('wow200/proposals/NOX-WOW51-100/wow51-100.css',html)
  self.assertTrue((self.stage.parent/'WOW200_STAGE_RECEIPT.json').is_file())
  with self.assertRaisesRegex(ValueError,'ALREADY_INSTALLED'):stage(self.stage,self.src)
 def test_d02_corruption_fail_closed(self):
  (self.stage/'Assets/home.png').write_bytes(b'broken')
  with self.assertRaisesRegex(ValueError,'CANONICAL_D02_SHA_HOLD'):stage(self.stage,self.src)
  self.assertFalse((self.stage/'Assets/creative/wow200').exists())
 def test_donor_byte_drift_fail_closed(self):
  (self.src/'proposals/NOX-WOW151-200/fake_00.mjs').write_bytes(b'modified')
  with self.assertRaisesRegex(ValueError,'WOW_DONOR_BLOB_IDENTITY_HOLD'):stage(self.stage,self.src)
  self.assertFalse((self.stage/'Assets/creative/wow200').exists())
 def test_path_traversal_fail_closed(self):
  p=self.src/'DONOR_BLOBS.json';obj=json.loads(p.read_text());obj['files']['proposals/../../oops']='00';p.write_text(json.dumps(obj))
  with self.assertRaisesRegex(ValueError,'UNSAFE_WOW_SOURCE_PATH'):stage(self.stage,self.src)
if __name__=='__main__':unittest.main()