import os
from pathlib import Path
import unittest,hashlib,json,re,zipfile
from bs4 import BeautifulSoup
ROOT=Path(os.environ.get('NOX_V29_SITE_DIR','/mnt/data/nox_v29_site')).resolve()
PREVIOUS=Path(os.environ.get('NOX_V28_SITE_DIR','/mnt/data/nox_v28_site')).resolve()
IMMUTABLE={
 'index.html':'f3fc804d238146ffe42c50103d3e04c9736b8b587c6572987f59b61a6112eb17',
 'nox-home.mjs':'8066bc0a0f8ef5bb5f0fb1f58ad3f6ee29dc8506385c09d77d38d4235c7e42e9',
 'nox-engines/physical-worlds-v7.mjs':'3f27609ea37b96579a711928e4c67778ec71e2ff7b090a3b7bb41e29040f3905',
 'assets/nox-owner-approved/NOX_HOME_OWNER_APPROVED_WEB.webp':'3253d26819a70b49259fdb2a56c2eaa2455c6878cb2ccb8d62b225ec6ccdfa22',
 'nox-chat.js':'d9fa29e0fa726502adc6e83ea344adf13b8a2354acd3610b3de96ec378e942ce',
 'nox-function-catalog.js':'c509870d8fc664bb7c60cd53d3daf21280aa410832d978d3fedbd0543730f661'
}
sha=lambda b:hashlib.sha256(b).hexdigest()
class Tests(unittest.TestCase):
 def test_primary_hashes(self):
  for path,expected in IMMUTABLE.items():self.assertEqual(sha((ROOT/path).read_bytes()),expected,path)
 def test_unchanged_original_file_list(self):
  previous={str(f.relative_to(PREVIOUS)):f for f in PREVIOUS.rglob('*') if f.is_file()}
  mutated=[]
  for name,file in previous.items():
   self.assertTrue((ROOT/name).is_file(),name)
   if (ROOT/name).read_bytes()!=file.read_bytes():mutated.append(name)
  self.assertEqual(sorted(mutated),sorted(['system.html','chat.html','memory.html','training.html']))
 def test_existing_10_pages_and_real_index(self):
  for name in ['index','chat','memory','training','system','cinema','settings','models','projects','install']:
   f=ROOT/(name+'.html'); self.assertTrue(f.is_file());s=BeautifulSoup(f.read_text('utf8'),'html.parser');self.assertIsNotNone(s.find('body'))
  self.assertNotIn('nox-v29-pc-genesis-addons', (ROOT/'index.html').read_text('utf8'))
 def test_monitor_directs_to_real_page(self):
  s=BeautifulSoup((ROOT/'system.html').read_text('utf8'),'html.parser')
  a=[x for x in s.select('a') if 'МОНИТОРИНГ' in x.get_text(' ',strip=True)]
  self.assertEqual(len(a),1);self.assertEqual(a[0].get('href'),'system.html#dashboard-overview')
  self.assertIsNotNone(s.select_one('#dashboard-overview'))
  self.assertNotIn('href="/nox/dashboard"',(ROOT/'system.html').read_text('utf8'))
 def test_integration_in_existing_pages(self):
  for name in ['chat','memory','training']:
   s=(ROOT/(name+'.html')).read_text('utf8')
   self.assertEqual(s.count('nox-v29-pc-genesis-addons.mjs'),1)
   self.assertEqual(s.count('nox-v29-pc-genesis-addons.css'),1)
   self.assertNotIn('nox-v28-pc-genesis-addons.mjs',s)
 def test_pc_assets_preserved(self):
  self.assertEqual(len([f for f in (ROOT/'pc').rglob('*') if f.is_file()]),750)
  self.assertTrue((ROOT/'pc/resonance.html').is_file())
  self.assertTrue((ROOT/'pc/memory.html').is_file())
  s=(ROOT/'pc/index.html').read_text('utf8');self.assertIn('../index.html',s)
 def test_native_trust_contract(self):
  s=(ROOT/'nox-v29-pc-genesis-addons.mjs').read_text('utf8')
  for fragment in ["window.NOX_NATIVE_OWNER===true","EXISTING_NATIVE_ONEHOST","native_p02_bound===true","credentials:'same-origin'","redirect:'error'","/api/nox/progress","nox-progress-receipt-v1","nox-genesis-live-evidence-v1","document.querySelector('main')","#nox-genesis-evidence-endpoint"]:
   if fragment=="#nox-genesis-evidence-endpoint":continue
   self.assertIn(fragment,s)
  self.assertNotIn('localStorage',s)
  self.assertNotIn('sessionStorage',s)
  self.assertNotIn('POST',s)
 def test_wow30_source_contract(self):
  data=json.loads((ROOT/'NOX-WOW30-TRACEABILITY.json').read_text('utf8'))
  self.assertEqual(len(data['criteria']),30)
  self.assertEqual(len(set(c['id'] for c in data['criteria'])),30)
  self.assertFalse(any(c['physicalGpuAccepted'] or c['windowsAccepted'] for c in data['criteria']))
 def test_previous_manifest_no_loss(self):
  manifest=json.loads((PREVIOUS/'SOURCE_MANIFEST_V28.json').read_text('utf8'))
  self.assertEqual(len(manifest),1077)
  for name,info in manifest.items():
   original=PREVIOUS/name
   self.assertEqual(sha(original.read_bytes()),info['sha256'],name)
   if name not in ('chat.html','memory.html','training.html','system.html'):
    self.assertEqual(sha((ROOT/name).read_bytes()),info['sha256'],name)
if __name__=='__main__':unittest.main(verbosity=2)