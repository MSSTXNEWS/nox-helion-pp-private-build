"""Smoke evaluator unit fixtures; these are explicitly NOT Windows acceptance."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('native_smoke_tested',ROOT/'coordination/e06/native_onehost_smoke.py')
smoke=importlib.util.module_from_spec(spec);spec.loader.exec_module(smoke)

def ok(value):return {'status':'OK','result':value}

class ScriptedPipeFixture:
    """No process, model or Windows claims. Models/chat below are test inputs."""
    def __init__(self,models=(),cancel='STOP'):
        self.models=list(models);self.rows=[];self.calls=[];self.cancel=cancel;self.frames=[]
    def request(self,route,payload,timeout):
        self.calls.append(route)
        if route=='chat.model':
            return ok({'models':self.models,'selectedModel':payload.get('model'),
                'provider_state':'READY' if self.models else 'NO_LOCAL_MODEL',
                'lineage':{'S03':'ORIGINAL_STORE_READY','SEED':'ORIGINAL_BYTES_VERIFIED_NOT_RELEASE_ACCEPTED',
                    'seed_archive_sha256':smoke.SEED_SHA,'optimizer_sha256':smoke.OPTIMIZER_SHA}}),[]
        if route=='chat.history':
            rows=self.rows if payload.get('persona_id')==smoke.SCOPE['persona_id'] else []
            return ok({'messages':list(rows)}),[]
        if route=='chat.stop':return ok({'stopRequested':True}),[]
        if route=='helion.chat':
            self.rows=[{'role':'user','content':payload['text']},{'role':'assistant','content':'fixture answer'}]
            return ok({'answer':'fixture answer','done':True}),[{'delta':'fixture answer'}]
        raise AssertionError(route)
    def send(self,route,payload):
        if route=='helion.chat':
            self.frames.append({'requestId':'chat','status':'EVENT','event':{'delta':'started'}})
            return 'chat'
        self.frames.append({'requestId':'stop','status':'OK','result':{'stopRequested':True}})
        terminal=({'requestId':'chat','status':'HOLD','errorCode':'NATIVE_CHAT_STOP'} if self.cancel=='STOP' else
                  {'requestId':'chat','status':'OK','result':{'answer':'finished','done':True}} if self.cancel=='RACE' else
                  {'requestId':'chat','status':'HOLD','errorCode':'NATIVE_CHAT_TIMEOUT'})
        self.frames.append(terminal)
        return 'stop'
    def receive(self,deadline):return self.frames.pop(0)

class SmokeProofTests(unittest.TestCase):
    def test_no_approved_model_never_claims_live_chat_or_live_stop(self):
        fixture=ScriptedPipeFixture()
        routes,_,rows=smoke.exercise_routes(fixture,None,10)
        self.assertEqual(routes['helion.chat']['status'],'HOLD')
        self.assertEqual(routes['chat.stop']['live_cancel'],'HOLD_NO_APPROVED_MODEL')
        self.assertNotIn('helion.chat',fixture.calls);self.assertEqual(rows,[])
    def test_installed_but_unselected_model_is_not_implicitly_approved(self):
        fixture=ScriptedPipeFixture(['local:test'])
        routes,_,_=smoke.exercise_routes(fixture,None,10)
        self.assertEqual(routes['chat.model']['selection'],'NOT_RUN')
        self.assertEqual(routes['helion.chat']['status'],'HOLD')
    def test_live_stop_requires_real_stop_terminal_and_unchanged_exchange(self):
        routes,_,rows=smoke.exercise_routes(ScriptedPipeFixture(['local:test']),'local:test',10)
        self.assertEqual(routes['helion.chat']['status'],'PASS')
        self.assertEqual(routes['chat.stop']['live_cancel'],'PASS')
        self.assertEqual(len(rows),2)
    def test_completed_before_stop_is_hold_not_cancel_pass(self):
        routes,_,_=smoke.exercise_routes(ScriptedPipeFixture(['local:test'],'RACE'),'local:test',10)
        self.assertEqual(routes['chat.stop']['live_cancel'],'HOLD_MODEL_COMPLETED_BEFORE_STOP')
    def test_timeout_cannot_masquerade_as_stop(self):
        with self.assertRaisesRegex(smoke.SmokeFailed,'STOP_WAS_CONFUSED'):
            smoke.exercise_routes(ScriptedPipeFixture(['local:test'],'TIMEOUT'),'local:test',10)
    def test_cancelled_exchange_cannot_be_saved_as_success(self):
        class BrokenStore(ScriptedPipeFixture):
            def send(self,route,payload):
                nonce=super().send(route,payload)
                if route=='chat.stop':self.rows.append({'role':'assistant','content':'cancelled partial'})
                return nonce
        with self.assertRaisesRegex(smoke.SmokeFailed,'CANCELLED_EXCHANGE_WAS_PERSISTED'):
            smoke.exercise_routes(BrokenStore(['local:test']),'local:test',10)
    def test_terminal_reply_without_stream_cannot_pass_streaming(self):
        class NoStream(ScriptedPipeFixture):
            def request(self,route,payload,timeout):
                result,events=super().request(route,payload,timeout)
                return result,[] if route=='helion.chat' else events
        with self.assertRaisesRegex(smoke.SmokeFailed,'REAL_CHAT_OR_STREAM_EVENT_MISSING'):
            smoke.exercise_routes(NoStream(['local:test']),'local:test',10)
    def test_frame_provenance_checks_run_nonce_and_duplicate_keys(self):
        valid={'protocol':smoke.PROTOCOL,'runId':'run','requestId':'nonce','status':'OK','result':{}}
        self.assertEqual(smoke.decode_frame(json.dumps(valid).encode(),'run',{'nonce'})['status'],'OK')
        for raw in [json.dumps({**valid,'runId':'other'}).encode(),
                    json.dumps({**valid,'requestId':'other'}).encode(),
                    b'{"protocol":"x","protocol":"y"}']:
            with self.subTest(raw=raw),self.assertRaises(smoke.SmokeFailed):
                smoke.decode_frame(raw,'run',{'nonce'})
    def test_nonfinite_native_evidence_is_rejected(self):
        raw=b'{"protocol":"NOX-P02-NATIVE-v1","runId":"run","requestId":"nonce","status":"OK","result":{"value":1e9999}}'
        with self.assertRaises(smoke.SmokeFailed):smoke.decode_frame(raw,'run',{'nonce'})

if __name__=='__main__':unittest.main()
