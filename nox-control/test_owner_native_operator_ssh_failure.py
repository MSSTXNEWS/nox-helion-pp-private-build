import importlib.util
import json
from pathlib import Path
import unittest


OPERATOR = Path(__file__).with_name('owner_native_operator.py')
SPEC = importlib.util.spec_from_file_location('owner_native_operator_diagnostic_test', OPERATOR)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SSHFailureDiagnosticTests(unittest.TestCase):
    def test_auth_failure_is_redacted_and_stops_retries_immediately(self):
        fake_host = 'root@203.0.113.78'
        fake_secret = 'PRIVATE-KEY-MATERIAL-NOT-REAL'
        raw = f'Permission denied (publickey) for {fake_host}; {fake_secret}'
        result = MODULE.ssh_failure_diagnostic(stderr=raw, returncode=255)
        encoded = json.dumps(result, sort_keys=True)
        self.assertEqual(result['category'], 'SSH_AUTH_DENIED')
        self.assertEqual(result['errno'], 'EACCES')
        self.assertFalse(result['retryable'])
        self.assertEqual(result['returncode'], 255)
        self.assertFalse(MODULE.ssh_should_retry(result, 1))
        self.assertNotIn(fake_host, encoded)
        self.assertNotIn(fake_secret, encoded)
        self.assertNotIn('Permission denied', encoded)

    def test_controlmaster_timeout_is_classified_and_has_four_attempt_cap(self):
        result = MODULE.ssh_failure_diagnostic(timed_out=True, timeout_s=25)
        self.assertEqual(result, {
            'category': 'SSH_COMMAND_TIMEOUT',
            'errno': 'ETIMEDOUT',
            'timeout_s': 25,
            'returncode': None,
            'retryable': True,
        })
        self.assertTrue(MODULE.ssh_should_retry(result, 1))
        self.assertTrue(MODULE.ssh_should_retry(result, 3))
        self.assertFalse(MODULE.ssh_should_retry(result, 4))
        self.assertEqual(MODULE.MAX_SSH_AUTH_ATTEMPTS, 4)

    def test_host_key_rejection_is_terminal_and_does_not_echo_host(self):
        fake_host = 'onehost.private.invalid'
        result = MODULE.ssh_failure_diagnostic(
            stderr=f'Host key verification failed for {fake_host}', returncode=255)
        self.assertEqual(result['category'], 'SSH_HOST_KEY_REJECTED')
        self.assertEqual(result['errno'], 'EKEYREJECTED')
        self.assertFalse(result['retryable'])
        self.assertFalse(MODULE.ssh_should_retry(result, 1))
        self.assertNotIn(fake_host, json.dumps(result))

    def test_transient_network_failure_is_mapped_to_errno_without_raw_text(self):
        fake_host = '203.0.113.19'
        result = MODULE.ssh_failure_diagnostic(
            stderr=f'ssh: connect to host {fake_host} port 1234: Connection refused',
            returncode=255)
        self.assertEqual(result['category'], 'SSH_CONNECTION_REFUSED')
        self.assertEqual(result['errno'], 'ECONNREFUSED')
        self.assertTrue(result['retryable'])
        self.assertNotIn(fake_host, json.dumps(result))


if __name__ == '__main__':
    unittest.main()
