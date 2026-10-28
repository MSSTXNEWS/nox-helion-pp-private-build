import unittest,tempfile,zipfile,json,sys,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import stage_persona_media as ps
from stage_persona_media import stage,ACTIVE,BLOCKED
from unittest.mock import patch
import hashlib
BUNDLE=Path(os.getenv('NOX_PERSONA_R15_BUNDLE','/mnt/data/NOX_V16_PERSONA_CAM_LOOPS_R15_20261028.zip'))
def synthetic_fixture(dest):
 entries=[];items={}
 for n in ['KV','AM','LA','KW','EV']:
  row={'id':n,'status':'IDENTITY_CONFLICT_HOLD' if n=='EV' else 'APPROVED_SOURCE',
       'approved_for_active_persona':n!='EV'}
  for kind,ext in [('loop','mp4'),('poster','jpg')]:
   filename=f'NOX_PERSONA_{n}_'+('CAMERA_LOOP.mp4' if kind=='loop' else 'POSTER.jpg')
   data=(n+kind).encode()*8
   row[kind+'_filename']=filename;row[kind+'_sha256']=hashlib.sha256(data).hexdigest()
   items[filename]=data
  entries.append(row)
 items['PERSONA_MOTION_MANIFEST.json']=json.dumps({'schema':'NOX_PERSONA_PARALLAX_SILENT_LOOP_V1','entries':entries}).encode()
 with zipfile.ZipFile(dest,'w') as z:
  for n,data in items.items():z.writestr(n,data)
 return dest
class PersonaMediaTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name)/'R11';(self.root/'Assets/creative').mkdir(parents=True)
  (self.root/'NOX.P01.Shell.csproj').write_text('original stub\n')
  self.bundle=BUNDLE if BUNDLE.exists() else synthetic_fixture(Path(self.tmp.name)/'fixture.zip')
  self.pin=ps.PINNED_BUNDLE_SHA256
  if not BUNDLE.exists():ps.PINNED_BUNDLE_SHA256=hashlib.sha256(self.bundle.read_bytes()).hexdigest()
  self.addCleanup(lambda:setattr(ps,'PINNED_BUNDLE_SHA256',self.pin))
 def test_four_approved_media_and_unapproved_ev_stays_out(self):
  receipt=stage(self.root,self.bundle)
  self.assertEqual(receipt['active_count'],4)
  self.assertEqual(receipt['media_files'],8)
  self.assertEqual(receipt['identity_candidate_hold'],1)
  for id in ACTIVE:
   self.assertTrue((self.root/'Assets/creative/personas'/('NOX_PERSONA_'+id+'_CAMERA_LOOP.mp4')).is_file())
  self.assertFalse((self.root/'Assets/creative/personas'/'NOX_PERSONA_EV_CAMERA_LOOP.mp4').exists())
  self.assertFalse(receipt['facial_animation'])
  self.assertFalse(receipt['native_windows_accepted'])
 def test_does_not_overwrite(self):
  stage(self.root,self.bundle)
  with self.assertRaisesRegex(ValueError,'NO_OVERWRITE'):stage(self.root,self.bundle)
 def test_reject_changed_video_without_writing(self):
  contents={}
  with zipfile.ZipFile(self.bundle) as z:
   for name in z.namelist():contents[name]=z.read(name)
  contents['NOX_PERSONA_KV_CAMERA_LOOP.mp4']=b'evil'
  bad=Path(self.tmp.name)/'bad.zip'
  with zipfile.ZipFile(bad,'w') as z:
   for n,data in contents.items():z.writestr(n,data)
  with patch.object(ps,'PINNED_BUNDLE_SHA256',hashlib.sha256(bad.read_bytes()).hexdigest()):
   with self.assertRaisesRegex(ValueError,'SHA_HOLD'):stage(self.root,bad)
  self.assertFalse((self.root/'Assets/creative/personas').exists())
 def test_blocked_identity_cannot_be_promoted_by_manifest_only(self):
  contents={}
  with zipfile.ZipFile(self.bundle) as z:
   for name in z.namelist():contents[name]=z.read(name)
  manifest=json.loads(contents['PERSONA_MOTION_MANIFEST.json'])
  for row in manifest['entries']:
   if row['id']=='EV':row['approved_for_active_persona']=True
  contents['PERSONA_MOTION_MANIFEST.json']=json.dumps(manifest).encode()
  bad=Path(self.tmp.name)/'promoted.zip'
  with zipfile.ZipFile(bad,'w') as z:
   for n,data in contents.items():z.writestr(n,data)
  with patch.object(ps,'PINNED_BUNDLE_SHA256',hashlib.sha256(bad.read_bytes()).hexdigest()):
   with self.assertRaisesRegex(ValueError,'UNAPPROVED_PERSONA'):stage(self.root,bad)
  self.assertFalse((self.root/'Assets/creative/personas').exists())
if __name__=='__main__':unittest.main()