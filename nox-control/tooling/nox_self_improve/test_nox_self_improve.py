import importlib.util,json,tempfile,unittest,datetime
from pathlib import Path
root=Path(__file__).resolve().parent
def load(name):
 spec=importlib.util.spec_from_file_location(name,root/(name+'.py')); m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
journal=load('journal');watch=load('relay_watchdog');reconcile=load('ingest_native_queue')
class GuardTests(unittest.TestCase):
 def test_stop_blocks_restart(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d,'stop');p.write_text('1')
   cfg={'stop_contract_verified':True,'stop_paths':[str(p)],'existing_dispatcher_owner_cas_verified':True,
       'services':[{'name':'service','allowlisted':True,'restart_argv':['supervisorctl','restart','service']}]}
   self.assertEqual(watch.step(cfg)['services'][0]['action'],'HOLD_OWNER_STOP_OR_MAINTENANCE_PRESENT')
 def test_default_fails_closed(self):
  self.assertFalse(watch.gates({})[0])
 def test_journal_requires_independent_verifier(self):
  with tempfile.TemporaryDirectory() as d:
   db=journal.connect(str(Path(d,'j.sqlite')))
   journal.record(db,'T1','e1','ERROR','404')
   journal.record(db,'T1','e2','ERROR','404')
   self.assertEqual(journal.repeated(db,2)[0]['count'],2)
   with self.assertRaises(ValueError):journal.record(db,'T1','e3','ACCEPTED',verified=True,owner_receipt='x')
 def test_ingest_requires_real_ids_and_verifier(self):
  c={'cards':[{'id':'1A01','category':'Чат'}]}
  r=reconcile.reconcile({'items':[{'id':'1A01','status':'done'},{'id':'1A01','status':'done'},{'status':'done'}]},c)
  self.assertEqual(r['actual_unique_native_ids_in_snapshot'],1)
  self.assertFalse(r['records'][0]['accepted'])
  with self.assertRaises(ValueError):reconcile.reconcile({'count':1492},c)
if __name__=='__main__':unittest.main()
