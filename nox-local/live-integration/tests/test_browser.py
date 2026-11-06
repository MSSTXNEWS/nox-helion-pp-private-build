"""Run after launching NOX integrated on 18775; Playwright is optional but recommended."""
import os, unittest, urllib.request
class BrowserSmoke(unittest.TestCase):
 def test_page_navigation_buttons_and_overlay(self):
  try:from playwright.sync_api import sync_playwright
  except ImportError:self.skipTest('Playwright not installed on the current PC')
  url=os.environ.get('NOX_TEST_URL','http://127.0.0.1:18775/').rstrip('/')+'/'
  try:
   with urllib.request.urlopen(url+'api/nox/pages',timeout=3) as res:
    if res.status!=200:self.skipTest('NOX integrated server not active')
  except OSError:self.skipTest('NOX integrated server not started')
  with sync_playwright() as p:
   try:b=p.chromium.launch(headless=True,executable_path=os.environ.get('CHROMIUM_PATH') or None,args=['--no-sandbox'])
   except Exception as e:self.skipTest('Chromium absent: '+str(e)[:160])
   page=b.new_page(viewport={'width':1440,'height':900})
   try:
    for route in ('','chat.html','training.html','models.html','memory.html','system.html','install.html','projects.html','settings.html'):
     with self.subTest(route=route):
      try:page.goto(url+route,timeout=15000)
      except Exception as e:
       if 'ERR_BLOCKED_BY_ADMINISTRATOR' in str(e):self.skipTest('Chromium sandbox blocks localhost')
       raise
      self.assertTrue(page.title().startswith('NOX'))
    page.goto(url+'index.html',timeout=15000)
    self.assertTrue(page.locator('#openCoreChat').count()==1)
    page.locator('#openCoreChat').click()
    self.assertTrue(page.url.endswith('chat.html'))
    self.assertEqual(page.locator('#tags button').count(),12)
    page.locator('#tags button').first.click()
    self.assertTrue(page.locator('#prompt').input_value().strip())
    self.assertTrue(page.locator('#stop').count()==1)
    self.assertLessEqual(page.locator('#nox-cinema-hud').count(),1)
    self.assertEqual(page.locator('.nox-addons').count(),0)
    page.goto(url+'models.html',timeout=15000)
    self.assertTrue(page.locator('#nox-live-content').count()==1)
   finally:b.close()
if __name__=='__main__':unittest.main()