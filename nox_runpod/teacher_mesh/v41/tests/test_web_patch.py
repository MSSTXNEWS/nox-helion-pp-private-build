import unittest, pathlib, json, hashlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
class ExistingWebTests(unittest.TestCase):
 def test_original_routes_preserved(self):
  for n in ('site/training.html','site/pc/training.html'):
   s=(ROOT/'web'/n).read_text('utf8')
   self.assertIn('nox-progress-panel.js',s)
   self.assertIn('nox-learning-3axes.js',s)
   self.assertIn('nox-learning-3axes.css',s)
   self.assertIn('NOX HELION',s)
   self.assertEqual(s.count('nox-learning-3axes.js'),1)
 def test_source_contract_hash_matches(self):
  contract=json.loads((ROOT/'source_contract/WEB_V29_3_BASELINE.json').read_text('utf8'))
  for p,v in contract['web_paths'].items():
   self.assertEqual(hashlib.sha256((ROOT/'web'/p).read_bytes()).hexdigest(),v['patched_sha256'])
 def test_no_fabricated_dashboard(self):
  d=json.loads((ROOT/'web/nox-learning-3axes-dashboard.json').read_text('utf8'))
  self.assertIsNone(d['overall']['percent']);self.assertEqual(d['source_state'],'SOURCE_READ')
  self.assertTrue(all(v['state']=='HOLD' for v in d['axes'].values()))
 def test_no_second_backend(self):
  s=(ROOT/'web/nox-learning-3axes.js').read_text('utf8')
  self.assertEqual(s.count('http://'),1)  # SVG namespace only, not an API call
  self.assertIn("'./nox-learning-3axes-dashboard.json'",s)
 def test_six_queues_existing_only(self):
  d=json.loads((ROOT/'training/NOX_SIX_LANES.json').read_text('utf8'))
  self.assertEqual(len(d['lanes']),6);self.assertEqual(d['scheduler'],'EXISTING_NOX_ONEHOST_ONLY')
