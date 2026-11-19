"""Regression checks for status substitution; all transports/actions are mocked."""
import ast
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import owner_chat_stream as frozen
import owner_chat_stream_action_routing as candidate

FROZEN_SHA = '5b7bafde0c25fa26d6b8f98dfbb4958f0faa42ee77292da561834a63097a2e8e'
STATUS = {'id': 'legacy-status', 'name': 'run_admin', 'arguments': {'action': 'status'}}
QUEUE = {'id': 'legacy-queue', 'name': 'run_admin', 'arguments': {'action': 'queue_status'}}


def frame(content=None, finish=None, calls=None):
    delta = {}
    if content is not None:
        delta['content'] = content
    if calls is not None:
        delta['tool_calls'] = calls
    return ('data: ' + json.dumps({'choices': [{'delta': delta, 'finish_reason': finish}]}) + '\n\n').encode()


class Chunks(httpx.AsyncByteStream):
    def __init__(self, rows):
        self.rows = rows

    async def __aiter__(self):
        for row in self.rows:
            yield row


def answer(text):
    return Chunks([frame(text), frame(finish='stop'), b'data: [DONE]\n\n'])


class RoutingTests(unittest.IsolatedAsyncioTestCase):
    def native(self, module=candidate, direct=(), heuristic=(), deterministic=None, result=None):
        self.dispatched = []
        self.audited = []

        def dispatch(name, args):
            self.dispatched.append((name, dict(args)))
            return result or {'ok': True, 'text': 'RAW_STATUS_READBACK'}

        def parse(message, content):
            self.assertEqual(content, '')
            return [{'id': row['id'], 'name': row['function']['name'],
                     'arguments': row['function']['arguments']} for row in message['tool_calls']]

        native = {'TOOLS': [{'type': 'function', 'function': {'name': 'run_admin'}}],
                  '_POOL': deterministic is not None, 'MAX_STEPS': 8,
                  'DIRECT_ADMIN': {'status', 'queue_status', 'training_resume'},
                  '_direct_admin_calls': lambda text: list(direct),
                  'heuristic_tools': lambda text: list(heuristic),
                  'try_deterministic': lambda text: deterministic,
                  'prepare_payload': lambda payload, cache: payload,
                  'dedup_calls': lambda calls: calls,
                  'parse_tool_calls': parse, 'dispatch': dispatch,
                  'audit': lambda event, **fields: self.audited.append((event, fields)),
                  'confirm_marker': lambda rec: ' [CONFIRM public-fixture]',
                  '_sse': lambda text, finish=None: frame(text, finish).decode(),
                  '_final_json': lambda text: {'choices': [{'message': {'content': text}}]}}
        module.install(native)
        return native

    async def complete(self, module, native, text, streams):
        requests = []

        def respond(request):
            requests.append(json.loads(request.content))
            self.assertLessEqual(len(requests), len(streams), 'unexpected model call')
            return httpx.Response(200, stream=streams[len(requests)-1])

        real = httpx.AsyncClient
        transport = httpx.MockTransport(respond)
        factory = lambda **kw: real(transport=transport, **kw)
        payload = {'messages': [{'role': 'user', 'content': text}]}
        with patch.object(module.httpx, 'AsyncClient', side_effect=factory), \
                patch.object(module._current, 'augment_messages', side_effect=lambda messages, _: messages), \
                patch.object(module._current, 'dispatch', return_value=None):
            response = await native['owner_completion']('http://public-fixture/model', payload, text, True)
            wire = ''.join([row async for row in response.body_iterator])
        return wire, payload, requests

    async def test_long_tool_result_reaches_model_without_8k_truncation(self):
        # Public fixture: the old [:8000] dropped the evidence suffix.
        evidence = 'START|' + ('доказательство-' * 630) + '|END'
        self.assertGreater(len(evidence), 8000)
        native = self.native(heuristic=[{'name': 'run_admin', 'arguments': {'action': 'explain_result'}}],
                             result={'ok': True, 'text': evidence})
        _, payload, requests = await self.complete(candidate, native,
            'Explain the evidence from the tool', [answer('GROUNDED_FINAL')])
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]['messages'][0]['content'], 'Explain the evidence from the tool')
        self.assertEqual(requests[0]['messages'][-1]['role'], 'tool')
        self.assertEqual(requests[0]['messages'][-1]['content'], evidence)
        self.assertTrue(requests[0]['messages'][-1]['content'].endswith('|END'))
        self.assertEqual(payload['_agent_final'], 'GROUNDED_FINAL')

    async def test_original_bug_and_candidate_action_reaches_model_without_status_substitution(self):
        text = 'Оптимизируй сервер и GPU, скачай все веса'
        native = self.native(frozen, direct=[STATUS], heuristic=[STATUS])
        _, payload, requests = await self.complete(frozen, native, text, [])
        self.assertEqual(payload['_agent_final'], 'RAW_STATUS_READBACK')
        self.assertEqual(len(self.dispatched), 1)
        self.assertEqual(requests, [])
        native = self.native(direct=[STATUS], heuristic=[STATUS])
        _, payload, requests = await self.complete(candidate, native, text, [answer('MODEL_PLAN_WITHOUT_CLAIMED_EXECUTION')])
        self.assertEqual(payload['_agent_final'], 'MODEL_PLAN_WITHOUT_CLAIMED_EXECUTION')
        self.assertEqual(self.dispatched, [])
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]['tool_choice'], 'auto')
        self.assertEqual(requests[0]['messages'][-1]['content'], text)

    async def test_all_three_pre_model_selectors_filter_only_status_and_queue_status_for_actions(self):
        for selector in ('direct', 'deterministic', 'heuristic'):
            for call in (STATUS, QUEUE):
                with self.subTest(selector=selector, action=call['arguments']['action']):
                    kwargs = {selector: [call]} if selector != 'deterministic' else {
                        'deterministic': {'tool': 'run_admin', 'arguments': call['arguments']}}
                    native = self.native(**kwargs)
                    _, _, requests = await self.complete(candidate, native,
                        'Запусти шесть агентов для выполнения задач', [answer('MODEL_RESPONSE')])
                    self.assertEqual(self.dispatched, [])
                    self.assertEqual(len(requests), 1)

    async def test_pure_status_aliases_keep_single_direct_read_without_model(self):
        for text in ('Статус GPU', 'Покажи состояние сервера', 'Проверь статус очереди',
                     'GPU status', 'Queue status', 'Не запускай задачи, покажи статус GPU'):
            with self.subTest(text=text):
                self.assertFalse(candidate.status_needs_model(text))
                native = self.native(direct=[STATUS])
                _, payload, requests = await self.complete(candidate, native, text, [])
                self.assertEqual(payload['_agent_final'], 'RAW_STATUS_READBACK')
                self.assertEqual(len(self.dispatched), 1)
                self.assertEqual(requests, [])

    async def test_model_status_tool_on_action_turn_continues_to_second_model_request(self):
        native = self.native(direct=[STATUS], heuristic=[STATUS])
        tool = Chunks([frame(calls=[{'index': 0, 'id': 'model-status', 'type': 'function',
                'function': {'name': 'run_admin', 'arguments': '{"action":"status"}'}}]),
                frame(finish='tool_calls'), b'data: [DONE]\n\n'])
        wire, payload, requests = await self.complete(candidate, native, 'Оптимизируй GPU',
                                                     [tool, answer('MODEL_AFTER_STATUS')])
        self.assertEqual(self.dispatched, [('run_admin', {'action': 'status'})])
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[1]['messages'][-1], {'role': 'tool', 'tool_call_id': 'model-status',
                         'name': 'run_admin', 'content': 'RAW_STATUS_READBACK'})
        self.assertEqual(payload['_agent_final'], 'MODEL_AFTER_STATUS')
        self.assertNotIn('model-status', wire)

    async def test_explanations_and_formats_are_not_action_authority_but_continue_after_read(self):
        for text in ('Почему GPU не работает?', 'Что означает статус GPU?',
                     'Когда можно запустить агентов?', 'Напиши статус GPU только в JSON',
                     'Can you explain why the GPU is stopped?'):
            with self.subTest(text=text):
                self.assertFalse(candidate.action_request(text))
                self.assertTrue(candidate.status_needs_model(text))
                native = self.native(direct=[STATUS])
                _, payload, requests = await self.complete(candidate, native, text, [answer('MODEL_EXPLANATION')])
                self.assertEqual(len(self.dispatched), 1)
                self.assertEqual(len(requests), 1)
                self.assertEqual(requests[0]['messages'][-1]['role'], 'tool')
                self.assertEqual(payload['_agent_final'], 'MODEL_EXPLANATION')

    async def test_mutating_tool_confirmation_is_unchanged_and_never_force_confirmed(self):
        call = {'name': 'run_admin', 'arguments': {'action': 'training_resume'}}
        native = self.native(direct=[call], result={'ok': False, 'needs_confirmation': True,
                                                   'text': 'Existing confirmation required'})
        _, payload, requests = await self.complete(candidate, native, 'Возобнови обучение', [])
        self.assertEqual(self.dispatched, [('run_admin', {'action': 'training_resume'})])
        self.assertIn('[CONFIRM public-fixture]', payload['_agent_final'])
        self.assertEqual(requests, [])

    async def test_readonly_executor_and_inventory_early_answers_do_not_replace_action(self):
        for text in ('Оптимизируй агентов и покажи статус', 'Оптимизируй загрузки, покажи статус'):
            with self.subTest(text=text):
                self.assertFalse(candidate.executor_status_query(text))
                self.assertTrue(candidate.owner_request_query(text))
                native = self.native(direct=[STATUS])
                with patch.object(candidate._current, 'download_status_query', return_value=True), \
                        patch.object(candidate._current, 'inventory_reply', side_effect=AssertionError('no early inventory')):
                    _, payload, _ = await self.complete(candidate, native, text, [answer('MODEL_PLAN')])
                self.assertEqual(payload['_agent_final'], 'MODEL_PLAN')

    async def test_media_fastpath_keeps_original_single_enqueue_without_model(self):
        native = self.native()
        text = 'Нарисуй синий круг на белом фоне'
        payload = {'messages': [{'role': 'user', 'content': text}]}
        with patch.object(candidate._current, 'dispatch', return_value={'ok': True, 'text': 'QUEUED_NOT_COMPLETED'}) as dispatch, \
                patch.object(candidate.httpx, 'AsyncClient', side_effect=AssertionError('no model')):
            response = await native['owner_completion']('http://public-fixture/model', payload, text, True)
            _ = ''.join([row async for row in response.body_iterator])
        self.assertEqual(dispatch.call_count, 1)
        self.assertEqual(dispatch.call_args.args[:3], ('owner_queue_media_v1', {'kind': 'image'}, text))
        self.assertEqual(payload['_agent_final'], 'QUEUED_NOT_COMPLETED')

    async def test_ordinary_chat_adds_no_status_or_training_file_io(self):
        native = self.native()
        with patch.object(candidate._current, 'current_evidence', side_effect=AssertionError('no evidence IO')), \
                patch.object(candidate.os, 'open', side_effect=AssertionError('no file IO')):
            _, payload, requests = await self.complete(candidate, native, 'Привет, отвечай кратко', [answer('Привет')])
        self.assertEqual(payload['_agent_final'], 'Привет')
        self.assertEqual(self.dispatched, [])
        self.assertEqual(len(requests), 1)


class PredicateAndSourceTests(unittest.TestCase):
    def test_explicit_mixed_and_polite_action_clauses(self):
        yes = ('Оптимизируй сервер и GPU, скачай все веса', 'Запустите шесть агентов',
               'Покажи статус GPU, затем исправь проблему', 'Покажи очередь и выполни задачу',
               'Нокс, пожалуйста, настрой сервер', 'Можешь, пожалуйста, настроить GPU?',
               'Нужно скачать веса на сервер', 'Please show GPU status and configure the server',
               'Can you please optimize the GPU?', 'Не меняй память, но исправь сервер')
        for text in yes:
            with self.subTest(text=text):
                self.assertTrue(candidate.action_request(text))

    def test_mentions_negations_questions_and_style_are_not_action_instructions(self):
        no = ('Почему не получилось запустить GPU?', 'Что нужно сделать, чтобы запустить агентов?',
              'Когда ты сможешь настроить сервер?', 'Как скачать веса на сервер?',
              'Что означает команда «запусти агентов»?', 'Пример: `run GPU status`',
              'Не запускай процессы, только покажи статус GPU', 'Do not run jobs; show GPU status',
              'Can you not restart the GPU?', 'Можно ли запустить агента?',
              'Нужно ли скачать веса?', 'Напиши рассказ про GPU и агентов',
              'Расскажи, что означает слово «оптимизируй»', None, '', 'x' * 8001)
        for text in no:
            with self.subTest(text=str(text)[:80]):
                self.assertFalse(candidate.action_request(text))

    def test_frozen_base_and_protocol_permission_functions_remain_exact(self):
        base = (HERE / 'owner_chat_stream.py').read_bytes()
        self.assertEqual(hashlib.sha256(base).hexdigest(), FROZEN_SHA)
        newer = (HERE / 'owner_chat_stream_action_routing.py').read_bytes()
        old_tree, new_tree = ast.parse(base), ast.parse(newer)
        old_defs = {node.name: node for node in old_tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        new_defs = {node.name: node for node in new_tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        allowed = {'owner_request_query', 'executor_status_query', '_run'}
        for name, node in old_defs.items():
            if name not in allowed:
                self.assertEqual(ast.dump(node), ast.dump(new_defs[name]), name)
        self.assertEqual(candidate._READONLY_STATUS_ACTIONS, frozenset({'status', 'queue_status'}))
        self.assertNotIn('confirmed=True', newer.decode())
        self.assertNotIn('confirmed = True', newer.decode())
        self.assertEqual(candidate._initial_calls([STATUS, {'name': 'run_admin', 'arguments': {'action': 'training_resume'}}], True),
                         [{'name': 'run_admin', 'arguments': {'action': 'training_resume'}}])


if __name__ == '__main__':
    unittest.main()
