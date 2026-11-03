#!/usr/bin/env python3
"""Focused actual-AST test: owner P03 ACK cannot be a scalar/list.

In a checkout run:
  python tests/test_c04_p03_ack_scalar_rejection.py
For a verified source fixture run:
  python tests/test_c04_p03_ack_scalar_rejection.py <path-to-p03_onehost_port.py>
No Windows, runner or native acceptance is inferred.
"""
import ast
from pathlib import Path
import sys
import unittest

SOURCE = (Path(__file__).resolve().parents[1] /
          'Packages/P03/Source/python-host/p03_onehost_port.py')

class P03PortHold(RuntimeError):
    pass

class P03PortDenied(PermissionError):
    pass


def load_real_result_branch():
    """Execute the exact response-processing AST from the source under test."""
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'), filename=str(SOURCE))
    port = next(n for n in tree.body if isinstance(n, ast.ClassDef) and
                n.name == 'P03OneHostPort')
    method = next(n for n in port.body if isinstance(n, ast.FunctionDef) and
                  n.name == 'execute_backend')
    branch = next(n for n in method.body if isinstance(n, ast.Try) and
                  n.body and isinstance(n.body[0], ast.Assign) and
                  any(isinstance(t, ast.Name) and t.id == 'result'
                      for t in n.body[0].targets))
    wrapper = ast.FunctionDef(
        name='respond',
        args=ast.arguments(posonlyargs=[], args=[ast.arg(arg=v)
                    for v in ('func', 'session', 'args')], vararg=None,
                    kwonlyargs=[], kw_defaults=[], kwarg=None,
                    defaults=[]),
        body=[branch], decorator_list=[])
    module = ast.fix_missing_locations(ast.Module(body=[wrapper], type_ignores=[]))
    namespace = {'P03PortHold': P03PortHold, 'P03PortDenied': P03PortDenied}
    exec(compile(module, str(SOURCE), 'exec'), namespace)
    return lambda value: namespace['respond'](lambda *_: value, None, {})


class P03RealAckBranchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.respond = staticmethod(load_real_result_branch())

    def test_false_and_true_are_not_native_receipts(self):
        for value in (False, True):
            with self.subTest(value=value), self.assertRaises(P03PortHold):
                self.respond(value)

    def test_numeric_and_text_scalar_not_receipts(self):
        for value in (0, 1, '', 'COMPLETED'):
            with self.subTest(value=value), self.assertRaises(P03PortHold):
                self.respond(value)

    def test_array_not_a_queue_ack(self):
        for value in ([], ['queued']):
            with self.subTest(value=value), self.assertRaises(P03PortHold):
                self.respond(value)

    def test_no_ack_and_hold_are_rejected(self):
        for value in (None, {'status': 'HOLD', 'ok': False}):
            with self.subTest(value=value), self.assertRaises(P03PortHold):
                self.respond(value)

    def test_completed_uncancelled_preserves_factual_result(self):
        value = {'status': 'COMPLETED', 'result': {'cancelled': False}}
        self.assertEqual(self.respond(value), value)
        self.assertFalse(self.respond(value)['result']['cancelled'])

if __name__ == '__main__':
    # Discovery owns its arguments; a source override belongs to this CLI only.
    if len(sys.argv) > 1:
        SOURCE = Path(sys.argv[1]).resolve()
        sys.argv[:] = sys.argv[:1]
    unittest.main(verbosity=2)
