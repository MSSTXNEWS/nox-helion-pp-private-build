"""Stream parsing safety regression: unexpected teacher SSE shapes never abort chat."""
import ast
import json
import unittest
from pathlib import Path


def load_parser():
    source = Path(__file__).resolve().parents[1] / "native_v29_chat_bridge.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
              and n.name == "_token_from_delta")
    module = ast.Module(body=[fn], type_ignores=[])
    namespace = {"json": json}
    exec(compile(ast.fix_missing_locations(module), str(source), "exec"), namespace)
    return namespace["_token_from_delta"]


class StreamDeltaGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parse = staticmethod(load_parser())

    def test_valid_content_token(self):
        line = 'data: {"choices":[{"delta":{"content":"Привет"}}]}'
        self.assertEqual(self.parse(line), ("delta", "Привет"))

    def test_done(self):
        self.assertEqual(self.parse("data: [DONE]"), ("done", ""))

    def test_invalid_choice_shape(self):
        for choices in ({"delta": {"content": "x"}}, "bad", 123, None):
            with self.subTest(choices=choices):
                line = "data: " + json.dumps({"choices": choices})
                self.assertEqual(self.parse(line), ("", ""))

    def test_invalid_delta_shape(self):
        for delta in ("bad", ["x"], 123, None):
            with self.subTest(delta=delta):
                line = "data: " + json.dumps({"choices": [{"delta": delta}]})
                self.assertEqual(self.parse(line), ("", ""))

    def test_no_reasoning_leak(self):
        line = 'data: {"choices":[{"delta":{"reasoning_content":"secret"}}]}'
        self.assertEqual(self.parse(line), ("", ""))


if __name__ == "__main__":
    unittest.main()
