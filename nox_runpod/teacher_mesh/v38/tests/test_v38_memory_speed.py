"""Regression: C02 never silently omitted to make TTFT look faster."""
from __future__ import annotations
import json,time, unittest, threading
from ..synaptic_brain import SynapticBrain, NativePorts, Session, PulseConfig
from ..native_bridge_v38 import AttachedNOX, HostBindings, automatic_quality_mode
from ..durable_runtime import WarmS03Cache

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
        rows=[record(text='Реальное воспоминание с источником '+('ж'*200)+f' №{i}') for i in range(8)]
        b=SynapticBrain(NativePorts(authorize=lambda s:True,stop=lambda:False,
                       s03_recall=lambda s,p,l:rows),
                       PulseConfig(fast_deadline_ms=100,deep_deadline_ms=180,
                           memory_deadline_ms=180,max_workers=8,max_context_chars=6400))
        self.addCleanup(b.close)
        result=b.pulse(S,'Вспомни дату',deep=True)
        self.assertEqual(result['state'],'READY_FOR_ONE_NOX_MODEL')
        data=json.loads(result['context_json'])
        hits=data['C02']['signals']['hits']
        self.assertEqual(len(hits),8)
        self.assertEqual([hit['text'] for hit in hits],[row['content'] for row in rows])
        self.assertEqual([hit['source'] for hit in hits],[row['source_uri'] for row in rows])

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

    def test_cache_repeat_never_drops_native_records(self):
        calls=[]
        rows=[record(text='cached '+str(i)) for i in range(2)]
        def recall(s,p,l):
            calls.append((p,l));return [dict(x) for x in rows]
        cache=WarmS03Cache(recall,lambda s:'revision-1')
        first=cache(S,'вспомни',8)
        second=cache(S,'вспомни',8)
        self.assertEqual(first,second)
        self.assertEqual(len(calls),1)
        second[0]['content']='caller mutated copy'
        self.assertEqual(cache(S,'вспомни',8)[0]['content'],'cached 0')

    def test_cache_nested_provenance_isolated_from_native_and_caller(self):
        calls=[]
        native=record(text='verified source')
        native['provenance']={'source':{'uri':'s03://owner/original'}}
        native['labels']=['owner-verified']
        def recall(s,p,l):
            calls.append(True)
            return [native]
        cache=WarmS03Cache(recall,lambda s:'revision-1')
        first=cache(S,'remember genesis',8)
        first[0]['provenance']['source']['uri']='s03://caller-poison'
        first[0]['labels'].append('caller-poison')
        native['provenance']['source']['uri']='s03://native-mutated'
        native['labels'].append('native-mutated')
        second=cache(S,'remember genesis',8)
        self.assertEqual(second[0]['provenance']['source']['uri'],'s03://owner/original')
        self.assertEqual(second[0]['labels'],['owner-verified'])
        second[0]['provenance']['source']['uri']='s03://again'
        second[0]['labels'].append('again')
        third=cache(S,'remember genesis',8)
        self.assertEqual(third[0]['provenance']['source']['uri'],'s03://owner/original')
        self.assertEqual(third[0]['labels'],['owner-verified'])
        self.assertEqual(len(calls),1)

    def test_cache_persona_switch_requires_fresh_native_recall(self):
        # Same owner/chat and S03 revision, but a different persona scope.
        calls=[]
        def recall(s,p,l):
            persona=s.persona_id if s.persona_enabled else None
            calls.append(persona)
            return [record(persona=persona,text='recall-'+str(persona))]
        cache=WarmS03Cache(recall,lambda s:'shared-revision')
        kv=Session(tenant='nox',principal='owner',chat_id='resonance',
                   persona_enabled=True,persona_id='KV')
        am=Session(tenant='nox',principal='owner',chat_id='resonance',
                   persona_enabled=True,persona_id='AM')
        self.assertEqual(cache(kv,'memory',8)[0]['content'],'recall-KV')
        self.assertEqual(cache(S,'memory',8)[0]['content'],'recall-None')
        self.assertEqual(cache(am,'memory',8)[0]['content'],'recall-AM')
        self.assertEqual(cache(kv,'memory',8)[0]['content'],'recall-KV')
        self.assertEqual(calls,['KV',None,'AM'])
        self.assertEqual(cache.stats['hits'],1)
        cache.invalidate(S)
        self.assertEqual(cache(kv,'memory',8)[0]['content'],'recall-KV')
        self.assertEqual(calls,['KV',None,'AM','KV'])

    def test_cache_ru_es_language_switch_requires_fresh_recall(self):
        calls=[]
        def recall(s,p,l):
            calls.append(s.language)
            return [record(text='native-language-'+s.language)]
        cache=WarmS03Cache(recall,lambda s:'shared-revision')
        es=Session(tenant='nox',principal='owner',chat_id='resonance',language='es')
        self.assertEqual(cache(S,'same prompt',8)[0]['content'],'native-language-ru')
        self.assertEqual(cache(es,'same prompt',8)[0]['content'],'native-language-es')
        self.assertEqual(cache(S,'same prompt',8)[0]['content'],'native-language-ru')
        self.assertEqual(calls,['ru','es'])

    def test_cache_inflight_invalidation_never_resurrects_stale_rows(self):
        # Same native revision before and after a global or scoped revoke.
        # A late pre-revocation callback must never warm RAM after revoke.
        for global_revoke in (False, True):
            with self.subTest(global_revoke=global_revoke):
                entered=threading.Event()
                release=threading.Event()
                calls=[]
                def native(s,p,l):
                    calls.append(True)
                    if len(calls)==1:
                        entered.set()
                        release.wait(3)
                    return [record(text='native-call-'+str(len(calls)))]
                cache=WarmS03Cache(native,lambda s:'same-revision')
                first=[]
                errors=[]
                def read_first():
                    try:
                        first.extend(cache(S,'genesis',8))
                    except RuntimeError as exc:
                        errors.append(str(exc))
                thread=threading.Thread(target=read_first,daemon=True)
                thread.start()
                try:
                    self.assertTrue(entered.wait(2),'native recall did not start')
                    cache.invalidate(None if global_revoke else S)
                finally:
                    release.set()
                    thread.join(3)
                self.assertFalse(thread.is_alive())
                self.assertEqual(len(calls),1)
                # A revoked in-flight read is not only barred from the cache:
                # it must never return a stale row to the caller.
                self.assertEqual(first,[])
                self.assertEqual(errors,['HOLD_S03_CACHE_INVALIDATED_DURING_READ'])
                fresh=cache(S,'genesis',8)
                self.assertEqual(fresh[0]['content'],'native-call-2')
                self.assertEqual(len(calls),2)
                self.assertEqual(cache(S,'genesis',8)[0]['content'],'native-call-2')
                self.assertEqual(len(calls),2)

    def test_cache_bypasses_foreign_chat_without_losing_authorised_record(self):
        calls=[]
        rows=[record(chat='other-chat',text='owner-granted cross chat')]
        def recall(s,p,l):
            calls.append(True);return rows
        cache=WarmS03Cache(recall,lambda s:'revision-1')
        self.assertEqual(cache(S,'test',8),rows)
        self.assertEqual(cache(S,'test',8),rows)
        self.assertEqual(len(calls),2)
        self.assertEqual(cache.stats['hits'],0)

    def test_cache_bypasses_overflow_instead_of_truncating(self):
        calls=[]
        rows=[record(text='row'+str(i)) for i in range(9)]
        def recall(s,p,l):
            calls.append(True);return rows
        cache=WarmS03Cache(recall,lambda s:'revision-1')
        self.assertEqual(len(cache(S,'test',2)),9)
        self.assertEqual(len(cache(S,'test',2)),9)
        self.assertEqual(len(calls),2)

    def test_memory_scheduled_before_optional_slow_sensors(self):
        seen=[]
        def native_memory(s,p,l):
            seen.append('memory');return [record()]
        def sensor(s):
            time.sleep(.04)
            seen.append('sensor');return {'gpu':'real'}
        brain=SynapticBrain(NativePorts(authorize=lambda s:True,stop=lambda:False,
            s03_recall=native_memory,sensors=sensor),
            PulseConfig(max_workers=1,max_inflight=1,fast_deadline_ms=25,
                        deep_deadline_ms=180,memory_deadline_ms=180))
        self.addCleanup(brain.close)
        result=brain.pulse(S,'memory test')
        self.assertEqual(result['state'],'READY_FOR_ONE_NOX_MODEL')
        self.assertEqual(result['cores']['C02']['hit_count'],1)

    def test_response_contract_is_single_model_and_proactive_with_evidence(self):
        calls=[]
        def generator(prompt,meta):
            calls.append(meta)
            return iter(['Проверенный ответ NOX.'])
        brain=self._p(lambda s,p,l:[record()])
        events=list(brain.stream(S,'Объясни и предложи исправление',generator))
        self.assertEqual(len(calls),1)
        self.assertEqual(events[-1]['type'],'done')
        policy=calls[0]['response_contract']
        self.assertEqual(policy['quality_mode'],'fast')
        self.assertIn('native receipt',policy['initiative_policy'])
        self.assertIn('M0-M7',policy['memory_policy'])
        self.assertIn('S03',calls[0]['cognitive_context'])
        self.assertNotIn('teacher_response',calls[0])

    def test_deep_contract_reuses_same_installed_model(self):
        calls=[]
        brain=self._p(lambda s,p,l:[record()])
        list(brain.stream(S,'Глубокий анализ',lambda p,m:calls.append(m) or iter(['Ответ']),deep=True))
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0]['response_contract']['quality_mode'],'deep')

    def test_auto_deep_is_deterministic_and_fast_remains_fast(self):
        self.assertFalse(automatic_quality_mode('Привет!'))
        self.assertFalse(automatic_quality_mode('Как дела?'))
        self.assertTrue(automatic_quality_mode('Сравни модели, проанализируй ошибки и предложи исправления'))
        self.assertTrue(automatic_quality_mode('Please compare the architectures and analyze likely failures'))

    def test_auto_deep_reaches_single_main_model(self):
        called=[]
        def main(prompt,meta):
            called.append(meta)
            return iter(['Ответ'])
        agent=AttachedNOX(HostBindings(
            authorize=lambda s:True,stop=lambda:False,
            s03_recall=lambda s,p,l:[record()],
            s03_revision=lambda s:'one',
            s03_append=lambda s,p:{'verified':True,'durable':True,'event_id':'event'},
            model_stream=main),PulseConfig(max_workers=8))
        self.addCleanup(agent.close)
        res=list(agent.stream(S,'Сравни и проанализируй причины ошибки','nox-deep-001'))
        self.assertEqual(res[-1]['type'],'done')
        self.assertEqual(len(called),1)
        self.assertEqual(called[0]['response_contract']['quality_mode'],'deep')

    def test_placeholder_only_answer_gets_one_same_model_retry(self):
        calls=[]
        def model(prompt,metadata):
            calls.append(metadata)
            return iter(['...', ' ']) if len(calls)==1 else iter(['Полный ответ NOX'])
        brain=self._p(lambda s,p,l:[record()])
        events=list(brain.stream(S,'Почему? Объясни и исправь.',model))
        self.assertEqual(len(calls),2)
        self.assertEqual([e['text'] for e in events if e['type']=='delta'],['Полный ответ NOX'])
        self.assertEqual(events[-1]['type'],'done')
        self.assertIn('repair_instruction',calls[1]['response_contract'])

    def test_twice_placeholder_never_claims_done(self):
        brain=self._p(lambda s,p,l:[record()])
        calls=[]
        def model(prompt,meta):
            calls.append(meta)
            return iter(['…'])
        events=list(brain.stream(S,'Проверь работу',model))
        self.assertEqual(len(calls),2)
        self.assertEqual(events[-1]['state'],'HOLD_PLACEHOLDER_ONLY_MODEL_ANSWER')
        self.assertFalse(any(e['type']=='delta' for e in events))

    def test_real_reply_is_one_call_no_quality_regression(self):
        brain=self._p(lambda s,p,l:[record()])
        calls=[]
        def model(prompt,meta):
            calls.append(meta)
            return iter(['Привет', ', чем могу помочь?'])
        events=list(brain.stream(S,'Привет',model))
        self.assertEqual(len(calls),1)
        self.assertEqual(''.join(e['text'] for e in events if e['type']=='delta'),'Привет, чем могу помочь?')
        self.assertEqual(events[-1]['type'],'done')

    def test_stop_during_placeholder_retry_prevents_second_call(self):
        calls=[];live=[False]
        brain=SynapticBrain(NativePorts(authorize=lambda s:True,stop=lambda:live[0],
            s03_recall=lambda s,p,l:[record()]),PulseConfig(max_workers=8))
        self.addCleanup(brain.close)
        def model(p,m):
            calls.append(True)
            live[0]=True
            return iter(['...'])
        events=list(brain.stream(S,'Привет',model))
        self.assertEqual(len(calls),1)
        self.assertEqual(events[-1]['state'],'HOLD_STOP_DURING_STREAM')

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
