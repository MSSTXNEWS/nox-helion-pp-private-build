"""Targeted offline tests of actual old bugs and bounded replacements."""
import ast
import copy
import json
from pathlib import Path
import types
import unittest

import owner_context_budget as cb
import source_transform as transform


class Scripted:
    def __init__(self, replies, *, advance=None):
        self.replies = list(replies)
        self.calls = []
        self.advance = advance
    def __call__(self, method, url, payload, timeout):
        self.calls.append((method, url, payload, timeout))
        if self.advance is not None:
            self.advance()
        value = self.replies.pop(0)
        if isinstance(value, Exception):
            raise value
        return json.dumps(value).encode()


class ContextCounterTests(unittest.TestCase):
    primary = 'http://127.0.0.1:8098/v1/chat/completions'
    fallback = 'http://127.0.0.1:8085/v1/chat/completions'
    sample = [{'role': 'user', 'content': 'Нормальный вопрос'}]

    def test_actual_old_false_zero_and_strict_unknown_replacement(self):
        text = (Path(__file__).with_name('actual_counter_functions.py')).read_text()
        node = next(n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name == '_count_msg_tokens')
        replies = [{}, {}]
        class Response:
            status_code = 200
            def __init__(self, value): self.value = value
            def json(self): return self.value
        env = {'load_backend': lambda: {'host': '127.0.0.1', 'port': 8098},
               'httpx': types.SimpleNamespace(post=lambda *a, **kw: Response(replies.pop(0)))}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<isolated-actual-count>', 'exec'), env)
        self.assertEqual(env['_count_msg_tokens'](self.sample), 0)  # Reproduces the actual old defect.
        cases = [([{}], 'TEMPLATE_SCHEMA'),
                 ([{'prompt': 'rendered'}, {}], 'TOKENS_SCHEMA'),
                 ([{'prompt': 'rendered'}, {'tokens': []}], 'EMPTY_TOKENS_FOR_NONEMPTY_PROMPT'),
                 ([{'prompt': 'rendered'}, {'tokens': [True]}], 'TOKEN_IDS_SCHEMA')]
        for responses, reason in cases:
            with self.subTest(reason=reason):
                wire = Scripted(responses)
                result = cb.count_messages(self.sample, self.primary,
                    session=cb.Session(self.primary, transport=wire))
                self.assertFalse(result.known)
                self.assertIsNone(result.tokens)
                self.assertEqual(result.reason, reason)
        real_empty = Scripted([{'prompt': ''}, {'tokens': []}])
        result = cb.count_messages([], self.primary, session=cb.Session(self.primary, transport=real_empty))
        self.assertTrue(result.known)
        self.assertEqual(result.tokens, 0)

    def test_selected_route_template_cache_and_two_round_limit(self):
        wire = Scripted([{'prompt': 'template-A'}, {'tokens': [10, 11]}, {'prompt': 'template-A'}])
        session = cb.Session(self.fallback, transport=wire)
        one = cb.count_messages(self.sample, self.fallback, session=session)
        two = cb.count_messages(self.sample, self.fallback, session=session)
        self.assertEqual((one.tokens, two.tokens), (2, 2))
        self.assertTrue(two.cached)
        self.assertEqual(len(wire.calls), 3)
        self.assertTrue(all(url.startswith('http://127.0.0.1:8085/') for _, url, _, _ in wire.calls))
        mismatch = cb.count_messages(self.sample, self.primary, session=session)
        self.assertEqual(mismatch.reason, 'SELECTED_ROUTE_SESSION_MISMATCH')
        limited = cb.count_messages(self.sample, self.fallback, session=session)
        self.assertEqual(limited.reason, 'TOKENIZER_ROUND_LIMIT')
        self.assertEqual(len(wire.calls), 3)
        changed = Scripted([{'prompt': 'template-A'}, {'tokens': [1]},
                            {'prompt': 'template-B'}, {'tokens': [1, 2, 3]}])
        active = cb.Session(self.primary, transport=changed)
        a = cb.count_messages(self.sample, self.primary, session=active)
        b = cb.count_messages(self.sample, self.primary, session=active)
        self.assertNotEqual(a.prompt_sha256, b.prompt_sha256)
        self.assertFalse(b.cached)
        self.assertEqual(b.tokens, 3)
        self.assertEqual(len(changed.calls), 4)

    def test_cumulative_time_budget_stops_before_second_endpoint(self):
        now = [0.0]
        wire = Scripted([{'prompt': 'text'}], advance=lambda: now.__setitem__(0, 1.21))
        session = cb.Session(self.primary, transport=wire, clock=lambda: now[0])
        result = cb.count_messages(self.sample, self.primary, session=session)
        self.assertFalse(result.known)
        self.assertEqual(result.reason, 'TIME_BUDGET_EXHAUSTED')
        self.assertEqual(len(wire.calls), 1)

    def test_original_question_delimiter_instructions_and_tool_groups_survive(self):
        stable = 'Обязательные инструкции целиком.\n' + cb.CONTRACT_MARK + ' Ничего не выдумывай.'
        original = 'Сохрани весь вопрос.\n\n---\nЭто продолжение МОЕГО вопроса. ' + 'важно ' * 400
        messages = [{'role': 'system', 'content': stable + '\n\nВременная справка ' + 'x' * 600},
            {'role': 'user', 'content': 'предыдущий вопрос ' * 200},
            {'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'call-1'}]},
            {'role': 'tool', 'content': 'старый результат', 'tool_call_id': 'call-1'},
            {'role': 'assistant', 'content': 'итог предыдущего вопроса'},
            {'role': 'user', 'content': original + '\n\n---\nСгенерированная справка ' + 'y' * 12000}]
        untouched = copy.deepcopy(messages)
        wire = Scripted([[{'n_ctx': 4096}, {'n_ctx': 4096}], {'prompt': 'too-long'},
            {'tokens': list(range(5000))}, {'prompt': 'final'}, {'tokens': list(range(900))}])
        result = cb.trim_messages(messages, selected_url=self.primary, original_user_text=original,
                                  session=cb.Session(self.primary, transport=wire))
        self.assertEqual(messages, untouched)
        self.assertEqual(result.messages[0]['content'], stable)
        self.assertEqual(result.messages[-1]['content'], original)
        self.assertEqual([r['role'] for r in result.messages], ['system', 'user'])
        self.assertEqual(result.assessment['final_message_tokens'], 900)
        self.assertEqual(result.assessment['tokenizer_rounds'], 2)
        self.assertEqual(result.assessment['helper_http_attempts'], 5)
        self.assertFalse(result.assessment['exact_final_context_fit'])

    def test_unknown_count_keeps_long_question_and_stable_prefix_without_retry(self):
        stable = cb.CONTRACT_MARK + ' Неприкосновенные инструкции. ' + 's' * 3000
        original = 'Не обрезать: ' + 'вопрос ' * 1200 + '\n\n---\nПоследняя инструкция.'
        messages = [{'role': 'system', 'content': stable},
                    {'role': 'user', 'content': original + '\n\n---\nGenerated supplement'}]
        wire = Scripted([[{'n_ctx': 4096}], {}])
        result = cb.trim_messages(messages, selected_url=self.primary, original_user_text=original,
                                  session=cb.Session(self.primary, transport=wire))
        self.assertEqual(result.messages[0]['content'], stable)
        self.assertEqual(result.messages[-1]['content'], original)
        self.assertIsNone(result.assessment['final_message_tokens'])
        self.assertEqual(result.assessment['status'], 'HEURISTIC_ONLY_TOKENIZER_UNAVAILABLE')
        self.assertEqual(len(wire.calls), 2)

    def test_protected_only_known_overflow_is_not_silently_truncated(self):
        messages = [{'role': 'system', 'content': cb.CONTRACT_MARK + ' Полные инструкции'},
                    {'role': 'user', 'content': 'Полный исходный вопрос'}]
        wire = Scripted([[{'n_ctx': 4096}], {'prompt': 'protected'}, {'tokens': list(range(3000))}])
        with self.assertRaisesRegex(cb.ProtectedContextTooLarge, 'PROTECTED_MESSAGES_EXCEED'):
            cb.trim_messages(messages, selected_url=self.primary, original_user_text=messages[-1]['content'],
                             session=cb.Session(self.primary, transport=wire))
        self.assertEqual(len(wire.calls), 3)
        self.assertEqual(messages[-1]['content'], 'Полный исходный вопрос')

    def test_actual_source_delta_preserves_identity_branch_and_inverse(self):
        p = Path(__file__).parents[1] / 'model_identity_binding_20261118/private_postimages/chat_proxy.py'
        before = p.read_bytes(); after = transform.transform(before)
        self.assertEqual(transform.reverse(after, before), before)
        old, new = ast.parse(before), ast.parse(after)
        old_completion = next(n for n in old.body if isinstance(n, ast.AsyncFunctionDef) and n.name == '_proxy_completion')
        new_completion = next(n for n in new.body if isinstance(n, ast.AsyncFunctionDef) and n.name == '_proxy_completion')
        old_selector = next(n for n in ast.walk(old_completion) if isinstance(n, ast.IfExp)
                            and '_nox_model_identity_query' in ast.unparse(n.test))
        branch = next(n for n in ast.walk(new_completion) if isinstance(n, ast.If)
                      and '_nox_model_identity_query' in ast.unparse(n.test))
        self.assertEqual(ast.dump(old_selector.test), ast.dump(branch.test))
        self.assertIn('_build_messages(body)', ast.unparse(branch.body[0]))
        self.assertNotIn('owner_context_budget', ast.unparse(ast.Module(body=branch.body, type_ignores=[])))
        normal = ast.unparse(ast.Module(body=branch.orelse, type_ignores=[]))
        self.assertIn('selected_url=url', normal)
        self.assertIn('original_user_text=_utext', normal)
        self.assertIn('status_code=413', normal)


if __name__ == '__main__':
    unittest.main()
