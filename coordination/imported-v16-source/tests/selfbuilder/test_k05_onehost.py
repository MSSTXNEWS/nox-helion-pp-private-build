"""Actual original S03 SQLite and temp Git; injected model is a test double."""
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from dataclasses import dataclass
from nox_selfbuilder.onehost_store import OneHostStoreActor
from nox_selfbuilder.onehost_queue import NativeWorkQueue, NativeQueueHold
from nox_selfbuilder.onehost_builder import OneHostSelfBuilder
from nox_selfbuilder.background_forge import ForgeJob
from helion.storage import Store

@dataclass(frozen=True)
class Session:
    tenant:str='local';principal:str='test-owner';chat_id:str='test-chat'
    allowed:frozenset=frozenset({'chat.commands'})
    def validate(self):pass

class Integrated(unittest.TestCase):
    def test_original_s03_git_candidate_owner_review_and_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);repo=root/'repo';repo.mkdir();stage=root/'stage';stage.mkdir()
            text='def approved_source():\n    return "owner approved reference"\n'
            (repo/'approved.py').write_text(text)
            def git(*args):
                return subprocess.check_output(['git','-C',str(repo),*args],stderr=subprocess.DEVNULL,text=True).strip()
            git('init');git('config','user.email','fixture@example.invalid');git('config','user.name','Fixture')
            git('add','approved.py');git('commit','-m','fixture')
            head=git('rev-parse','HEAD');source='git:'+head+':approved.py'
            scope={'project_id':'default','persona_id':'persona.kairen_voss','core_id':'core.core'}
            db=root/'helion.sqlite3';session=Session()
            with OneHostStoreActor(lambda:Store(db)) as actor:
                queue=NativeWorkQueue(actor,authorize=lambda *_:True,stop_requested=lambda:False)
                model_calls=[]
                def model(_session,request):
                    model_calls.append(request)
                    return json.dumps({'files':[{'path':'extensions/verified/action.py','content':'def action():\n    return 1\n'}],
                       'source_ids':[source],'rationale':'An additive candidate from exact source evidence.'})
                service=OneHostSelfBuilder(queue=queue,coder=model,memory_scope=lambda s:scope,
                    authorize=lambda *_:True,stop_requested=lambda:False,source_root=repo,workspace=stage,source_paths=['approved.py'])
                response=service.command(session,{'action':'selfbuilder.propose','task':'Create an additive verified source command'})
                self.assertTrue(response['ack']);queue.close()
                row=queue.get(session,response['task_id'])
                self.assertEqual(row['state'],'CANDIDATE_REVIEW_REQUIRED')
                self.assertEqual(len(model_calls),1)
                self.assertEqual(model_calls[0]['source_evidence'][0]['verification'],'S03_OWNER_FACT_MATCHED_EXACT_GIT_HEAD')
                self.assertEqual(git('rev-parse','HEAD'),head)
                self.assertFalse((repo/'extensions').exists())
                receipt=row['result']['receipt']
                self.assertTrue((stage/receipt['run_id']/'candidate.patch').is_file())
                reviewed=service.command(session,{'action':'selfbuilder.feedback','task_id':response['task_id'],'outcome':'ACCEPTED'})
                self.assertTrue(reviewed['S03_WRITE_PERFORMED']);self.assertFalse(reviewed['integrated'])
                self.assertEqual(actor.call(lambda store:store.tasks())[0]['status'],'DRAFT')
                with self.assertRaises(PermissionError):queue.get(Session(principal='another-owner'),response['task_id'])
            with OneHostStoreActor(lambda:Store(db)) as actor:
                restored=NativeWorkQueue(actor,authorize=lambda *_:True,stop_requested=lambda:False)
                row=restored.get(session,response['task_id'])
                self.assertEqual(row['state'],'OWNER_ACCEPTED')
                self.assertEqual(row['result']['lesson']['patch_sha256'],receipt['patch_sha256'])
                self.assertEqual(actor.call(lambda s:s.conn.execute('PRAGMA user_version').fetchone()[0]),4)
                restored.close()

    def test_forge_dedup_and_scope_cadence(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);session=Session()
            def job(run):return ForgeJob(run,'P04-task',p,p/'lock','a'*40,p/'manifest',p/'verify',p/'train',p/'holdout',p/run)
            with OneHostStoreActor(lambda:Store(p/'helion.sqlite3')) as actor:
                queue=NativeWorkQueue(actor,authorize=lambda *_:True,stop_requested=lambda:False)
                first=job('first');tid=queue.register_forge(session,first)
                queue.submit(session,first,lambda:{'status':'PAUSED'});queue.close()
                restored=NativeWorkQueue(actor,authorize=lambda *_:True,stop_requested=lambda:False)
                self.assertEqual(restored.register_forge(session,first),tid)
                second=job('second');restored.register_forge(session,second)
                self.assertIsNotNone(restored.last_run(session,second))
                self.assertIsNotNone(restored.last_run(session,second).tzinfo)
                restored.close()

    def test_stop_epoch_cannot_be_revived_by_cleared_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            epoch=[0];entered=threading.Event();release=threading.Event();session=Session()
            with OneHostStoreActor(lambda:Store(Path(tmp)/'helion.sqlite3')) as actor:
                queue=NativeWorkQueue(actor,authorize=lambda *_:True,stop_requested=lambda:False,stop_epoch=lambda:epoch[0])
                tid=queue.enqueue(session,kind='SELF_WRITE',payload={'task':'Approved bounded source job'},permission='selfbuilder.propose')
                def work():
                    entered.set();release.wait(2);return {'status':'CANDIDATE_REVIEW_REQUIRED'}
                queue.submit_source(session,tid,work);self.assertTrue(entered.wait(2));self.assertTrue(queue.is_busy())
                epoch[0]+=1;release.set();queue.close()
                self.assertEqual(queue.get(session,tid)['result']['reason'],'NATIVE_STOP_EPOCH_CHANGED')

    def test_model_transaction_cas_identity_and_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            session=Session()
            with OneHostStoreActor(lambda:Store(Path(tmp)/'helion.sqlite3')) as actor:
                queue=NativeWorkQueue(actor,authorize=lambda *_:True,stop_requested=lambda:False)
                record={'transaction_id':'tx1','merged_payload_sha256':'a'*64,'previous_model':'old',
                        'previous_digest':'b'*64,'target_model':'new','target_digest':'c'*64,'status':'PREPARED'}
                queue.record_transaction(session,'tx1',record)
                self.assertIsNone(queue.load_transaction(Session(principal='other'),'tx1'))
                with self.assertRaises(NativeQueueHold):
                    queue.record_transaction(session,'tx1',{**record,'target_model':'changed','status':'SELECTED_PENDING_NATIVE_E07'})
                queue.record_transaction(session,'tx1',{**record,'status':'SELECTED_PENDING_NATIVE_E07'})
                queue.record_transaction(session,'tx1',{**record,'status':'PREVIOUS_MODEL_SELECTION_RESTORED'})
                with self.assertRaises(NativeQueueHold):queue.record_transaction(session,'tx1',record)
                queue.close()

    def test_forge_merge_followup_same_task_rehydrates_and_rejects_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);session=Session()
            job=ForgeJob('merge-run','P04-task',p,p/'lock','a'*40,p/'manifest',p/'verify',p/'train',p/'holdout',p/'output')
            with OneHostStoreActor(lambda:Store(p/'helion.sqlite3')) as actor:
                queue=NativeWorkQueue(actor,authorize=lambda *_:True,stop_requested=lambda:False)
                tid=queue.register_forge(session,job)
                queue.record(session,tid,'ADAPTER_CANDIDATE_PENDING_E07',{'status':'ADAPTER_CANDIDATE_PENDING_E07'})
                queue.close()
                resumed=NativeWorkQueue(actor,authorize=lambda *_:True,stop_requested=lambda:False)
                ack=resumed.submit_followup(session,job,lambda:{'status':'MERGED_CANDIDATE_PENDING_IMPORT'})
                self.assertEqual(ack['task_id'],tid);resumed.close()
                self.assertEqual(resumed.get(session,tid)['state'],'MERGED_CANDIDATE_PENDING_IMPORT')
                self.assertEqual(len(actor.call(lambda s:s.tasks())),1)
                with self.assertRaises(NativeQueueHold):resumed.submit_followup(session,job,lambda:{'status':'BAD_REPLAY'})

    def test_real_native_ingress_scope_stop_restart_and_source_candidate(self):
        import importlib.util
        import shutil
        import sys
        import uuid
        root=Path(__file__).resolve().parents[2]
        sys.path[:0]=[str(root/'Packages/P02/worker-python'),str(root/'Packages/P03/Source/python-host')]
        if 'nox_native_bridge' not in sys.modules:
            spec=importlib.util.spec_from_file_location('nox_native_bridge',root/'proposals/NOX-PACK01-50/native_bridge.py')
            bridge=importlib.util.module_from_spec(spec);sys.modules[spec.name]=bridge;spec.loader.exec_module(bridge)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);repo=p/'repo';repo.mkdir();stage=p/'stage';stage.mkdir();data=p/'data';data.mkdir()
            (repo/'approved.py').write_text('def source_reference():\n    return 7\n')
            def git(*args):return subprocess.check_output(['git','-C',str(repo),*args],stderr=subprocess.DEVNULL,text=True).strip()
            git('init');git('config','user.email','fixture@example.invalid');git('config','user.name','Fixture');git('add','approved.py');git('commit','-m','fixture')
            head=git('rev-parse','HEAD');source='git:'+head+':approved.py'
            (data/'onehost-native-config.json').write_text(json.dumps({'version':1,'source_root':str(repo),'source_paths':['approved.py'],'candidate_workspace':str(stage)}))
            deployed=p/'app';(deployed/'helion').mkdir(parents=True);(deployed/'assets').mkdir()
            owner_file=deployed/'helion'/'e06_native_stdio_owner.py'
            shutil.copy2(root/'coordination/e06/e06_native_stdio_owner.py',owner_file)
            shutil.copy2(root/'assets/NOX_SOUL_CPU_REAL_WEIGHTS_TRAINED_V1_20261022.zip',deployed/'assets')
            spec=importlib.util.spec_from_file_location('k05_actual_host_fixture',owner_file)
            owner=importlib.util.module_from_spec(spec);spec.loader.exec_module(owner)
            class Model:
                def stop(self,*args):pass
                def models(self):return ['fixture-code:7b']
                def stream(self,model,messages,stop):
                    yield {'delta':json.dumps({'files':[{'path':'extensions/native/action.py','content':'def action():\n    return 7\n'}],
                        'source_ids':[source],'rationale':'One native-host source candidate with exact evidence.'}),'done':True}
            with OneHostStoreActor(lambda:Store(data/'helion.sqlite3')) as actor:
                ingress=owner.create_existing_ingress(actor,'fixture-run',client=Model(),native_approve=lambda *_:True,data_dir=data)
                def call(route,payload):
                    result=ingress.handle(json.dumps({'protocol':'NOX-P02-NATIVE-v1','requestId':uuid.uuid4().hex,'route':route,'payload':payload,'runId':'fixture-run'}).encode())
                    return json.loads(result)['result']
                call('chat.model',{'model':'fixture-code:7b'})
                scoped={'core_id':'core.core','persona_id':'persona.kairen_voss'}
                call('chat.commands',dict(scoped,action='selfbuilder.worker.stop'))
                ack=call('chat.commands',dict(scoped,action='selfbuilder.propose',task='Create a native integrated source candidate'))
                self.assertTrue(ack['ack']);ingress.close()
                result=call('chat.commands',dict(scoped,action='selfbuilder.worker.status'))
                self.assertEqual(result['tasks'][0]['state'],'CANDIDATE_REVIEW_REQUIRED',result)
                self.assertTrue(list(stage.glob('SBX-*/candidate.patch')))
