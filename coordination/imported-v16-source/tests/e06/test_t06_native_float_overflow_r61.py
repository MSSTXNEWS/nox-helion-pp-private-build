"""Focused regression of original T06 builder's pure native proof parser.
Import its AST only: never invoke top-level archive extraction, build or native IPC.
"""
import ast
import json
import math
import pathlib
import unittest

SOURCE = pathlib.Path(__file__).resolve().parents[2] / 'coordination/e06/t06_native_proven_builder.py'

def load_guard(source_text):
    tree = ast.parse(source_text)
    nodes = [node for node in tree.body
             if isinstance(node, ast.FunctionDef) and node.name == 'strict_native_json']
    if len(nodes) != 1:
        raise AssertionError('original native proof guard missing or duplicated')
    isolated = ast.Module(body=nodes, type_ignores=[])
    env = {'json': json, 'math': math}
    exec(compile(isolated, str(SOURCE), 'exec'), env)
    return env['strict_native_json']

class NativeReplyExponentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.decode = staticmethod(load_guard(SOURCE.read_text(encoding='utf-8')))

    def test_normal_finite_float_preserved(self):
        self.assertEqual(self.decode(b'{"model":1.25e2}', 'NATIVE_HOLD')['model'], 125.0)

    def test_float_exponent_overflow_is_hold(self):
        with self.assertRaisesRegex(RuntimeError, 'NATIVE_HOLD'):
            self.decode(b'{"model":1e999}', 'NATIVE_HOLD')

    def test_nested_float_exponent_overflow_is_hold(self):
        with self.assertRaisesRegex(RuntimeError, 'NATIVE_HOLD'):
            self.decode(b'{"result":{"models":[1e999]}}', 'NATIVE_HOLD')

    def test_nan_literal_is_hold(self):
        with self.assertRaisesRegex(RuntimeError, 'NATIVE_HOLD'):
            self.decode(b'{"model":NaN}', 'NATIVE_HOLD')

    def test_duplicate_reply_key_is_hold(self):
        with self.assertRaisesRegex(RuntimeError, 'NATIVE_HOLD'):
            self.decode(b'{"status":"OK","status":"HOLD"}', 'NATIVE_HOLD')

if __name__ == '__main__':
    unittest.main()
