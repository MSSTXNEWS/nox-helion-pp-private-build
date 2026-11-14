from __future__ import annotations
import contextlib, io, json, unittest, hashlib, time
from pathlib import Path
from unittest.mock import patch

from .. import noxctl
from ..synaptic_brain import NativePorts, Session, PulseConfig, SynapticBrain
from ..native_bridge_v38 import HostBindings, AttachedNOX
from ..durable_runtime import native_query_plan, WarmS03Cache

class ShellAuditTests(unittest.TestCase):
    def test_gpu_rows(self):
        rows=noxctl.gpu_rows('0, Tesla V100-SXM2-32GB, GPU-TEST, 32768, 1024, 73, 48')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['compute_util_pct'],73)
        self.assertEqual(rows[0]['vram_used_mib'],1024)
    def test_invalid_metrics_not_pass(self):
        self.assertEqual(noxctl.gpu_rows('0, Tesla V100, GPU-TEST, 32768, N/A, N/A, 40'),[])
    def test_supervisor_parse(self):
        rows=noxctl.supervisor_rows('nox-chat-8081 RUNNING pid 71, uptime 2:11:03\nnox-train-worm STOPPED Not started\n')
        self.assertEqual([r['state'] for r in rows],['RUNNING','STOPPED'])
        self.assertEqual(rows[0]['pid'],71)
    def test_command_missing(self):
        r=noxctl.command(['no-special-nox-binary-xxxxx'])
        self.assertEqual(r['state'],'NOT_INSTALLED')
    def test_no_cleanup_execute(self):
        r=noxctl.cleanup_candidates([Path('/workspace/checkpoints')])
        self.assertFalse(r['delete_executed'])
        self.assertEqual(r['items'],[])
    def test_cli_prints_valid_json(self):
        with patch.object(noxctl,'inventory',return_value={'schema':'test'}):
            dest=io.StringIO()
            with contextlib.redirect_stdout(dest):
                self.assertEqual(noxctl.main(['status']),0)
            self.assertEqual(json.loads(dest.getvalue())['schema'],'test')

class CognitionTests(unittest.TestCase):
    def setUp(self):
        self.s=Session(tenant='nox',principal='owner',chat_id='resonance')
        self.calls=[]
    def native(self,**overrides):
        callbacks=dict(authorize=lambda _:True, stop=lambda:False,
            sensors=lambda _:{'gpu':{'used_vram_mib':100}},
            s03_recall=lambda s,p,l:[{'verified':True,'tenant':s.tenant,'principal':s.principal,
              'chat_id':s.chat_id,'segment':'M7','content':'Genesis fact','source_uri':'s03://genesis/event'}],
            self_receipts=lambda _:[{'native_verified':True,'kind':'verified_birth','verified_sha256':'a'*64,
                       'optimizer_step_verified':True,'weights_reloaded':True}],
            affect=lambda s,p:{'label':'neutral','confidence':0.9},
            preferences=lambda s:{'language':'ru'},
            available_skills=lambda s:{'available':['code']}, queue_status=lambda s:{'running':3})
        callbacks.update(overrides)
        return NativePorts(**callbacks)
    def test_all_groups_when_fast(self):
        b=SynapticBrain(self.native(),PulseConfig(fast_deadline_ms=300,deep_deadline_ms=400,max_workers=8))
        try:
            r=b.pulse(self.s,'Кто ты?')
            self.assertEqual(r['state'],'READY_FOR_ONE_NOX_MODEL')
            self.assertEqual(len(r['cores']),8)
            self.assertEqual(r['cores']['C02']['state'],'OBSERVED')
            self.assertTrue(r['cores']['C02']['hits'])
            self.assertFalse(r['cores']['C05']['master_persona_switch'])
        finally:b.close()
    def test_stop_denies(self):
        b=SynapticBrain(self.native(stop=lambda:True))
        try:self.assertNotEqual(b.pulse(self.s,'hello')['state'],'READY_FOR_ONE_NOX_MODEL')
        finally:b.close()
    def test_no_arbitrary_persona(self):
        with self.assertRaises(ValueError):
            Session(tenant='nox',principal='owner',chat_id='chat',persona_enabled=True,persona_id='hacker').validate()
    def test_cross_chat_memory_is_rejected(self):
        wrong={'verified':True,'tenant':'other','principal':'owner','chat_id':'different','segment':'M7',
               'content':'leak','source_uri':'s03://private/test'}
        b=SynapticBrain(self.native(s03_recall=lambda s,p,l:[wrong]),PulseConfig(fast_deadline_ms=300,deep_deadline_ms=400,max_workers=8))
        try:self.assertEqual(b.pulse(self.s,'remember')['cores']['C02']['hit_count'],0)
        finally:b.close()
    def test_query_plan_all_segments(self):
        self.assertEqual(len(native_query_plan('Помнишь вчера?')['segments']),8)

class BindingTests(unittest.TestCase):
    def test_callback_requirement(self):
        with self.assertRaises(TypeError):AttachedNOX(HostBindings(*[None]*6))
    def test_persistent_stream_one_model(self):
        s=Session(tenant='nox',principal='owner',chat_id='chat')
        events=[];calls=[];rev=['v1']
        def save(session,payload):
            events.append(payload)
            return {'verified':True,'durable':True,'event_id':f"s03-event-{payload['seq']}"}
        def llm(prompt,context):
            calls.append((prompt,context))
            for part in ('Я NOX, ', 'отвечаю ', 'из ядра.'):
                yield part
        host=HostBindings(authorize=lambda _:True,stop=lambda:False,
             s03_recall=lambda s,p,l:[],s03_revision=lambda _:rev[0],
             s03_append=save,model_stream=llm)
        agent=AttachedNOX(host)
        try:
            result=list(agent.stream(s,'Привет','turn-000001'))
            self.assertEqual(len(calls),1)
            self.assertEqual(result[-1]['type'],'done')
            self.assertEqual(result[-1]['state'],'S03_DURABLE_TURN')
            self.assertEqual(events[0]['kind'],'user_message')
            self.assertEqual(events[-1]['kind'],'assistant_final')
        finally:agent.close()
    def test_no_proof_no_draft_display(self):
        s=Session(tenant='nox',principal='owner',chat_id='chat')
        host=HostBindings(authorize=lambda _:True,stop=lambda:False,
            s03_recall=lambda s,p,l:[],s03_revision=lambda _:'rev1',
            s03_append=lambda s,p:{'verified':False},model_stream=lambda p,c:iter(['hello']))
        agent=AttachedNOX(host)
        try:self.assertEqual(list(agent.stream(s,'hello','turn-1'))[0]['type'],'hold')
        finally:agent.close()

if __name__=='__main__':unittest.main()
