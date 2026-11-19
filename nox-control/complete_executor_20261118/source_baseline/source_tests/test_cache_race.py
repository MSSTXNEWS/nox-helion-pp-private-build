"""Actual current V38 cache, synchronized threads, no native S03/model claims."""
import argparse,concurrent.futures,dataclasses,importlib.util,json,sys,threading,types,unittest
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--runtime',type=Path,required=True);parser.add_argument('--v38',type=Path,required=True);args,rest=parser.parse_known_args()
pkg=types.ModuleType('a1_v38');pkg.__path__=[str(args.v38.resolve())];sys.modules[pkg.__name__]=pkg
spec=importlib.util.spec_from_file_location('a1_v38.durable_runtime',args.runtime);runtime=importlib.util.module_from_spec(spec);sys.modules[spec.name]=runtime;spec.loader.exec_module(runtime)
Session=runtime.Session;Cache=runtime.WarmS03Cache
S=Session('nox','owner','chat');OTHER=Session('nox','owner','other')
def row(s=S,text='old'):
 return {'id':'r','verified':True,'superseded':False,'tenant':s.tenant,'principal':s.principal,'chat_id':s.chat_id,'segment':'M2','content':text}
class Revocation(unittest.TestCase):
 def race(self,phase,global_invalidate=False,unrelated=False,bypass=False):
  entered=threading.Event();release=threading.Event();first=[True];calls=[];revoked=[False]
  def pause():
   if first[0]:
    first[0]=False;entered.set()
    if not release.wait(2):raise RuntimeError('fixture release deadline')
  def revision(s):
   if phase in ('revision','revision_error') and first[0]:
    pause()
    if phase=='revision_error':raise RuntimeError('revision revoked')
   return 'unchanged-db-revision'
  def recall(s,p,l):
   # Capture a result before the invalidation; DB revision may stay identical.
   value='fresh' if revoked[0] else 'old';calls.append(value)
   if phase=='recall':pause()
   return [row(s,value)]
  cache=Cache(recall,None if bypass else revision)
  with concurrent.futures.ThreadPoolExecutor(max_workers=1) as workers:
   task=workers.submit(cache,S,'question',4)
   try:
    self.assertTrue(entered.wait(2),'callback not reached')
    cache.invalidate(None if global_invalidate else OTHER if unrelated else S)
    revoked[0]=not unrelated
   finally:release.set()
   if unrelated:self.assertEqual(task.result(2)[0]['content'],'old')
   else:
    with self.assertRaisesRegex(RuntimeError,'HOLD_S03_CACHE_INVALIDATED_DURING_READ'):task.result(2)
   if phase in ('revision','revision_error') and not unrelated:
    self.assertEqual(calls,[],'revoked native S03 read must not start after revision callback')
  value=cache(S,'question',4)
  self.assertEqual(value[0]['content'],'old' if unrelated else 'fresh')
  self.assertEqual(len(calls),1 if unrelated or phase in ('revision','revision_error') else 2)
 def test_scope_revoke_during_revision_lookup_cannot_repopulate(self):self.race('revision')
 def test_failed_revision_callback_after_revoke_must_not_fallback_to_recall(self):self.race('revision_error')
 def test_scope_revoke_during_recall_cannot_return_stale(self):self.race('recall')
 def test_global_revoke_fences_uncached_read(self):self.race('recall',global_invalidate=True,bypass=True)
 def test_unrelated_scope_revoke_keeps_other_read_and_cache_valid(self):self.race('recall',unrelated=True)
 def test_existing_persona_and_language_isolation_preserved(self):
  calls=[]
  def recall(s,p,l):calls.append(s);return [row(s,str((s.language,s.persona_enabled,s.persona_id)))]
  cache=Cache(recall,lambda s:'same-revision')
  scopes=[S,dataclasses.replace(S,persona_enabled=True,persona_id='KV'),dataclasses.replace(S,persona_enabled=True,persona_id='AM'),dataclasses.replace(S,language='es')]
  values=[cache(s,'same',4) for s in scopes]
  self.assertEqual(len({v[0]['content'] for v in values}),4)
  self.assertEqual([cache(s,'same',4) for s in scopes],values);self.assertEqual(len(calls),4)
 def test_callback_exception_does_not_poison_next_recall(self):
  calls=[]
  def recall(s,p,l):
   calls.append(1)
   if len(calls)==1:raise OSError('source read failed')
   return [row(s,'fresh')]
  cache=Cache(recall,lambda s:'r')
  with self.assertRaises(OSError):cache(S,'q',4)
  cache.invalidate(S);self.assertEqual(cache(S,'q',4)[0]['content'],'fresh')
  self.assertEqual(cache(S,'q',4)[0]['content'],'fresh');self.assertEqual(len(calls),2)
if __name__=='__main__':unittest.main(argv=[sys.argv[0],*rest])
