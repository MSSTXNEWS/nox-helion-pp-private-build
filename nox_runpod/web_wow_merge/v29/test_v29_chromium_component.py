import os
"""Real Chromium component interaction with actual V29 JS, without localhost navigation.
API fixtures are TEST-ONLY; never claim live OneHost, native S03 or hardware acceptance.
"""
from playwright.sync_api import sync_playwright
from pathlib import Path
import unittest
ROOT=Path(os.environ.get('NOX_V29_SITE_DIR','/mnt/data/nox_v29_site')).resolve()
SCRIPT=(ROOT/'nox-v29-pc-genesis-addons.mjs').read_text('utf8')
CSS=(ROOT/'nox-v29-pc-genesis-addons.css').read_text('utf8')
class BrowserTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.p=sync_playwright().start();cls.browser=cls.p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
 @classmethod
 def tearDownClass(cls):cls.browser.close();cls.p.stop()
 def page(self,kind,width=390,native=False):
  pg=self.browser.new_page(viewport={'width':width,'height':844})
  pg.set_content(f'<!doctype html><html><body data-page="{kind}"><main><div class="nox-document-panel" id="reader"><input id="docSearch"></div></main></body></html>')
  pg.add_style_tag(content=CSS)
  if native:pg.evaluate('window.NOX_NATIVE_OWNER=true')
  pg.add_script_tag(content=SCRIPT,type='module')
  pg.wait_for_selector('#nox-v29-addons',timeout=4000)
  return pg
 def test_public_hold_three_pages_both_viewports(self):
  for width in (390,1440):
   for kind,expected in [('chat',5),('memory',5),('training',2)]:
    with self.subTest(page=kind,width=width):
     pg=self.page(kind,width)
     calls=[]
     pg.on('request',lambda req:calls.append(req.url))
     self.assertEqual(pg.locator('[data-nox-pc-action]').count(),expected)
     pg.locator('[data-nox-pc-action="genesis"]').click()
     self.assertIn('HOLD',pg.locator('.nox-v29-result').inner_text())
     self.assertEqual(pg.evaluate('window.NOX_WEB_V29_ADDONS.diagnostics().trustedNative'),False)
     self.assertFalse(any('/api/' in url for url in calls),'Public preview sent unauthorized API request')
     self.assertEqual(pg.locator('iframe').count(),0,'Another PC chat embedded')
     pg.close()
 def test_native_fixtures_never_claim_gpu(self):
  pg=self.page('chat',1440,True)
  pg.evaluate('''window.__NOX_TEST_LOG=[];window.fetch=async (url,opts)=>{
   window.__NOX_TEST_LOG.push({url,method:opts?.method||'GET'});
   let v=url==='/api/nox/status'?{backend:'EXISTING_NATIVE_ONEHOST',native_p02_bound:true,primary_model:'NOX'}:
   url==='/api/nox/progress'?{schema:'nox-progress-receipt-v1',status:'VERIFIED_CHECKPOINT_STEPS',model:'NOX',studentWeightsSha256:'a'.repeat(64),completedSteps:10,targetSteps:100,weightUpdateVerified:true,windowsSyncVerified:false,qualityGainVerified:false}:
   {status:'HOLD',reason:'OFFLINE_FIXTURE'};
   return {ok:true,status:200,headers:new Headers({'content-type':'application/json'}),text:async()=>JSON.stringify(v)};
  };''')
  pg.locator('[data-nox-pc-action="genesis"]').click()
  pg.wait_for_function("document.querySelector('.nox-v29-result').textContent.includes('Собственные веса SHA256')")
  self.assertIn('НЕ НЕЗАВИСИМЫЙ GPU PASS',pg.locator('.nox-v29-result').inner_text())
  self.assertEqual(pg.evaluate('window.NOX_WEB_V29_ADDONS.diagnostics().liveGpuAccepted'),False)
  q=pg.evaluate('window.__NOX_TEST_LOG')
  self.assertEqual([x['url'] for x in q if x['url'] is not None],['/api/nox/status','/api/nox/progress'])
  self.assertTrue(all(x['method']=='GET' for x in q if x['url'] is not None))
  pg.close()
 def test_mismatched_owner_blocks_addon(self):
  pg=self.page('memory',390,True)
  pg.evaluate('''window.__NOX_TEST_LOG=[];window.fetch=async (url,opts)=>{
   window.__NOX_TEST_LOG.push(url);
   let v={backend:'UNTRUSTED_SERVER',native_p02_bound:false,primary_model:'NOX'};
   return {ok:true,status:200,headers:new Headers({'content-type':'application/json'}),text:async()=>JSON.stringify(v)};};''')
  pg.locator('[data-nox-pc-action="pc-s03"]').click()
  pg.wait_for_function("document.querySelector('.nox-v29-result').textContent.includes('не подтверждена идентичность')")
  self.assertEqual([x for x in pg.evaluate('window.__NOX_TEST_LOG') if x is not None],['/api/nox/status'])
  pg.close()
if __name__=='__main__':unittest.main(verbosity=2)