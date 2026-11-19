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

    def test_s03_memory_text_and_source_are_not_truncated(self):
        memory='воспоминание' * 80
        source='s03://memory/' + 'a' * 300
        record={'verified':True,'tenant':'nox','principal':'owner','chat_id':'resonance',
                'segment':'M2','content':memory,'source_uri':source}
        b=SynapticBrain(self.native(s03_recall=lambda s,p,l:[record]),
            PulseConfig(fast_deadline_ms=300,deep_deadline_ms=400,max_workers=8))
        try:
            result=b.pulse(self.s,'Вспомни подтверждённый факт')
            self.assertEqual(result['state'],'READY_FOR_ONE_NOX_MODEL')
            hit=result['cores']['C02']['hits'][0]
            self.assertEqual(hit['text'],memory)
            self.assertEqual(hit['source'],source)
        finally:b.close()

    def test_oversized_memory_holds_before_model_call_without_trimming(self):
        memory='полный контекст ' * 120
        record={'verified':True,'tenant':'nox','principal':'owner','chat_id':'resonance',
                'segment':'M1','content':memory,'source_uri':'s03://memory/full'}
        called=[]
        b=SynapticBrain(self.native(s03_recall=lambda s,p,l:[record]),
            PulseConfig(fast_deadline_ms=300,deep_deadline_ms=400,max_workers=8,
                        max_context_chars=1000))
        try:
            events=list(b.stream(self.s,'Что ты помнишь?',lambda p,m:called.append((p,m)) or iter(['не должен появиться'])))
            self.assertEqual(events[-1],{'type':'hold','state':'HOLD_CONTEXT_TOO_LARGE'})
            self.assertEqual(called,[])
        finally:b.close()

    def test_genesis_birth_requires_strict_native_true(self):
        seed={'native_verified':True,'kind':'verified_birth','verified_sha256':'a'*64,
              'occurred_at':'2026-11-15T00:00:00Z'}
        for step,reload,expected in [('false','false',False),(1,True,False),
                                     (True,'no',False),(True,True,True)]:
            with self.subTest(step=step,reload=reload):
                event=dict(seed,optimizer_step_verified=step,weights_reloaded=reload)
                b=SynapticBrain(self.native(self_receipts=lambda _:[event]),
                    PulseConfig(fast_deadline_ms=300,deep_deadline_ms=400,max_workers=8))
                try:
                    core=b.pulse(self.s,'Genesis')['cores']['C03']
                    self.assertEqual(bool(core['events']),expected)
                    self.assertEqual(core['consciousness_claim'],'NOT_ESTABLISHED')
                finally:b.close()

    def test_spanish_response_contract_keeps_truthful_self_model(self):
        s=Session(tenant='nox',principal='owner',chat_id='resonance',language='es')
        calls=[]
        b=SynapticBrain(self.native(),PulseConfig(fast_deadline_ms=300,deep_deadline_ms=400,max_workers=8))
        try:
            ev=list(b.stream(s,'¿Quién eres?',lambda p,m:calls.append(m) or iter(['Soy NOX.'])))
            self.assertEqual(ev[-1]['type'],'done')
            self.assertEqual(len(calls),1)
            g=calls[0]['response_contract']
            self.assertEqual(g['language'],'es')
            self.assertIn('C04',g['affect_policy'])
            self.assertIn('Genesis',g['self_model_policy'])
            self.assertIn('RU/ES/EN',g['language_policy'])
        finally:b.close()

    def test_query_plan_all_segments(self):
        self.assertEqual(len(native_query_plan('Помнишь вчера?')['segments']),8)

class BindingTests(unittest.TestCase):
    def test_callback_requirement(self):
        with self.assertRaises(TypeError):AttachedNOX(HostBindings(*[None]*6))
    def test_persistent_stream_one_model(self):
        sessions=[
            Session(tenant='nox',principal='owner',chat_id='chat-ru-kv',
                    language='ru',persona_enabled=True,persona_id='KV'),
            Session(tenant='nox',principal='owner',chat_id='chat-es-am',
                    language='es',persona_enabled=True,persona_id='AM'),
        ]
        receipts={
            'chat-ru-kv':'a'*64,
            'chat-es-am':'b'*64,
        }
        memories=[
            {'tenant':'nox','principal':'owner','chat_id':'chat-ru-kv',
             'persona_id':'KV','segment':'M2','content':'private memory KV RU',
             'source_uri':'s03://chat-ru-kv/kv-memory','verified':True},
            {'tenant':'nox','principal':'owner','chat_id':'chat-es-am',
             'persona_id':'AM','segment':'M2','content':'memoria privada AM ES',
             'source_uri':'s03://chat-es-am/am-memory','verified':True},
        ]
        events=[];calls=[];callback_sessions={'self':[],'affect':[],'preferences':[],
                                                'memory_scope':[],'recall':[]}
        def save(session,payload):
            event_id=f"s03-{session.chat_id}-{payload['seq']}"
            event={'event_id':event_id,'chat_id':session.chat_id,**payload}
            events.append(event)
            return {'verified':True,'durable':True,'event_id':event_id}
        def readback(session,event_id):
            rows=[e for e in events if e['chat_id']==session.chat_id
                  and e['event_id']==event_id]
            if len(rows)!=1:return {'verified':False}
            event=rows[0]
            payload={key:event[key] for key in ('turn_id','seq','kind','schema','body')}
            payload_sha256=hashlib.sha256(json.dumps(
                payload,ensure_ascii=False,sort_keys=True,separators=(',',':'),
                allow_nan=False).encode('utf8')).hexdigest()
            return {'verified':True,'durable':True,'event_id':event_id,
                    'turn_id':event['turn_id'],'seq':event['seq'],'kind':event['kind'],
                    'payload_sha256':payload_sha256}
        def indexed_recall(session,plan,limit):
            callback_sessions['recall'].append((session.chat_id,plan,limit))
            return memories
        def self_receipts(session):
            callback_sessions['self'].append(session.chat_id)
            return [{'kind':'checkpoint','native_verified':True,
                     'verified_sha256':receipts[session.chat_id]}]
        def affect(session,prompt):
            callback_sessions['affect'].append((session.chat_id,prompt))
            return {'tone':'calm' if session.language=='ru' else 'cordial',
                    'language':session.language}
        def preferences(session):
            callback_sessions['preferences'].append(session.chat_id)
            return {'reply_language':session.language,'concise':True}
        def memory_scope_authorize(session,record):
            callback_sessions['memory_scope'].append((session.chat_id,record['chat_id']))
            return True
        def llm(prompt,metadata):
            calls.append((prompt,metadata))
            yield 'Ответ NOX.' if prompt.startswith('RU:') else 'Respuesta NOX.'
        host=HostBindings(
            authorize=lambda _:True,stop=lambda:False,
            s03_recall=lambda s,p,l:[],s03_revision=lambda _:'v1',
            s03_append=save,model_stream=llm,s03_readback=readback,
            self_receipts=self_receipts,affect=affect,preferences=preferences,
            memory_scope_authorize=memory_scope_authorize,
            s03_indexed_recall=indexed_recall)
        agent=AttachedNOX(host)
        try:
            results=[
                list(agent.stream(sessions[0],'RU: ответь кратко','turn-ru-0001')),
                list(agent.stream(sessions[1],'ES: responde breve','turn-es-0001')),
            ]
            self.assertEqual(len(calls),2)
            self.assertEqual([x[0] for x in calls],
                             ['RU: ответь кратко','ES: responde breve'])
            for session,result in zip(sessions,results):
                done=result[-1]
                self.assertEqual((done['type'],done['state']),
                                 ('done','S03_DURABLE_TURN'))
                final=[e for e in events if e['chat_id']==session.chat_id
                       and e['kind']=='assistant_final']
                self.assertEqual(len(final),1)
                self.assertEqual(done['receipt'],
                                 f"s03-{session.chat_id}-{final[0]['seq']}")
            for session,(_,metadata) in zip(sessions,calls):
                context=json.loads(metadata['cognitive_context'])
                self.assertEqual(metadata['core_schema'],'NOX_V38_SYNAPTIC')
                self.assertEqual(metadata['response_contract']['language'],session.language)
                c02=context['C02']['signals']
                visible=' '.join(hit['text'] for hit in c02['hits'])
                own='private memory KV RU' if session.persona_id=='KV' else 'memoria privada AM ES'
                foreign='memoria privada AM ES' if session.persona_id=='KV' else 'private memory KV RU'
                self.assertIn(own,visible)
                self.assertNotIn(foreign,visible)
                c03=context['C03']['signals']
                self.assertEqual(c03['state'],'OBSERVED')
                self.assertEqual(c03['consciousness_claim'],'NOT_ESTABLISHED')
                self.assertIn(receipts[session.chat_id],
                              [event['sha256'] for event in c03['events']])
                c04=context['C04']['signals']
                self.assertEqual(c04['user_tone']['data']['language'],session.language)
                self.assertEqual(c04['preferences']['data']['reply_language'],session.language)
                c05=context['C05']['signals']
                self.assertTrue(c05['master_persona_switch'])
                self.assertEqual(c05['persona_id'],session.persona_id)
            self.assertEqual(callback_sessions['self'],['chat-ru-kv','chat-es-am'])
            self.assertEqual([x[0] for x in callback_sessions['affect']],
                             ['chat-ru-kv','chat-es-am'])
            self.assertEqual(callback_sessions['preferences'],['chat-ru-kv','chat-es-am'])
            self.assertEqual([x[0] for x in callback_sessions['recall']],
                             ['chat-ru-kv','chat-es-am'])
            self.assertEqual(
                {scope for _,scope in callback_sessions['memory_scope']},
                {'chat-ru-kv','chat-es-am'})
            finals=[e for e in events if e['kind']=='assistant_final']
            self.assertEqual({e['chat_id'] for e in finals},
                             {'chat-ru-kv','chat-es-am'})
            self.assertTrue(all(e['body']['sha256'] for e in finals))
        finally:agent.close()
    def test_missing_independent_readback_holds_before_model(self):
        s=Session(tenant='nox',principal='owner',chat_id='chat')
        model_calls=[]
        host=HostBindings(authorize=lambda _:True,stop=lambda:False,
            s03_recall=lambda s,p,l:[],s03_revision=lambda _:'rev1',
            s03_append=lambda s,p:{'verified':True,'durable':True,'event_id':'event-1'},
            model_stream=lambda p,c:model_calls.append(p) or iter(['hello']))
        agent=AttachedNOX(host)
        try:
            result=list(agent.stream(s,'hello','turn-1'))
            self.assertEqual(result,[{'type':'hold','state':'HOLD_S03_READBACK_UNBOUND'}])
            self.assertEqual(model_calls,[])
        finally:agent.close()

if __name__=='__main__':unittest.main()
