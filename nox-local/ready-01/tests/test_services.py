import os,sys,json,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import nox_services as s
class TestServices(unittest.TestCase):
 def test_unconfigured_trainer_hold(self):
  self.assertFalse(s.training_status()['can_start'])
 def test_unconfigured_push_hold(self):
  self.assertFalse(s.push_status()['browser_close_delivery_verified'])
 def test_training_log_only_numbers(self):
  self.assertEqual(s.parse_training_line('{"loss":0.23,"epoch":2,"secret":"x"}'),{'loss':0.23,'epoch':2})
  self.assertIsNone(s.parse_training_line('badline'))
 def test_path_boundary(self):
  self.assertFalse(s.inside('C:\\OTHER\\secret.db','C:\\NOX_HELION'))
 def test_s03_no_write(self):
  self.assertNotEqual(s.s03_status()['status'],'WRITABLE')
if __name__=='__main__':unittest.main()