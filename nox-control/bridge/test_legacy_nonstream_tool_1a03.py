#!/usr/bin/env python3
"""RELAY35 1A03 source-only: real nonstream parser may not attest tool output."""
import ast
import asyncio
from pathlib import Path
import unittest
from unittest.mock import Mock


def load_ask():
    tree = ast.parse(Path(__file__).with_name("nox_bridge.py").read_text(encoding="utf-8"))
    fn = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "ask")
    module = ast.Module(body=[fn], type_ignores=[])
    ast.fix_missing_locations(module)
    env = {"MODEL": "http://model.invalid/v1/chat/completions", "NKEEP": 10}
    exec(compile(module, "<actual-nonstream-ask>", "exec"), env)
    return env


class Response:
    status_code = 200
    def __init__(self, data):
        self.data = data
    def json(self):
        return self.data


class NonstreamCompletionFence(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.env = load_ask()
        self.client = Mock()
        self.client.post = Mock()
        async def post(_url, **_kwargs):
            return Response(self.payload)
        self.client.post.side_effect = post
        self.env["hc"] = lambda: self.client
        self.env["log"] = lambda _message: None

    async def run_response(self, choice):
        self.payload = {"choices": [choice]}
        return await self.env["ask"]([{"role": "user", "content": "проверка"}], 20)

    async def test_valid_assistant_unicode_stop(self):
        result = await self.run_response({"finish_reason": "stop", "message": {
            "role": "assistant", "content": "  Ответ 🌍  "}})
        self.assertEqual(result, "Ответ 🌍")
        self.assertEqual(self.client.post.call_count, 1)

    async def test_visible_text_with_unexecuted_tool_call_is_rejected(self):
        for member in ("tool_calls", "function_call"):
            with self.subTest(member=member):
                with self.assertRaisesRegex(ValueError, "UPSTREAM_UNEXECUTED_TOOL_CALL"):
                    await self.run_response({"finish_reason": "stop", "message": {
                        "role": "assistant", "content": "Tool not run", member: []}})

    async def test_nonassistant_and_choice_tool_calls_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "UPSTREAM_MESSAGE_INVALID"):
            await self.run_response({"finish_reason": "stop", "message": {
                "role": "tool", "content": "Tool says done"}})
        with self.assertRaisesRegex(ValueError, "UPSTREAM_UNEXECUTED_TOOL_CALL"):
            await self.run_response({"finish_reason": "stop",
                                     "tool_calls": [], "message": {
                "role": "assistant", "content": "Not certified"}})

    async def test_invalid_content_and_ambiguous_choices_rejected(self):
        for bad in (0, False, [], {"text": "not a string"}, "\\ud800"):
            with self.subTest(bad=repr(bad)):
                with self.assertRaisesRegex(ValueError, "UPSTREAM_CONTENT_INVALID"):
                    await self.run_response({"finish_reason": "stop", "message": {
                        "role": "assistant", "content": bad}})
        self.payload = {"choices": []}
        with self.assertRaisesRegex(ValueError, "UPSTREAM_CHOICES_INVALID"):
            await self.env["ask"]([{"role": "user", "content": "x"}], 20)

    async def test_length_or_error_never_retries_or_records_response(self):
        with self.assertRaisesRegex(ValueError, "UPSTREAM_NONSTOP_COMPLETION"):
            await self.run_response({"finish_reason": "length", "message": {
                "role": "assistant", "content": "Partial"}})
        self.payload = {"error": "upstream failed", "choices": [{
            "finish_reason": "stop", "message": {
                "role": "assistant", "content": "not valid"}}]}
        with self.assertRaisesRegex(ValueError, "UPSTREAM_RESPONSE_INVALID"):
            await self.env["ask"]([{"role": "user", "content": "x"}], 20)


if __name__ == "__main__":
    unittest.main()
