"""6V14-12: bounded recovery of known read-only probes, without a model gate."""
import unittest
from unittest import mock

import owner_dispatcher_mentor as mentor


class ReadOnlyRetryBackoffTests(unittest.TestCase):
    def setUp(self):
        for name, value in (('stop_active', False), ('discover_senior', None),
                            ('reserve_incident', True), ('journal', None)):
            patcher = mock.patch.object(mentor, name, return_value=value)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)
        self.clock = mock.patch.object(mentor.time, 'time', return_value=1000).start()
        self.addCleanup(mock.patch.stopall)
        self.consult = mock.patch.object(mentor, 'consult', side_effect=AssertionError('no advisor for bounded probe retry')).start()
        self.run = mock.patch.object(mentor.subprocess, 'run', side_effect=AssertionError('no service operation')).start()

    def fail_probe(self, handler='verify_q4', error='TimeoutError: timed out', retries=1, maximum=3):
        task = {'id': 'probe.test', 'handler': handler, 'status': 'running',
                'retries': retries, 'max_retries': maximum}
        result = mentor.on_failure(task, error)
        return task, result

    def test_timeout_probe_recovers_without_senior(self):
        task, result = self.fail_probe()
        self.assertEqual(task['status'], 'pending')
        self.assertEqual(task['next_try'], 1030)
        self.assertEqual(result['state'], 'READ_ONLY_TRANSIENT_RETRY_SCHEDULED')
        self.assertFalse(result['verified_fix'])
        self.discover_senior.assert_not_called()
        self.consult.assert_not_called()
        self.run.assert_not_called()

    def test_connection_refused_wait_probe_is_bounded(self):
        task, result = self.fail_probe('wait_q4', 'Connection refused', retries=2)
        self.assertEqual(task['status'], 'pending')
        self.assertEqual(task['next_try'], 1060)
        self.assertEqual(task['retries'], 2)
        self.assertFalse(result['verified_fix'])

    def test_stop_wins_before_retry_or_senior(self):
        self.stop_active.return_value = True
        task, result = self.fail_probe()
        self.assertEqual(task['status'], 'blocked')
        self.assertEqual(result['state'], 'BLOCKED_OWNER_STOP')
        self.discover_senior.assert_not_called()

    def test_exhausted_or_disabled_budget_never_reopens(self):
        for retries, maximum in ((3, 3), (0, 0), (2, 2), (False, 3), ('invalid', 3)):
            with self.subTest(retries=retries, maximum=maximum):
                task, result = self.fail_probe(retries=retries, maximum=maximum)
                self.assertEqual(task['status'], 'blocked')
                self.assertEqual(result['state'], 'BLOCKED_RETRY_BUDGET_EXHAUSTED')

    def test_unknown_or_mutating_handler_keeps_existing_gate(self):
        for handler in ('owner_native_project_work', 'ensure_scheduler', 'unknown'):
            with self.subTest(handler=handler):
                task, result = self.fail_probe(handler=handler)
                self.assertEqual(task['status'], 'blocked')
                self.assertNotEqual(result['state'], 'READ_ONLY_TRANSIENT_RETRY_SCHEDULED')
        self.run.assert_not_called()

    def test_only_reviewed_probe_pair_bypasses_advisor(self):
        for handler in ('new_gguf', 'holdout_gate'):
            with self.subTest(handler=handler):
                task, result = self.fail_probe(handler=handler)
                self.assertEqual(task['status'], 'blocked')
                self.assertNotEqual(result['state'], 'READ_ONLY_TRANSIENT_RETRY_SCHEDULED')

    def test_validation_permission_and_oom_do_not_blindly_retry(self):
        for error in ('invalid output', 'permission denied', 'cuda oom', 'unclassified failure'):
            with self.subTest(error=error):
                task, _ = self.fail_probe(error=error)
                self.assertEqual(task['status'], 'blocked')

    def test_retry_keeps_failure_and_resolution_as_unaccepted_evidence(self):
        task, result = self.fail_probe()
        self.assertEqual(task['mentor'], result)
        self.assertEqual(task['mentor_incident'], result['incident'])
        self.assertTrue(all(call.kwargs.get('accepted') is False
                            for call in self.journal.call_args_list))
        self.assertEqual([call.args[0] for call in self.journal.call_args_list],
                         ['error_observed', 'resolution'])


if __name__ == '__main__':
    unittest.main()
