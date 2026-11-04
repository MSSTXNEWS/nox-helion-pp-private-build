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

# Imports under unittest discovery must neither consume nor mutate runner argv.
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
                    for v in ('func', 'session', 'args', 'route', 'job_id')], vararg=None,
                    kwonlyargs=[], kw_defaults=[], kwarg=None,
                    defaults=[ast.Constant(value='models.queue'), ast.Constant(value=None)]),
        body=[branch], decorator_list=[])
    module = ast.fix_missing_locations(ast.Module(body=[wrapper], type_ignores=[]))
    namespace = {'P03PortHold': P03PortHold, 'P03PortDenied': P03PortDenied}
    exec(compile(module, str(SOURCE), 'exec'), namespace)
    # The response branch is REAL production AST; supply its route/job guard
    # scope explicitly rather than masking NameError as a false operation HOLD.
    return lambda value, route='models.queue', job_id=None: namespace['respond'](
        lambda *_: value, None, {}, route, job_id)


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

    def test_cancel_retry_ack_identity_on_actual_source_branch(self):
        for route, status in (('models.cancel', 'CANCEL_REQUESTED'),
                              ('models.retry', 'QUEUED')):
            with self.subTest(route=route):
                wrong = {'jobId': 'foreign', 'status': status}
                with self.assertRaises(P03PortHold):
                    self.respond(wrong, route=route, job_id='requested')
                valid = {'jobId': 'requested', 'status': status}
                self.assertEqual(self.respond(valid, route=route, job_id='requested'), valid)
                with self.assertRaises(P03PortHold):
                    self.respond({'status': status}, route=route, job_id='requested')


class P03InvocationTest(unittest.TestCase):
    def test_discovery_import_preserves_runner_arguments_and_owner_source(self):
        import runpy
        from unittest.mock import patch
        expected = (Path(__file__).resolve().parents[1] /
                    'Packages/P03/Source/python-host/p03_onehost_port.py')
        for tail in (['discover', '-s', 'tests', '-v'],
                     ['test_c04_p03_ack_scalar_rejection', '-v']):
            argv = ['python -m unittest', *tail]
            before = argv[:]
            with self.subTest(argv=before), patch.object(sys, 'argv', argv):
                loaded = runpy.run_path(str(Path(__file__).resolve()),
                                       run_name='p03_invocation_probe')
                self.assertEqual(sys.argv, before)
                self.assertEqual(loaded['SOURCE'], expected)

    def test_direct_fixture_argument_preserves_unittest_flags(self):
        import runpy
        from unittest.mock import patch
        fixture = Path(__file__).resolve().with_name('reviewed_p03_fixture.py')
        argv = [str(Path(__file__).resolve()), str(fixture), '-v']
        with patch.object(sys, 'argv', argv), patch('unittest.main') as runner:
            loaded = runpy.run_path(str(Path(__file__).resolve()), run_name='__main__')
            self.assertEqual(loaded['SOURCE'], fixture)
            self.assertEqual(sys.argv, [str(Path(__file__).resolve()), '-v'])
            runner.assert_called_once_with(verbosity=2)

    def test_direct_unittest_flag_is_not_a_source_filename(self):
        import runpy
        from unittest.mock import patch
        argv = [str(Path(__file__).resolve()), '-v']
        with patch.object(sys, 'argv', argv), patch('unittest.main') as runner:
            loaded = runpy.run_path(str(Path(__file__).resolve()), run_name='__main__')
            self.assertEqual(loaded['SOURCE'], Path(__file__).resolve().parents[1] /
                             'Packages/P03/Source/python-host/p03_onehost_port.py')
            self.assertEqual(sys.argv, [str(Path(__file__).resolve()), '-v'])
            runner.assert_called_once_with(verbosity=2)

if __name__ == '__main__':
    # Only direct script invocation accepts the optional reviewed source fixture.
    # Leave unittest flags intact; discovery uses the repository's actual owner.
    if len(sys.argv) > 1 and not sys.argv[1].startswith('-'):
        SOURCE = Path(sys.argv.pop(1)).resolve()
    unittest.main(verbosity=2)
