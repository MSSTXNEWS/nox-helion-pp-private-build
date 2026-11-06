"""Run on Windows after installation with python -m unittest tests.test_browser.
Requires Playwright and browser (download if absent). Skip gracefully if unavailable.
"""
import unittest,os
class BrowserSmoke(unittest.TestCase):
 def test_nox_chat_navigation_and_control(self):
  try:from playwright.sync_api import sync_playwright
  except ImportError:self.skipTest('Playwright not installed')
  url=os.environ.get('NOX_TEST_URL','http://127.0.0.1:18774/')
  import urllib.request
  try:
   with urllib.request.urlopen(url+'api/mega/health',timeout=2) as resp:
    if resp.status!=200:self.skipTest('NOX server not running')
  except Exception:self.skipTest('Browser QA requires launched NOX; run this test after START_NOX_READY.ps1')
  with sync_playwright() as p:
   try:browser=p.chromium.launch(headless=True,executable_path=os.environ.get('CHROMIUM_PATH') or None,args=['--no-sandbox'])
   except Exception as e:self.skipTest('Chromium unavailable: '+str(e)[:180])
   page=browser.new_page(viewport={'width':1440,'height':900})
   try:
    try:page.goto(url,timeout=15000)
    except Exception as err:
     if 'ERR_BLOCKED_BY_ADMINISTRATOR' in str(err):self.skipTest('Browser blocked by sandbox administrator')
     raise
    self.assertIn('NOX',page.title().upper())
    page.goto(url+'chat.html',timeout=15000)
    self.assertTrue(page.locator('#chatForm').count()==1)
    self.assertEqual(page.locator('#tags button').count(),12)
    page.locator('#tags button').first.click()
    self.assertTrue(page.locator('#prompt').input_value().strip())
    self.assertTrue(page.locator('#stop').count()==1)
    self.assertTrue(page.locator('.nox-addons').count()>=1)
    page.goto(url+'training.html',timeout=15000)
    self.assertTrue(page.locator('.nox-addons').count()>=1)
   finally:browser.close()
if __name__=='__main__':unittest.main()