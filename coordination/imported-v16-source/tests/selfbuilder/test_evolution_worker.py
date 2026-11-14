import tempfile
import unittest
import json
from pathlib import Path
from nox_selfbuilder.evolution import EvolutionWorker, EvolutionHold
from nox_selfbuilder.builder import SelfBuilderHold

HEAD='f74300d19314b41a20f0c959dc59309f7e93d409'
SOURCE='NOX-PRODUCT-OWNER-SPEC'

class Host:
    def __init__(self,tasks=(),enabled=True,approve=True):
        self.tasks=list(tasks)
        self.enabled=enabled
        self.approve=approve
        self.stopped=False
        self.results=[]
        self.acks=[]
        self.beats=[]
        self.call_count=0
        self.s03_saved=True
        self.due=False
        self.suggestions=[]
        self.discovery_record=[]
    def release_ticket(self, task):
        return {'task_id':task['task_id'],'owner_id':'1','head':task['source_head'],
        'existing_code_checked':True,'critical_sources_complete':True,
        'overlapping_owner_paths':False,'required_scope_fixed':True,
        'code_preimage_sha':'ABSENT'}
    def current_source_head(self):return HEAD
    def discovery_due(self):return self.due
    def discover_opportunities(self,limit):return self.suggestions[:limit]
    def record_opportunities(self,items):self.discovery_record.extend(items);return True
    def worker_enabled(self): return self.enabled
    def stop_requested(self): return self.stopped
    def claim_task(self): return self.tasks.pop(0) if self.tasks else None
    def native_authorize(self,session,route,args): return self.approve
    def recall(self,session,task,source_ids): return [{'source_id':SOURCE,'verified':True,'text':'Approved source with exact requirement and owner policy'}]
    def generate(self,session,prompt):
        self.call_count+=1
        return json.dumps({'module_path':'extensions/route_status/action.py',
              'code':'def status():\n    return "ready"\n',
              'tests':'def test_status():\n    assert 1 == 1\n',
              'rationale':'A new verified minimal status action under scoped extension',
              'sources':[SOURCE]})
    def record_result(self,tid,status,receipt):
        self.results.append((tid,status,receipt));return self.s03_saved
    def finish_task(self,tid,status):self.acks.append((tid,status));return True
    def heartbeat(self,status):self.beats.append(status)
    def reflect(self,task):return {'verified':True,'lesson':'Known errors should not be repeated','task_id':task['task_id']}
    def forge_preflight(self,task):return {'status':'HOLD'}


def job(kind='SELF_WRITE'):
    return {'task_id':'SB-001','kind':kind,'source_head':HEAD,'session':object(),
            'task':'Create a real status command in the approved existing NOX UI'}

class Tests(unittest.TestCase):
    def test_background_idle_does_not_generate(self):
        with tempfile.TemporaryDirectory() as t:
            h=Host()
            w=EvolutionWorker(h,workspace=t,idle_seconds=.2)
            self.assertEqual(w.run(max_ticks=3,sleeper=lambda _:None),3)
            self.assertEqual(h.call_count,0)
            self.assertEqual(h.beats,['IDLE']*3)
    def test_active_selfwrite_staging_not_live(self):
        with tempfile.TemporaryDirectory() as t:
            h=Host([job()])
            w=EvolutionWorker(h,workspace=t,idle_seconds=.2)
            result=w.tick()
            self.assertEqual(result.status,'CANDIDATE_REVIEW_REQUIRED')
            self.assertEqual(h.acks,[('SB-001','CANDIDATE_REVIEW_REQUIRED')])
            self.assertEqual(len(list(Path(t).glob('SB-*/candidate.py'))),1)
            self.assertEqual(len(list(Path(t).glob('SB-*/receipt.json'))),1)
            self.assertEqual(h.call_count,1)
    def test_no_opt_in(self):
        with tempfile.TemporaryDirectory() as t:
            h=Host([job()],enabled=False)
            with self.assertRaises(EvolutionHold):EvolutionWorker(h,workspace=t).tick()
            self.assertEqual(h.call_count,0)
            self.assertEqual(h.results,[])
    def test_stop(self):
        with tempfile.TemporaryDirectory() as t:
            h=Host([job()]);h.stopped=True
            with self.assertRaises(EvolutionHold):EvolutionWorker(h,workspace=t).tick()
            self.assertEqual(len(h.tasks),1)
    def test_reflection(self):
        with tempfile.TemporaryDirectory() as t:
            h=Host([job('REFLECT')]);r=EvolutionWorker(h,workspace=t).tick()
            self.assertEqual(r.status,'REFLECTION_REVIEW_REQUIRED')
            self.assertEqual(h.call_count,0)
            self.assertTrue(r.receipt['verified'])
    def test_denied_reflection(self):
        with tempfile.TemporaryDirectory() as t:
            h=Host([job('REFLECT')],approve=False);r=EvolutionWorker(h,workspace=t).tick()
            self.assertEqual(r.status,'HOLD')
    def test_forge_no_gpu(self):
        with tempfile.TemporaryDirectory() as t:
            x=job('FORGE_REVIEW');x.update(dataset_sha256='0'*64,base_sha256='1'*64,rights_id='consent-review-1')
            h=Host([x]);r=EvolutionWorker(h,workspace=t).tick()
            self.assertEqual(r.status,'HOLD')
            self.assertIn('FORGE_NATIVE_GPU_HOLD',r.receipt['reason'])
    def test_no_s03_ack(self):
        with tempfile.TemporaryDirectory() as t:
            h=Host([job()]);h.s03_saved=False
            with self.assertRaises(EvolutionHold):EvolutionWorker(h,workspace=t).tick()
            self.assertEqual(h.acks,[])
    def test_unknown_kind_holds_before_generator(self):
        with tempfile.TemporaryDirectory() as t:
            h=Host([job('PURCHASE_CLOUD')])
            with self.assertRaises(EvolutionHold):EvolutionWorker(h,workspace=t).tick()
            self.assertEqual(h.call_count,0)
    def test_stopped_worker_no_new_tasks(self):
        with tempfile.TemporaryDirectory() as t:
            h=Host([job()]);w=EvolutionWorker(h,workspace=t);w.stop()
            with self.assertRaises(EvolutionHold):w.tick()
            self.assertEqual(h.call_count,0)
    def test_bad_host(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(EvolutionHold):EvolutionWorker(object(),workspace=t)
    def test_idle_discovery_writes_only_s03_suggestions(self):
        with tempfile.TemporaryDirectory() as t:
            h=Host();h.due=True
            h.suggestions=[{'source_id':SOURCE,'summary':'An approved missing feature may be useful','evidence_verified':True}]
            r=EvolutionWorker(h,workspace=t).tick()
            self.assertEqual(r.status,'OPPORTUNITIES_REVIEW_REQUIRED')
            self.assertEqual(len(h.discovery_record),1)
            self.assertEqual(h.call_count,0)
            self.assertEqual(list(Path(t).iterdir()),[])
    def test_discovery_unverified_fails_closed(self):
        with tempfile.TemporaryDirectory() as t:
            h=Host();h.due=True
            h.suggestions=[{'source_id':SOURCE,'summary':'Unknown','evidence_verified':False}]
            with self.assertRaises(EvolutionHold):EvolutionWorker(h,workspace=t).tick()
            self.assertEqual(h.discovery_record,[])
    def test_owner_review_learning_record_uses_s03(self):
        with tempfile.TemporaryDirectory() as t:
            x=job('REVIEW_LESSON');x.update(run_id='SB-0',
                proposal_receipt={'status':'SOURCE_CANDIDATE_REVIEW_REQUIRED_NOT_EXECUTED', 'code_sha256':'0'*64},
                reviewer_source_id='owner-verified-review-1',outcome='ACCEPTED')
            h=Host([x]);r=EvolutionWorker(h,workspace=t).tick()
            self.assertEqual(r.status,'LESSON_READY_FOR_EXISTING_S03')
            self.assertFalse(r.receipt['S03_WRITE_PERFORMED'])
            self.assertEqual(h.acks,[('SB-001','LESSON_READY_FOR_EXISTING_S03')])
            self.assertFalse(r.receipt['weights_updated'])
    def test_worker_config_no_external_autonomous(self):
        p=Path(__file__).resolve().parents[2]/'contracts'/'provider_capabilities.json'
        r=json.loads(p.read_text(encoding='utf8'))
        ext=[v for v in r['providers'] if v['type']=='external_client']
        self.assertTrue(all(not v['autonomous_loop_eligible'] for v in ext))
        self.assertTrue(next(x for x in r['providers'] if x['id']=='existing_p02_ollama')['autonomous_loop_eligible'])

if __name__=='__main__':unittest.main()
