"""Strict source/read-only acceptance of future module and R75 geometric donor.
Not E07 Windows visual/graphics acceptance or approval to change R1.
"""
from pathlib import Path
import unittest,json,re,math
from engine.studio import INDEX
from engine.integration import run_job
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'donors/R75_MENU10_HITBOX_ADDITIVE.css'
class WowUITests(unittest.TestCase):
 def test_no_external_code(self):
  self.assertNotIn('https://', INDEX)
  self.assertNotIn('fetch(\'https:',INDEX)
  self.assertIn('LOCAL · READ ONLY',INDEX)
 def test_ten_real_dom_buttons(self):
  self.assertEqual(len(re.findall(r'<button class="world"',INDEX)),10)
  self.assertIn('addEventListener(\'keydown\'',INDEX)
 def test_no_fake_193_functions(self):
  self.assertNotIn('193 ОБРАБОТЧИКОВ ГОТОВО',INDEX)
  self.assertIn('IDEA_UNVERIFIED',INDEX)
 def test_pagination_is_nine(self):
  self.assertIn('pageSize=9',INDEX)
  self.assertIn('id="more"',INDEX)
 def test_economy_motion(self):
  self.assertIn('prefers-reduced-motion:reduce',INDEX)
  self.assertIn('data-motion="ECO"',INDEX)
 def test_original_catalog_unchanged(self):
  data=json.loads((ROOT/'catalog/ideas_60.json').read_text('utf-8'))
  self.assertEqual(len(data),60)
  self.assertTrue(all(x['status']=='IDEA_UNVERIFIED' for x in data))
 def test_streams_are_real_readonly(self):
  x=run_job({'contract':'nox.oie.job.v1','action':'idea.list'})
  self.assertTrue(x['ok']);self.assertEqual(x['result']['count'],60)
  self.assertTrue(all(y.get('stream') for y in x['result']['ideas']))
 def test_immutable_no_backend_promote(self):
  for x in ['pilot.approve','business.launch','megablock1.pay']:
   self.assertFalse(run_job({'contract':'nox.oie.job.v1','action':x})['ok'])
 def test_donor_provenance(self):
  c=SOURCE.read_text('utf-8');self.assertIn('ead9b2b4',c);self.assertIn('24e5eecf7d55994f6b2e1f32c296305503a63d5a',c)
  self.assertIn('width:9.8%; height:17%',c)
 def test_donor_no_bbox_overlap_at_percent(self):
  p=[('work',47.3,12.5),('intelligence',29.1,20.1),('knowledge',19.1,37.2),('learning',20.1,56.5),('entertainment',33.7,76.6),('people',56.3,81.9),('creative',73.1,74.5),('business',82.1,55.2),('world',79.7,33.4),('pc',66.7,16)]
  for i,(a,x,y) in enumerate(p):
   for b,X,Y in p[i+1:]:
    self.assertTrue(abs(x-X)>=9.8 or abs(y-Y)>=17,f'bounding boxes intersect: {a} and {b}')
 def test_visual_hold_not_e07(self):
  self.assertIn('не подмена утверждённых HOME/MENU/WORK',INDEX)
  self.assertNotIn('E07 ACCEPTED',INDEX)
if __name__=='__main__':unittest.main()
