#!/usr/bin/env python3
"""Focused actual-AST test: owner P03 ACK cannot be a scalar/list.

In a checkout run:
  python tests/test_c04_p03_ack_scalar_rejection.py
For a verified source fixture run:
  python tests/test_c04_p03_ack_scalar_rejection.py <path-to-p03_onehost_port.py>
No Windows, runner or native acceptance is inferred.
"""
import ast
import re
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
    # Execute the exact owner denial predicate from the same reviewed source.
    # Omitting this helper lets its NameError enter the original broad
    # operation fence, causing genuine ACKs to look like backend outages.
    # Never stub the predicate or bypass backend/owner approval.
    guard_globals = [
        next(n for n in tree.body if isinstance(n, ast.Assign) and
             any(isinstance(t, ast.Name) and t.id == name for t in n.targets))
        for name in ('_OWNER3_DENIAL_TOKENS', '_OWNER3_DENIAL_PAIRS',
                     '_OWNER3_CANCEL_ACK_STATES', '_OWNER3_RETRY_ACK_STATES')
    ]
    guard_predicate = next(n for n in tree.body
                           if isinstance(n, ast.FunctionDef) and
                           n.name == '_owner3_status_denied')
    module = ast.fix_missing_locations(ast.Module(
        body=[*guard_globals, guard_predicate, wrapper], type_ignores=[]))
    namespace = {'P03PortHold': P03PortHold, 'P03PortDenied': P03PortDenied,
                 're': re}
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

    def test_prefixed_owner_denials_still_hold_with_real_guard(self):
        for status in ('PROVIDER_OFFLINE_HOLD', 'CONSENT_REQUIRED',
                       'NOT_AUTHORIZED', 'PERMISSION_DENIED'):
            with self.subTest(status=status), self.assertRaises(P03PortHold):
                self.respond({'status': status, 'jobId': 'requested'},
                             route='models.retry', job_id='requested')

    def test_legacy_queue_ack_still_accepted_without_fake_backend(self):
        receipt = {'status': 'QUEUED', 'ack': True}
        self.assertEqual(self.respond(receipt), receipt)

    def test_completed_uncancelled_preserves_factual_result(self):
        value = {'status': 'COMPLETED', 'result': {'cancelled': False}}
        self.assertEqual(self.respond(value), value)
        self.assertFalse(self.respond(value)['result']['cancelled'])

    def test_queued_only_receipt_is_not_active_stop(self):
        # Existing backend contract: queue placement != cancellation evidence.
        queued_only = {'jobId': 'requested', 'queued': True}
        with self.assertRaises(P03PortHold):
            self.respond(queued_only, route='models.cancel', job_id='requested')
        # The identical queue receipt remains valid for a requested retry.
        self.assertEqual(
            self.respond(queued_only, route='models.retry', job_id='requested'),
            queued_only)
        # Legacy status-bound cancellation remains valid for the exact job.
        stop_requested = {'jobId': 'requested', 'status': 'CANCEL_REQUESTED',
                          'queued': True}
        self.assertEqual(
            self.respond(stop_requested, route='models.cancel',
                         job_id='requested'), stop_requested)

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


    def test_pending_backend_receipt_never_confirms_model_mutation(self):
        # A transport ACK or job identity cannot turn unresolved native
        # approval/progress into a confirmed model pull or GGUF import.
        for route in ('models.pull', 'models.gguf.import'):
            for state in ('PENDING', 'OWNER_PENDING', 'ACK_PENDING',
                          'READY_PENDING'):
                with self.subTest(route=route, status=state), self.assertRaises(P03PortHold):
                    self.respond({'status': state, 'ack': True},
                                 route=route)
            valid = {'status': 'QUEUED', 'ack': True}
            self.assertEqual(self.respond(valid, route=route), valid)


    def test_nested_owner_refusals_never_promote_outer_ack(self):
        # Source's real response AST; no fake owner acceptance.
        for route, status in (('models.pull', 'PROVIDER_OFFLINE_HOLD'),
                              ('models.gguf.import', 'CONSENT_REQUIRED'),
                              ('models.cancel', 'OWNER_PENDING'),
                              ('models.retry', 'PERMISSION_DENIED')):
            for envelope in ('result', 'receipt', 'ownerReceipt'):
                with self.subTest(route=route, status=status, envelope=envelope):
                    result = {'status': ('CANCEL_REQUESTED' if route == 'models.cancel'
                                         else 'QUEUED'),
                              'ack': True, envelope: {'status': status}}
                    if route in ('models.cancel', 'models.retry'):
                        result['jobId'] = 'requested'
                    with self.assertRaises(P03PortHold):
                        self.respond(result, route=route,
                                     job_id='requested' if 'jobId' in result else None)
        for field in ('ok', 'ack', 'accepted', 'success'):
            with self.subTest(field=field), self.assertRaises(P03PortHold):
                self.respond({'status': 'QUEUED', 'result': {field: False}},
                             route='models.pull')
        with self.assertRaises(P03PortHold):
            self.respond({'status': 'QUEUED',
                          'receipt': {'error': 'PROVIDER_OFFLINE_HOLD'}},
                         route='models.pull')
        with self.assertRaises(P03PortHold):
            self.respond({'status': 'QUEUED',
                          'result': {'status': None}}, route='models.pull')
        valid = {'status': 'CANCEL_REQUESTED', 'jobId': 'requested',
                 'result': {'cancelled': False}}
        self.assertEqual(self.respond(valid, route='models.cancel',
                                      job_id='requested'), valid)
        queued = {'status': 'QUEUED', 'ack': True,
                  'receipt': {'status': 'QUEUED'}}
        self.assertEqual(self.respond(queued, route='models.pull'), queued)



    def test_deep_owner_denial_cannot_confirm_mutating_ack(self):
        for route, state in (('models.pull', 'QUEUED'),
                             ('models.gguf.import', 'QUEUED'),
                             ('models.cancel', 'CANCEL_REQUESTED'),
                             ('models.retry', 'QUEUED')):
            for key, refused in (('ownerReceipt', {'status': 'CONSENT_REQUIRED'}),
                                 ('receipt', {'error': 'PROVIDER_OFFLINE_HOLD'}),
                                 ('result', {'accepted': False})):
                value = {'status': state, 'ack': True,
                         'receipt': {'ownerReceipt': {key: refused}}}
                if route in ('models.cancel', 'models.retry'):
                    value['jobId'] = 'requested'
                with self.subTest(route=route, key=key), self.assertRaises(P03PortHold):
                    self.respond(value, route=route,
                                 job_id=value.get('jobId'))

    def test_deep_positive_receipt_and_legacy_owner_result(self):
        valid = {'status': 'QUEUED', 'ack': True,
                 'ownerReceipt': {'receipt': {'status': 'QUEUED', 'ok': True}}}
        self.assertEqual(self.respond(valid, route='models.pull'), valid)
        legacy = {'status': 'CANCEL_REQUESTED', 'jobId': 'requested',
                  'result': {'cancelled': False}}
        self.assertEqual(self.respond(legacy, route='models.cancel',
                                      job_id='requested'), legacy)

    def test_cyclic_and_unbounded_nested_receipts_hold(self):
        cycle = {'status': 'QUEUED', 'ack': True}
        cycle['ownerReceipt'] = cycle
        with self.assertRaises(P03PortHold):
            self.respond(cycle, route='models.pull')
        root = {'status': 'QUEUED', 'ack': True}
        node = root
        for _ in range(5):
            child = {'status': 'QUEUED'}
            node['ownerReceipt'] = child
            node = child
        with self.assertRaises(P03PortHold):
            self.respond(root, route='models.pull')



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
