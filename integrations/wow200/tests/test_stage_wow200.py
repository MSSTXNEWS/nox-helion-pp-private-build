import json, tempfile, unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stage_wow200 as eng
from stage_wow200 import stage, D02, gitsha, digest
class WowStageTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  # Mirror the real repository layout: <root>/integrations/wow200.
  # stage() uses source.parents[1] to resolve immutable E01 owner files.
  self.stage=self.root/'stage/R11'; self.src=self.root/'integrations/wow200'
  (self.stage/'Assets/creative').mkdir(parents=True)
  (self.stage/'NOX.P01.Shell.csproj').write_text('<Project/>')
  (self.stage/'Assets/creative/studio.html').write_text('<html><head></head><body><section id="screen-immersive"></section></body></html>')
  (self.stage/'Assets/creative/studio.js').write_text('// original')
  (self.stage/'Assets/index.html').write_text('<html><head></head><body>nox-orbit-stage nox-eclipse nox-orbit-core CONSCIOUSNESS FORGE</body></html>')
  # MENU uses the actual same-commit JS/CSS/contract bytes, not placeholder fixtures.
  repository=Path(__file__).resolve().parents[3]
  for relative in eng.MENU_V2_SHA256:
   origin=repository/relative;target=self.root/relative
   target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(origin.read_bytes())
  for relative in eng.P01_OWNER_BLOBS:
   origin=repository/relative;target=self.root/relative
   target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(origin.read_bytes())
  self.preimages=dict(D02)
  self.old_engine_pins={k:dict(v) for k,v in eng.OWNER1_D02_ENGINE.items()}
  # Simulate exact owner1-vs-legacy Git blobs with distinct fixture bytes.
  for rel in eng.OWNER1_D02_ENGINE:
   active=self.root/rel;active.parent.mkdir(parents=True,exist_ok=True)
   active.write_bytes(("owner1 canonical "+rel).encode())
   eng.OWNER1_D02_ENGINE[rel]["active_blob"]=gitsha(active.read_bytes())
  for n in D02:
   sample=("approved D02 fixture: "+n).encode()
   (self.stage/'Assets'/n).write_bytes(sample)
   D02[n]=digest(self.stage/'Assets'/n)
  manifest={}
  for i in range(50):
   rel=f'proposals/NOX-WOW151-200/fake_{i:02}.mjs'
   p=self.src/rel;p.parent.mkdir(parents=True,exist_ok=True);b=f'// archived cue {i}\n'.encode();p.write_bytes(b)
   manifest[rel]=gitsha(b)
  for rel in list(eng.REQUIRED_DONORS):
   p=self.src/rel;p.parent.mkdir(parents=True,exist_ok=True);b=(f'// {rel}\n').encode();p.write_bytes(b);manifest[rel]=gitsha(b)
  # Fixed 56 total exact donor paths including REQUIRED_DONORS.
  for i in range(len(manifest)-56):
   rel=f'proposals/NOX-WOW151-200/fake_{i:02}.mjs'
   p=self.src/rel;p.unlink();manifest.pop(rel)
  # Fixture-only runtime identity: production SHA pins remain unchanged.
  # Test fixtures must not inherit a concurrent checkout's unreviewed
  # source edits. The REAL builder still uses original hard pins and HOLDs.
  self.original_runtime_pins=dict(eng.WOW_RUNTIME_BLOBS)
  for rel in eng.WOW_RUNTIME_BLOBS:
   p=self.src/rel;p.parent.mkdir(parents=True,exist_ok=True)
   if rel=='runtime/home-guard.css':
    sample=(repository/'integrations/wow200'/rel).read_bytes()
   else:
    sample=("// reviewed fixture runtime "+rel+"\n").encode('utf-8')
   p.write_bytes(sample)
   eng.WOW_RUNTIME_BLOBS[rel]=gitsha(sample.replace(b'\r\n',b'\n'))
  # Original chrome compact source is an independently pinned product donor.
  # Stage its real approved bytes into our disposable fixture; do not mock
  # this pin or bypass the production path/rights checks.
  chrome_rel='runtime/p01-original-chrome-compact-v6.css'
  chrome_src=repository/'integrations/wow200'/chrome_rel
  approved_chrome=eng.pinned_source_bytes(chrome_src,eng.ORIGINAL_CHROME_COMPACT_BLOB)
  if approved_chrome is None:
   raise RuntimeError('TEST_APPROVED_CHROME_SOURCE_HOLD')
  chrome_dest=self.src/chrome_rel
  chrome_dest.parent.mkdir(parents=True,exist_ok=True)
  chrome_dest.write_bytes(approved_chrome)
  for rel in eng.OWNER1_D02_ENGINE:
   eng.OWNER1_D02_ENGINE[rel]["legacy_blob"]=manifest[rel]
  (self.src/'DONOR_BLOBS.json').write_text(json.dumps({'schema':'NOX_WOW200_OWNER_BLOB_PIN_V1','count':56,'files':manifest}))
  cat=self.root/'proposals/NOX-PACK01-50/catalog.json'
  cat.parent.mkdir(parents=True,exist_ok=True)
  cat.write_text(json.dumps({'status':'SOURCE_CANDIDATE_NOT_INTEGRATED','actions':[
   {'taskId':f'NIP01-{i+1:02}','routeId':f'chat.test{i+1}','category':'chat'} for i in range(50)
  ]}),encoding='utf-8')
  self.old_catalog_blob=eng.PACK01_CATALOG_BLOB
  eng.PACK01_CATALOG_BLOB=gitsha(cat.read_bytes())
  self.old_manifest_blob=eng.DONOR_MANIFEST_BLOB
  eng.DONOR_MANIFEST_BLOB=gitsha((self.src/'DONOR_BLOBS.json').read_bytes())
 def tearDown(self):
  D02.clear();D02.update(self.preimages)
  eng.DONOR_MANIFEST_BLOB=self.old_manifest_blob
  eng.PACK01_CATALOG_BLOB=self.old_catalog_blob
  eng.WOW_RUNTIME_BLOBS.clear()
  eng.WOW_RUNTIME_BLOBS.update(self.original_runtime_pins)
  eng.OWNER1_D02_ENGINE.clear();eng.OWNER1_D02_ENGINE.update(self.old_engine_pins)
  self.tmp.cleanup()
 def test_additive_preimage_and_readback(self):
  original={n:digest(self.stage/'Assets'/n) for n in D02}
  receipt=stage(self.stage,self.src)
  # 56 donors + 2 active D02 variants + 8 MENU + 9 P01 + 8 runtime + catalog + 2 HTML.
  expected=56+2+len(eng.MENU_V2_SHA256)+len(eng.P01_OWNER_BLOBS)+len(eng.WOW_RUNTIME_BLOBS)+3
  self.assertEqual(expected,86)
  self.assertEqual(receipt['count'],expected)
  self.assertEqual(len(receipt['files']),expected)
  self.assertEqual(len({f['path'] for f in receipt['files']}),expected)
  orb=(self.stage/'Assets/creative/wow200/runtime/home-guard.css').read_bytes()
  self.assertEqual(orb,(self.src/'runtime/home-guard.css').read_bytes())
  self.assertIn(b'NOX D02 ORB STEP01',orb)
  self.assertIn(b'pointer-events:none',orb)
  self.assertIn(b'prefers-reduced-motion:reduce',orb)
  self.assertEqual(receipt['menu_v2_atomic_source_sha256'],eng.MENU_V2_SHA256)
  self.assertTrue(receipt['p01_owner_source_staged'])
  self.assertFalse(receipt['p01_owner_native_mount_activated'])
  self.assertEqual(receipt['p01_owner_native_route_e2e'],'NOT_RUN')
  self.assertEqual(receipt['p01_owner_source_git_blobs'],eng.P01_OWNER_BLOBS)
  for relative in eng.P01_OWNER_BLOBS:
   target=self.stage/'Assets/creative/wow200'/relative
   self.assertEqual(target.read_bytes(),eng.pinned_source_bytes(self.root/relative,eng.P01_OWNER_BLOBS[relative]))
  for relative in eng.MENU_V2_SHA256:
   staged=self.stage/'Assets/creative/wow200/ui'/Path(relative).name
   self.assertEqual(staged.read_bytes(),eng.canonical_menu_bytes(self.root/relative))
  home=(self.stage/'Assets/index.html').read_text(encoding='utf-8')
  self.assertIn('creative/wow200/ui/onehost-menu-bindings.mjs',home)
  self.assertIn('creative/wow200/ui/selfbuilder-menu-v2.css',home)
  # R11 WOW V5 is physically staged with the original HOME and source pin.
  fx=(self.stage/'Assets/creative/wow200/ui/nox-r11-wow.css').read_text(encoding='utf-8')
  self.assertIn('NOX R11 WOW V5 / ORIGINAL WINDOWS SCENE',fx)
  self.assertIn('NOX R11 CINEMA V6 / OPEN PROPS',fx)
  self.assertIn('Copyright (c) 2021 Adam Argyle',fx)
  self.assertIn('@keyframes nox-cinema-v6-aurora',fx)
  self.assertIn('--nox-cinema-ease-out:cubic-bezier(.19,1,.22,1)',fx)
  self.assertIn('body[data-fx="ECO"]',fx)
  self.assertIn('@media(prefers-reduced-motion:reduce)',fx)
  self.assertIn('pointer-events:none',fx)
  self.assertIn('html body #nox-express-primary > button[data-nox-primary]',fx)
  self.assertIn('.nox-r11-enhanced .nox-r11-world::before',fx)
  self.assertIn('@media(prefers-reduced-motion:reduce)',fx)
  self.assertIn('body[data-fx="ECO"]',fx)
  self.assertEqual(digest(self.stage/'Assets/creative/wow200/ui/nox-r11-wow.css'),eng.MENU_V2_SHA256['ui/nox-r11-wow.css'])
  self.assertIn('creative/wow200/ui/selfbuilder-wow-workbench.css',home)
  self.assertEqual(receipt['pack01_catalog_routes'],50)
  self.assertEqual((self.stage/'Assets/creative/wow200/pack01-catalog.json').read_bytes(),(self.root/'proposals/NOX-PACK01-50/catalog.json').read_bytes())
  for rel in eng.OWNER1_D02_ENGINE:
   active=self.stage/'Assets/creative/wow200'/rel
   archive=self.stage/'Assets/creative/wow200/legacy/d02-pr30'/Path(rel).name
   self.assertEqual(active.read_bytes(),(self.root/rel).read_bytes())
   self.assertEqual(archive.read_bytes(),(self.src/rel).read_bytes())
   self.assertNotEqual(active.read_bytes(),archive.read_bytes())
  self.assertEqual(receipt['active_d02_engine'],'OWNER1_PR144_PINNED')
  self.assertFalse(receipt['legacy_d02_runtime_imported'])
  self.assertEqual({n:digest(self.stage/'Assets'/n) for n in D02},original)
  html=(self.stage/'Assets/creative/studio.html').read_text(encoding='utf-8')
  self.assertIn('wow200/runtime/loader.mjs',html)
  self.assertIn('creative/wow200/runtime/home-scene.mjs',(self.stage/'Assets/index.html').read_text(encoding='utf-8'))
  self.assertTrue(receipt['home_pr30_renderer_staged'])
  self.assertIn('wow200/proposals/NOX-WOW51-100/wow51-100.css',html)
  self.assertTrue((self.stage.parent/'WOW200_STAGE_RECEIPT.json').is_file())
  with self.assertRaisesRegex(ValueError,'ALREADY_INSTALLED'):stage(self.stage,self.src)
 def test_p01_menu10_source_drift_rejected_before_all_staging(self):
  file=self.root/'proposals/P01/WOW-MAX10/mount-p01.mjs'
  file.write_bytes(file.read_bytes()+b'// unapproved change\n')
  with self.assertRaisesRegex(ValueError,'P01_MENU10_SOURCE_BLOB_HOLD'):
   stage(self.stage,self.src)
  self.assertFalse((self.stage/'Assets/creative/wow200').exists())
 def test_p01_menu10_crlf_preserves_exact_approved_modules(self):
  file=self.root/'proposals/P01/WOW-MAX10/scene-contract.mjs'
  original=eng.pinned_source_bytes(file,eng.P01_OWNER_BLOBS['proposals/P01/WOW-MAX10/scene-contract.mjs'])
  self.assertIsNotNone(original)
  file.write_bytes(original.replace(b'\n',b'\r\n'))
  receipt=stage(self.stage,self.src)
  target=self.stage/'Assets/creative/wow200/proposals/P01/WOW-MAX10/scene-contract.mjs'
  self.assertEqual(target.read_bytes(),original)
  self.assertTrue(receipt['p01_owner_source_staged'])
 def test_windows_menu_crlf_normalizes_to_exact_pinned_content(self):
  path=self.root/'ui/selfbuilder-menu-v2.mjs'
  original=eng.canonical_menu_bytes(path)
  windows_bytes=original.replace(b'\n',b'\r\n')
  path.write_bytes(windows_bytes)
  stage(self.stage,self.src)
  published=self.stage/'Assets/creative/wow200/ui/selfbuilder-menu-v2.mjs'
  self.assertEqual(published.read_bytes(),original)
  self.assertEqual(path.read_bytes(),windows_bytes)
 def test_bare_carriage_return_is_rejected(self):
  path=self.root/'ui/selfbuilder-menu-v2.mjs'
  path.write_bytes(path.read_bytes().replace(b'\n',b'\r',1))
  with self.assertRaisesRegex(ValueError,'MENU_V2_UNEXPECTED_CARRIAGE_RETURN'):
   stage(self.stage,self.src)
  self.assertFalse((self.stage/'Assets/creative/wow200').exists())
 def test_checkout_crlf_donor_manifest_still_exact_git_blob(self):
  p=self.src/'DONOR_BLOBS.json'
  normalized=(json.dumps(json.loads(p.read_text(encoding='utf-8')),indent=2)+'\n').encode()
  p.write_bytes(normalized.replace(b'\n',b'\r\n'))
  eng.DONOR_MANIFEST_BLOB=gitsha(normalized)
  result=stage(self.stage,self.src)
  self.assertEqual(result['count'],86)
  self.assertEqual(len(result['files']),86)
  self.assertEqual(len({f['path'] for f in result['files']}),86)
 def test_checkout_crlf_donor_script_uses_pinned_canonical_bytes(self):
  p=self.src/'proposals/NOX-WOW51-100/catalog.mjs'
  normalized=p.read_bytes()
  p.write_bytes(normalized.replace(b'\n',b'\r\n'))
  stage(self.stage,self.src)
  staged=self.stage/'Assets/creative/wow200/proposals/NOX-WOW51-100/catalog.mjs'
  self.assertEqual(staged.read_bytes(),normalized)
 def test_unapproved_runtime_bytes_hold_before_any_staging(self):
  origin=self.src/'runtime/loader.mjs'
  origin.write_bytes(origin.read_bytes()+b'// unreviewed runtime change\\n')
  with self.assertRaisesRegex(ValueError,'WOW_RUNTIME_BLOB_HOLD:runtime/loader.mjs'):
   stage(self.stage,self.src)
  self.assertFalse((self.stage/'Assets/creative/wow200').exists())
 def test_original_pack01_catalog_is_pinned(self):
  file=self.root/'proposals/NOX-PACK01-50/catalog.json'
  file.write_text(file.read_text(encoding='utf-8')+'\\n',encoding='utf-8')
  with self.assertRaisesRegex(ValueError,'PACK01_CATALOG_PIN_HOLD'):stage(self.stage,self.src)
  self.assertFalse((self.stage/'Assets/creative/wow200').exists())
 def test_pack01_fifty_distinct_routes_hard_hold(self):
  file=self.root/'proposals/NOX-PACK01-50/catalog.json'
  obj=json.loads(file.read_text(encoding='utf-8'))
  obj['actions'][1]['routeId']=obj['actions'][0]['routeId']
  file.write_text(json.dumps(obj),encoding='utf-8')
  eng.PACK01_CATALOG_BLOB=gitsha(file.read_bytes())
  with self.assertRaisesRegex(ValueError,'PACK01_CATALOG_50_ROUTES_HOLD'):stage(self.stage,self.src)
  self.assertFalse((self.stage/'Assets/creative/wow200').exists())
 def test_owner1_d02_css_sha_drift_fail_closed(self):
  file=self.root/'proposals/NOX-CINEMA-FX/nox-cinema.css'
  file.write_bytes(b'unapproved css replacement')
  with self.assertRaisesRegex(ValueError,'OWNER1_D02_ENGINE_SHA_HOLD'):stage(self.stage,self.src)
  self.assertFalse((self.stage/'Assets/creative/wow200').exists())
 def test_pr30_legacy_css_sha_drift_fail_closed(self):
  file=self.src/'proposals/NOX-CINEMA-FX/nox-cinema.css'
  file.write_bytes(b'unapproved legacy css')
  with self.assertRaisesRegex(ValueError,'D02_LEGACY_ENGINE_SHA_HOLD'):stage(self.stage,self.src)
  self.assertFalse((self.stage/'Assets/creative/wow200').exists())
 def test_owner1_d02_engine_sha_drift_fail_closed(self):
  file=self.root/'proposals/NOX-CINEMA-FX/nox-cinema.mjs'
  file.write_bytes(b'unapproved replacement')
  with self.assertRaisesRegex(ValueError,'OWNER1_D02_ENGINE_SHA_HOLD'):stage(self.stage,self.src)
  self.assertFalse((self.stage/'Assets/creative/wow200').exists())
 def test_d02_corruption_fail_closed(self):
  (self.stage/'Assets/home.png').write_bytes(b'broken')
  with self.assertRaisesRegex(ValueError,'CANONICAL_D02_SHA_HOLD'):stage(self.stage,self.src)
  self.assertFalse((self.stage/'Assets/creative/wow200').exists())
 def test_donor_byte_drift_fail_closed(self):
  (self.src/'proposals/NOX-WOW51-100/catalog.mjs').write_bytes(b'modified')
  with self.assertRaisesRegex(ValueError,'WOW_DONOR_BLOB_IDENTITY_HOLD'):stage(self.stage,self.src)
  self.assertFalse((self.stage/'Assets/creative/wow200').exists())
 def test_path_traversal_fail_closed(self):
  p=self.src/'DONOR_BLOBS.json';obj=json.loads(p.read_text(encoding='utf-8'));obj['files'].pop(next(k for k in obj['files'] if '/fake_' in k));obj['files']['proposals/../../oops']='00';p.write_text(json.dumps(obj))
  eng.DONOR_MANIFEST_BLOB=gitsha(p.read_bytes())
  with self.assertRaisesRegex(ValueError,'UNSAFE_WOW_SOURCE_PATH'):stage(self.stage,self.src)
 def test_manifest_tampering_is_rejected_before_mutation(self):
  p=self.src/'DONOR_BLOBS.json'
  p.write_text(p.read_text(encoding='utf-8')+'\n')
  with self.assertRaisesRegex(ValueError,'DONOR_MANIFEST_PIN_HOLD'):stage(self.stage,self.src)
  self.assertFalse((self.stage/'Assets/creative/wow200').exists())
 def test_required_engine_missing_is_hard_hold(self):
  p=self.src/'DONOR_BLOBS.json';obj=json.loads(p.read_text(encoding='utf-8'))
  obj['files'].pop('proposals/NOX-CINEMA-FX/nox-cinema.mjs')
  obj['files']['proposals/NOX-WOW151-200/another_00.mjs']='f'*40
  p.write_text(json.dumps(obj));eng.DONOR_MANIFEST_BLOB=gitsha(p.read_bytes())
  with self.assertRaisesRegex(ValueError,'REQUIRED_ENGINE_MISSING_HOLD'):stage(self.stage,self.src)
  self.assertFalse((self.stage/'Assets/creative/wow200').exists())
if __name__=='__main__':unittest.main()

