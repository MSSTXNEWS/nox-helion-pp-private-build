"""Regression: C02 never silently omitted to make TTFT look faster."""
from __future__ import annotations
import json,time, unittest
from ..synaptic_brain import SynapticBrain, NativePorts, Session, PulseConfig
from ..native_bridge_v38 import AttachedNOX, HostBindings

S=Session(tenant='nox',principal='owner',chat_id='resonance')

def record(*,chat='resonance',persona=None,text='Запись из проверенной памяти'):
    r=dict(id='verified-memory',tenant='nox',principal='owner',chat_id=chat,
           segment='M7',source_uri='s03://owner/memory/verified',content=text,
           verified=True,superseded=False)
    if persona is not None:r['persona_id']=persona
    return r

class RequiredMemory(unittest.TestCase):
    def _p(self, fn, **kwargs):
        b=SynapticBrain(NativePorts(authorize=lambda s:True,stop=lambda:False,
                       s03_recall=fn, **kwargs),
                       PulseConfig(fast_deadline_ms=25,deep_deadline_ms=180,
                           memory_deadline_ms=180,max_workers=8,max_context_chars=3100))
        self.addCleanup(b.close)
        return b

    def test_slow_memory_is_waited_for(self):
        def slow(s,p,l):time.sleep(.075);return [record()]
        b=self._p(slow)
        result=b.pulse(S,'Вспомни вчера')
        self.assertEqual(result['state'],'READY_FOR_ONE_NOX_MODEL')
        self.assertEqual(result['cores']['C02']['hit_count'],1)
        self.assertGreaterEqual(result['elapsed_ms'],60)

    def test_missing_memory_cannot_generate_model_text(self):
        b=self._p(lambda *args: (_ for _ in ()).throw(OSError('not available')))
        calls=[]
        events=list(b.stream(S,'Вспомни',lambda p,c: calls.append(True) or iter(('FAKE ANSWER',))))
        self.assertEqual(events[0]['type'],'phase')
        self.assertEqual(events[-1]['state'],'HOLD_MEMORY_NOT_READY')
        self.assertEqual(calls,[])

    def test_memory_kept_under_context_pressure(self):
        b=self._p(lambda s,p,l:[record(text='Реальное воспоминание с источником '+('ж'*200)) for i in range(8)])
        result=b.pulse(S,'Вспомни дату',deep=True)
        self.assertEqual(result['state'],'READY_FOR_ONE_NOX_MODEL')
        data=json.loads(result['context_json'])
        self.assertEqual(data['C02']['signals']['state'],'OBSERVED')
        self.assertGreater(data['C02']['signals']['hit_count'],0)
        self.assertIn('s03://owner/memory/verified',result['context_json'])

    def test_cross_chat_requires_trusted_grant(self):
        foreign=[record(chat='other-chat')]
        b=self._p(lambda s,p,l:foreign)
        self.assertEqual(b.pulse(S,'test')['cores']['C02']['hit_count'],0)
        good=self._p(lambda s,p,l:foreign,memory_scope_authorize=lambda s,r:True)
        self.assertEqual(good.pulse(S,'test')['cores']['C02']['hit_count'],1)

    def test_persona_specific_event_isolated_even_with_cross_grant(self):
        entries=[record(chat='other-chat',persona='KV')]
        b=self._p(lambda s,p,l:entries,memory_scope_authorize=lambda s,r:True)
        self.assertEqual(b.pulse(S,'test')['cores']['C02']['hit_count'],0)
        selected=Session(tenant='nox',principal='owner',chat_id='resonance',persona_enabled=True,persona_id='KV')
        self.assertEqual(b.pulse(selected,'test')['cores']['C02']['hit_count'],1)

    def test_indexed_native_query_plan(self):
        calls=[]
        def planned(sess, plan, limit):
            calls.append(plan);return [record()]
        agent=AttachedNOX(HostBindings(authorize=lambda s:True,stop=lambda:False,
                        s03_recall=lambda s,p,l: (_ for _ in ()).throw(AssertionError('fallback')),
                        s03_revision=lambda s:'rev1',s03_append=lambda s,p:{'verified':True,'durable':True,'event_id':'r'},
                        model_stream=lambda p,c:iter(['Привет из NOX!']),s03_indexed_recall=planned),
                        PulseConfig(fast_deadline_ms=100,deep_deadline_ms=200,max_workers=8))
        self.addCleanup(agent.close)
        answer=list(agent.stream(S,'Помнишь вчера?','turn-v381-indexed'))
        self.assertEqual(answer[-1]['type'],'done')
        self.assertEqual(calls[0]['segments'],[f'M{i}' for i in range(8)])
        self.assertGreater(len(calls[0]['queries']),1)

    def test_first_visible_delta_early_and_durable(self):
        receipts=[]
        def persist(s,p):
            receipts.append(p);return {'verified':True,'durable':True,'event_id':'rc-'+str(p['seq'])}
        chunks=['Я '+('N'*40), 'подключён '+('A'*120), 'готов.']
        agent=AttachedNOX(HostBindings(authorize=lambda s:True,stop=lambda:False,
                          s03_recall=lambda s,p,l:[],s03_revision=lambda s:'rev1',
                          s03_append=persist,model_stream=lambda p,c:iter(chunks)),
                          PulseConfig(fast_deadline_ms=100,deep_deadline_ms=200,max_workers=8))
        self.addCleanup(agent.close)
        events=list(agent.stream(S,'Как дела?','turn-v381-fast'))
        first_delta=next(e for e in events if e['type']=='delta')
        self.assertEqual(first_delta['text'],chunks[0])
        self.assertEqual(first_delta['evidence_receipt'],'rc-1')
        self.assertEqual(events[-1]['type'],'done')
        self.assertEqual(sum(e['kind']=='assistant_draft_chunk' for e in receipts),3)

if __name__=='__main__':unittest.main()
