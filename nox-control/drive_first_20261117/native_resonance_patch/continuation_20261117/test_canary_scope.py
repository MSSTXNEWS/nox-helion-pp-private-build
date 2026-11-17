"""Network-free regression for the real pinned canary's history acceptance.

Loads only its two pure functions. Fixtures are synthetic; they are never
described as native model/STOP/S03 evidence.
"""
import ast
import copy
import hashlib
from pathlib import Path
import re
import unittest

HERE = Path(__file__).resolve().parent


def load_functions(filename):
    tree = ast.parse((HERE / filename).read_text())
    selected = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                and n.name in ('digest', 'public_turn')]
    namespace = {'hashlib': hashlib, 're': re}
    exec(compile(ast.Module(body=selected, type_ignores=[]), filename, 'exec'), namespace)
    return namespace['public_turn']


class CanaryHistoryBinding(unittest.TestCase):
    def setUp(self):
        self.original = load_functions('BASE_DECODED.py')
        self.patched = load_functions('CANDIDATE_DECODED.py')
        self.did = 'a' * 32
        self.question = '[QA 0123456789ab] Сколько будет 17 + 25? Ответь только числом.'
        self.turn = {'answer': '42', 'done': {'saved': True, 's03_integrated': True, 'exchange_id': 'owned-exchange'},
                     'first_meaningful_delta_ms': 1000, 'stream_total_ms': 2000,
                     'delta_count': 1, 'placeholder_delta_count': 0}
        self.history = {'status': 'READY', 'dialog_id': self.did, 'messages': [
            {'role': 'user', 'content': self.question, 'exchange_id': 'owned-exchange'},
            {'role': 'assistant', 'content': '42', 'exchange_id': 'owned-exchange'}]}

    def check(self, history=None, turn=None, did=None):
        return self.patched(turn or self.turn, self.history if history is None else history,
                            self.question, self.did if did is None else did)

    def test_real_preimage_accepts_foreign_dialog_but_patch_rejects_it(self):
        foreign = copy.deepcopy(self.history)
        foreign['dialog_id'] = 'b' * 32
        self.assertTrue(self.original(self.turn, foreign, self.question)['useful_chat_pass'])
        self.assertFalse(self.check(foreign)['useful_chat_pass'])

    def test_real_preimage_accepts_split_exchanges_but_patch_rejects_them(self):
        split = copy.deepcopy(self.history)
        split['messages'][1]['exchange_id'] = 'another-exchange'
        self.assertTrue(self.original(self.turn, split, self.question)['useful_chat_pass'])
        self.assertFalse(self.check(split)['useful_chat_pass'])

    def test_terminal_provenance_must_match_the_persisted_exchange(self):
        for changes in ({'exchange_id': 'foreign'}, {'exchange_id': None},
                        {'exchange_id': True}, {'dialog_id': 'b' * 32}):
            wrong = copy.deepcopy(self.turn)
            wrong['done'].update(changes)
            with self.subTest(changes=changes):
                self.assertTrue(self.original(wrong, self.history, self.question)['useful_chat_pass'])
                self.assertFalse(self.check(turn=wrong)['useful_chat_pass'])
                self.assertFalse(self.check(turn=wrong)['history_persisted'])

    def test_matching_owned_pair_remains_accepted(self):
        result = self.check()
        self.assertTrue(result['useful_chat_pass'])
        self.assertTrue(result['history_persisted'])
        self.assertTrue(result['own_dialog_matches'])
        self.assertEqual(result['question_sha256'], hashlib.sha256(self.question.encode()).hexdigest())

    def test_missing_or_failed_history_status_rejected(self):
        for status in (None, 'ERROR', False):
            wrong = copy.deepcopy(self.history)
            wrong['status'] = status
            with self.subTest(status=status):
                self.assertFalse(self.check(wrong)['useful_chat_pass'])

    def test_missing_or_untyped_exchange_rejected(self):
        for value in (None, '', 1, True, 'x' * 201):
            wrong = copy.deepcopy(self.history)
            for row in wrong['messages']:
                row['exchange_id'] = value
            with self.subTest(value=repr(value)[:25]):
                self.assertFalse(self.check(wrong)['history_persisted'])

    def test_partial_terminal_proof_survives_empty_history(self):
        result = self.check({})
        self.assertTrue(result['terminal_receipt'])
        self.assertTrue(result['receipt_saved'])
        self.assertTrue(result['receipt_s03_integrated'])
        self.assertEqual(result['answer_sha256'], hashlib.sha256(b'42').hexdigest())
        self.assertFalse(result['history_persisted'])
        self.assertEqual(result['terminal_exchange_id_sha256'], hashlib.sha256(b'owned-exchange').hexdigest())

    def test_untyped_terminal_saved_flag_does_not_pass(self):
        wrong = copy.deepcopy(self.turn)
        wrong['done']['saved'] = 'true'
        self.assertFalse(self.check(turn=wrong)['useful_chat_pass'])

    def test_malformed_expected_dialog_rejected(self):
        for did in ('', 'A' * 32, 'a' * 31, True):
            with self.subTest(did=did):
                self.assertFalse(self.check(did=did)['useful_chat_pass'])

    def test_existing_stream_request_has_one_literal_token_budget(self):
        tree = ast.parse((HERE / 'CANDIDATE_DECODED.py').read_text())
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute) and n.func.attr == 'request'
                 and n.args and isinstance(n.args[0], ast.Constant)
                 and n.args[0].value == '/api/nox/chat/stream']
        self.assertEqual(len(calls), 1)
        payload = calls[0].args[1]
        values = {key.value: value for key, value in zip(payload.keys, payload.values)}
        self.assertEqual(ast.literal_eval(values['max_tokens']), 32)
        self.assertIsInstance(values['dialog_id'], ast.Name)
        self.assertEqual(values['dialog_id'].id, 'did')


if __name__ == '__main__':
    unittest.main(verbosity=2)
