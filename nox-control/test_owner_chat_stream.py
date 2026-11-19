import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

import httpx

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import owner_chat_stream as stream
import owner_chat_ui as ui
import owner_chat_source_patch as transforms


def frame(content=None,finish=None,calls=None):
    delta={}
    if content is not None:delta['content']=content
    if calls is not None:delta['tool_calls']=calls
    return ('data: '+json.dumps({'choices':[{'delta':delta,'finish_reason':finish}]},ensure_ascii=False)+'\n\n').encode()


class Chunks(httpx.AsyncByteStream):
    def __init__(self,parts,gate=None):self.parts=parts;self.gate=gate;self.closed=False
    async def __aiter__(self):
        for index,part in enumerate(self.parts):
            if index==1 and self.gate is not None:await self.gate.wait()
            yield part
    async def aclose(self):self.closed=True


class StreamTests(unittest.IsolatedAsyncioTestCase):
    def native(self,heuristic=None,result=None):
        self.dispatched=[]
        def dispatch(name,args):
            self.dispatched.append((name,args))
            return result or {'ok':True,'text':'323'}
        def parse(message,content):
            self.assertEqual(content,'')
            return [{'id':call['id'],'name':call['function']['name'],
                     'arguments':call['function']['arguments']} for call in message['tool_calls']]
        native={'TOOLS':[{'type':'function','function':{'name':'calculate'}}],
                '_POOL':False,'MAX_STEPS':8,'DIRECT_ADMIN':{'status'},
                '_direct_admin_calls':lambda text:[],
                'heuristic_tools':lambda text:heuristic or [],
                'parse_tool_calls':parse,'dispatch':dispatch,'audit':lambda *a,**k:None,
                'confirm_marker':lambda rec:' [CONFIRM fixture]',
                '_sse':lambda text,finish=None:frame(text,finish).decode(),
                '_final_json':lambda text:{'choices':[{'message':{'content':text}}]}}
        stream.install(native)
        return native

    def transport(self,streams):
        requests=[]
        def reply(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200,stream=streams[len(requests)-1])
        transport=httpx.MockTransport(reply)
        real_client=httpx.AsyncClient
        factory=lambda **kwargs:real_client(transport=transport,**kwargs)
        return requests,patch.object(stream.httpx,'AsyncClient',side_effect=factory)

    async def test_duplicate_sse_and_tool_argument_json_keys_hold_before_dispatch(self):
        # Duplicate keys make both model envelopes and nested tool arguments
        # ambiguous; Python's default last-key-wins would alter evidence.
        bad_envelope=(b'data: {"choices":[],"choices":[{"delta":{"content":"wrong"},'
                      b'"finish_reason":"stop"}]}\n\n')
        bad_args=frame(calls=[{'index':0,'id':'dup_args','type':'function',
                               'function':{'name':'calculate',
                                           'arguments':'{"amount":1,"amount":2}'}}])
        cases=(
            ([bad_envelope,b'data: [DONE]\n\n'],'HOLD_MODEL_SSE_INVALID'),
            ([bad_args,frame(finish='tool_calls'),b'data: [DONE]\n\n'],
             'HOLD_TOOL_ARGUMENTS'),
        )
        for parts,code in cases:
            with self.subTest(code=code):
                chunks=Chunks(parts)
                requests,factory=self.transport([chunks])
                native=self.native()
                payload={'messages':[{'role':'user','content':'Calculate'}]}
                with factory:
                    response=await native['owner_completion'](
                        'http://native/model',payload,'Calculate',True)
                    wire=''.join([piece async for piece in response.body_iterator])
                self.assertIn(code,wire)
                self.assertNotIn('[DONE]',wire)
                self.assertNotIn('_agent_final',payload)
                self.assertEqual(len(requests),1)
                self.assertEqual(self.dispatched,[])
                self.assertTrue(chunks.closed)

    async def test_bounded_sse_metadata_preserves_real_tokens_and_terminal(self):
        # Some upstream SSE servers prepend standard event/id fields to data.
        chunks=Chunks([b': heartbeat\n\n',b'event: message\nid: reply-7\n',
                       frame('Hola'),frame(finish='stop'),b'data: [DONE]\n\n'])
        _,factory=self.transport([chunks])
        native=self.native();payload={'messages':[{'role':'user','content':'Hola'}]}
        with factory:
            response=await native['owner_completion']('http://native/model',payload,'Hola',True)
            wire=''.join([chunk async for chunk in response.body_iterator])
        self.assertIn('Hola',wire)
        self.assertNotIn('reply-7',wire)
        self.assertIn('[DONE]',wire)
        self.assertEqual(payload['_agent_final'],'Hola')
        self.assertTrue(chunks.closed)

    async def test_standard_sse_bom_retry_and_bare_id_metadata_does_not_drop_chat(self):
        # WHATWG allows one leading UTF-8 BOM, retry fields, and fields without
        # a colon (empty value). None may cause a new POST or enter S03 text.
        prelude=b'\xef\xbb\xbf: upstream heartbeat\nretry: 2500\nid\nevent\n\n'
        chunks=Chunks([prelude,frame('Hola completo'),frame(finish='stop'),
                       b'data: [DONE]\n\n'])
        requests,factory=self.transport([chunks])
        native=self.native()
        payload={'messages':[{'role':'user','content':'Hola'}]}
        with factory:
            response=await native['owner_completion'](
                'http://native/model',payload,'Hola',True)
            wire=''.join([part async for part in response.body_iterator])
        self.assertIn('Hola completo',wire)
        self.assertIn('[DONE]',wire)
        self.assertNotIn('2500',wire)
        self.assertNotIn('heartbeat',wire)
        self.assertEqual(payload.get('_agent_final'),'Hola completo')
        self.assertEqual(len(requests),1)
        self.assertTrue(chunks.closed)

    async def test_multiline_sse_data_fields_are_one_json_frame(self):
        # A newline between two JSON fields is legal SSE data continuation.
        whole=frame('Hola').decode('utf-8').split('data: ',1)[1].strip()
        first,rest=whole.split(', "finish_reason"',1)
        wire=(f'event: message\nid: multiline-1\n'
              f'data: {first}\ndata: , "finish_reason"{rest}\n\n').encode('utf-8')
        chunks=Chunks([wire,frame(finish='stop'),b'data: [DONE]\n\n'])
        _,factory=self.transport([chunks])
        native=self.native()
        payload={'messages':[{'role':'user','content':'Hola'}]}
        with factory:
            response=await native['owner_completion']('http://native/model',payload,'Hola',True)
            answer=''.join([part async for part in response.body_iterator])
        self.assertIn('Hola',answer)
        self.assertIn('[DONE]',answer)
        self.assertEqual(payload.get('_agent_final'),'Hola')
        self.assertTrue(chunks.closed)

    async def test_bare_data_field_joins_following_json_without_losing_s03(self):
        # WHATWG treats a bare `data` as `data:` (an empty data value).
        # The resulting leading LF is JSON whitespace, not a second event.
        chunks=Chunks([b'data\r\n',frame('Hola sin pérdida'),
                       frame(finish='stop'),b'data: [DONE]\n\n'])
        requests,factory=self.transport([chunks])
        native=self.native()
        payload={'messages':[{'role':'user','content':'Hola'}]}
        with factory:
            response=await native['owner_completion'](
                'http://native/model',payload,'Hola',True)
            wire=''.join([part async for part in response.body_iterator])
        self.assertIn('Hola sin pérdida',wire)
        self.assertIn('[DONE]',wire)
        self.assertEqual(payload.get('_agent_final'),'Hola sin pérdida')
        self.assertEqual(len(requests),1)
        self.assertTrue(chunks.closed)

    async def test_unbounded_metadata_record_cannot_starve_chat_or_save_s03(self):
        # Every comment is a legal SSE field; their *unbounded number* is not.
        chunks=Chunks([frame('Partial'),b': keepalive\n'*1025+b'\n',
                       frame(finish='stop'),b'data: [DONE]\n\n'])
        _,factory=self.transport([chunks])
        native=self.native()
        payload={'messages':[{'role':'user','content':'Hola'}]}
        with factory:
            response=await native['owner_completion'](
                'http://native/model',payload,'Hola',True)
            wire=''.join([chunk async for chunk in response.body_iterator])
        self.assertIn('HOLD_MODEL_SSE_FRAME',wire)
        self.assertNotIn('[DONE]',wire)
        self.assertNotIn('_agent_final',payload)
        self.assertTrue(chunks.closed)

    async def test_unterminated_oversized_sse_line_holds_before_next_network_chunk(self):
        # A 350k-byte comment without a newline made httpx.aiter_lines()
        # await another network read before the adapter's line limit ran.
        gate=asyncio.Event()
        chunks=Chunks([b': '+b'x'*350000,frame('unreachable')],gate)
        requests,factory=self.transport([chunks])
        native=self.native()
        payload={'messages':[{'role':'user','content':'Hola'}]}
        with factory:
            response=await native['owner_completion'](
                'http://native/model',payload,'Hola',True)
            async def collect():
                return ''.join([part async for part in response.body_iterator])
            wire=await asyncio.wait_for(collect(),2.0)
        self.assertIn('HOLD_MODEL_SSE_FRAME',wire)
        self.assertNotIn('[DONE]',wire)
        self.assertNotIn('_agent_final',payload)
        self.assertEqual(len(requests),1)
        self.assertTrue(chunks.closed)

    async def test_large_metadata_bytes_cannot_starve_chat_or_certify_s03(self):
        # Six comments are under the line-count and per-line caps, but their
        # aggregate 360k-byte record must never consume unbounded chat work.
        metadata=(b': '+b'x'*60000+b'\n')*6+b'\n'
        chunks=Chunks([frame('Partial'),metadata,frame(finish='stop'),
                       b'data: [DONE]\n\n'])
        requests,factory=self.transport([chunks])
        native=self.native()
        payload={'messages':[{'role':'user','content':'Hola'}]}
        with factory:
            response=await native['owner_completion'](
                'http://native/model',payload,'Hola',True)
            wire=''.join([piece async for piece in response.body_iterator])
        self.assertIn('HOLD_MODEL_SSE_FRAME',wire)
        self.assertNotIn('[DONE]',wire)
        self.assertNotIn('_agent_final',payload)
        self.assertEqual(len(requests),1)
        self.assertTrue(chunks.closed)

    async def test_untrusted_sse_event_or_id_metadata_fails_closed(self):
        cases=((b'event: error\n\n','HOLD_MODEL_SSE_EVENT'),
               (b'id: '+b'x'*257+b'\n\n','HOLD_MODEL_SSE_FRAME'))
        for metadata,code in cases:
            with self.subTest(code=code):
                chunks=Chunks([frame('partial'),metadata,frame(finish='stop'),
                               b'data: [DONE]\n\n'])
                _,factory=self.transport([chunks])
                native=self.native();payload={'messages':[{'role':'user','content':'Hola'}]}
                with factory:
                    response=await native['owner_completion']('http://native/model',payload,'Hola',True)
                    wire=''.join([chunk async for chunk in response.body_iterator])
                self.assertIn(code,wire)
                self.assertNotIn('[DONE]',wire)
                self.assertNotIn('_agent_final',payload)
                self.assertTrue(chunks.closed)

    async def test_first_model_content_arrives_before_completion_and_sets_final_before_done(self):
        gate=asyncio.Event()
        chunks=Chunks([frame('323'),frame('',finish='stop'),b'data: [DONE]\n\n'],gate)
        requests,factory=self.transport([chunks])
        native=self.native();payload={'messages':[{'role':'user','content':'17*19'}]}
        with factory:
            response=await native['owner_completion']('http://native/model',payload,'17*19',True)
            iterator=response.body_iterator.__aiter__()
            first=await asyncio.wait_for(anext(iterator),.5)
            self.assertIn('323',first)
            self.assertNotIn('…',first)
            self.assertNotIn('17*19',first)
            self.assertNotIn('_agent_final',payload)
            gate.set()
            terminal=await anext(iterator)
            self.assertEqual(payload['_agent_final'],'323')
            self.assertIn('"finish_reason": "stop"',terminal)
            self.assertEqual(await anext(iterator),'data: [DONE]\n\n')
            with self.assertRaises(StopAsyncIteration):await anext(iterator)
        self.assertTrue(requests[0]['stream'])
        self.assertTrue(requests[0]['cache_prompt'])
        self.assertTrue(chunks.closed)

    async def test_structured_tool_arguments_remain_private_and_ids_roundtrip(self):
        first=Chunks([
            frame(calls=[{'index':0,'id':'call_fixture','type':'function',
                          'function':{'name':'calculate','arguments':'{"a":17,'}}]),
            frame(calls=[{'index':0,'function':{'arguments':'"b":19}'}}]),
            frame(finish='tool_calls'),b'data: [DONE]\n\n'])
        last=Chunks([frame('323'),frame(finish='stop'),b'data: [DONE]\n\n'])
        requests,factory=self.transport([first,last])
        native=self.native();payload={'messages':[{'role':'user','content':'Compute'}]}
        with factory:
            response=await native['owner_completion']('http://native/model',payload,'Compute',True)
            wire=''.join([chunk async for chunk in response.body_iterator])
        self.assertEqual(self.dispatched,[('calculate',{'a':17,'b':19})])
        self.assertNotIn('call_fixture',wire)
        self.assertNotIn('calculate',wire)
        self.assertEqual(requests[1]['messages'][-1]['tool_call_id'],'call_fixture')
        self.assertEqual(requests[1]['messages'][-2]['tool_calls'][0]['id'],'call_fixture')
        self.assertEqual(payload['_agent_final'],'323')

    async def test_complete_tool_observation_is_not_silently_clipped(self):
        # Prior adapter sent only the first 8000 characters to the model.
        # Preserve real RU/ES evidence, including its final non-ASCII suffix.
        observation='RU начало:'+'я'*8050+'\nES final: contexto completo 🦊'
        call=Chunks([
            frame(calls=[{'index':0,'id':'full_context_call','type':'function',
                          'function':{'name':'calculate','arguments':'{}'}}]),
            frame(finish='tool_calls'),b'data: [DONE]\n\n'])
        answer=Chunks([frame('Respuesta completa'),frame(finish='stop'),
                       b'data: [DONE]\n\n'])
        requests,factory=self.transport([call,answer])
        native=self.native(result={'ok':True,'text':observation})
        payload={'messages':[{'role':'user','content':'Usa el resultado completo'}]}
        with factory:
            response=await native['owner_completion'](
                'http://native/model',payload,'Usa el resultado completo',True)
            wire=''.join([piece async for piece in response.body_iterator])
        self.assertEqual(requests[1]['messages'][-1]['content'],observation)
        self.assertEqual(payload['_agent_final'],'Respuesta completa')
        self.assertNotIn(observation,wire)
        self.assertTrue(call.closed)
        self.assertTrue(answer.closed)

        # Beyond the current safe source envelope, HOLD rather than send a
        # forged prefix as if it were the complete tool result.
        too_large='x'*2000001
        upstream=Chunks([
            frame(calls=[{'index':0,'id':'oversized_tool','type':'function',
                          'function':{'name':'calculate','arguments':'{}'}}]),
            frame(finish='tool_calls'),b'data: [DONE]\n\n'])
        requests,factory=self.transport([upstream])
        native=self.native(result={'ok':True,'text':too_large})
        payload={'messages':[{'role':'user','content':'Preserva todo'}]}
        with factory:
            response=await native['owner_completion'](
                'http://native/model',payload,'Preserva todo',True)
            wire=''.join([piece async for piece in response.body_iterator])
        self.assertIn('HOLD_TOOL_RESULT_FULL_CONTEXT',wire)
        self.assertNotIn('[DONE]',wire)
        self.assertNotIn('_agent_final',payload)
        self.assertEqual(len(requests),1)
        self.assertTrue(upstream.closed)

    async def test_untrusted_model_tool_id_overflow_never_dispatches_or_saves(self):
        # A tool-call ID may be streamed incrementally by Maya/llama.cpp.
        # The limit is cumulative, not a per-frame cap.
        cases=(
            [frame(calls=[{'index':0,'id':'x'*161,'type':'function',
                           'function':{'name':'calculate','arguments':'{}'}}])],
            [frame(calls=[{'index':0,'id':'x'*100,'type':'function',
                           'function':{'name':'calculate','arguments':'{}'}}]),
             frame(calls=[{'index':0,'id':'y'*61}])],
        )
        for fragments in cases:
            with self.subTest(frames=len(fragments)):
                chunks=Chunks([*fragments,frame(finish='tool_calls'),
                               b'data: [DONE]\n\n'])
                _,factory=self.transport([chunks])
                native=self.native()
                payload={'messages':[{'role':'user','content':'Compute'}]}
                with factory:
                    response=await native['owner_completion'](
                        'http://native/model',payload,'Compute',True)
                    wire=''.join([part async for part in response.body_iterator])
                self.assertIn('HOLD_TOOL_CALL_ID_SIZE',wire)
                self.assertNotIn('[DONE]',wire)
                self.assertNotIn('_agent_final',payload)
                self.assertEqual(self.dispatched,[])
                self.assertTrue(chunks.closed)

    async def test_model_tool_call_id_at_limit_preserves_native_roundtrip(self):
        valid_id='c'*160
        first=Chunks([frame(calls=[{'index':0,'id':valid_id,
                                   'type':'function','function':{
                                       'name':'calculate','arguments':'{}'}}]),
                      frame(finish='tool_calls'),b'data: [DONE]\n\n'])
        second=Chunks([frame('ok'),frame(finish='stop'),
                       b'data: [DONE]\n\n'])
        requests,factory=self.transport([first,second])
        native=self.native()
        payload={'messages':[{'role':'user','content':'Compute'}]}
        with factory:
            response=await native['owner_completion'](
                'http://native/model',payload,'Compute',True)
            wire=''.join([part async for part in response.body_iterator])
        self.assertIn('[DONE]',wire)
        self.assertEqual(self.dispatched,[('calculate',{})])
        self.assertEqual(requests[1]['messages'][-1]['tool_call_id'],valid_id)
        self.assertEqual(payload['_agent_final'],'ok')
        self.assertTrue(first.closed)
        self.assertTrue(second.closed)

    async def test_direct_admin_multiple_actions_holds_before_model_or_dispatch(self):
        # Exact regression from previously reviewed #394/#420: ambiguous
        # administrative actions must neither be clipped nor partly executed.
        native=self.native()
        calls={'prepare':0,'deterministic':0,'heuristic':0,'dispatch':0}
        native['_POOL']=True
        native['_direct_admin_calls']=lambda text:[
            {'name':'run_admin','arguments':{'action':'pause'}},
            {'name':'run_admin','arguments':{'action':'resume'}},
        ]
        def prepare(req,cache=False):
            calls['prepare']+=1
            return req
        def deterministic(text):
            calls['deterministic']+=1
            return None
        def heuristic(text):
            calls['heuristic']+=1
            return []
        def dispatch(name,args):
            calls['dispatch']+=1
            self.dispatched.append((name,args))
            return {'ok':True,'text':'unexpected dispatch'}
        native['prepare_payload']=prepare
        native['try_deterministic']=deterministic
        native['heuristic_tools']=heuristic
        native['dispatch']=dispatch
        payload={'messages':[
            {'role':'system','content':'Keep all input intact.'},
            {'role':'user','content':'Пауза и возобновление: проверь оба действия.'},
            {'role':'assistant','content':'История 🧠','tool_calls':[
                {'id':'prior_call','type':'function','function':{
                    'name':'calculate','arguments':'{"tail":"полный"}'}}]},
        ]}
        original_messages=json.loads(json.dumps(payload['messages'],ensure_ascii=False))
        evidence_dispatch=patch.object(stream._current,'dispatch',side_effect=AssertionError('no evidence dispatch'))
        model_client=patch.object(stream.httpx,'AsyncClient',side_effect=AssertionError('no model request'))
        with evidence_dispatch as evidence, model_client as model:
            response=await native['owner_completion']('http://native/model',payload,'Пауза и возобновление',True)
            wire=''.join([chunk async for chunk in response.body_iterator])
        self.assertIn('HOLD_DIRECT_ADMIN_MULTIPLE_ACTIONS',wire)
        self.assertEqual(calls,{'prepare':0,'deterministic':0,'heuristic':0,'dispatch':0})
        evidence.assert_not_called()
        model.assert_not_called()
        self.assertEqual(self.dispatched,[])
        self.assertEqual(payload,{'messages':original_messages})
        self.assertNotIn('_agent_final',payload)

    async def test_model_admin_batch_never_partly_executes_or_certifies_s03(self):
        # Model may propose an administrative action alongside another tool.
        # The first call must not execute while the remainder is silently dropped.
        for admin_first,pool_dedup in ((True,False),(False,False),(True,True),(False,True)):
            with self.subTest(admin_first=admin_first,pool_dedup=pool_dedup):
                admin={'index':0 if admin_first else 1,'id':'admin-call',
                       'type':'function','function':{
                           'name':'run_admin','arguments':'{"action":"status"}'}}
                math={'index':1 if admin_first else 0,'id':'math-call',
                      'type':'function','function':{
                          'name':'calculate','arguments':'{}'}}
                pieces=sorted((admin,math),key=lambda x:x['index'])
                chunks=Chunks([frame(calls=pieces),frame(finish='tool_calls'),
                               b'data: [DONE]\n\n'])
                requests,factory=self.transport([chunks])
                native=self.native()
                native['_POOL']=pool_dedup
                if pool_dedup:
                    native['prepare_payload']=lambda req,cache=False:req
                    native['try_deterministic']=lambda text:None
                    # A legacy optimization can discard the companion call;
                    # that must not turn a mixed model batch into one admin act.
                    native['dedup_calls']=lambda rows:[row for row in rows if row['name']=='run_admin']
                payload={'messages':[{'role':'user','content':'Состояние и расчёт'}]}
                with factory:
                    response=await native['owner_completion'](
                        'http://native/model',payload,'Состояние и расчёт',True)
                    wire=''.join([part async for part in response.body_iterator])
                self.assertIn('HOLD_DIRECT_ADMIN_MULTIPLE_ACTIONS',wire)
                self.assertNotIn('[DONE]',wire)
                self.assertNotIn('_agent_final',payload)
                self.assertEqual(len(requests),1)
                self.assertEqual(self.dispatched,[])
                self.assertTrue(chunks.closed)

    async def test_confirmation_stops_before_model_and_preserves_real_marker(self):
        native=self.native([{'name':'run_admin','arguments':{'action':'pause'}}],
                           {'ok':False,'needs_confirmation':True,'text':'Confirm pause'})
        payload={'messages':[{'role':'user','content':'Pause'}]}
        with patch.object(stream.httpx.AsyncClient,'stream',side_effect=AssertionError('no model')):
            response=await native['owner_completion']('http://native/model',payload,'Pause',True)
            wire=''.join([chunk async for chunk in response.body_iterator])
        self.assertIn('Confirm pause [CONFIRM fixture]',wire)
        self.assertEqual(payload['_agent_final'],'Confirm pause [CONFIRM fixture]')
        self.assertEqual(len(self.dispatched),1)

    async def test_incomplete_model_and_error_never_certify_partial_text(self):
        for parts in ([frame('Partial')],
                      [frame('Partial'),frame(finish='length'),b'data: [DONE]\n\n'],
                      [frame('Partial'),b'data: {"error":{"message":"private upstream detail"}}\n\n']):
            requests,factory=self.transport([Chunks(parts)])
            native=self.native();payload={'messages':[{'role':'user','content':'Question'}]}
            with factory:
                response=await native['owner_completion']('http://native/model',payload,'Question',True)
                wire=''.join([chunk async for chunk in response.body_iterator])
            self.assertIn('"error"',wire)
            self.assertNotIn('[DONE]',wire)
            self.assertNotIn('private upstream detail',wire)
            self.assertNotIn('_agent_final',payload)

    async def test_post_terminal_delta_or_repeated_finish_cannot_certify_s03(self):
        # An upstream completion frame is terminal. A trailing token or a
        # repeated finish must not be mistaken for a complete saved answer.
        trailing=(
            frame('late after stop'),
            frame(finish='stop'),
            frame(calls=[{'index':0,'id':'late','type':'function',
                          'function':{'name':'calculate','arguments':'{}'}}]),
        )
        for unwanted in trailing:
            with self.subTest(unwanted=unwanted):
                chunks=Chunks([frame('early'),frame(finish='stop'),unwanted,
                               b'data: [DONE]\n\n'])
                _,factory=self.transport([chunks])
                native=self.native()
                payload={'messages':[{'role':'user','content':'¿Prueba?'}]}
                with factory:
                    response=await native['owner_completion'](
                        'http://native/model',payload,'¿Prueba?',True)
                    wire=''.join([chunk async for chunk in response.body_iterator])
                self.assertIn('HOLD_MODEL_POST_TERMINAL_DELTA',wire)
                self.assertNotIn('[DONE]',wire)
                self.assertNotIn('_agent_final',payload)
                self.assertTrue(chunks.closed)

    async def test_falsey_malformed_model_delta_or_tool_calls_cannot_certify_s03(self):
        # A falsey but non-null malformed SSE field must never be treated as
        # an empty valid delta and certify a preceding partial assistant reply.
        docs=(
            *({'choices':[{'delta':bad,'finish_reason':'stop'}]}
              for bad in (False, [], 0)),
            *({'choices':[{'delta':{'tool_calls':bad},'finish_reason':'stop'}]}
              for bad in (False, 0, {})),
        )
        for doc in docs:
            with self.subTest(doc=doc):
                bad_frame=('data: '+json.dumps(doc)+'\n\n').encode()
                chunks=Chunks([frame('partial'),bad_frame,b'data: [DONE]\n\n'])
                requests,factory=self.transport([chunks])
                native=self.native()
                payload={'messages':[{'role':'user','content':'Question'}]}
                with factory:
                    response=await native['owner_completion'](
                        'http://native/model',payload,'Question',True)
                    wire=''.join([part async for part in response.body_iterator])
                self.assertIn('HOLD_MODEL_SSE_INVALID',wire)
                self.assertNotIn('[DONE]',wire)
                self.assertNotIn('_agent_final',payload)
                self.assertEqual(len(requests),1)
                self.assertEqual(self.dispatched,[])
                self.assertTrue(chunks.closed)

    async def test_falsey_model_tool_function_fragment_holds_before_dispatch(self):
        # A non-object 'function' must not be coalesced into an empty
        # continuation before a later fragment supplies executable fields.
        for invalid in (False, [], 0, ''):
            with self.subTest(invalid=repr(invalid)):
                first=frame(calls=[{'index':0,'id':'bad_fn','type':'function',
                                    'function':invalid}])
                continuation=frame(calls=[{'index':0,'function':{
                    'name':'calculate','arguments':'{}'}}])
                chunks=Chunks([first,continuation,frame(finish='tool_calls'),
                               b'data: [DONE]\n\n'])
                requests,factory=self.transport([chunks])
                native=self.native()
                payload={'messages':[{'role':'user','content':'Calculate'}]}
                with factory:
                    response=await native['owner_completion'](
                        'http://native/model',payload,'Calculate',True)
                    wire=''.join([part async for part in response.body_iterator])
                self.assertIn('HOLD_MODEL_SSE_INVALID',wire)
                self.assertNotIn('[DONE]',wire)
                self.assertNotIn('_agent_final',payload)
                self.assertEqual(len(requests),1)
                self.assertEqual(self.dispatched,[])
                self.assertTrue(chunks.closed)

    async def test_usage_only_after_terminal_still_completes_normally(self):
        usage=b'data: {"choices":[],"usage":{"completion_tokens":1}}\n\n'
        chunks=Chunks([frame('¡Respuesta!'),frame(finish='stop'),usage,
                       b'data: [DONE]\n\n'])
        _,factory=self.transport([chunks])
        native=self.native()
        payload={'messages':[{'role':'user','content':'Responde'}]}
        with factory:
            response=await native['owner_completion'](
                'http://native/model',payload,'Responde',True)
            wire=''.join([chunk async for chunk in response.body_iterator])
        self.assertEqual(payload['_agent_final'],'¡Respuesta!')
        self.assertIn('[DONE]',wire)
        self.assertTrue(chunks.closed)

    async def test_disconnect_does_not_save_or_fabricate_terminal(self):
        gate=asyncio.Event();chunks=Chunks([frame('Partial'),frame(finish='stop')],gate)
        _,factory=self.transport([chunks])
        native=self.native();payload={'messages':[{'role':'user','content':'Question'}]}
        with factory:
            response=await native['owner_completion']('http://native/model',payload,'Question',True)
            self.assertIn('Partial',await anext(response.body_iterator))
            await response.body_iterator.aclose()
            self.assertNotIn('_agent_final',payload)
            self.assertTrue(chunks.closed)

    async def test_reasoning_field_is_never_answer(self):
        reasoning=b'data: {"choices":[{"delta":{"reasoning_content":"private reasoning"},"finish_reason":null}]}\n\n'
        _,factory=self.transport([Chunks([reasoning,frame('Answer'),frame(finish='stop'),b'data: [DONE]\n\n'])])
        native=self.native();payload={'messages':[{'role':'user','content':'Question'}]}
        with factory:
            response=await native['owner_completion']('http://native/model',payload,'Question',True)
            wire=''.join([chunk async for chunk in response.body_iterator])
        self.assertNotIn('private reasoning',wire)
        self.assertEqual(payload['_agent_final'],'Answer')

    async def test_current_executor_count_is_actual_snapshot_without_model_or_action(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'state').mkdir()
            path=Path(folder)/'agents.json'
            doc={'n':6,'workers':[{'id':f'nox-agent-{i:02d}','status':'idle','current_task':None}
                                  for i in range(1,7)]}
            doc['workers'][0].update(status='busy',current_task={'id':'public-test-task'})
            path.write_text(json.dumps(doc))
            native=self.native();payload={'messages':[{'role':'user','content':'Сколько сейчас исполнителей и агентов?'}]}
            native['_direct_admin_calls']=lambda text:(_ for _ in ()).throw(AssertionError('no actions'))
            with patch.object(stream,'EXECUTOR_STATUS',path),patch.object(stream.httpx,'AsyncClient',side_effect=AssertionError('no model')),patch.object(ui,'ROOT',Path(folder)):
                response=await native['owner_completion']('http://native/model',payload,payload['messages'][0]['content'],True)
                wire=''.join([chunk async for chunk in response.body_iterator])
            self.assertIn('настроено 6',wire)
            self.assertIn('занято 1, свободно 5',wire)
            self.assertIn('6 исполнителей + NOX',wire)
            self.assertIn('nox-agent-06',wire)
            self.assertEqual(self.dispatched,[])
            self.assertIn('настроено 6',payload['_agent_final'])

    def test_executor_reply_respects_owner_maintenance_and_read_transition(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'state').mkdir()
            path=root/'agents.json'
            path.write_text(json.dumps({
                'n':1,'workers':[{'id':'nox-agent-01','status':'idle','current_task':None}]
            }))
            question='Сколько сейчас агентов?'
            with patch.object(ui,'ROOT',root):
                self.assertIn('настроено 1',stream._executor_status_reply(question,path))
                (root/'state'/'OWNER_MAINTENANCE.flag').touch()
                blocked=stream._executor_status_reply(question,path)
                self.assertIn('MODEL_UPDATE',blocked)
                self.assertNotIn('настроено',blocked)
                (root/'state').rename(root/'detached')
                self.assertIn('не могу подтвердить',stream._executor_status_reply(question,path))
                (root/'detached').rename(root/'state')
                (root/'state'/'OWNER_MAINTENANCE.flag').unlink()
                with patch.object(ui,'owner_maintenance_gate',side_effect=['ABSENT','PRESENT']):
                    transition=stream._executor_status_reply(question,path)
                self.assertIn('не могу подтвердить',transition)
                self.assertNotIn('настроено',transition)

    @unittest.skipUnless(hasattr(os,'mkfifo') and hasattr(os,'O_NONBLOCK'),
                         'POSIX FIFO nonblocking admission regression')
    def test_executor_fifo_status_path_cannot_block_chat(self):
        # A FIFO at this path must be rejected *before* an open() waits for a
        # writer. Previous O_NOFOLLOW-only logic blocked before the fstat gate.
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'agents.json'
            os.mkfifo(path)
            answers=[]
            worker=threading.Thread(
                target=lambda:answers.append(stream._executor_status_reply(
                    'Сколько агентов сейчас?',path)),daemon=True)
            worker.start()
            worker.join(0.75)
            self.assertFalse(worker.is_alive(),
                             'nonregular status FIFO blocked immediate chat admission')
            self.assertEqual(len(answers),1)
            self.assertIn('не могу подтвердить',answers[0])
            self.assertNotIn('настроено',answers[0])

    def test_executor_unknown_on_stale_corrupt_duplicate_or_inconsistent_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'agents.json'
            valid={'n':2,'workers':[{'id':f'nox-agent-{i:02d}','status':'idle','current_task':None}
                                   for i in (1,2)]}
            variants=[dict(valid,n=6),dict(valid,n=True),
                      dict(valid,workers=[valid['workers'][0],valid['workers'][0]]),
                      dict(valid,workers=[valid['workers'][0],dict(valid['workers'][1],status='busy')]),
                      dict(valid,workers=[valid['workers'][0],dict(valid['workers'][1],status='invented')])]
            for doc in variants:
                path.write_text(json.dumps(doc))
                answer=stream._executor_status_reply('Сколько агентов сейчас?',path)
                self.assertIn('не могу подтвердить',answer)
                self.assertNotIn('настроено',answer)
            path.write_text(json.dumps(valid));os.utime(path,(time.time()-60,time.time()-60))
            self.assertIn('не могу подтвердить',stream._executor_status_reply('Статус исполнителей',path))
            path.unlink();path.symlink_to(Path(folder)/'absent')
            self.assertIn('не могу подтвердить',stream._executor_status_reply('Сколько агентов?',path))

    def test_normalized_tool_ids_are_bounded_for_native_and_heuristic_routes(self):
        for value in ('z'*161, 12, [], ''):
            with self.subTest(value_type=type(value).__name__,size=len(value) if hasattr(value,'__len__') else 0):
                with self.assertRaisesRegex(stream.StreamFailure,'HOLD_TOOL_CALL_ID_SIZE'):
                    stream._normal_calls([{'id':value,'name':'calculate',
                                           'arguments':{}}],0)
        allowed=stream._normal_calls([{'id':'z'*160,'name':'calculate',
                                       'arguments':{}}],0)
        self.assertEqual(allowed[0]['id'],'z'*160)
        fallback=stream._normal_calls([{'name':'calculate','arguments':{}}],1)
        self.assertEqual(fallback[0]['id'],'owner_call_1_0')

    async def test_falsey_non_object_tool_arguments_hold_before_model_and_dispatch(self):
        # The native/heuristic route previously turned []/false/0 into {}.
        # Fail closed instead of invoking a tool with an invented empty object.
        for invalid in ([], False, 0, 0.0):
            with self.subTest(invalid=repr(invalid)):
                native=self.native(heuristic=[{'id':'bad_args','name':'calculate',
                                               'arguments':invalid}])
                payload={'messages':[{'role':'user','content':'Calculate 2+2'}]}
                with patch.object(stream.httpx,'AsyncClient',
                                  side_effect=AssertionError('model POST forbidden')):
                    response=await native['owner_completion'](
                        'http://native/model',payload,'Calculate 2+2',True)
                    wire=''.join([chunk async for chunk in response.body_iterator])
                self.assertIn('HOLD_TOOL_ARGUMENTS',wire)
                self.assertNotIn('[DONE]',wire)
                self.assertNotIn('_agent_final',payload)
                self.assertEqual(self.dispatched,[])
        # Preserve the legitimate no-argument native-tool contract.
        for row in ({'name':'calculate'}, {'name':'calculate','arguments':None},
                    {'name':'calculate','arguments':''},
                    {'name':'calculate','arguments':'{}'}):
            self.assertEqual(stream._normal_calls([row],0)[0]['arguments'],{})

    def test_executor_route_does_not_capture_actions_plans_or_history(self):
        for question in ('Включи 6 агентов','Сколько агентов нужно запустить?',
                         'Сколько агентов работало вчера?','Добавь активных исполнителей',
                         'Напиши рассказ про агента'):
            self.assertIsNone(stream._executor_status_reply(question))


class TransformTests(unittest.IsolatedAsyncioTestCase):
    def test_unknown_native_source_is_rejected(self):
        for transform in (transforms.patch_agent_loop,transforms.patch_slim,transforms.patch_proxy):
            with self.assertRaisesRegex(ValueError,'HOLD_CHAT_SOURCE_SHA'):
                transform(b'unknown native source')

    async def test_understanding_context_is_isolated_across_offloaded_requests(self):
        scope={}
        exec(transforms._REQUEST_STATE,scope)
        ready=asyncio.Event();count=0
        async def request(value):
            nonlocal count
            scope['_NOX_UNDERSTANDING_STATE'].set({'text':value,'skip_regex':False})
            count+=1
            if count==2:ready.set()
            await ready.wait()
            return await asyncio.to_thread(lambda:scope['_nox_request_understanding']()['text'])
        self.assertEqual(await asyncio.gather(request('owner-a'),request('owner-b')),
                         ['owner-a','owner-b'])

    def test_exact_inspected_sources_transform_and_compile(self):
        receipt=Path('/tmp/nox_chat_probe/receipt.json')
        if not receipt.is_file():self.skipTest('native probe fixture is local-only')
        sources={Path(row['data']['path']).name:row['data']['source'].encode()
                 for row in json.loads(receipt.read_text()) if row.get('kind')=='chat_source'}
        agent=transforms.patch_agent_loop(sources['agent_loop.py'])
        slim=transforms.patch_slim(sources['slim_chat_t885u.py'])
        self.assertIn(b'_nox_install_owner_stream(globals())',agent)
        self.assertNotIn('к владельцу только «мессир»',slim.decode())
        self.assertNotIn('Обращайся к нему только «мессир»',slim.decode())

    async def test_nonloopback_cookie_allowlist_does_not_open_other_mutators(self):
        path=Path('/tmp/nox_native_sources/chat_proxy.py')
        if not path.is_file():self.skipTest('sanitized native proxy fixture is local-only')
        text=transforms._transform_proxy(path.read_text())
        start=text.index('async def auth_mw(')
        end=text.index('\n\n@app.get("/")',start)
        code=text[start:end].replace('    [REDACTED_ASSIGNMENT]','    token = None')
        scope={'Request':object,'_is_public_path':lambda path:False,
               '_is_localhost':lambda request:False,
               '_session_ok':lambda request:request.cookies.get('owner')=='valid',
               '_auth_ok':lambda *args:False,'_unauthorized':lambda:401}
        exec(code,scope)
        async def next_call(request):return 200
        for endpoint in ('/api/nox/chat/stream','/api/nox/stop','/api/nox/status',
                         '/api/nox/self/observations'):
            for authenticated in (False,True):
                request=types.SimpleNamespace(url=types.SimpleNamespace(path=endpoint),
                    headers={},cookies={'owner':'valid'} if authenticated else {})
                result=await scope['auth_mw'](request,next_call)
                self.assertEqual(result,200 if authenticated else 401)
        request=types.SimpleNamespace(url=types.SimpleNamespace(path='/api/nox/unrelated-mutator'),
                                     headers={},cookies={'owner':'valid'})
        self.assertEqual(await scope['auth_mw'](request,next_call),401)


if __name__=='__main__':unittest.main()
