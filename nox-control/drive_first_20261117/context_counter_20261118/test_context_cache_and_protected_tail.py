"""Independent regression for the frozen request-local context helper.

No network, model generation, native files, or broad author-suite execution.
"""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest


SOURCE = Path(__file__).parents[1] / "context_counter_20261118" / "owner_context_budget.py"
spec = importlib.util.spec_from_file_location("reviewed_context_budget", SOURCE)
cb = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cb
spec.loader.exec_module(cb)


class Wire:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, method, url, payload, timeout):
        self.calls.append((method, url, copy.deepcopy(payload), timeout))
        value = self.replies.pop(0)
        return value if isinstance(value, bytes) else json.dumps(value).encode()


class IndependentContextRegression(unittest.TestCase):
    def test_same_rendered_prompt_cannot_alias_distinct_messages_and_unknown_keeps_tail(self):
        route = "http://127.0.0.1:8085/v1/chat/completions"
        wire = Wire([
            {"prompt": "identical-template-output"}, {"tokens": [7]},
            {"prompt": "identical-template-output"}, {"tokens": [8, 9]},
        ])
        session = cb.Session(route, transport=wire)
        first = cb.count_messages([{"role": "user", "content": "First question"}], route, session=session)
        second = cb.count_messages([{"role": "user", "content": "Different question"}], route, session=session)
        self.assertEqual(first.prompt_sha256, second.prompt_sha256)
        self.assertEqual((first.tokens, second.tokens), (1, 2))
        self.assertFalse(second.cached)
        self.assertEqual([call[1] for call in wire.calls], [
            "http://127.0.0.1:8085/apply-template", "http://127.0.0.1:8085/tokenize",
            "http://127.0.0.1:8085/apply-template", "http://127.0.0.1:8085/tokenize",
        ])
        exhausted = cb.count_messages([{"role": "user", "content": "Third"}], route, session=session)
        self.assertIsNone(exhausted.tokens)
        self.assertEqual(exhausted.reason, "TOKENIZER_ROUND_LIMIT")
        self.assertEqual(len(wire.calls), 4)

        original = "Мой исходный вопрос.\n\n---\nПоследнее обязательное условие."
        stable = "Stable prefix.\n" + cb.CONTRACT_MARK + " Keep these instructions."
        current_tail = [
            {"role": "user", "content": "Corrected wording, missing original. " + "supplement " * 2000},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "current-tool", "type": "function", "function": {"name": "lookup", "arguments": "{}"}}]},
            {"role": "tool", "content": "current result", "tool_call_id": "current-tool"},
            {"role": "assistant", "content": "Current conclusion"},
        ]
        messages = [
            {"role": "system", "content": stable + "\n\nVariable state " + "x" * 6000},
            {"role": "user", "content": "Old question"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "old-tool"}]},
            {"role": "tool", "content": "old result", "tool_call_id": "old-tool"},
        ] + current_tail
        untouched = copy.deepcopy(messages)
        invalid_200 = Wire([[{"n_ctx": 4096}], b'{"prompt":"one","prompt":"two"}'])
        result = cb.trim_messages(messages, selected_url=route, original_user_text=original,
                                  session=cb.Session(route, transport=invalid_200))
        self.assertEqual(messages, untouched)
        self.assertEqual(result.messages[0], {"role": "system", "content": stable})
        self.assertEqual(result.messages[1], {"role": "user", "content": original})
        self.assertEqual(result.messages[2:], current_tail[1:])
        self.assertEqual([row["role"] for row in result.messages],
                         ["system", "user", "assistant", "tool", "assistant"])
        self.assertEqual(result.assessment["count_reason"], "DUPLICATE_JSON_FIELD")
        self.assertIsNone(result.assessment["final_message_tokens"])
        self.assertFalse(result.assessment["exact_final_context_fit"])
        self.assertEqual((result.assessment["tokenizer_rounds"], result.assessment["helper_http_attempts"]), (1, 2))
        self.assertEqual(len(invalid_200.calls), 2)


if __name__ == "__main__":
    unittest.main()
